"""Run N parallel Quick vs Thinker 9x9 Go matches with balanced color assignment.

Uses `asyncio.wait_for` around each API call to prevent hung connections.
Usage: uv run python simulate.py [N_GAMES] [CONCURRENCY]
  defaults: N_GAMES=100, CONCURRENCY=20
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import sys
import time
from collections import Counter
import httpx
from dotenv import load_dotenv

from go_game import GameState, board_to_ascii, BLACK, WHITE, KOMI, count_area
from agent import QUICK_SYSTEM, THINKER_SYSTEM, QUICK_SCHEMA, THINKER_SCHEMA

load_dotenv()

BASE_URL = os.environ["GEMMA_BASE_URL"].rstrip("/")
API_KEY = os.environ["GEMMA_API_KEY"]
MODEL = os.environ["GEMMA_MODEL"]

DRAW = "draw"
CALL_TIMEOUT = 90.0  # hard timeout per API call

CFG = {
    "quick": {
        "system": QUICK_SYSTEM, "schema": QUICK_SCHEMA, "schema_name": "quick_move",
        "max_tokens": 400, "temperature": 0.7,
    },
    "thinker": {
        "system": THINKER_SYSTEM, "schema": THINKER_SCHEMA, "schema_name": "thinker_move",
        "max_tokens": 2000, "temperature": 0.4,
    },
}


def build_user_msg(board, color, legal):
    color_str = "黒(X)" if color == BLACK else "白(O)"
    legal_str = ", ".join(legal)
    return (
        f"あなたは {color_str} の手番です。\n\n"
        f"現在の盤面:\n{board_to_ascii(board)}\n\n"
        f"合法手 ({len(legal)}): {legal_str}\n\n"
        f"この中から1つ選んで JSON で答えてください。"
    )


def extract_attempted(text):
    try:
        return str(json.loads(text).get("move", ""))
    except json.JSONDecodeError:
        m = re.search(r"[a-i][1-9]|pass", text)
        return m.group(0) if m else "(parse-failed)"


async def call_model(client, style, board, color, legal, stats, max_retries=2):
    cfg = CFG[style]
    user_msg = build_user_msg(board, color, legal)
    messages = [
        {"role": "system", "content": cfg["system"]},
        {"role": "user", "content": user_msg},
    ]
    legal_set = set(legal)
    for attempt in range(max_retries + 1):
        payload = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": cfg["max_tokens"],
            "temperature": cfg["temperature"],
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": cfg["schema_name"], "schema": cfg["schema"]},
            },
        }
        t0 = time.monotonic()
        try:
            resp = await asyncio.wait_for(
                client.post(f"{BASE_URL}/chat/completions", json=payload),
                timeout=CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            stats["call_timeouts"] += 1
            raise httpx.ReadTimeout(f"call_model timeout after {CALL_TIMEOUT}s")
        latency = time.monotonic() - t0
        stats["latency_sum"] += latency
        stats["latency_count"] += 1
        if resp.status_code != 200:
            stats["http_errors"] += 1
            raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
        text = resp.json()["choices"][0]["message"]["content"] or ""
        stats["calls"] += 1
        try:
            obj = json.loads(text)
            move_str = obj.get("move", "")
        except json.JSONDecodeError:
            move_str = ""
        if move_str and move_str in legal_set:
            if attempt > 0:
                stats["retries"] += attempt
            return move_str, attempt, False
        attempted = extract_attempted(text)
        messages.append({"role": "assistant", "content": text})
        messages.append({
            "role": "user",
            "content": (
                f"あなたが返した {attempted!r} は合法手ではありません。"
                f"合法手は次のいずれかだけです: {', '.join(legal)}。"
                f"必ずこの中から1つ選び、同じ JSON フォーマットで再回答してください。"
            ),
        })
    stats["fallbacks"] += 1
    stats["retries"] += max_retries
    fallback = next((m for m in legal if m != "pass"), legal[0])
    return fallback, max_retries, True


async def play_game(game_id, client, sem, side, stats, results):
    async with sem:
        g = GameState()
        try:
            while not g.is_over:
                legal = g.legal_strs()
                style = side[g.turn]
                mv, retries, fb = await call_model(client, style, g.board, g.turn, legal, stats)
                g.play(mv, retries=retries, forced_fallback=fb)
            w = g.winner()
            winner_style = side[w] if w in (BLACK, WHITE) else DRAW
            results[game_id] = {
                "winner_style": winner_style,
                "sente_style": side[BLACK],
                "moves": g.moves_played,
                "error": None,
            }
        except Exception as e:
            stats["game_errors"] += 1
            results[game_id] = {
                "winner_style": None,
                "sente_style": side[BLACK],
                "moves": g.moves_played,
                "error": f"{type(e).__name__}: {e}",
            }


async def monitor(stats, results, n_games, start_t):
    while True:
        await asyncio.sleep(10)
        done = sum(1 for v in results.values() if v is not None)
        elapsed = time.time() - start_t
        avg_latency = stats["latency_sum"] / stats["latency_count"] if stats["latency_count"] else 0
        rate = stats["calls"] / elapsed if elapsed > 0 else 0
        ws = Counter(v["winner_style"] for v in results.values() if v is not None)
        print(
            f"[{elapsed:5.0f}s] games={done}/{n_games} | calls={stats['calls']} "
            f"({rate:.1f}/s, avg={avg_latency:.1f}s) | retries={stats['retries']} fb={stats['fallbacks']} | "
            f"http_err={stats['http_errors']} call_to={stats['call_timeouts']} game_err={stats['game_errors']} | "
            f"Q={ws.get('quick', 0)} T={ws.get('thinker', 0)} D={ws.get(DRAW, 0)}",
            flush=True,
        )
        if done >= n_games:
            return


async def main(n_games=100, concurrency=20):
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=120.0)
    limits = httpx.Limits(max_connections=concurrency + 20, max_keepalive_connections=concurrency + 20)
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    stats = {
        "calls": 0, "retries": 0, "fallbacks": 0,
        "http_errors": 0, "game_errors": 0, "call_timeouts": 0,
        "latency_sum": 0.0, "latency_count": 0,
    }
    results = {i: None for i in range(n_games)}

    half = n_games // 2
    sides = [
        {BLACK: "quick", WHITE: "thinker"} if i < half else {BLACK: "thinker", WHITE: "quick"}
        for i in range(n_games)
    ]

    print(f"=== Starting {n_games} Go games (concurrency={concurrency}, komi={KOMI}) ===", flush=True)
    print(f"Balanced: {half} Quick=Black, {n_games - half} Thinker=Black", flush=True)
    start_t = time.time()

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers, http2=False) as client:
        tasks = [
            asyncio.create_task(play_game(i, client, sem, sides[i], stats, results))
            for i in range(n_games)
        ]
        mon = asyncio.create_task(monitor(stats, results, n_games, start_t))
        await asyncio.gather(*tasks)
        mon.cancel()

    elapsed = time.time() - start_t
    style_c = Counter()
    when_quick_b = Counter()
    when_thinker_b = Counter()
    moves_by = {"quick": [], "thinker": [], DRAW: []}
    errors = []
    for r in results.values():
        if r["error"]:
            errors.append(r["error"])
            style_c["error"] += 1
            continue
        w = r["winner_style"]
        style_c[w] += 1
        if w in moves_by:
            moves_by[w].append(r["moves"])
        if r["sente_style"] == "quick":
            when_quick_b[w] += 1
        else:
            when_thinker_b[w] += 1

    def avg(lst):
        return f"{sum(lst)/len(lst):.1f}" if lst else "-"

    print()
    print("=" * 60)
    print(f"=== FINAL RESULTS ({n_games} games, {elapsed:.0f}s) ===")
    print("=" * 60)
    print(f"  ● Quick   wins: {style_c.get('quick', 0):>4}  (avg {avg(moves_by['quick'])} moves)")
    print(f"  ○ Thinker wins: {style_c.get('thinker', 0):>4}  (avg {avg(moves_by['thinker'])} moves)")
    print(f"  🤝 Draws       : {style_c.get(DRAW, 0):>4}  (avg {avg(moves_by[DRAW])} moves)")
    print(f"  ⚠ Errors      : {style_c.get('error', 0):>4}")
    print()
    print("--- By Black assignment ---")
    print(f"Quick=Black ({sum(when_quick_b.values())}): Q={when_quick_b.get('quick',0)} T={when_quick_b.get('thinker',0)} D={when_quick_b.get(DRAW,0)}")
    print(f"Thinker=Black ({sum(when_thinker_b.values())}): Q={when_thinker_b.get('quick',0)} T={when_thinker_b.get('thinker',0)} D={when_thinker_b.get(DRAW,0)}")
    print()
    print(f"Total calls: {stats['calls']} | avg latency: {stats['latency_sum']/max(stats['latency_count'],1):.2f}s "
          f"| throughput: {stats['calls']/elapsed:.1f}/s")
    print(f"Retries: {stats['retries']} | Fallbacks: {stats['fallbacks']}")
    print(f"HTTP errors: {stats['http_errors']} | Call timeouts: {stats['call_timeouts']} | Game errors: {stats['game_errors']}")
    if errors:
        print("\nSample errors:")
        for e in errors[:5]:
            print(f"  - {e}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    c = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    asyncio.run(main(n, c))
