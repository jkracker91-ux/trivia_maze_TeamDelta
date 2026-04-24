# S504_TriviaMaze_TeamDelta

A Harry Potter-themed maze game where a Hogwarts student must navigate the
Forbidden Forest by answering trivia questions at every passage. Built with
strict separation of concerns: `maze.py` (domain), `db.py` (persistence),
`main.py` (orchestration / CLI), `view.py` (CLI presentation), and a
first-person 3D front-end powered by pygame.

## How to Play

```bash
pip install -r requirements.txt

# CLI (terminal)
python main.py

# First-person 3D — raycasting corridor view (pure pygame, no extra libs)
python pygame_3d.py
```

Background music plays automatically using a built-in procedural ambient loop — no extra files needed. For a higher-quality soundtrack, place `forbidden-forest-theme-complete.mp3` in the `assets/` folder and it will be used instead.

See `Docs/RUNBOOK.md` for full controls and architecture details.

## Docker

Prebuilt image on Docker Hub: **`lemonbirdyy/maze:v1`**

```bash
docker pull lemonbirdyy/maze:v1
docker run --rm -it lemonbirdyy/maze:v1
```

Build the image locally:

```bash
cd Dockerfiles && docker build -t maze .
```

Run the local image:

```bash
docker run --rm -it maze
```

## Architecture

| Module          | Role                                                    |
|-----------------|---------------------------------------------------------|
| `maze.py`       | Pure domain logic (imports nothing from project)        |
| `db.py`         | Persistence layer (imports nothing from project)        |
| `main.py`       | Orchestration — sole bridge between maze & db           |
| `view.py`       | CLI presentation — sole owner of `print()`/`input()`    |
| `pygame_3d.py`  | First-person raycasting 3D front-end via pygame         |

The pygame front-end reuses `QuizMazeGame` from `main.py` for all game logic
and `SQLModelRepository` from `db.py` for persistence. It bypasses `view.py`
entirely, handling rendering through pygame surfaces.

## Key Features (3D Mode)

- First-person raycasting renderer with mouse look and smooth movement
- **Bobbing wand animation** — a glowing wizard wand visible in the lower-right corner, bobs and sways while walking (classic FPS-style character presence)
- **Atmospheric forest fog** — animated ground mist rising from the floor, 10 drifting wisps, ceiling mist, and distance haze that fades walls into green-grey fog
- **Thunder & lightning storm** — random multi-flicker lightning flashes with a blue-white screen overlay and a synthesized thunder crack + rumble sound
- **Procedural background music** — dark ambient loop (bass drone, shimmer, descending A-minor melody) plays automatically; place `forbidden-forest-theme-complete.mp3` in `assets/` for the full MP3 track
- **Music toggle** — clickable "♫ Music: ON/OFF" button in menu and status panel
- **SFX toggle** — separate "SFX: ON/OFF" button to independently mute all sound effects (footsteps, door, correct/wrong answers, thunder) while keeping music playing
- Enchanted fog on unvisited passages (dissolves after correct answer)
- Golden floor tint marks the exit cell
- Hogwarts-themed status panel ("Marauder's Map") with narrative compass
- **Random question gates** — ~50% of passages are gated by default; free passages let you through without trivia (`gate_fraction` tunable in `maze.py`)
- Selectable maze sizes (3x3, 5x5, 7x7) on the main menu
- Three lives system — wrong answers cost courage
- Minimap overlay, save/load, and high-score table


## Separation of Concerns

The codebase maintains strict boundaries between maze domain logic (`maze.py`)
and persistence (`db.py`): neither imports from the other, and `main.py` is the
sole translation layer for Position ↔ primitive conversion.

## How We Split the Work

Sam implemented the base game engine with pygame (the
raycasting 3D front-end), also he worked on main.py and integration test suite. Asia worked on maze.py and fog of war, then was polishing the game mechanics and and updating documentation to
reflect all changes. Justin was working on the db.py, contributed the initial game concept and design documents, sound/audio additions, and random gate placement across passages.


## AI Code Review & The Final Arbiter

AI was very helpful in finding the details we missed while merging different files, especially when it concerned tests. We missed a lot of small details, but with AI review they were quickly fixed. Also it was helpful in "standardizing" our word-usage across different files, so everything is consistent and works together nicely. For example, it noticed player.visited → player.visited_cells in main.py and test_engine_integration.py, or changing private to public attributes (game.\_player → game.player in test_cli_map_visibility.py)
