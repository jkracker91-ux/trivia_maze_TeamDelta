"""view.py — All presentation and I/O for the Forbidden Forest Quiz Maze.

This is the ONLY module allowed to call print() and input().
QuizMazeGame methods return strings; this module renders them.

Dependency rule: view.py imports from maze.py only.
It must never import from db.py or main.py.
"""

from __future__ import annotations

from maze import Direction, Maze, Position

# ── Theme constants ────────────────────────────────────────────────────────────

_W = 54
_BORDER  = "═" * _W
_DIVIDER = "─" * _W
_TITLE   = "✦  FORBIDDEN FOREST QUIZ MAZE  —  Hogwarts Edition  ✦"

_ICON_PLAYER  = " @ "   # current position
_ICON_VISITED = " · "   # previously visited cell
_ICON_EXIT    = "[E]"   # exit chamber
_ICON_FOG     = "???"   # unvisited / unknown

_WALL_H   = "═══"   # horizontal wall segment
_DOOR_H   = "   "   # open horizontal passage (door)
_WALL_V   = "║"     # vertical wall
_DOOR_V   = " "     # open vertical passage (door)

_CORNER_TL = "╔"
_CORNER_TR = "╗"
_CORNER_BL = "╚"
_CORNER_BR = "╝"
_TEE_L     = "╠"
_TEE_R     = "╣"
_TEE_T     = "╦"
_TEE_B     = "╩"
_CROSS     = "╬"

_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (-1,  0),
    Direction.SOUTH: ( 1,  0),
    Direction.EAST:  ( 0,  1),
    Direction.WEST:  ( 0, -1),
}


# ── Map rendering helpers (pure — no print) ────────────────────────────────────

def _is_visible(pos: Position, player_pos: Position, visited: set[Position]) -> bool:
    """A cell is visible if it is the current position or has been visited."""
    return pos == player_pos or pos in visited


def _exit_revealed(
    exit_pos: Position,
    player_pos: Position,
    visited: set[Position],
    maze: Maze,
) -> bool:
    """Exit is revealed once the player is there, has visited it, or
    has visited an adjacent cell."""
    if _is_visible(exit_pos, player_pos, visited):
        return True
    for d in Direction:
        if maze.can_move(exit_pos, d):
            dr, dc = _DELTA[d]
            neighbor = Position(exit_pos.row + dr, exit_pos.col + dc)
            if _is_visible(neighbor, player_pos, visited):
                return True
    return False


def _cell_icon(
    pos: Position,
    player_pos: Position,
    visited: set[Position],
    exit_pos: Position,
    maze: Maze,
) -> str:
    if pos == player_pos:
        return _ICON_PLAYER
    if pos == exit_pos and _exit_revealed(exit_pos, player_pos, visited, maze):
        return _ICON_EXIT
    if pos in visited:
        return _ICON_VISITED
    return _ICON_FOG


def _passage_visible(
    from_pos: Position,
    direction: Direction,
    player_pos: Position,
    visited: set[Position],
    maze: Maze,
) -> bool:
    """True if an open door in *direction* should be drawn (both sides checked)."""
    if not maze.can_move(from_pos, direction):
        return False
    dr, dc = _DELTA[direction]
    neighbor = Position(from_pos.row + dr, from_pos.col + dc)
    return (
        _is_visible(from_pos, player_pos, visited)
        or _is_visible(neighbor, player_pos, visited)
    )


def render_map(
    maze: Maze,
    player_pos: Position,
    visited: set[Position],
    exit_pos: Position,
) -> str:
    """Return the fog-of-war ASCII map as a single string (does NOT print).

    Rendering rules:
      @   — current cell (always visible)
      ·   — previously visited cell
      [E] — exit (visible only once player or adjacent cell is visited)
      ??? — unvisited, unknown cell (fog of war)
    Open doors between rooms are shown as gaps; walls as solid borders.
    """
    h, w = maze.height, maze.width
    lines: list[str] = []

    # Top border
    top = _CORNER_TL
    for c in range(w):
        top += _WALL_H
        top += (_TEE_T if c < w - 1 else _CORNER_TR)
    lines.append(top)

    for r in range(h):
        # Cell content row
        row_line = ""
        for c in range(w):
            pos = Position(r, c)
            if c == 0:
                row_line += _WALL_V
            else:
                west = Position(r, c - 1)
                row_line += (
                    _DOOR_V
                    if _passage_visible(west, Direction.EAST, player_pos, visited, maze)
                    else _WALL_V
                )
            row_line += _cell_icon(pos, player_pos, visited, exit_pos, maze)
        row_line += _WALL_V
        lines.append(row_line)

        # Horizontal separator or bottom border
        if r < h - 1:
            sep = _TEE_L
            for c in range(w):
                pos = Position(r, c)
                sep += (
                    _DOOR_H
                    if _passage_visible(pos, Direction.SOUTH, player_pos, visited, maze)
                    else _WALL_H
                )
                sep += (_CROSS if c < w - 1 else _TEE_R)
            lines.append(sep)
        else:
            bot = _CORNER_BL
            for c in range(w):
                bot += _WALL_H
                bot += (_TEE_B if c < w - 1 else _CORNER_BR)
            lines.append(bot)

    return "\n".join(lines)


# ── Print functions ────────────────────────────────────────────────────────────

def show_banner() -> None:
    """Print the full-width game title banner."""
    print()
    print(_BORDER)
    print(_TITLE.center(_W))
    print(_BORDER)
    print()


def show_message(text: str) -> None:
    """Print a narrative message followed by a thin divider."""
    print()
    print(text)
    print(_DIVIDER)


def show_map(
    maze: Maze,
    player_pos: Position,
    visited: set[Position],
    exit_pos: Position,
) -> None:
    """Print the fog-of-war ASCII map with a themed header and legend."""
    print()
    header = "  FORBIDDEN FOREST — Your Location  "
    print("  ╔" + "═" * len(header) + "╗")
    print("  ║" + header + "║")
    print("  ╚" + "═" * len(header) + "╝")
    print(render_map(maze, player_pos, visited, exit_pos))
    print("  Legend:  @ You   · Visited   [E] Exit   ??? Unknown")
    print(_DIVIDER)


def show_question(
    category: str,
    text: str,
    choices: list[str],
    direction: str,
) -> None:
    """Print the themed trivia challenge for a locked door."""
    print()
    print(_BORDER)
    print(f"  🔒  A door to the {direction.upper()} is locked!")
    print(f"  [{category.upper()}] Answer to pass:")
    print(_DIVIDER)
    print(f"  {text}")
    print()
    for i, choice in enumerate(choices, 1):
        print(f"    {i}. {choice}")
    print(_BORDER)


def show_status(
    pos: Position,
    exit_pos: Position,
    score: int,
    doors: list[str],
    questions_answered: int,
) -> None:
    """Print the immersive status panel."""
    doors_text = ", ".join(doors) if doors else "none — you are surrounded!"
    row_diff = exit_pos.row - pos.row
    col_diff = exit_pos.col - pos.col
    if row_diff == 0 and col_diff == 0:
        hint = "You stand at the exit!"
    else:
        ns = f"{'South' if row_diff > 0 else 'North'} {abs(row_diff)}"
        ew = f"{'East' if col_diff > 0 else 'West'} {abs(col_diff)}"
        hint = f"{ns}, {ew}"
    print()
    print(_BORDER)
    print("  ⚡  STATUS — Forbidden Forest")
    print(_DIVIDER)
    print(f"  Chamber  : row {pos.row}, col {pos.col}")
    print(f"  Exit at  : row {exit_pos.row}, col {exit_pos.col}  ({hint})")
    print(f"  Score    : {score} pts")
    print(f"  Answered : {questions_answered} question(s)")
    print(f"  Doors    : {doors_text}")
    print(_BORDER)


def show_scores(scores: list) -> None:
    """Print the Hall of Magical Achievement high-score table."""
    print()
    print(_BORDER)
    print("  🏆  HALL OF MAGICAL ACHIEVEMENT")
    print(_DIVIDER)
    if not scores:
        print("  No scores recorded yet.")
    else:
        print(f"  {'#':<4} {'Name':<22} {'Score':>6}  Status")
        print(_DIVIDER)
        for rank, s in enumerate(scores, 1):
            status = "✦ Completed" if s.completed else "  Quit"
            print(f"  {rank:<4} {s.player_name:<22} {s.score:>6}  {status}")
    print(_BORDER)


def show_win(player_name: str, score: int, questions: int) -> None:
    """Print the victory screen."""
    print()
    print(_BORDER)
    print("  ✦  YOU ESCAPED THE FORBIDDEN FOREST!  ✦".center(_W))
    print(_DIVIDER)
    print(f"  Well done, {player_name}!")
    print(f"  Final score  : {score} pts")
    print(f"  Questions    : {questions} answered")
    print(_BORDER)


def show_help() -> None:
    """Print the command reference."""
    print()
    print(_DIVIDER)
    print("  Commands: north  south  east  west  |  1 2 3 4  |  status  map  save  scores  quit")
    print(_DIVIDER)


# ── Input prompts ──────────────────────────────────────────────────────────────

def prompt_name() -> str:
    """Ask for the player's Hogwarts name. Loops until non-empty."""
    while True:
        name = input("\n  Enter your Hogwarts name: ").strip()
        if name:
            return name
        print("  Name cannot be empty.")


def prompt_command() -> str:
    """Show the themed command prompt; return stripped lowercase input.
    Returns 'quit' on EOF or keyboard interrupt."""
    try:
        return input("\n  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "quit"


def prompt_resume(player_name: str) -> bool:
    """Ask whether to resume a saved game. Returns True for yes."""
    answer = input(
        f"\n  Saved game found for '{player_name}'. Resume your journey? (y/n): "
    ).strip().lower()
    return answer == "y"


def prompt_replay() -> bool:
    """Ask whether to play again after winning. Returns True for yes."""
    answer = input("\n  Venture into the forest again? (y/n): ").strip().lower()
    return answer == "y"
