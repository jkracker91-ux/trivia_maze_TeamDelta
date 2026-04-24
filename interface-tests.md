# Quiz Maze Game — Interface Contract Tests

Each module can be developed independently. A module is **accepted** when it
passes every test listed below. Tests are grouped by module and tagged by
priority: **P0** (must pass for walking skeleton) or **P1** (important but can
follow).

---

## Module 1: `maze.py` Tests

These tests use ONLY maze.py types. No db.py imports.

All maze tests are **topology-agnostic**: they verify structural invariants
that hold for any DFS-generated maze, not a hardcoded layout. The `maze`
fixture is parameterized across multiple sizes (3×3, 4×4, 5×5).

### Position Value Object

| ID     | Test                                          | Priority |
|--------|-----------------------------------------------|----------|
| M-01   | Two Positions with same (row, col) are equal  | P0       |
| M-02   | Position is hashable (can be used in sets)     | P0       |
| M-03   | Position is immutable (frozen dataclass)       | P0       |

```python
# M-01
assert Position(0, 0) == Position(0, 0)
assert Position(0, 0) != Position(1, 0)

# M-02
s = {Position(0, 0), Position(0, 0)}
assert len(s) == 1

# M-03
p = Position(0, 0)
with pytest.raises(AttributeError):
    p.row = 1
```

### Maze Construction

| ID     | Test                                                      | Priority |
|--------|-----------------------------------------------------------|----------|
| M-10   | Maze reports correct width and height                      | P0       |
| M-11   | Maze start is on a grid edge                               | P0       |
| M-12   | Maze exit is on a different grid edge                      | P0       |
| M-13   | is_exit returns True only for exit position                | P0       |

```python
maze = generate_maze(width=4, height=4)

# M-10
assert maze.width >= 3
assert maze.height >= 3

# M-11 — start is on an edge
s = maze.start
assert s.row == 0 or s.row == maze.height - 1 or s.col == 0 or s.col == maze.width - 1

# M-12 — exit is on a different edge
e = maze.exit_pos
assert e.row == 0 or e.row == maze.height - 1 or e.col == 0 or e.col == maze.width - 1
assert maze.start != maze.exit_pos

# M-13
assert maze.is_exit(maze.exit_pos) is True
assert maze.is_exit(maze.start) is False
```

### Movement & Walls

| ID     | Test                                                          | Priority |
|--------|---------------------------------------------------------------|----------|
| M-20   | can_move returns True for a passage                            | P0       |
| M-21   | can_move returns False for wall                               | P0       |
| M-23   | can_move returns False for boundary directions                | P0       |
| M-24   | move returns a different Position for valid direction          | P0       |
| M-25   | move raises ValueError for wall / out-of-bounds               | P0       |
| M-26   | move is symmetric — if A→B exists then B→A exists            | P0       |

```python
# Tests find passages/walls dynamically — no hardcoded positions.

# M-20 — find any passage in the maze
pos, d = find_passage(maze)
assert maze.can_move(pos, d) is True

# M-21 — find any wall in the maze
pos, d = find_wall(maze)
assert maze.can_move(pos, d) is False

# M-23 — corners always have boundary walls
assert maze.can_move(Position(0, 0), Direction.NORTH) is False
assert maze.can_move(Position(0, 0), Direction.WEST) is False

# M-24 — moving through a passage yields a neighbor
pos, d = find_passage(maze)
neighbor = maze.move(pos, d)
assert isinstance(neighbor, Position)
assert neighbor != pos

# M-25
pos, d = find_wall(maze)
with pytest.raises(ValueError):
    maze.move(pos, d)

# M-26 — check every passage in the maze
for r in range(maze.height):
    for c in range(maze.width):
        pos = Position(r, c)
        for d in maze.get_open_directions(pos):
            neighbor = maze.move(pos, d)
            assert maze.can_move(neighbor, opposite(d))
```

### Gate Detection

| ID     | Test                                                          | Priority |
|--------|---------------------------------------------------------------|----------|
| M-30   | is_gated returns True for every passage                       | P0       |
| M-32   | is_gated returns False for a wall (no passage)                | P0       |
| M-33   | Gates are symmetric — if A→B is gated then B→A is too         | P0       |

```python
# M-30 — every passage in the entire maze is gated
for r in range(maze.height):
    for c in range(maze.width):
        pos = Position(r, c)
        for d in maze.get_open_directions(pos):
            assert maze.is_gated(pos, d) is True

# M-32 — wall: no passage at all
pos, d = find_wall(maze)
assert maze.is_gated(pos, d) is False

# M-33 — gate symmetry
for r in range(maze.height):
    for c in range(maze.width):
        pos = Position(r, c)
        for d in maze.get_open_directions(pos):
            neighbor = maze.move(pos, d)
            assert maze.is_gated(neighbor, opposite(d)) is True
```

### Cell Query

| ID     | Test                                                        | Priority |
|--------|-------------------------------------------------------------|----------|
| M-40   | get_cell returns Cell with correct position                  | P0       |
| M-41   | get_cell open_directions matches can_move for all directions | P1       |
| M-42   | gated_directions equals open_directions (every passage gated)| P0       |

```python
# M-40 — every cell in the grid
for r in range(maze.height):
    for c in range(maze.width):
        pos = Position(r, c)
        assert maze.get_cell(pos).position == pos

# M-41 — open_directions consistent with can_move
for r in range(maze.height):
    for c in range(maze.width):
        pos = Position(r, c)
        cell = maze.get_cell(pos)
        for d in Direction:
            assert (d in cell.open_directions) == maze.can_move(pos, d)

# M-42 — every passage is gated, so gated == open
for r in range(maze.height):
    for c in range(maze.width):
        cell = maze.get_cell(Position(r, c))
        assert cell.gated_directions == cell.open_directions
```

### Path & Structure Guarantee

| ID     | Test                                                               | Priority |
|--------|--------------------------------------------------------------------|----------|
| M-50   | At least one path exists from start to exit (DFS reachability)     | P0       |
| M-51   | Every passage is gated — no free moves exist                       | P0       |
| M-60   | Perfect maze: exactly N−1 passages for N cells (spanning tree)     | P0       |
| M-61   | Start and exit are distinct                                         | P0       |

```python
# M-50 — DFS from start, ignoring gates, must reach exit
assert dfs_reachable(maze, maze.start, maze.exit_pos) is True

# M-51 — every passage is gated, so skipping gates means
# the player cannot move at all from start
assert dfs_reachable_no_gates(maze, maze.start, maze.exit_pos) is False

# M-60 — spanning tree property
total_cells = maze.width * maze.height
passage_count = sum(
    len(maze.get_open_directions(Position(r, c)))
    for r in range(maze.height)
    for c in range(maze.width)
)
assert passage_count // 2 == total_cells - 1

# M-61
assert maze.start != maze.exit_pos
```

### Fog of War — `get_visible_cells()` (NEW)

| ID     | Test                                                                  | Priority |
|--------|-----------------------------------------------------------------------|----------|
| M-70   | `get_visible_cells({start})` returns exactly 1 cell                   | P0       |
| M-71   | `get_visible_cells(all_positions)` returns all cells in the grid      | P0       |
| M-72   | `get_visible_cells(set())` returns empty dict                         | P0       |
| M-73   | Returned cells have correct `open_directions` and `gated_directions`  | P0       |
| M-74   | Out-of-bounds positions in visited set are silently ignored            | P1       |

```python
# M-70
result = maze.get_visible_cells({maze.start})
assert len(result) == 1
assert maze.start in result
assert result[maze.start].position == maze.start

# M-71
all_pos = {Position(r, c) for r in range(maze.height) for c in range(maze.width)}
result = maze.get_visible_cells(all_pos)
assert len(result) == maze.width * maze.height

# M-72
result = maze.get_visible_cells(set())
assert result == {}

# M-73
result = maze.get_visible_cells({maze.start})
cell = result[maze.start]
assert cell.open_directions == frozenset(maze.get_open_directions(maze.start))
assert cell.gated_directions == cell.open_directions

# M-74
oob = {Position(-1, -1), Position(999, 999), maze.start}
result = maze.get_visible_cells(oob)
assert len(result) == 1
assert maze.start in result
```

---

## Module 2: `db.py` Tests

These tests use ONLY db.py types. No maze.py imports.

### GameRepository — Save / Load Round-Trip

| ID     | Test                                                          | Priority |
|--------|---------------------------------------------------------------|----------|
| D-01   | save_game then load_game returns identical GameStateRow        | P0       |
| D-02   | load_game returns None for nonexistent player                  | P0       |
| D-03   | save_game overwrites previous save for same player             | P0       |
| D-04   | delete_game removes saved game                                 | P0       |
| D-05   | delete_game on nonexistent player does not raise               | P1       |

```python
# D-01
repo = SQLModelRepository(db_url=f"sqlite:///{tmp_path / 'test.db'}")
state = GameStateRow(
    player_name="Harry",
    player_row=1,
    player_col=2,
    score=10,
    questions_answered=["q1", "q2"],
    visited_cells=[(0, 0), (1, 2)],
    maze_id="generated",
    timestamp="2026-02-17T12:00:00",
)
repo.save_game(state)
loaded = repo.load_game("Harry")
assert loaded == state

# D-02
assert repo.load_game("Draco") is None

# D-03
state2 = GameStateRow(
    player_name="Harry",
    player_row=2, player_col=1,
    score=20, questions_answered=["q1", "q2", "q3"],
    visited_cells=[(0, 0), (1, 2), (2, 1)],
    maze_id="generated", timestamp="2026-02-17T12:05:00",
)
repo.save_game(state2)
assert repo.load_game("Harry") == state2

# D-04
repo.delete_game("Harry")
assert repo.load_game("Harry") is None
```

### ScoreRepository — Leaderboard

| ID     | Test                                                       | Priority |
|--------|------------------------------------------------------------|----------|
| D-10   | save_score then get_high_scores includes the score          | P0       |
| D-11   | get_high_scores returns scores sorted descending by score   | P0       |
| D-12   | get_high_scores respects the limit parameter                | P0       |
| D-13   | get_player_scores returns only that player's scores         | P0       |
| D-14   | get_high_scores returns empty list when no scores exist     | P1       |

```python
# D-10, D-11, D-12
repo = SQLModelRepository(db_url=f"sqlite:///{tmp_path / 'test.db'}")
for name, score in [("Harry", 30), ("Ron", 50), ("Hermione", 40)]:
    repo.save_score(ScoreRow(
        player_name=name, score=score, total_questions=5,
        correct_answers=score // 10, completed=True,
        timestamp="2026-02-17T12:00:00",
    ))

top = repo.get_high_scores(limit=2)
assert len(top) == 2
assert top[0].player_name == "Ron"
assert top[1].player_name == "Hermione"

# D-13
harry_scores = repo.get_player_scores("Harry")
assert all(s.player_name == "Harry" for s in harry_scores)
```

### QuestionRepository — Trivia Questions

| ID     | Test                                                         | Priority |
|--------|--------------------------------------------------------------|----------|
| D-20   | get_question returns correct QuestionRow by ID                | P0       |
| D-21   | get_question returns None for unknown ID                      | P0       |
| D-22   | get_random_question returns a QuestionRow                     | P0       |
| D-23   | get_random_question with exclude list skips those IDs         | P0       |
| D-24   | get_random_question returns None when all questions excluded  | P1       |
| D-25   | get_all_questions returns every question                      | P1       |

```python
# D-20
repo = SQLModelRepository(db_url=f"sqlite:///{tmp_path / 'test.db'}")
# (assume test fixture seeds some questions)
q = repo.get_question("q1")
assert q is not None
assert q.question_id == "q1"

# D-21
assert repo.get_question("nonexistent") is None

# D-23
q = repo.get_random_question(exclude=["q1", "q2"])
assert q is not None
assert q.question_id not in ["q1", "q2"]
```

### Persistence Durability

| ID     | Test                                                            | Priority |
|--------|-----------------------------------------------------------------|----------|
| D-30   | Data survives object recreation (new SQLModelRepository, same DB) | P0       |
| D-31   | Empty/new database produces empty collections, not errors         | P0       |

```python
# D-30
db_url = f"sqlite:///{tmp_path / 'test.db'}"
repo1 = SQLModelRepository(db_url=db_url)
repo1.save_score(score_row)
del repo1

repo2 = SQLModelRepository(db_url=db_url)
scores = repo2.get_high_scores()
assert len(scores) == 1

# D-31
fresh = SQLModelRepository(db_url=f"sqlite:///{tmp_path / 'empty.db'}")
assert fresh.get_high_scores() == []
assert fresh.load_game("nobody") is None
```

### SQLModelRepository — SQLite Persistence (NEW)

| ID     | Test                                                                       | Priority |
|--------|----------------------------------------------------------------------------|----------|
| S-01   | SQLModelRepository creates themed tables on init                           | P0       |
| S-02   | save_game / load_game round-trip with visited_cells                        | P0       |
| S-03   | Question table stores and retrieves choices_json correctly                  | P0       |
| S-04   | get_random_question exclude list works with SQLModel queries               | P0       |
| S-05   | get_high_scores returns scores sorted descending (SQL ORDER BY)            | P0       |
| S-06   | Two SQLModelRepository instances on same DB do not corrupt data            | P1       |
| S-07   | Empty database returns empty collections (not errors)                       | P0       |
| S-08   | save_game with visited_cells persists and round-trips                       | P0       |

```python
# S-01 — themed tables exist after init
from sqlalchemy import inspect
repo = SQLModelRepository(db_url=f"sqlite:///{tmp_path / 'test.db'}")
inspector = inspect(repo._engine)
table_names = inspector.get_table_names()
assert "enchanted_questions" in table_names
assert "house_scores" in table_names
assert "game_chronicles" in table_names

# S-02 — visited_cells round-trip
state = GameStateRow(
    player_name="Harry",
    player_row=1, player_col=2,
    score=10, questions_answered=["q1"],
    visited_cells=[(0, 0), (1, 2)],
    maze_id="m1", timestamp="t1",
)
repo.save_game(state)
loaded = repo.load_game("Harry")
assert loaded is not None
assert loaded.visited_cells == [(0, 0), (1, 2)]

# S-03 — choices round-trip
q = QuestionRow("q1", "Test?", ["A", "B", "C", "D"], 2, "spells")
repo.load_questions([q])
result = repo.get_question("q1")
assert result is not None
assert result.choices == ["A", "B", "C", "D"]
assert result.correct_index == 2

# S-05 — sorted descending
for name, score in [("A", 30), ("B", 10), ("C", 50)]:
    repo.save_score(ScoreRow(name, score, 1, 1, True, "t"))
assert [s.score for s in repo.get_high_scores(10)] == [50, 30, 10]

# S-07 — empty database
fresh = SQLModelRepository(db_url=f"sqlite:///{tmp_path / 'empty.db'}")
assert fresh.get_all_questions() == []
assert fresh.load_game("anyone") is None
assert fresh.get_high_scores() == []
```

---

## Module 3: `main.py` Tests (Integration)

These tests import from BOTH maze.py and db.py, verifying that main.py
correctly bridges the two.

### Game Initialization

| ID     | Test                                                       | Priority |
|--------|------------------------------------------------------------|----------|
| G-01   | start_new_game places player at maze start position        | P0       |
| G-02   | start_new_game returns opening narrative (non-empty string) | P0       |
| G-03   | resume_game reconstructs Position from DB primitives        | P0       |

```python
# G-01
game = QuizMazeGame("Harry", maze, game_repo, score_repo, question_repo)
narrative = game.start_new_game()
assert game.player.position == maze.start

# G-03 — The critical DB boundary test
# Save a position somewhere in the grid, then reconstruct it
game_repo.save_game(GameStateRow(
    player_name="Harry", player_row=1, player_col=1,
    score=10, questions_answered=[],
    visited_cells=[(0, 0), (1, 1)],
    maze_id="generated",
    timestamp="2026-02-17T12:00:00",
))
game.resume_game()
assert game.player.position == Position(1, 1)
assert isinstance(game.player.position, Position)
```

### Movement — Walls & Invalid Input

| ID     | Test                                                      | Priority |
|--------|-----------------------------------------------------------|----------|
| G-11   | Moving into wall returns "blocked" narrative, position unchanged | P0 |
| G-12   | Invalid direction string returns error narrative            | P0       |

```python
# G-11 — move into a wall from start
game = make_test_game()
start = game.player.position
wall_dir = find_wall_from(maze, start)
result = game.move(wall_dir)
assert game.player.position == start

# G-12
result = game.move("sideways")
assert game.player.position == start
```

### Movement — Question Flow (Every Passage)

Every passage is gated with a Harry Potter trivia question. Moving in any
valid direction triggers a question; the player never moves for free.

| ID     | Test                                                                  | Priority |
|--------|-----------------------------------------------------------------------|----------|
| G-20   | Moving in any valid direction returns question text instead of moving | P0       |
| G-21   | Correct answer moves player through the passage                       | P0       |
| G-22   | Wrong answer keeps player in place, returns "incorrect" narrative     | P0       |
| G-23   | Score increases on correct answer                                      | P0       |
| G-24   | Score does not change on wrong answer                                  | P0       |
| G-25   | Answered question ID is added to questions_answered list               | P0       |

```python
# G-20
game = make_test_game()
start = game.player.position
open_dir = find_open_dir_from(maze, start)
result = game.move(open_dir)
assert game.player.position == start        # didn't move yet
assert "?" in result                        # question text

# G-21
result = game.answer_question(correct_choice_index)
assert game.player.position != start        # moved through!

# G-22
game = make_test_game()
start = game.player.position
open_dir = find_open_dir_from(maze, start)
game.move(open_dir)
result = game.answer_question(wrong_choice_index)
assert game.player.position == start        # still here

# G-23
game = make_test_game()
old_score = game.player.score
open_dir = find_open_dir_from(maze, game.player.position)
game.move(open_dir)
game.answer_question(correct_choice_index)
assert game.player.score > old_score
```

### Victory Condition

| ID     | Test                                                    | Priority |
|--------|---------------------------------------------------------|----------|
| G-30   | Reaching exit position returns victory narrative         | P0       |
| G-31   | Victory saves score to ScoreRepository                   | P0       |
| G-32   | Victory score record has completed=True                  | P0       |

```python
# G-30 — Place player one move from exit
neighbor, direction = find_neighbor_of_exit(maze)
game = make_test_game_at(neighbor)
result = game.move(direction)
game.answer_question(correct_choice_index)
assert maze.is_exit(game.player.position)

# G-31
scores = score_repo.get_high_scores()
assert len(scores) >= 1
assert scores[-1].player_name == "Harry"

# G-32
assert scores[-1].completed is True
```

### Save / Load Round-Trip (Position Integrity)

| ID     | Test                                                              | Priority |
|--------|-------------------------------------------------------------------|----------|
| G-40   | save_game then resume_game restores exact player position          | P0       |
| G-41   | save_game then resume_game restores score and questions_answered   | P0       |
| G-42   | Position object is fully functional after round-trip               | P0       |

```python
# G-40, G-41, G-42 — The full round-trip integration test
game1 = make_test_game()
open_dir = find_open_dir_from(maze, game1.player.position)
game1.move(open_dir)
game1.answer_question(correct_choice_index)
moved_pos = game1.player.position
game1.save_game()

game2 = QuizMazeGame("Harry", maze, game_repo, score_repo, question_repo)
game2.resume_game()

assert game2.player.position == moved_pos
assert game2.player.score == game1.player.score
assert game2.player.questions_answered == game1.player.questions_answered

# G-42 — The reconstructed Position works with the maze
assert len(maze.get_open_directions(game2.player.position)) > 0
```

### Status & Display

| ID     | Test                                               | Priority |
|--------|----------------------------------------------------|----------|
| G-50   | get_status returns non-empty string                 | P1       |
| G-51   | get_status mentions available directions            | P1       |
| G-52   | get_status mentions current score                   | P1       |

---

## Fog of War Integration Tests (FW-xx) — NEW

These tests verify that Fog of War tracking is correctly wired through
the full stack: maze.py visibility → main.py player state → db.py persistence.

| ID     | Test                                                                     | Priority |
|--------|--------------------------------------------------------------------------|----------|
| FW-01  | `start_new_game()` initializes `visited_cells` with start position       | P0       |
| FW-02  | Correct answer adds new position to `visited_cells`                      | P0       |
| FW-03  | Wrong answer does NOT add the target position to `visited_cells`         | P0       |
| FW-04  | `get_status()` output contains `??` for unvisited cells                  | P0       |
| FW-05  | `get_status()` shows player marker `@` at current position               | P0       |
| FW-06  | `save_game` persists `visited_cells` through round-trip                  | P0       |
| FW-07  | `resume_game` reconstructs `visited_cells` from DB                       | P0       |
| FW-08  | Free passage (questions exhausted) still adds to `visited_cells`         | P1       |

```python
# FW-01 — start cell is in visited_cells
game = make_test_game()
assert game._maze.start in game.player.visited_cells

# FW-02 — correct answer reveals the new cell
game = make_test_game()
start_pos = game.player.position
direction = first_open_direction(game._maze, start_pos)
game.move(direction.value)
pending = game._pending_question
game.answer_question(pending.correct_index + 1)
new_pos = game.player.position
assert new_pos in game.player.visited_cells

# FW-03 — wrong answer does NOT reveal
game = make_test_game()
start_pos = game.player.position
direction = first_open_direction(game._maze, start_pos)
game.move(direction.value)
pending = game._pending_question
wrong = next(i for i in range(1, 5) if (i - 1) != pending.correct_index)
game.answer_question(wrong)
target = game._maze.move(start_pos, direction)
assert target not in game.player.visited_cells

# FW-04 — unvisited cells show as ??
game = make_test_game()
status = game.get_status()
assert "??" in status

# FW-05 — player marker is visible
game = make_test_game()
status = game.get_status()
assert "@" in status

# FW-06 — visited_cells persist through save/load
game, repo = make_game_with_repo(tmp_path)
game.save_game()
state = repo.load_game(game.player.name)
assert state is not None
assert len(state.visited_cells) >= 1

# FW-07 — resume reconstructs visited_cells
game, repo = make_game_with_repo(tmp_path, "Ginny")
game.player.visited_cells = {Position(0, 0), Position(1, 1)}
game.save_game()
game2 = QuizMazeGame("Ginny", generate_maze(4, 4), repo, repo, repo)
game2.resume_game()
assert Position(0, 0) in game2.player.visited_cells
assert Position(1, 1) in game2.player.visited_cells

# FW-08 — free passage still tracks visited
game = make_test_game()
all_ids = [q.question_id for q in repo.get_all_questions()]
game.player.questions_answered = all_ids
start_pos = game.player.position
direction = first_open_direction(game._maze, start_pos)
game.move(direction.value)
if game.player.position != start_pos:
    assert game.player.position in game.player.visited_cells
```

---

---

## Test Fixture Requirements

Each module's test suite should provide:

| Fixture                          | Module   | Purpose                                          |
|----------------------------------|----------|--------------------------------------------------|
| `maze` (parameterized)           | maze.py  | `generate_maze()` at sizes 3×3, 4×4, 5×5        |
| `tmp_sqlmodel_repo()`            | db.py    | Returns SQLModelRepository with temp SQLite DB    |
| `seed_questions(repo)`           | db.py    | Loads 5+ Harry Potter trivia questions            |
| `make_test_game()`               | main.py  | Returns QuizMazeGame at maze start position       |
| `make_test_game_at(p)`           | main.py  | Returns QuizMazeGame with player at position p    |
| `make_game_with_repo(tmp_path)`  | main.py  | Returns (QuizMazeGame, repo) for persistence tests|

---

## Summary: Test Count by Module

| Module          | P0 Tests | P1 Tests | Total | Note                                   |
|-----------------|----------|----------|-------|----------------------------------------|
| maze.py         | 22       | 2        | 24    | Each test runs at 3 maze sizes (×3)    |
| db.py           | 18       | 4        | 22    | Includes S-01..S-08 for SQLModel       |
| main.py (EI)    | 14       | 3        | 17    | Integration tests                      |
| Fog of War (FW) | 7        | 1        | 8     | Fog of War integration tests           |
| **Total**       | **61**   | **10**   | **71**|                                        |
