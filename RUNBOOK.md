# Quiz Maze Game — RUNBOOK

## Project: Forbidden Forest Quiz Maze

A Harry Potter-themed maze game where the player (a Hogwarts student) must
navigate a procedurally generated maze through the Forbidden Forest, answering
Harry Potter trivia questions at each new passage to find their way back to
Hogwarts castle. Maze sizes are selectable (3x3, 5x5, 7x7). Once a passage
is cleared, the player can walk freely through it for the rest of the session.

---

## Dependency Rules

These rules are **inviolable**. Any import that breaks them is a build failure.

### Rule 1: `maze.py` imports NOTHING from the project

```
maze.py → (only Python stdlib: dataclasses, enum, random, typing)
```

`maze.py` is pure domain logic. It defines its own types (`Position`,
`Direction`, `Cell`) and has zero knowledge of persistence, UI, or questions.
This makes it trivially testable and reusable.

**Enforcement:** `maze.py` shall contain no `from db import` or
`from main import` statements. A CI grep check can verify this.

### Rule 2: `db.py` imports NOTHING from the project

```
db.py → (only Python stdlib: dataclasses, typing, json, pathlib, random)
```

`db.py` defines its own persistence types (`GameStateRow`, `ScoreRow`,
`QuestionRow`) using only primitives. It has zero knowledge of maze topology
or domain objects like `Position`.

**Enforcement:** `db.py` shall contain no `from maze import` or
`from main import` statements.

### Rule 3: `main.py` imports from both, bridges the gap

```
main.py → maze.py  (for Position, Direction, Maze)
main.py → db.py    (for Repositories, Row types)
```

`main.py` is the **only** module where maze.py and db.py concepts meet. It
handles all translation between domain objects and persistence primitives.

### Dependency Matrix

| Module    | maze.py | db.py | main.py | stdlib |
|-----------|---------|-------|---------|--------|
| maze.py   | —       | NO    | NO      | YES    |
| db.py     | NO      | —     | NO      | YES    |
| main.py   | YES     | YES   | —       | YES    |

### Why This Matters

- **maze.py** and **db.py** can be developed, tested, and modified
  independently with zero risk of breaking each other.
- The persistence layer uses `SQLModelRepository` (SQLite) — changes were limited to db.py and the
  entry points. maze.py was untouched.
- The maze generation algorithm can be completely rewritten without touching
  persistence code.

---

## P0 (Critical) Tests — Definition of "Done"

The walking skeleton is **done** when ALL of the following pass. These are
the minimum viable tests that prove the three modules integrate correctly.

### P0-MAZE: Domain Logic Works

| #  | Test ID | Description                                              |
|----|---------|----------------------------------------------------------|
| 1  | M-01    | Position equality (value semantics)                       |
| 2  | M-11    | Maze start is on a grid edge                              |
| 3  | M-12    | Maze exit is on a different grid edge                     |
| 4  | M-20    | can_move True for passage (all passages are gated)        |
| 5  | M-21    | can_move False for wall                                   |
| 6  | M-24    | move returns correct new Position                         |
| 7  | M-25    | move raises ValueError for wall                           |
| 8  | M-30    | is_gated True for every passage                           |
| 9  | M-31    | is_gated True for all traversable directions from a cell  |
| 10 | M-50    | Path exists from start to exit                            |
| 11 | M-51    | Every passage on every path is gated (no free moves)      |

### P0-DB: Persistence Works

| #  | Test ID | Description                                              |
|----|---------|----------------------------------------------------------|
| 12 | D-01    | GameStateRow save/load round-trip                         |
| 13 | D-02    | load_game returns None for unknown player                 |
| 14 | D-10    | ScoreRow save then appears in high scores                 |
| 15 | D-11    | High scores sorted descending                             |
| 16 | D-20    | get_question by ID                                        |
| 17 | D-22    | get_random_question returns a question                    |
| 18 | D-30    | Data survives object re-creation                          |
| 19 | D-31    | Missing file handled gracefully                           |

### P0-INTEGRATION: Modules Work Together

| #  | Test ID | Description                                              |
|----|---------|----------------------------------------------------------|
| 20 | G-01    | New game places player at maze start                      |
| 21 | G-03    | resume_game reconstructs Position from DB ints            |
| 22 | G-11    | Wall blocks movement                                      |
| 23 | G-20    | Any passage triggers question (no immediate move)         |
| 24 | G-21    | Correct answer moves player through passage               |
| 25 | G-22    | Wrong answer keeps player in place                        |
| 26 | G-23    | Score increases on correct answer                         |
| 27 | G-30    | Reaching exit triggers victory                            |
| 28 | G-40    | Save/load round-trip preserves Position exactly           |
| 29 | G-42    | Round-tripped Position works with maze operations         |

**Total P0 tests: 29**

A passing run of all 29 means:
- The maze is navigable and every passage is gated with a trivia question
- Persistence stores and retrieves data without corruption
- Position survives the domain→primitives→domain round-trip
- The game loop handles trivia questions at every move, victory, and save/load

---

## File Structure (Walking Skeleton)

```
project/
├── maze.py                          # Module 1: Pure domain logic
├── db.py                            # Module 2: Persistence (SQLite via SQLModel)
├── main.py                          # Module 3: Game orchestration & CLI entry point
├── view.py                          # Module 4: CLI presentation (all print/input)
├── pygame_3d.py                     # Module 5: First-person raycasting 3D (pygame)
├── game_data.db                     # Runtime: SQLite database (auto-created)
├── questions.json                   # Seed data: Harry Potter trivia questions
├── tests/
│   ├── pytest.ini                   # Pytest config (pythonpath = .)
│   ├── test_maze.py                 # maze.py contract tests (M-xx)
│   ├── test_db.py                   # db.py / SQLModelRepository tests (D-xx, S-xx)
│   ├── test_engine_integration.py   # Full-stack integration tests (EI-xx)
│   ├── test_view.py                 # view.render_map tests (VW-xx)
│   ├── test_cli_map_visibility.py   # Fog-of-war CLI tests (FW-xx)
│   ├── test_question_bank.py        # Question bank tests (QB-xx)
│   └── test_repo_sqlite.py         # SQLite repo tests
├── Docs/
│   ├── interfaces.md                # Architecture & interface document
│   ├── interface-tests.md           # Test specifications
│   ├── game_concept.md              # Original game concept
│   ├── RUNBOOK.md                   # This file
│   └── Sample HP Trivia Questions   # Sample question data
└── requirements.txt                 # pytest, sqlmodel, pygame-ce
```

---

## Development Order

The modules can be developed in parallel, but this is the recommended
order for a solo developer:

### Phase 1: Foundation (can be parallel)

1. **maze.py** — Implement Position, Direction, Cell, Maze with DFS
   recursive backtracker generation. Run tests M-01 through M-61.

2. **db.py** — Implement Row dataclasses, Protocols, and SQLModelRepository.
   Run tests D-01 through D-31.

### Phase 2: Integration

3. **main.py** — Implement Player, QuizMazeGame, and the game loop.
   Wire maze.py and db.py together. Run tests G-01 through G-52.

### Phase 3: Content

4. **questions.json** — Author 20+ Harry Potter trivia questions (every
   passage requires a unique question per playthrough, so the pool must
   be large enough to cover the longest path).
   Categories: spells, characters, potions, creatures, locations.

### Phase 4: Polish

5. Add narrative flavor text (Forbidden Forest atmosphere).
6. Improve the CLI display (ASCII maze rendering).
7. Error handling and edge cases.

---

## Persistence: SQLModelRepository

Both entry points (`main.py` and `pygame_3d.py`) use `SQLModelRepository`
backed by SQLite (`game_data.db`).

Questions are seeded automatically from `questions.json` via
`seed_questions_if_empty()` on first run. The `exclude` list passed to
`get_random_question()` ensures only correctly-answered questions are
filtered out — wrong answers do not consume the question pool.

---

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run only P0 tests (using pytest markers)
pytest tests/ -v -m p0
```

### Entry Points

The game ships with **two** front-ends. Both share the same `QuizMazeGame`
engine from `main.py` and the same question pool from `questions.json`.

```bash
# 1. CLI — text-based terminal interface (view.py handles all I/O)
python main.py

# 2. First-person 3D — raycasting renderer (pure pygame, no extra libs).
python pygame_3d.py
```

#### `pygame_3d.py` controls

| Key / Input             | Action                              |
|-------------------------|-------------------------------------|
| Mouse movement          | Look left / right                   |
| Left / Right arrows     | Rotate view (keyboard)              |
| Up arrow / W            | Move forward (smooth walk)          |
| A / D                   | Strafe left / right                 |
| 1  2  3  4              | Answer a pending gate question      |
| N                       | Toggle music on / off               |
| Ctrl+S                  | Save game                           |
| Tab                     | View high-score table               |
| M                       | Toggle minimap                      |
| ESC                     | Save and quit                       |

#### Main menu

| Input                   | Action                              |
|-------------------------|-------------------------------------|
| Type name + Enter       | Start / resume game                 |
| Left / Right arrows     | Change maze size (3x3 / 5x5 / 7x7) |
| Click ◄ / ► buttons     | Change maze size (mouse)            |
| Click ♫ Music button    | Toggle background music             |

#### Gameplay notes

- **Fog**: Unvisited passages are covered in shimmering enchanted fog.
  Answering a question correctly dissolves the fog permanently.
- **Exit**: The exit cell has a golden floor tint visible from any angle.
- **Lives**: Three hearts (courage). Wrong answers cost one heart.
  Losing all hearts ends the run.
- **Questions**: Only correct answers consume questions from the pool.
  Wrong answers do not drain the question bank.
- **Movement**: Walking uses smooth ease-out interpolation (no teleporting).
- **Status panel**: "Marauder's Map" shows house points, spells cast,
  open passages, and a narrative compass hint toward Hogwarts.
- **Messages**: "Owl Post" displays narrative game events (no coordinates).

---

## Quick Reference: The Position Boundary

The single most important architectural decision in this project:

```
┌─────────────┐         ┌──────────────┐         ┌────────────┐
│   maze.py   │         │   main.py    │         │   db.py    │
│             │         │  (boundary)  │         │            │
│  Position   │◄────────│  translate   │────────►│ player_row │
│  (row, col) │         │  both ways   │         │ player_col │
│             │         │              │         │   (ints)   │
└─────────────┘         └──────────────┘         └────────────┘

  Domain object     Decompose on save       Persistence
  (frozen, typed,   Reconstruct on load     primitives
   hashable)                                (plain ints)
```

If you're ever unsure whether a change is correct, ask: "Does Position
ever appear in db.py?" If yes, the architecture is broken.
