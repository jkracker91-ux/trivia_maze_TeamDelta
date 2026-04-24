# Justin's Harry Potter Trivia Maze Concept

## MVC (Model-View-Controller)

*   **Model**: `maze.py` (domain logic), `db.py` (persistence) — handle data and logic
*   **View**: `view.py` (CLI), `pygame_3d.py` (first-person 3D via pygame)
*   **Controller**: `main.py` (orchestration — connects Model and View)

## Section A: The Theme (The Hook)

The player is a student at Hogwarts School of Witchcraft and Wizardry. You are lost in the Forbidden Forest and attempting to make your way back to the castle. **Every** passage in the maze is sealed with a themed Harry Potter trivia question — the player must answer correctly to pass through any door. There are no free moves; the entire journey is a trivia gauntlet. Wrong answers keep the player in place, wasting precious time in the forest.

## Section B: The Test Strategy (QA & Algorithms)

We practice Test Driven Development (TDD). Describe specifically how we will verify the system works next week.

### The Happy Path
The player attempts to move in any direction. Since every passage is gated, the system presents a themed Harry Potter trivia question. The player answers correctly. The door unlocks, the player moves into the next room, and their score increases by 10 points. This repeats for every single move until the player reaches the castle.

### The Edge Case
The player attempts to move North into a solid wall (boundary of the maze). The system catches the invalid move request, prevents the player's coordinates from changing, and displays a "You cannot go that way" message.

### The Failure State
The external trivia API is unreachable or returns a corrupted response. The game catches the connection exception and seamlessly loads a default set of local backup questions so gameplay can continue without crashing.

### The Solvability Check (Algorithm Selection)

*   **Problem**: How do we ensure the randomly generated maze is solvable and the exit is reachable?
*   **Solution**: We will use **Depth-First Search (DFS)** to traverse the graph.
*   **Logic**: We will start at the player's starting position (0,0) and attempt to traverse to adjacent accessible rooms. We will mark visited rooms to avoid cycles. If the DFS traversal reaches the designated exit coordinate, the maze is valid. If the traversal completes without finding the exit, the maze is discarded and regenerated.

## Section C: The Architecture Map (Patterns)

Based on the lecture, map our game to the MVC pattern and any other patterns if they fit your design.

*   **Model**:
    *   `maze.py`: Generates the grid via DFS recursive backtracker, stores room connectivity (all passages gated), and validates moves. Pure domain — imports nothing from the project.
    *   `db.py`: Persistence layer backed by SQLite via SQLModel. Stores questions, scores, and saved game state. Imports nothing from the project.
*   **View**:
    *   `view.py`: CLI presentation — owns all `print()` and `input()` calls. Renders fog-of-war ASCII map.
    *   `pygame_3d.py`: First-person raycasting 3D front-end using pygame. Renders the maze as a Wolfenstein-style 3D corridor view with mouse look, smooth walking, minimap, and sound.
*   **Controller**:
    *   `main.py`: Orchestration layer and the sole bridge between `maze.py` and `db.py`. Handles all translation between domain objects (`Position`) and persistence primitives (`player_row`, `player_col`). Contains `QuizMazeGame` which both front-ends reuse for game logic.
