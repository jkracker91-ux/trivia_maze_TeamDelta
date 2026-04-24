# Handoff Document — Forbidden Forest Quiz Maze

Use this document to pick up work on the project after a break. It summarizes the codebase, recent changes, and where to look next.

---

## Project summary

**S504_TriviaMaze_TeamDelta** is a Harry Potter–themed trivia dungeon: the player navigates the Forbidden Forest (a randomly generated maze), answers trivia at locked gates, and tries to reach the exit without losing three “courage” lives.

- **Entry point for 3D play:** `python pygame_3d.py`
- **CLI entry point:** `python main.py`
- **Stack:** Python, pygame (3D raycasting), SQLite via SQLModel (`db.py`)

See [README.md](README.md) and [Docs/RUNBOOK.md](Docs/RUNBOOK.md) for setup, controls, and architecture.

---

## Recent changes (session summary)

The following was implemented in recent work:

1. **Background music (Forbidden Forest MP3)**  
   - BGM is the file `forbidden-forest-theme-complete.mp3`, loaded from (in order):  
     - `S504_TriviaMaze_TeamDelta/assets/forbidden-forest-theme-complete.mp3`  
     - Fallback: `c:\Users\jkrac\Downloads\forbidden-forest-theme-complete.mp3`  
   - Uses `pygame.mixer.music`; plays when entering PLAYING state, loops, continues during question overlays, stops on WIN/NO_HEARTS.  
   - If the file is missing, no BGM plays (no procedural fallback).  
   - **File:** [pygame_3d.py](pygame_3d.py) (paths, `_resolve_bgm_mp3_path()`, `bgm_is_music_file`, and all BGM control points).

2. **Music toggle**  
   - Music is toggled **only** by the **“♫ Music: ON/OFF”** button (menu and in-game status panel).  
   - The **N** key no longer toggles music; that binding was removed.  
   - **File:** [pygame_3d.py](pygame_3d.py) (event handlers and controls bar text).

3. **Random question gates**  
   - Not every passage has a trivia question. Gates are placed randomly.  
   - **Maze:** [maze.py](maze.py) — `generate_maze(..., gate_fraction=0.5)`. By default 50% of passages are gated; the rest can be crossed freely.  
   - **Game logic:** [main.py](main.py) — `move()` checks `is_gated()`; if the passage is not gated, the player moves without a question and sees “The passage opens freely. You step through.”  
   - **Tests:** [tests/test_maze.py](tests/test_maze.py) fixture uses `gate_fraction=1.0` so existing “all gated” contract tests still pass.

---

## Key files and roles

| File / folder      | Purpose |
|--------------------|--------|
| `pygame_3d.py`     | 3D entry point: raycasting, BGM, music toggle, UI, calls `main.QuizMazeGame` and `maze.generate_maze`. |
| `main.py`          | Game engine: move, answer_question, save/load; uses `maze.Maze` and `db` repos. |
| `maze.py`          | Maze domain: `Maze`, `Position`, `Direction`, `generate_maze(width, height, gate_fraction=0.5)`. |
| `db.py`            | Persistence: SQLModel/SQLite, game state, questions, high scores. |
| `view.py`          | CLI presentation (used by `main.py` CLI, not by `pygame_3d.py`). |
| `questions.json`   | Trivia question bank (used if DB is empty). |
| `Docs/RUNBOOK.md`  | Controls, architecture, run instructions. |
| `Docs/interfaces.md` | API/interface notes. |

---

## How to run and test

```bash
cd "c:\Users\jkrac\OneDrive\Documents\GC-SDE\TCSS 503\S504_TriviaMaze_TeamDelta"
pip install -r requirements.txt

# 3D game
python pygame_3d.py

# Tests (PowerShell: use ; instead of &&)
python -m pytest tests/ -v --tb=short
python -m pytest tests/test_maze.py -v
```

For BGM to play, place `forbidden-forest-theme-complete.mp3` in the project under `assets/` or at the fallback path above.

---

## Possible next steps

- **Tune gate density:** In `maze.py`, `generate_maze(..., gate_fraction=0.5)`. Callers (e.g. `pygame_3d.py`’s `_start_session` → `generate_maze(maze_w, maze_h)`) could pass a different `gate_fraction` or a value from a menu.  
- **Music:** If you add a different BGM or multiple tracks, extend the path list and/or `pygame.mixer.music` logic in `pygame_3d.py`.  
- **Bug:** If the player starts with music off and later turns it on via the button, BGM might not start until the next time they enter PLAYING (e.g. after win/restart). Fix: when toggling music on during PLAYING, call `pygame.mixer.music.play(loops=-1)` if nothing is playing.  
- **Docs:** Update [README.md](README.md) / [Docs/RUNBOOK.md](Docs/RUNBOOK.md) to mention random gates and “music: toggle button only” if not already there.

---

## Environment and paths

- **Project path:** `c:\Users\jkrac\OneDrive\Documents\GC-SDE\TCSS 503\S504_TriviaMaze_TeamDelta`  
- **BGM fallback path (current):** `c:\Users\jkrac\Downloads\forbidden-forest-theme-complete.mp3`  
- **DB path:** `game_data.db` in the project directory (see `_DB_URL` in `pygame_3d.py`).

---

*Last handoff: session that added Forbidden Forest BGM, button-only music toggle, and random gate placement.*
