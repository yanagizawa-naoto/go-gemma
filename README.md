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

## Results: 100-game balanced tournament

100 games with balanced color assignment (50 Quick=Black, 50 Thinker=Black), concurrency 20,
7.5 komi, 200-move safety cap. Wall-clock: ~101 minutes.

| Outcome | Count | Share (of 96 valid) |
|---|---|---|
| ○ **Thinker wins** | **60** | **62.5%** |
| ● Quick wins | 36 | 37.5% |
| 🤝 Draws | 0 | 0% (komi 7.5 guarantees no ties) |
| ⚠ Errors | 4 | — (all `ReadTimeout` after 90s) |

**Thinker dominates Go with nearly 2:1 odds vs. Quick.** Unlike shogi (where the CoT couldn't
translate into mate), Go's area-score objective rewards patient territorial play — which is exactly
what the Thinker prompt encourages. The "intuitive" Quick agent makes locally plausible moves but
loses on global shape evaluation.

### Breakdown by color

| Black side | Games | Quick wins | Thinker wins |
|---|---|---|---|
| Quick = Black | 49 | 15 (31%) | 34 (69%) |
| Thinker = Black | 47 | 21 (45%) | 26 (55%) |

Thinker wins regardless of color, but its margin is much larger when it plays White (gote). Black's
"first move" advantage is nearly cancelled by 7.5 komi, so the real driver is playing style.

### Performance

- Total API calls: 17,089
- Avg latency: 6.56 s
- Throughput: 2.8 calls/s
- Retries: 757 (4.4% — Gemma occasionally suggests already-occupied points or ko violations)
- Fallbacks: 25 (retries exhausted → first legal non-pass move)
- Timeouts: 4 (all `ReadTimeout` after 90 s)
- Avg game length: 170 moves (played to 200-move cap or two-pass)

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
