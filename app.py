"""Streamlit UI for Gemma vs Gemma 9x9 Go match."""
from __future__ import annotations
import html
import time
import streamlit as st
from dotenv import load_dotenv

from go_game import GameState, BLACK, WHITE, EMPTY, SIZE, count_area, KOMI, str_to_coord
from agent import make_players

load_dotenv()
st.set_page_config(page_title="Gemma vs Gemma — Go", layout="wide")


def init_state():
    if "game" not in st.session_state:
        st.session_state.game = GameState()
    if "players" not in st.session_state:
        quick, thinker = make_players()
        st.session_state.players = {BLACK: quick, WHITE: thinker}
    if "running" not in st.session_state:
        st.session_state.running = False
    if "error" not in st.session_state:
        st.session_state.error = None


GLOBAL_CSS = """
<style>
.go-board { border-collapse: collapse; margin: 0; background: #dcb36a; padding: 6px; }
.go-board td {
    width: 38px; height: 38px; text-align: center; vertical-align: middle;
    font-size: 26px; font-weight: bold;
    background-image:
      linear-gradient(to right, #5b3a18 50%, transparent 50%),
      linear-gradient(to bottom, #5b3a18 50%, transparent 50%);
    background-size: 2px 100%, 100% 2px;
    background-repeat: no-repeat;
    background-position: center center;
    position: relative;
}
.go-board td.tl { background-image:
  linear-gradient(to right, transparent 50%, #5b3a18 50%),
  linear-gradient(to bottom, transparent 50%, #5b3a18 50%); }
.go-board td.tr { background-image:
  linear-gradient(to left, transparent 50%, #5b3a18 50%),
  linear-gradient(to bottom, transparent 50%, #5b3a18 50%); }
.go-board td.bl { background-image:
  linear-gradient(to right, transparent 50%, #5b3a18 50%),
  linear-gradient(to top, transparent 50%, #5b3a18 50%); }
.go-board td.br { background-image:
  linear-gradient(to left, transparent 50%, #5b3a18 50%),
  linear-gradient(to top, transparent 50%, #5b3a18 50%); }
.go-board td.top { background-image:
  linear-gradient(to right, #5b3a18 50%, transparent 50%),
  linear-gradient(to bottom, transparent 50%, #5b3a18 50%); }
.go-board td.bot { background-image:
  linear-gradient(to right, #5b3a18 50%, transparent 50%),
  linear-gradient(to top, transparent 50%, #5b3a18 50%); }
.go-board td.lft { background-image:
  linear-gradient(to right, transparent 50%, #5b3a18 50%),
  linear-gradient(to bottom, #5b3a18 50%, transparent 50%); }
.go-board td.rgt { background-image:
  linear-gradient(to left, transparent 50%, #5b3a18 50%),
  linear-gradient(to bottom, #5b3a18 50%, transparent 50%); }
.go-board td.last { outline: 3px solid #d32f2f; outline-offset: -3px; }
.go-board th {
    width: 20px; height: 18px; text-align: center;
    font-family: monospace; color: #5b3a18; padding: 2px; font-size: 11px;
    background: transparent;
}
.stone {
    display: inline-block; width: 30px; height: 30px; border-radius: 50%;
    position: relative; z-index: 2;
}
.stone.black { background: radial-gradient(circle at 30% 30%, #555, #000); }
.stone.white { background: radial-gradient(circle at 30% 30%, #fff, #bbb); border: 1px solid #888; }

/* Chat bubbles */
.bubble-row { display: flex; margin: 8px 0; align-items: flex-end; }
.bubble-row.left { justify-content: flex-start; }
.bubble-row.right { justify-content: flex-end; }
.bubble-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: #fff; border: 2px solid #888;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0; margin: 0 6px;
}
.bubble-avatar.black { background: #111; color: #fff; }
.bubble-avatar.white { background: #fafafa; color: #111; border-color: #111; }
.bubble {
    padding: 9px 13px; border-radius: 18px; max-width: 80%;
    line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,0.12); font-size: 14px;
}
.bubble.quick { background: #8de08a; color: #1b3a1a; }
.bubble.thinker { background: #a3d3f5; color: #0e2a44; }
.bubble.thinking.quick { background: #d6f0d4; font-style: italic; opacity: 0.9; }
.bubble.thinking.thinker { background: #d8ebf8; font-style: italic; opacity: 0.9; }
.bubble .meta { font-size: 11px; opacity: 0.7; margin-bottom: 3px; }
.bubble .move-chip {
    display: inline-block; color: #fff; padding: 1px 8px; border-radius: 10px;
    font-family: monospace; font-weight: bold; margin-left: 6px; font-size: 12px;
}
.bubble.quick .move-chip { background: #2e7d32; }
.bubble.thinker .move-chip { background: #1565c0; }
.bubble .retry-flag {
    display: inline-block; background: #ffb74d; color: #4e2a00;
    padding: 1px 6px; border-radius: 8px; font-size: 10px; margin-left: 4px;
}
.bubble .fb-flag {
    display: inline-block; background: #e57373; color: #fff;
    padding: 1px 6px; border-radius: 8px; font-size: 10px; margin-left: 4px;
}
.bubble .cap-flag {
    display: inline-block; background: #9c27b0; color: #fff;
    padding: 1px 6px; border-radius: 8px; font-size: 10px; margin-left: 4px;
}
</style>
"""


def render_board_html(board, last_coord=None):
    parts = ['<table class="go-board">']
    parts.append('<tr><th></th>' + ''.join(f'<th>{chr(ord("a") + c)}</th>' for c in range(SIZE)) + '</tr>')
    for r in range(SIZE):
        parts.append(f'<tr><th>{r + 1}</th>')
        for c in range(SIZE):
            cell = board[r][c]
            # Determine intersection position for line drawing
            is_top = r == 0
            is_bot = r == SIZE - 1
            is_lft = c == 0
            is_rgt = c == SIZE - 1
            cls = []
            if is_top and is_lft: cls.append("tl")
            elif is_top and is_rgt: cls.append("tr")
            elif is_bot and is_lft: cls.append("bl")
            elif is_bot and is_rgt: cls.append("br")
            elif is_top: cls.append("top")
            elif is_bot: cls.append("bot")
            elif is_lft: cls.append("lft")
            elif is_rgt: cls.append("rgt")
            if last_coord == (r, c):
                cls.append("last")
            stone = ""
            if cell == BLACK:
                stone = '<span class="stone black"></span>'
            elif cell == WHITE:
                stone = '<span class="stone white"></span>'
            cls_attr = f' class="{" ".join(cls)}"' if cls else ''
            parts.append(f'<td{cls_attr}>{stone}</td>')
        parts.append('</tr>')
    parts.append('</table>')
    return '\n'.join(parts)


def bubble_html(h):
    is_black = h["player"] == BLACK
    side = "left" if is_black else "right"
    avatar_cls = "black" if is_black else "white"
    avatar_glyph = "●" if is_black else "○"
    name = "Quick" if is_black else "Thinker"
    bubble_kind = "quick" if is_black else "thinker"
    move = h["move"]
    summary = html.escape(h.get("comment") or "(出力なし)")
    flags = ""
    cap = h.get("captured", 0)
    if cap > 0:
        flags += f'<span class="cap-flag">捕獲 {cap}</span>'
    if h.get("retries", 0) > 0:
        if h.get("forced_fallback"):
            flags += '<span class="fb-flag">⚠ FB</span>'
        else:
            flags += f'<span class="retry-flag">🔁{h["retries"]}</span>'
    inner = (
        f'<div class="meta">{name}</div>'
        f'<div>{summary}</div>'
        f'<div style="margin-top:4px"><span class="move-chip">{move}</span>{flags}</div>'
    )
    avatar = f'<div class="bubble-avatar {avatar_cls}">{avatar_glyph}</div>'
    bubble = f'<div class="bubble {bubble_kind}">{inner}</div>'
    if side == "left":
        return f'<div class="bubble-row left">{avatar}{bubble}</div>'
    return f'<div class="bubble-row right">{bubble}{avatar}</div>'


def thinking_bubble_html(player):
    is_black = player == BLACK
    side = "left" if is_black else "right"
    avatar_cls = "black" if is_black else "white"
    avatar_glyph = "●" if is_black else "○"
    name = "Quick" if is_black else "Thinker"
    bubble_kind = "quick" if is_black else "thinker"
    bubble = f'<div class="bubble thinking {bubble_kind}"><div class="meta">{name}</div>考え中…</div>'
    avatar = f'<div class="bubble-avatar {avatar_cls}">{avatar_glyph}</div>'
    if side == "left":
        return f'<div class="bubble-row left">{avatar}{bubble}</div>'
    return f'<div class="bubble-row right">{bubble}{avatar}</div>'


def render_feed(game, thinking_player=None):
    parts = []
    if thinking_player is not None:
        parts.append(thinking_bubble_html(thinking_player))
    for h in reversed(game.history):
        parts.append(bubble_html(h))
    return "\n".join(parts)


def step_one_move(feed_placeholder, game):
    if game.is_over:
        st.session_state.running = False
        return
    legal = game.legal_strs()
    color = game.turn
    player = st.session_state.players[color]
    feed_placeholder.markdown(render_feed(game, thinking_player=color), unsafe_allow_html=True)
    try:
        resp = player.choose_move_streaming(game.board, color, legal)
    except Exception as e:
        st.session_state.error = f"{player.name} エラー: {e}"
        st.session_state.running = False
        return
    try:
        game.play(
            resp.move, reasoning=resp.reasoning, raw_text=resp.raw_text, comment=resp.comment,
            retries=resp.retries, forced_fallback=resp.forced_fallback,
        )
    except ValueError as e:
        st.session_state.error = f"内部エラー: {e}"
        st.session_state.running = False


def main():
    init_state()
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    game: GameState = st.session_state.game

    col_left, col_right = st.columns([1, 1])

    with col_left:
        bscore, wscore = count_area(game.board)
        if game.is_over:
            w = game.winner()
            final_b = bscore
            final_w = wscore + KOMI
            if w == BLACK:
                st.markdown(f"### 🏆 ● Quick 勝ち — `{final_b:g} vs {final_w:g} (komi {KOMI})`")
            elif w == WHITE:
                st.markdown(f"### 🏆 ○ Thinker 勝ち — `{final_b:g} vs {final_w:g} (komi {KOMI})`")
            else:
                st.markdown(f"### 🤝 引き分け")
        else:
            turn_label = "● Quick" if game.turn == BLACK else "○ Thinker"
            st.markdown(f"### 手数 {game.moves_played} → 次: **{turn_label}**  "
                        f"盤上 `黒{bscore}` `白{wscore}`")

        last_coord = None
        if game.history:
            last = game.history[-1]
            parsed = str_to_coord(last["move"])
            if parsed not in (None, "pass"):
                last_coord = parsed
        st.markdown(render_board_html(game.board, last_coord=last_coord), unsafe_allow_html=True)

        bcol1, bcol2, bcol3, bcol4 = st.columns(4)
        with bcol1:
            if st.button("▶", help="自動再生", disabled=st.session_state.running or game.is_over, use_container_width=True):
                st.session_state.running = True
                st.rerun()
        with bcol2:
            if st.button("⏸", help="停止", disabled=not st.session_state.running, use_container_width=True):
                st.session_state.running = False
                st.rerun()
        with bcol3:
            if st.button("⏭", help="1手進める", disabled=st.session_state.running or game.is_over, use_container_width=True):
                st.session_state._do_step_once = True
                st.rerun()
        with bcol4:
            if st.button("🔄", help="リセット", use_container_width=True):
                st.session_state.game = GameState()
                st.session_state.running = False
                st.session_state.error = None
                st.session_state.pop("_do_step_once", None)
                st.rerun()

        if st.session_state.error:
            st.error(st.session_state.error)

    with col_right:
        feed_placeholder = st.empty()
        feed_placeholder.markdown(render_feed(game), unsafe_allow_html=True)

        do_step_once = st.session_state.pop("_do_step_once", False)
        do_autoplay_step = st.session_state.running and not game.is_over

        if do_autoplay_step or do_step_once:
            if do_autoplay_step and game.history:
                time.sleep(1.5)
            step_one_move(feed_placeholder, game)
            st.rerun()


if __name__ == "__main__":
    main()
