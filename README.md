# Go (囲碁): Gemma vs Gemma

Two Gemma-backed agents playing 9×9 Go against each other, differentiated only by prompting.
Same architecture as the [othello-gemma](https://github.com/yanagizawa-naoto/othello-gemma) and
[shogi-gemma](https://github.com/yanagizawa-naoto/shogi-gemma) companion projects.

## Players

Both players use the **same underlying Gemma model**. Differentiation via prompting only.

| Player | Style | Output |
|---|---|---|
| **Quick** | Intuitive / immediate | `{intent, move}` |
| **Thinker** | Deliberate / CoT | `{thinking, summary, move}` — considers strength, territory, balance, neighbor reactions |

## Rules

- 9×9 board
- Chinese area scoring
- **Komi 7.5** (white compensation, guarantees no draws)
- Simple positional ko rule
- No suicide
- Game ends after 2 consecutive passes, or at move 200 (safety cap)

### Move notation

Columns `a`–`i` (left to right), rows `1`–`9` (top to bottom). Examples: `e5` (center star
point), `pass`. Regex: `^([a-i][1-9]|pass)$`.

## Results

Tournament results will be added here after the 100-game balanced run completes (see
`simulate.py`).

## Quick start

```bash
git clone https://github.com/yanagizawa-naoto/go-gemma
cd go-gemma
cp .env.example .env
# edit with your endpoint details
uv sync
uv run streamlit run app.py       # interactive viewer
uv run python simulate.py 100 20  # 100 games, concurrency 20
```

### Required environment variables

See `.env.example`:

- `GEMMA_API_KEY`
- `GEMMA_BASE_URL` (OpenAI-compatible endpoint)
- `GEMMA_MODEL`

## Files

| File | Purpose |
|---|---|
| `go_game.py` | 9×9 Go game logic (captures, ko, suicide, area scoring) |
| `agent.py` | Quick / Thinker players with JSON-schema-constrained output + retry |
| `app.py` | Streamlit viewer (wood-grain board, chat bubbles, last-move highlight) |
| `simulate.py` | Async parallel tournament with per-call timeout and balanced colors |

## License

MIT
