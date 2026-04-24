# Forbidden Forest Quiz Maze — Interfaces & Data Structures

## Architecture Overview

Five modules with strict dependency rules:

```
main.py  ──imports──▶  maze.py
   │                      ▲
   ├──imports──▶  db.py   │
   │                      │
   └──imports──▶  view.py─┘

pygame_3d.py   ──imports──▶  main.py (QuizMazeGame)
      │                         │
      ├──imports──▶  maze.py    │
      └──imports──▶  db.py      │
```

- **maze.py** — Pure domain logic. Imports nothing from the project.
- **db.py** — Persistence layer. Imports nothing from the project.
- **main.py** — Orchestration + CLI entry point. Imports maze.py, db.py, and view.py.
- **view.py** — CLI presentation. Imports maze.py only. Owns all `print()` and `input()`.
- **pygame_3d.py** — First-person raycasting 3D entry point. Imports main.py, maze.py,
  and db.py. Renders via pygame; does **not** use view.py.

`maze.py` and `db.py` have **zero coupling** to each other. `main.py` is the
only place where they meet, and it handles all translation between domain
objects and persistence representations.

The pygame front-end reuses `QuizMazeGame` from `main.py` for all game logic.
It provides its own rendering and event loop, bypassing `view.py` entirely.
It uses `SQLModelRepository` from `db.py` for persistence.

**I/O Constraint (non-negotiable):** In the CLI path, `print()` and `input()`
may only appear in `view.py`. `maze.py` and `db.py` must never call either. A
CI grep check enforces this rule. `QuizMazeGame` methods return strings;
`main()` passes them to `view.show_message()` for rendering. The pygame
front-end handles its own I/O through the pygame event loop and surface
rendering.

---

## Theme: The Forbidden Forest

The player is a Hogwarts student lost in the **Forbidden Forest**, attempting
to navigate back to the castle. The forest is divided into a grid of
**clearings** — open grassy spaces among ancient trees — connected by narrow
**forest paths**.

Every path between clearings is shrouded in **enchanted fog** — thick,
magical mist that blocks visibility and passage. To dispel the fog and move
through, the player must answer a Harry Potter trivia question correctly.

**Key mechanic: fog dissolution is permanent.** Once a player answers
correctly, the fog on that passage dissolves forever (within the game session).
The player builds a growing network of fog-free paths through the forest.
Wrong answers leave the fog intact — the player stays put and must try a
different passage or attempt the same one again (with a different question).

### Theme ↔ Code Mapping

Code names are kept **generic** so the game can be reskinned to different
themes (dungeon, space station, underwater caves, etc.) without renaming
classes or methods. The theme lives in the narrative text and UI, not in the
domain model.

| Theme Concept (Forbidden Forest) | Code Name / Generic Concept         |
| -------------------------------- | ----------------------------------- |
| Clearing (grassy open space)     | `Cell` — a single grid position     |
| Forest path                      | Passage — connection between cells  |
| Enchanted fog                    | Gate — passage requires a question  |
| Fog dissolves (permanent)        | Passage cleared — free re-traversal |
| Dense, ancient forest            | Wall — impassable boundary          |
| Hogwarts castle                  | Exit cell                           |
| Starting clearing                | Start cell                          |

---

## Module 1: `maze.py` — Maze Domain

### Value Objects

```python
from dataclasses import dataclass
from enum import Enum

class Direction(Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST  = "east"
    WEST  = "west"

@dataclass(frozen=True)
class Position:
    """Immutable (row, col) coordinate in the maze grid.

    (0,0) is top-left. Row increases downward, col increases rightward.
    This is a value object — equality is structural, not identity-based.
    """
    row: int
    col: int

@dataclass(frozen=True)
class Cell:
    """A single cell in the maze grid.

    In the Forbidden Forest theme, each cell represents a clearing —
    an open grassy space among the trees. The code name stays generic
    so the game can be reskinned to other themes.

    open_directions  — directions with passages to adjacent cells.
    gated_directions — subset of open_directions that require a question
                       to traverse. At generation time, every passage is
                       gated (in the forest theme: shrouded in fog).
    """
    position: Position
    open_directions: frozenset[Direction]
    gated_directions: frozenset[Direction]
```

### Maze Class

```python
class Maze:
    """Immutable 2D grid maze. Knows topology but NOT questions, players,
    or gate-clearing state.

    Every passage between cells starts gated — the player must answer
    a trivia question to pass. In the Forbidden Forest theme, gates
    are enchanted fog that dissolves when answered correctly.

    The maze defines the INITIAL gate placement. Actual gate clearing
    during gameplay is tracked by the orchestration layer (main.py).

    The maze does NOT enforce gate logic — that is the caller's
    responsibility.
    """

    def __init__(
        self,
        width: int,                                          # columns
        height: int,                                         # rows
        passages: set[tuple[Position, Position]],            # connections
        gates: set[tuple[Position, Position]],               # gated subset
        start: Position,
        exit_pos: Position,
    ) -> None: ...

    # --- Queries ---

    def can_move(self, from_pos: Position, direction: Direction) -> bool:
        """True if a passage exists in the given direction (gated or not)."""

    def is_gated(self, from_pos: Position, direction: Direction) -> bool:
        """True if a passage exists AND is gated.

        At generation time every passage is gated, so this returns
        the same result as can_move. Kept as a separate query so the
        architecture can support mixed open/gated layouts in the future.

        NOTE: This reflects the INITIAL gate state from generation.
        Runtime gate clearing is tracked in main.py, not here.
        """

    def get_open_directions(self, pos: Position) -> list[Direction]:
        """Return all directions that have a passage (all start gated)."""

    def get_cell(self, pos: Position) -> Cell:
        """Return the Cell object for the given position."""

    def is_exit(self, pos: Position) -> bool:
        """True if pos is the exit cell."""

    # --- Fog of War ---

    def get_visible_cells(
        self, visited: set[Position]
    ) -> dict[Position, Cell]:
        """Return Cell data only for positions the player has visited.

        Out-of-bounds positions in *visited* are silently ignored.
        This method is the sole Fog of War query in maze.py — it returns
        the subset of the grid that the player is allowed to see.
        """

    # --- Movement ---

    def move(self, from_pos: Position, direction: Direction) -> Position:
        """Return the new Position after moving.

        Raises ValueError if a wall blocks the direction.
        NOTE: Does NOT enforce gates. The caller must check gate state
        and handle the question flow before calling move().
        """

    # --- Properties ---

    @property
    def start(self) -> Position: ...

    @property
    def exit_pos(self) -> Position: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...
```

### Maze Generation (DFS Recursive Backtracker)

Mazes are generated at runtime using a DFS recursive backtracker
(`generate_maze(width, height)`). The algorithm produces a **perfect
maze** — a spanning tree of the grid with exactly one path between any
two cells. Every passage is initially gated — there are no free moves
at the start.

**Structural invariants (guaranteed by the algorithm):**

1. Start and exit are placed on random, distinct edges of the grid with a
   minimum Manhattan distance of `max(2, (width+height)//2)`.
2. Exactly one path exists between any two cells (perfect maze).
3. The maze has N−1 passages for N cells (spanning tree property).
4. Every passage is initially gated — the player must answer a question to pass.
5. Passages are symmetric — if A→B exists then B→A exists.
6. Boundary walls are always impassable.

**Example** of a possible 3×3 generated layout (actual layout is random):

```
   +───────────+───────────+───────────+
   │  START    │                       │
   │  (0,0)   🌫 (0,1)    🌫 (0,2)    │
   │  clearing │  clearing │  clearing │
   +───────────+────🌫─────+───────────+
   │                       │           │
   │  (1,0)   🌫 (1,1)    │  (1,2)    │
   │  clearing │  clearing │  clearing │
   +────🌫─────+───────────+────🌫─────+
   │           │                       │
   │  (2,0)   │  (2,1)    🌫   EXIT   │
   │  clearing │  clearing │  (2,2)    │
   +───────────+───────────+───────────+

   🌫 = gated passage (in forest theme: enchanted fog — answer to dissolve)
   Solid walls = impassable (in forest theme: dense, ancient forest)
```

The player must answer a trivia question for the **first** traversal of
each gated passage. Once a gate is cleared, the path remains open for the
rest of the session. This rewards exploration and correct answers with
permanent freedom of movement.

---

## Module 2: `db.py` — Persistence Layer (SQLModel)

### Design Principle: No Domain Objects

The DB layer uses **only primitives and its own SQLModel models**. It never
imports `Position`, `Direction`, `Cell`, or any type from `maze.py`. This is
what keeps the two modules decoupled.

### SQLModel Table Models

```python
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON

class Question(SQLModel, table=True):
    """A single trivia question stored in the database."""
    id: int | None = Field(default=None, primary_key=True)
    question_id: str = Field(index=True, unique=True)
    text: str
    choices: list[str] = Field(sa_column=Column(JSON, nullable=False))
    correct_index: int
    category: str              # e.g. "spells", "characters", "potions"

class Score(SQLModel, table=True):
    """A completed or quit game score record."""
    id: int | None = Field(default=None, primary_key=True)
    player_name: str = Field(index=True)
    score: int
    total_questions: int
    correct_answers: int
    completed: bool            # True if player reached the exit
    timestamp: str             # ISO-8601 format

class GameState(SQLModel, table=True):
    """A saved in-progress game.

    CRITICAL DESIGN DECISION: Position is stored as two ints (player_row,
    player_col), NOT as a Position object. The orchestration layer (main.py)
    is responsible for decomposing Position → (row, col) on save, and
    reconstructing Position(row, col) on load.

    Cleared passages (gates that have been permanently opened) are stored
    as a JSON list of [row1, col1, row2, col2] coordinate quads. main.py
    handles the translation to/from sets of Position pairs.
    """
    id: int | None = Field(default=None, primary_key=True)
    player_name: str = Field(index=True, unique=True)
    player_row: int                 # ← primitive, NOT Position
    player_col: int                 # ← primitive, NOT Position
    score: int
    questions_answered: list[str] = Field(
        sa_column=Column(JSON, nullable=False, default=[])
    )
    cleared_passages: list[list[int]] = Field(
        sa_column=Column(JSON, nullable=False, default=[])
    )
    maze_id: str                    # identifies which maze layout
    timestamp: str                  # ISO-8601 format
```

### SQLModel Table Models (Internal to Repository)

These models define the actual SQLite schema. They are **not** part of the
Protocol contract — they are internal to `SQLModelRepository`. The themed
table names give the database a Harry Potter flavor.

```python
from sqlmodel import SQLModel, Field
from typing import Optional

class Question(SQLModel, table=True):
    """SQLite table for trivia questions."""
    __tablename__ = "enchanted_questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: str = Field(index=True, unique=True)
    text: str
    choices_json: str       # JSON-serialized list[str]
    correct_index: int
    category: str

class Score(SQLModel, table=True):
    """SQLite table for game scores."""
    __tablename__ = "house_scores"

    id: Optional[int] = Field(default=None, primary_key=True)
    player_name: str = Field(index=True)
    score: int
    total_questions: int
    correct_answers: int
    completed: bool
    timestamp: str

class GameState(SQLModel, table=True):
    """SQLite table for saved in-progress games."""
    __tablename__ = "game_chronicles"

    id: Optional[int] = Field(default=None, primary_key=True)
    player_name: str = Field(index=True, unique=True)
    player_row: int
    player_col: int
    score: int
    questions_answered_json: str    # JSON-serialized list[str]
    visited_cells_json: str         # JSON-serialized list of [row, col] pairs
    maze_id: str
    timestamp: str
```

**Why JSON-serialized columns?** SQLite has no native array type.
`choices_json`, `questions_answered_json`, and `visited_cells_json` store
their data as JSON strings. The repository handles serialization and
deserialization transparently when converting between SQLModel rows and
DTO dataclasses.

### Repository Protocols

```python
from typing import Protocol

class GameRepository(Protocol):
    """Interface for saving/loading in-progress games."""

    def save_game(self, state: GameState) -> None: ...

    def load_game(self, player_name: str) -> GameState | None: ...

    def delete_game(self, player_name: str) -> None: ...

class ScoreRepository(Protocol):
    """Interface for recording and retrieving completed game scores."""

    def save_score(self, score: Score) -> None: ...

    def get_high_scores(self, limit: int = 10) -> list[Score]: ...

    def get_player_scores(self, player_name: str) -> list[Score]: ...

class QuestionRepository(Protocol):
    """Interface for retrieving trivia questions."""

    def get_question(self, question_id: str) -> Question | None: ...

    def get_random_question(
        self, exclude: list[str] | None = None
    ) -> Question | None: ...

    def get_all_questions(self) -> list[Question]: ...
```

### SQLModelRepository

```python
from sqlmodel import Session, create_engine, select

class SQLModelRepository:
    """ORM-backed repository satisfying all three repository protocols.

    Backed by SQLite via SQLModel. Provides the sole persistence
    layer for the project.

    Tables are auto-created on __init__ via SQLModel.metadata.create_all().
    """

    def __init__(self, db_url: str = "sqlite:///game_data.db") -> None:
        self._engine = create_engine(db_url)
        SQLModel.metadata.create_all(self._engine)

    # --- GameRepository ---
    def save_game(self, state: GameState) -> None: ...
    def load_game(self, player_name: str) -> GameState | None: ...
    def delete_game(self, player_name: str) -> None: ...

    # --- ScoreRepository ---
    def save_score(self, score: Score) -> None: ...
    def get_high_scores(self, limit: int = 10) -> list[Score]: ...
    def get_player_scores(self, player_name: str) -> list[Score]: ...

    # --- QuestionRepository ---
    def get_question(self, question_id: str) -> Question | None: ...
    def get_random_question(self, exclude: list[str] | None = None) -> Question | None: ...
    def get_all_questions(self) -> list[Question]: ...

    # --- Seeding (not part of any Protocol) ---
    def load_questions(self, questions: list[Question]) -> None:
        """Replace stored questions with the given list."""
    def load_questions_from_file(self, filepath: str | Path) -> None:
        """Read a JSON array of question dicts and upsert them."""
```

---

## Module 3: `main.py` — Game Orchestration

### Application-Layer Types

```python
from dataclasses import dataclass, field

@dataclass
class Player:
    """Mutable player state managed by the game session.
    
    This is an APPLICATION-layer type, not a domain type. It bridges
    maze.py's Position with db.py's primitives.

    visited tracks every room the player has entered; QuizMazeGame adds
    the new position to visited after every successful move (including
    game start). On save, main.py decomposes visited: set[Position] →
    list[list[int]] for GameStateRow.visited_cells. On load, it
    reconstructs the set[Position] from that list.
    """
    name: str
    position: Position              # from maze.py — domain object
    score: int = 0
    questions_answered: list[str] = field(default_factory=list)
    visited: set[Position] = field(default_factory=set)  # fog-of-war history
```

### Game Session Class

```python
class QuizMazeGame:
    """Orchestrates gameplay between the maze domain and persistence layer.

    This is the ONLY place where maze.py types and db.py types meet.
    It handles all translation between the two, including gate-clearing state.
    """

    def __init__(
        self,
        player_name: str,
        maze: Maze,                         # from maze.py
        game_repo: GameRepository,          # from db.py (Protocol)
        score_repo: ScoreRepository,        # from db.py (Protocol)
        question_repo: QuestionRepository,  # from db.py (Protocol)
    ) -> None: ...

    # --- Game Lifecycle ---

    def start_new_game(self) -> str:
        """Initialize a new game. Returns opening narrative.

        Resets player to maze start, score to 0, and all passages
        to fully gated (no cleared passages).
        """

    def resume_game(self) -> str:
        """Load saved state from DB. Returns resumption narrative.

        THIS is where Position AND cleared-passage reconstruction happens:
            row = game_state.player_row
            col = game_state.player_col
            self.player.position = Position(row, col)
            self.player.cleared_passages = _decode_cleared(game_state.cleared_passages)
        """

    # --- Player Actions ---

    def move(self, direction_str: str) -> str:
        """Attempt to move in a direction. Returns narrative text.

        Flow:
        1. Parse direction_str → Direction enum
        2. Check maze.can_move(pos, direction)
        3. If blocked by wall → return "wall" narrative
        4. Passage exists, gate cleared → move freely (no question)
        5. Passage exists, gate active → store pending move, return question text
        6. After correct answer → clear gate permanently, execute move
        7. After wrong answer → gate holds, stay put
        8. If new position is exit → return victory narrative
        """

    def answer_question(self, choice: int) -> str:
        """Submit answer to the pending gate question.

        Correct → gate clears on that passage permanently, player moves through.
        Incorrect → gate holds, player stays put, pending state cleared.
        """

    # --- State ---

    def get_status(self) -> str:
        """Return current game status: position, score, passage info, exits."""

    def save_game(self) -> None:
        """Persist current state to DB.

        THIS is where Position AND cleared-passage decomposition happens:
            GameState(
                player_row=self.player.position.row,
                player_col=self.player.position.col,
                cleared_passages=_encode_cleared(self.player.cleared_passages),
                ...
            )
        """

    def quit_game(self) -> None:
        """Save and exit."""

    # --- Map Rendering (fog-of-war) ---

    def _render_map(self) -> str:
        """Return ASCII fog-of-war map by delegating to view.render_map.

        Lazy import keeps view.py optional for headless tests.
        Rendering rules: @ current, · visited, [E] exit, ??? unknown.
        """

    # --- Translation Helpers (private) ---

    def _to_game_state_row(self) -> GameStateRow:
        """Decompose domain objects → DB primitives.

        Position → (player_row, player_col) ints.
        visited set[Position] → visited_cells list[list[int]].
        """

    def _from_game_state_row(self, row: GameStateRow) -> Player:
        """Reconstruct domain objects ← DB primitives.

        (player_row, player_col) ints → Position.
        visited_cells list[list[int]] → set[Position].
        """
```

**Visibility rules:**

- A cell is visible if and only if it is in `player.visited_cells`.
- The start cell is added to `visited_cells` at game start.
- Each successful move adds the new position to `visited_cells`.
- Wrong answers do NOT reveal the target cell.
- Visited cells are persisted through save/load cycles.

### Game Loop (free function)

```python
def main() -> None:
    """Top-level game loop. All I/O routed through view.py.

    Commands:
        north / south / east / west  — attempt to move through a door
        1 / 2 / 3 / 4               — answer a pending question
        status                       — show status panel + map
        map                          — redraw the fog-of-war map
        save                         — save game
        quit                         — save and exit
        scores                       — show high-score table
        help / ?                     — show command reference
    """
```

---

## Critical Design Decision: Position Across the DB Boundary

### The Problem

`Position` is a frozen dataclass defined in `maze.py`. The DB layer (`db.py`)
must persist the player's location AND visited cell history. But `db.py`
cannot import from `maze.py` (dependency rule: no coupling between domain and
persistence).

### The Solution: Primitive Decomposition at the Boundary

```
                    main.py (translation layer)
                   ┌───────────────────────────┐
                   │                           │
  maze.py          │   Position(row=1, col=2)  │          db.py
  ────────         │         ↕ translate ↕      │         ────────
  Position  ◄──────┤   player_row=1             ├──────►  GameState
  (domain          │   player_col=2             │         (SQLModel
   object)         │                           │          table)
                   └───────────────────────────┘
```

**On Save** (`main.py._to_game_state`):

```python
GameState(
    player_row = self.player.position.row,   # Position → int
    player_col = self.player.position.col,   # Position → int
    ...
)
```

**On Load** (`main.py._from_game_state`):

```python
Player(
    position = Position(row=state.player_row, col=state.player_col),  # int → Position
    ...
)
```

### Why Not a Shared `models.py`?

A shared types module would couple maze.py and db.py through a common
dependency, defeating the purpose of the separation. By keeping translation in
main.py:

1. **maze.py** can evolve its domain types freely (e.g., add `z` coordinate
   for 3D mazes) without changing db.py.
2. **db.py** can change its schema freely (e.g., store position as a single
   string `"1,2"`) without changing maze.py.
3. **main.py** is the single place that knows how both sides represent
   location, making it easy to update the translation if either side changes.

---

## Module 4: `view.py` — Presentation Layer

### Design Principle: Sole Owner of I/O

`view.py` is the **only** module that may call `print()` or `input()`.
It imports from `maze.py` only (for `Position`, `Direction`, `Maze`).
It must never import from `db.py` or `main.py`.

### Pure rendering function (testable)

```python
def render_map(
    maze: Maze,
    player_pos: Position,
    visited: set[Position],
    exit_pos: Position,
) -> str:
    """Return the fog-of-war ASCII map as a plain string. Does NOT print.

    Rendering rules:
      @   — current cell (always visible)
      ·   — previously visited cell
      [E] — exit (visible only once the player or an adjacent cell is visited)
      ??? — unvisited, unknown cell (fog of war)
    Open doors shown as gaps; walls as box-drawing borders.
    Output has exactly 2*height+1 lines.
    """
```

### Print functions (side-effecting)

```python
def show_banner() -> None:
    """Print the full-width game title banner."""

def show_message(text: str) -> None:
    """Print a narrative message followed by a thin divider."""

def show_map(maze, player_pos, visited, exit_pos) -> None:
    """Print render_map() output with a themed header and legend."""

def show_question(category, text, choices, direction) -> None:
    """Print the themed trivia challenge for a locked door."""

def show_status(pos, exit_pos, score, doors, questions_answered) -> None:
    """Print the immersive status panel."""

def show_scores(scores) -> None:
    """Print the Hall of Magical Achievement high-score table."""

def show_win(player_name, score, questions) -> None:
    """Print the victory screen."""

def show_help() -> None:
    """Print the command reference."""
```

### Input prompts

```python
def prompt_name() -> str:
    """Ask for the player's Hogwarts name. Loops until non-empty."""

def prompt_command() -> str:
    """Show '> ' prompt; return stripped lowercase input.
    Returns 'quit' on EOF or keyboard interrupt."""

def prompt_resume(player_name: str) -> bool:
    """Ask whether to resume a saved game. Returns True for yes."""

def prompt_replay() -> bool:
    """Ask whether to play again after winning. Returns True for yes."""
```

---

## Module 5: `pygame_3d.py` — First-Person Raycasting 3D Entry Point

### Design Principle: Self-contained 3D Rendering

`pygame_3d.py` is a **standalone graphical front-end** for the game. It uses a
**raycasting first-person 3D view** built with pure pygame (no OpenGL or
additional 3D libraries). It imports `QuizMazeGame` from `main.py` for all
game logic and `SQLModelRepository` from `db.py` for persistence. It does
**not** use `view.py` — all rendering is handled through pygame surfaces.

**Run with:** `python pygame_3d.py`

### Dependencies

```
pygame_3d.py → main.py  (QuizMazeGame, POINTS_PER_CORRECT)
             → maze.py  (Direction, Position, generate_maze)
             → db.py    (SQLModelRepository, seed_questions_if_empty)
             → pygame   (rendering, audio, event loop)
```

### State Machine

```
MENU ──Enter──▶ PLAYING ──question──▶ QUESTION ──answer──▶ PLAYING
  ▲                │                                          │
  │                ├──win──▶ WIN ──R──▶ (restart)             │
  │                ├──Tab──▶ SCORES ──key──▶ PLAYING          │
  │                └──0 hearts──▶ NO_HEARTS ──key──▶ MENU     │
  └────────────────────────────────────────────────────────────┘
```

### Controls

| Key / Input             | Action                              |
|-------------------------|-------------------------------------|
| Mouse movement          | Look left / right                   |
| Left / Right arrows     | Rotate view (keyboard)              |
| Up arrow / W            | Move forward (smooth ease-out walk) |
| A / D                   | Strafe left / right                 |
| 1  2  3  4              | Answer a pending gate question      |
| N                       | Toggle music on / off               |
| Ctrl+S                  | Save game                           |
| Tab                     | View high-score table               |
| M                       | Toggle minimap                      |
| ESC                     | Save and quit                       |

### Key Visual Features

- **Enchanted fog**: Green shimmering fog on unvisited passage boundaries.
  Dissolves permanently after the player clears the passage with a correct
  answer. Uses per-column alpha blending with a time-based shimmer offset.
- **Exit floor tint**: The exit cell floor is tinted warm gold using
  per-column floor-casting, visible from any distance and angle.
- **Smooth walking**: Movement uses linear interpolation with ease-out
  deceleration (`WALK_SPEED = 1.8`). No instant teleportation.
- **Mouse look**: First-person mouse control with grab/release on state
  transitions (`MOUSE_SENS = 0.003`).
- **Hogwarts-themed UI**: Status panel titled "Marauder's Map" shows
  courage (lives), house points (score), spells cast (questions answered),
  open passages, and a narrative proximity compass. Message log titled
  "Owl Post" with colour-coded narrative text.
- **Maze size selector**: Clickable ◄ / ► buttons and keyboard arrows
  on the main menu. Sizes: 3x3, 5x5, 7x7.
- **Music toggle**: Clickable button on both main menu and in-game
  status panel, plus `N` keyboard shortcut.

### Entry Point

```python
def main() -> None:
    """Initialise pygame, set up SQLModelRepository, seed questions,
    and enter the raycasting event loop at 60 FPS.

    Reuses QuizMazeGame from main.py for all game logic. This module
    owns only the 3D raycasting renderer and first-person input mapping.
    """
```
