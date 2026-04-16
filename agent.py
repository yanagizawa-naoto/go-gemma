"""Quick (intuition) and Thinker (CoT) 9x9 Go players using Gemma + JSON schema."""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from typing import Callable
import httpx
from go_game import board_to_ascii


QUICK_SYSTEM = """あなたは9路盤の囲碁の対局者です。スタイルは「直感型・即答」。
盤面と合法手リストを見て、深く読まずに直感で着手を決めます。

座標表記:
- 列は a〜i（左から）、行は 1〜9（上から）。例: "e5"=中央
- パスは "pass"
- 必ず提示された合法手リストの中から1つ選ぶこと

JSON で次を返してください:
- intent: この手で何を狙っているかの宣言文（例 "中央を厚くして全局の主導権を取る狙い"）
- move: 座標文字列（例 "e5" または "pass"）"""

THINKER_SYSTEM = """あなたは9路盤の囲碁の対局者です。スタイルは「熟考型・じっくり読む」。
盤面と合法手リストを見て、最低3つの候補手を比較検討します。

検討の観点:
- 石の強弱（眼形、連絡、切断）
- 地の多少（自分の地の拡大、相手の地の削減）
- 厚み vs 実利のバランス
- 隅・辺・中央の形勢
- 次の相手の反応を想定

座標表記: 列 a〜i、行 1〜9（例 "e5"）、パスは "pass"

JSON で次を返してください:
- thinking: 候補手3つ以上を比較した詳細な検討プロセス
- summary: 最終決定の理由を一行で端的に
- move: 座標文字列（必ず合法手リストから選ぶこと）"""


MOVE_PATTERN = r"^([a-i][1-9]|pass)$"

QUICK_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "minLength": 5},
        "move": {"type": "string", "pattern": MOVE_PATTERN},
    },
    "required": ["intent", "move"],
    "additionalProperties": False,
}

THINKER_SCHEMA = {
    "type": "object",
    "properties": {
        "thinking": {"type": "string", "minLength": 30},
        "summary": {"type": "string", "minLength": 5},
        "move": {"type": "string", "pattern": MOVE_PATTERN},
    },
    "required": ["thinking", "summary", "move"],
    "additionalProperties": False,
}


@dataclass
class AgentResponse:
    move: str | None
    raw_text: str
    reasoning: str
    comment: str
    retries: int = 0
    forced_fallback: bool = False


class GemmaPlayer:
    def __init__(self, name, style, model, base_url, api_key):
        assert style in ("quick", "thinker")
        self.name = name
        self.style = style
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.system_prompt = QUICK_SYSTEM if style == "quick" else THINKER_SYSTEM
        self.schema = QUICK_SCHEMA if style == "quick" else THINKER_SCHEMA
        self.schema_name = "quick_move" if style == "quick" else "thinker_move"
        self.max_tokens = 400 if style == "quick" else 2000
        self.temperature = 0.7 if style == "quick" else 0.4

    def _build_user_msg(self, board, color: int, legal: list[str]) -> str:
        color_str = "黒(X)" if color == 1 else "白(O)"
        legal_str = ", ".join(legal)
        return (
            f"あなたは {color_str} の手番です。\n\n"
            f"現在の盤面（X=黒, O=白, . =空点）:\n{board_to_ascii(board)}\n\n"
            f"合法手 ({len(legal)}): {legal_str}\n\n"
            f"この中から1つ選んで JSON で答えてください。"
        )

    def _payload(self, messages, stream):
        return {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": self.schema_name, "schema": self.schema},
            },
        }

    def _stream_one_attempt(self, messages, on_chunk_with_delta):
        text = ""
        with httpx.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=self._payload(messages, stream=True),
            timeout=180,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}).get("content")
                if delta:
                    text += delta
                    if on_chunk_with_delta:
                        on_chunk_with_delta(delta)
        return text

    def choose_move_streaming(self, board, color: int, legal: list[str],
                              on_chunk: Callable[[str, str], None] | None = None,
                              max_retries: int = 2) -> AgentResponse:
        user_msg = self._build_user_msg(board, color, legal)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_msg},
        ]
        legal_set = set(legal)
        overall = ""
        last_text = ""
        for attempt in range(max_retries + 1):
            if attempt > 0:
                marker = f"\n\n--- 🔁 再試行 {attempt}/{max_retries} ---\n\n"
                overall += marker
                if on_chunk:
                    on_chunk(marker, overall)

            def per_chunk(delta):
                nonlocal overall
                overall += delta
                if on_chunk:
                    on_chunk(delta, overall)

            text = self._stream_one_attempt(messages, per_chunk)
            last_text = text
            mv, intent, thinking, summary = self._parse(text)
            if mv and mv in legal_set:
                return AgentResponse(
                    move=mv, raw_text=overall,
                    reasoning=thinking, comment=(intent if self.style == "quick" else summary),
                    retries=attempt,
                )
            attempted = mv or "(parse-failed)"
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": (
                    f"あなたが返した {attempted!r} は合法手ではありません。"
                    f"合法手は次のいずれかだけです: {', '.join(legal)}。"
                    f"必ずこの中から1つ選び、同じ JSON フォーマットで再回答してください。"
                ),
            })
        # fallback: first legal (excluding pass if possible)
        fallback = next((m for m in legal if m != "pass"), legal[0])
        mv, intent, thinking, summary = self._parse(last_text)
        return AgentResponse(
            move=fallback, raw_text=overall,
            reasoning=thinking, comment=(intent if self.style == "quick" else summary) or "(fallback)",
            retries=max_retries, forced_fallback=True,
        )

    @staticmethod
    def _parse(text: str):
        try:
            obj = json.loads(text)
            return (
                obj.get("move", "") or "",
                obj.get("intent", "") or "",
                obj.get("thinking", "") or "",
                obj.get("summary", "") or "",
            )
        except json.JSONDecodeError:
            m = re.search(r"[a-i][1-9]|pass", text)
            return (m.group(0) if m else ""), "", "", ""


def make_players():
    base_url = os.environ.get("GEMMA_BASE_URL", "")
    api_key = os.environ.get("GEMMA_API_KEY", "")
    model = os.environ.get("GEMMA_MODEL", "")
    missing = [k for k, v in {
        "GEMMA_API_KEY": api_key, "GEMMA_BASE_URL": base_url, "GEMMA_MODEL": model,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Required env vars not set: {', '.join(missing)} (see .env.example)")
    quick = GemmaPlayer("Gemma Quick", "quick", model, base_url, api_key)
    thinker = GemmaPlayer("Gemma Thinker", "thinker", model, base_url, api_key)
    return quick, thinker
