"""Maze domain module — pure topology, wall logic, and gate tracking.

Imports NOTHING from the project (only Python stdlib).
Output is data, not text — no print() calls.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """Cardinal directions for maze movement."""
    NORTH = "north"
    SOUTH = "south"
    EAST  = "east"
    WEST  = "west"


_OFFSETS: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (-1, 0),
    Direction.SOUTH: (1, 0),
    Direction.EAST:  (0, 1),
    Direction.WEST:  (0, -1),
}

_OPPOSITES: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST:  Direction.WEST,
    Direction.WEST:  Direction.EAST,
}


@dataclass(frozen=True)
class Position:
    """Immutable (row, col) coordinate in the maze grid.

    (0,0) is top-left.  Row increases downward, col increases rightward.
    Frozen dataclass ⇒ structural equality, hashable, immutable.
    """
    row: int
    col: int


@dataclass(frozen=True)
class Cell:
    """Snapshot of a single cell's connectivity."""
    position: Position
    open_directions: frozenset[Direction]
    gated_directions: frozenset[Direction]


@dataclass(frozen=True)
class CellStatus:
    """Visibility and role status of a single grid cell for UI rendering.

    Generic name for theme flexibility. Theme equivalents:
    - Forbidden Forest: ClearingStatus
    - Space Station: SectorStatus
    - Dungeon Crawler: ChamberStatus
    """
    position: Position
    visited: bool
    is_player_here: bool
    is_exit: bool
    is_start: bool
    open_directions: frozenset[Direction]
    gated_directions: frozenset[Direction]


@dataclass(frozen=True)
class MapData:
    """Structured snapshot of the full map with Fog of War applied.

    Returned by Maze.get_map_data() for UI consumption.  Unvisited cells
    have their directions hidden (empty frozensets).

    Generic name for theme flexibility. Theme equivalents:
    - Forbidden Forest: ForestMap
    - Space Station: StationMap
    - Dungeon Crawler: DungeonMap
    """
    width: int
    height: int
    grid: dict[Position, CellStatus]
    player_position: Position
    exit_position: Position
    start_position: Position


class Maze:
    """Immutable 2D grid maze.  Knows topology but NOT questions or players.

    Some passages are gated (trivia required); others can be crossed freely.
    The maze does NOT enforce gate logic; that is the caller's job.
    """

    def __init__(
        self,
        width: int,
        height: int,
        passages: set[tuple[Position, Position]],
        gates: set[tuple[Position, Position]],
        start: Position,
        exit_pos: Position,
    ) -> None:
        self._width = width
        self._height = height
        self._start = start
        self._exit_pos = exit_pos

        self._adj: dict[tuple[Position, Direction], Position] = {}
        for a, b in passages:
            d_ab = _direction_between(a, b)
            d_ba = _OPPOSITES[d_ab]
            self._adj[(a, d_ab)] = b
            self._adj[(b, d_ba)] = a

        self._gates: set[frozenset[Position]] = {
            frozenset((a, b)) for a, b in gates
        }

    # ── Queries ──────────────────────────────────────────────

    def can_move(self, from_pos: Position, direction: Direction) -> bool:
        """True if a passage exists in the given direction."""
        return (from_pos, direction) in self._adj

    def is_gated(self, from_pos: Position, direction: Direction) -> bool:
        """True if a passage exists AND is gated (trivia required to cross)."""
        if not self.can_move(from_pos, direction):
            return False
        neighbor = self._adj[(from_pos, direction)]
        return frozenset((from_pos, neighbor)) in self._gates

    def get_open_directions(self, pos: Position) -> list[Direction]:
        """All directions that have a passage (gated or not)."""
        return [d for d in Direction if (pos, d) in self._adj]

    def get_cell(self, pos: Position) -> Cell:
        """Return a Cell snapshot for *pos*."""
        open_dirs = frozenset(self.get_open_directions(pos))
        gated_dirs = frozenset(
            d for d in open_dirs if self.is_gated(pos, d)
        )
        return Cell(
            position=pos,
            open_directions=open_dirs,
            gated_directions=gated_dirs,
        )

    def is_exit(self, pos: Position) -> bool:
        """True if *pos* is the exit cell."""
        return pos == self._exit_pos

    # ── Fog of War ────────────────────────────────────────────

    def get_visible_cells(
        self, visited: set[Position]
    ) -> dict[Position, Cell]:
        """Return Cell data only for positions the player has visited.

        Out-of-bounds positions in *visited* are silently ignored.
        """
        result: dict[Position, Cell] = {}
        for pos in visited:
            if 0 <= pos.row < self._height and 0 <= pos.col < self._width:
                result[pos] = self.get_cell(pos)
        return result

    def get_map_data(
        self,
        player_pos: Position,
        visited: set[Position],
    ) -> MapData:
        """Build a structured map snapshot with Fog of War for the UI.

        Every cell in the grid is represented.  Visited cells expose their
        full connectivity; unvisited cells hide their directions behind
        empty frozensets (the fog).
        """
        visible = self.get_visible_cells(visited)
        grid: dict[Position, CellStatus] = {}
        for r in range(self._height):
            for c in range(self._width):
                pos = Position(r, c)
                cell = visible.get(pos)
                is_visited = cell is not None
                grid[pos] = CellStatus(
                    position=pos,
                    visited=is_visited,
                    is_player_here=(pos == player_pos),
                    is_exit=(pos == self._exit_pos),
                    is_start=(pos == self._start),
                    open_directions=cell.open_directions if cell else frozenset(),
                    gated_directions=cell.gated_directions if cell else frozenset(),
                )
        return MapData(
            width=self._width,
            height=self._height,
            grid=grid,
            player_position=player_pos,
            exit_position=self._exit_pos,
            start_position=self._start,
        )

    # ── Movement ─────────────────────────────────────────────

    def move(self, from_pos: Position, direction: Direction) -> Position:
        """Return the new Position after moving.

        Raises ValueError if a wall blocks the direction.
        Does NOT enforce gates — the caller must check is_gated()
        and handle the question flow before calling move().
        """
        if not self.can_move(from_pos, direction):
            raise ValueError(
                f"Cannot move {direction.value} from {from_pos}: wall"
            )
        return self._adj[(from_pos, direction)]

    # ── Properties ───────────────────────────────────────────

    @property
    def start(self) -> Position:
        return self._start

    @property
    def exit_pos(self) -> Position:
        return self._exit_pos

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height


# ── Helpers (module-private) ─────────────────────────────────

def _direction_between(a: Position, b: Position) -> Direction:
    """Return the Direction from *a* to adjacent cell *b*."""
    dr = b.row - a.row
    dc = b.col - a.col
    for direction, (or_, oc) in _OFFSETS.items():
        if dr == or_ and dc == oc:
            return direction
    raise ValueError(f"{a} and {b} are not orthogonally adjacent")


def _random_edge_position(width: int, height: int) -> Position:
    """Pick a random cell on the edge of a *width* x *height* grid."""
    side = random.choice(["north", "south", "east", "west"])
    if side == "north":
        return Position(0, random.randint(0, width - 1))
    if side == "south":
        return Position(height - 1, random.randint(0, width - 1))
    if side == "west":
        return Position(random.randint(0, height - 1), 0)
    return Position(random.randint(0, height - 1), width - 1)


# ── Factory ──────────────────────────────────────────────────

def generate_maze(
    width: int = 5,
    height: int = 5,
    gate_fraction: float = 0.5,
) -> Maze:
    """Generate a random maze using DFS recursive backtracker.

    A random subset of passages are gated (trivia required); the rest can
    be crossed freely.  gate_fraction (default 0.5) is the proportion of
    passages that are gated (0.0 = none, 1.0 = all).  Start and exit are
    placed on random (different) edges.  The algorithm produces a perfect
    maze — exactly one path between any two cells — so solvability is
    guaranteed.
    """
    passages: set[tuple[Position, Position]] = set()
    visited: set[tuple[int, int]] = set()

    _carve_passages_dfs(0, 0, width, height, visited, passages)

    start = _random_edge_position(width, height)
    min_dist = max(2, (width + height) // 2)
    exit_pos = _random_edge_position(width, height)
    while (exit_pos == start
           or abs(exit_pos.row - start.row) + abs(exit_pos.col - start.col) < min_dist):
        exit_pos = _random_edge_position(width, height)

    gate_fraction = max(0.0, min(1.0, gate_fraction))
    passages_list = list(passages)
    n_gates = min(len(passages_list), max(0, int(len(passages_list) * gate_fraction)))
    gates = set(random.sample(passages_list, n_gates)) if n_gates > 0 else set()

    return Maze(
        width=width,
        height=height,
        passages=passages,
        gates=gates,
        start=start,
        exit_pos=exit_pos,
    )


def _carve_passages_dfs(
    row: int,
    col: int,
    width: int,
    height: int,
    visited: set[tuple[int, int]],
    passages: set[tuple[Position, Position]],
) -> None:
    """Recursive backtracker: carve passages through the grid via DFS."""
    visited.add((row, col))

    neighbors = [(-1, 0), (1, 0), (0, 1), (0, -1)]
    random.shuffle(neighbors)

    for dr, dc in neighbors:
        nr, nc = row + dr, col + dc
        if 0 <= nr < height and 0 <= nc < width and (nr, nc) not in visited:
            passages.add((Position(row, col), Position(nr, nc)))
            _carve_passages_dfs(nr, nc, width, height, visited, passages)
