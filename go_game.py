"""9x9 Go (囲碁) game logic with Chinese area scoring and 7.5 komi."""
from __future__ import annotations
from dataclasses import dataclass, field
from copy import deepcopy

EMPTY, BLACK, WHITE = 0, 1, 2
SIZE = 9
KOMI = 7.5  # White compensation for going second; 7.5 avoids ties.
MAX_MOVES = 200


def opponent(c: int) -> int:
    return WHITE if c == BLACK else BLACK


def neighbors(r: int, c: int):
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < SIZE and 0 <= nc < SIZE:
            yield nr, nc


def find_group(board, r: int, c: int):
    """Return (stones, liberties) for the group containing (r, c)."""
    color = board[r][c]
    if color == EMPTY:
        return set(), set()
    stones = set()
    liberties = set()
    stack = [(r, c)]
    while stack:
        pr, pc = stack.pop()
        if (pr, pc) in stones:
            continue
        stones.add((pr, pc))
        for nr, nc in neighbors(pr, pc):
            if board[nr][nc] == EMPTY:
                liberties.add((nr, nc))
            elif board[nr][nc] == color and (nr, nc) not in stones:
                stack.append((nr, nc))
    return stones, liberties


def apply_move(board, row: int, col: int, color: int):
    """Try to place a stone. Return (new_board, captured_list, ok, reason)."""
    if board[row][col] != EMPTY:
        return None, [], False, "occupied"
    new_board = deepcopy(board)
    new_board[row][col] = color
    # Capture opponent groups that lost their last liberty
    opp = opponent(color)
    captured = []
    seen = set()
    for nr, nc in neighbors(row, col):
        if new_board[nr][nc] == opp and (nr, nc) not in seen:
            stones, libs = find_group(new_board, nr, nc)
            seen |= stones
            if not libs:
                for sr, sc in stones:
                    new_board[sr][sc] = EMPTY
                    captured.append((sr, sc))
    # Suicide check
    _, own_libs = find_group(new_board, row, col)
    if not own_libs:
        return None, [], False, "suicide"
    return new_board, captured, True, "ok"


def count_area(board):
    """Chinese area scoring: stones + solely-surrounded empty territory."""
    bstones = wstones = 0
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] == BLACK:
                bstones += 1
            elif board[r][c] == WHITE:
                wstones += 1
    visited = [[False] * SIZE for _ in range(SIZE)]
    bter = wter = 0
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] != EMPTY or visited[r][c]:
                continue
            region = []
            borders = set()
            stack = [(r, c)]
            while stack:
                pr, pc = stack.pop()
                if visited[pr][pc]:
                    continue
                visited[pr][pc] = True
                region.append((pr, pc))
                for nr, nc in neighbors(pr, pc):
                    if board[nr][nc] == EMPTY:
                        if not visited[nr][nc]:
                            stack.append((nr, nc))
                    else:
                        borders.add(board[nr][nc])
            if borders == {BLACK}:
                bter += len(region)
            elif borders == {WHITE}:
                wter += len(region)
    return bstones + bter, wstones + wter


def coord_to_str(row: int, col: int) -> str:
    """(0, 0) -> 'a1' (column a, row 1)."""
    return f"{chr(ord('a') + col)}{row + 1}"


def str_to_coord(s: str):
    s = s.strip().lower()
    if s == "pass":
        return "pass"
    if len(s) < 2 or len(s) > 3:
        return None
    col_ch = s[0]
    if not ("a" <= col_ch <= "i"):
        return None
    col = ord(col_ch) - ord("a")
    try:
        row = int(s[1:]) - 1
    except ValueError:
        return None
    if not (0 <= row < SIZE):
        return None
    return (row, col)


def board_to_ascii(board) -> str:
    sym = {EMPTY: ".", BLACK: "X", WHITE: "O"}
    lines = ["  a b c d e f g h i"]
    for r in range(SIZE):
        cells = " ".join(sym[board[r][c]] for c in range(SIZE))
        lines.append(f"{r + 1} {cells}")
    return "\n".join(lines)


@dataclass
class GameState:
    board: list = field(default_factory=lambda: [[EMPTY] * SIZE for _ in range(SIZE)])
    turn: int = BLACK
    history: list = field(default_factory=list)
    passes_in_a_row: int = 0
    prev_board: list | None = None  # For simple positional ko
    moves_played: int = 0

    @property
    def is_over(self) -> bool:
        return self.passes_in_a_row >= 2 or self.moves_played >= MAX_MOVES

    def legal_strs(self) -> list[str]:
        moves = ["pass"]
        for r in range(SIZE):
            for c in range(SIZE):
                if self.board[r][c] != EMPTY:
                    continue
                nb, _, ok, _ = apply_move(self.board, r, c, self.turn)
                if not ok:
                    continue
                if self.prev_board is not None and nb == self.prev_board:
                    continue
                moves.append(coord_to_str(r, c))
        return moves

    def play(self, move_str: str, *, reasoning: str = "", raw_text: str = "",
             comment: str = "", retries: int = 0, forced_fallback: bool = False) -> None:
        prev = deepcopy(self.board)
        parsed = str_to_coord(move_str)
        if parsed == "pass":
            self.passes_in_a_row += 1
            captured = 0
        elif parsed is None:
            raise ValueError(f"Bad move string: {move_str!r}")
        else:
            r, c = parsed
            nb, cap, ok, reason = apply_move(self.board, r, c, self.turn)
            if not ok:
                raise ValueError(f"Illegal move {move_str}: {reason}")
            if self.prev_board is not None and nb == self.prev_board:
                raise ValueError(f"Illegal move {move_str}: ko violation")
            self.board = nb
            self.prev_board = prev
            self.passes_in_a_row = 0
            captured = len(cap)
        self.history.append({
            "player": self.turn,
            "move": move_str,
            "reasoning": reasoning,
            "comment": comment,
            "raw_text": raw_text,
            "board_after": deepcopy(self.board),
            "captured": captured,
            "retries": retries,
            "forced_fallback": forced_fallback,
        })
        self.turn = opponent(self.turn)
        self.moves_played += 1

    def winner(self):
        """Return BLACK / WHITE / 0(draw — shouldn't happen with 7.5 komi) / None if ongoing."""
        if not self.is_over:
            return None
        b, w = count_area(self.board)
        bf = b
        wf = w + KOMI
        if bf > wf:
            return BLACK
        if wf > bf:
            return WHITE
        return 0
