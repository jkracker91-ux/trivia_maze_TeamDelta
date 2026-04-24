"""Game orchestration module for Quiz Maze — Harry Potter Edition.

This is the ONLY module that imports from both maze.py and db.py.
It owns all translation between domain objects (Position) and
persistence primitives (player_row, player_col, visited_cells).

All print() and input() calls are delegated to view.py.
QuizMazeGame methods return strings; main() passes them to view.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from maze import Direction, MapData, Maze, Position, generate_maze
from db import (
    GameRepository,
    GameStateRow,
    QuestionRepository,
    QuestionRow,
    ScoreRepository,
    ScoreRow,
    SQLModelRepository,
    seed_questions_if_empty,
)

_QUESTIONS_PATH = Path(__file__).parent / "questions.json"
_DB_URL = "sqlite:///" + str(Path(__file__).parent / "game_data.db")

POINTS_PER_CORRECT = 10


@dataclass
class Player:
    """Mutable player state managed by the game session.

    APPLICATION-layer type — bridges maze.py's Position with db.py's primitives.
    visited tracks every room the player has entered for fog-of-war rendering.
    """

    name: str
    position: Position
    score: int = 0
    questions_answered: list[str] = field(default_factory=list)
    visited_cells: set[Position] = field(default_factory=set)


class QuizMazeGame:
    """Orchestrates gameplay between the maze domain and the persistence layer.

    The ONLY place where maze.py types and db.py types meet.
    Methods return narrative strings; they never call print() or input().
    """

    def __init__(
        self,
        player_name: str,
        maze: Maze,
        game_repo: GameRepository,
        score_repo: ScoreRepository,
        question_repo: QuestionRepository,
    ) -> None:
        self._maze = maze
        self._game_repo = game_repo
        self._score_repo = score_repo
        self._question_repo = question_repo
        self._session_id = str(uuid.uuid4())
        self._maze_id = self._session_id

        self.player = Player(name=player_name, position=maze.start)
        self._pending_direction: Direction | None = None
        self._pending_question: QuestionRow | None = None
        self._pending_exit: bool = False
        self.confirm_exit_enabled: bool = False
        self.game_active = False
        self.game_won = False

    # ── Game Lifecycle ────────────────────────────────────────────────────────

    def start_new_game(self) -> str:
        """Initialise a new game, reset visited tracking, return opening narrative."""
        self._session_id = str(uuid.uuid4())
        self._maze_id = self._session_id
        self.player.position = self._maze.start
        self.player.score = 0
        self.player.questions_answered = []
        self.player.visited_cells = {self._maze.start}
        self.game_active = True
        self.game_won = False
        return (
            f"Welcome, {self.player.name}! Your quest through the Forbidden Forest begins.\n"
            f"The trees close in around you — somewhere ahead lies the path to Hogwarts.\n"
            f"Every passage is sealed by ancient magic. "
            f"Only correct answers will open the way."
        )

    def resume_game(self) -> str:
        """Load saved state from the DB and return resumption narrative.

        Position reconstruction: int, int → Position(row, col)
        visited_cells reconstruction: [[row,col],…] → set[Position]
        """
        state = self._game_repo.load_game(self.player.name)
        if state is None:
            return self.start_new_game()
        self.player = self._from_game_state_row(state)
        self._maze_id = state.maze_id
        self._session_id = state.maze_id
        self.game_active = True
        self.game_won = False
        return (
            f"Welcome back, {self.player.name}!\n"
            f"The forest remembers you… your journey continues."
        )

    # ── Player Actions ────────────────────────────────────────────────────────

    def move(self, direction_str: str) -> str:
        """Attempt to move in a direction and return narrative text.

        Flow:
        1. Parse direction_str → Direction enum.
        2. Check maze.can_move — wall blocks immediately.
        3. Passage found → fetch a fresh unused question, store as pending.
        4. After a correct answer the actual move executes in answer_question().
        """
        if not self.game_active:
            return "No active game. Start or resume a game first."
        if self._pending_exit:
            return "You stand at the castle gates! Decide whether to leave (y/n)."
        if self._pending_question is not None:
            return "You have a pending question! Answer it first (type 1, 2, 3, or 4)."
        try:
            direction = Direction(direction_str.lower())
        except ValueError:
            return (
                f"Unknown direction: '{direction_str}'. "
                "Use north, south, east, or west."
            )

        if not self._maze.can_move(self.player.position, direction):
            return f"There is no door to the {direction.value}. The wall holds firm."

        new_pos = self._maze.move(self.player.position, direction)

        if new_pos in self.player.visited_cells:
            self.player.position = new_pos
            if self._maze.is_exit(new_pos):
                return self._maybe_win(
                    f"The fog has lifted here. You stride {direction.value} "
                    f"through the familiar clearing."
                )
            return (
                f"The fog has lifted here. You stride {direction.value} "
                f"through the familiar clearing."
            )

        if not self._maze.is_gated(self.player.position, direction):
            self.player.position = new_pos
            self.player.visited_cells.add(new_pos)
            if self._maze.is_exit(new_pos):
                return self._maybe_win(
                    f"The passage to the {direction.value} opens freely. "
                    f"You step through."
                )
            return (
                f"The passage to the {direction.value} opens freely. "
                f"You step through."
            )

        question = self._question_repo.get_random_question(
            exclude=self.player.questions_answered
        )
        if question is None:
            self.player.position = new_pos
            self.player.visited_cells.add(new_pos)
            if self._maze.is_exit(new_pos):
                return self._maybe_win(
                    f"Your knowledge has impressed the forest. "
                    f"The passage {direction.value} opens freely before you."
                )
            return (
                f"Your knowledge has impressed the forest. "
                f"The passage {direction.value} opens freely before you."
            )

        self._pending_direction = direction
        self._pending_question = question
        choices_text = "\n".join(
            f"  {i + 1}. {choice}" for i, choice in enumerate(question.choices)
        )
        return (
            f"A locked door blocks the passage to the {direction.value}!\n\n"
            f"[{question.category.upper()}] {question.text}\n\n"
            f"{choices_text}\n\n"
            f"Answer with 1, 2, 3, or 4."
        )

    def answer_question(self, choice: int) -> str:
        """Submit an answer (1-based) to the pending gate question.

        Correct → execute the pending move, award points, update visited.
        Incorrect → stay put, discard pending question.
        """
        if self._pending_question is None:
            return "No pending question. Move in a direction first."

        question = self._pending_question
        direction = self._pending_direction

        if choice < 1 or choice > len(question.choices):
            return (
                f"Invalid choice. Enter a number between 1 and {len(question.choices)}."
            )

        answer_index = choice - 1

        # Clear pending state before the move so re-entrant calls are safe.
        self._pending_question = None
        self._pending_direction = None

        if answer_index == question.correct_index:
            self.player.questions_answered.append(question.question_id)
            self.player.score += POINTS_PER_CORRECT
            new_pos = self._maze.move(self.player.position, direction)
            self.player.position = new_pos
            self.player.visited_cells.add(new_pos)
            if self._maze.is_exit(new_pos):
                return self._maybe_win(
                    f"Correct! +{POINTS_PER_CORRECT} house points. "
                    f"The enchantment fades and the passage opens."
                )
            return (
                f"Correct! +{POINTS_PER_CORRECT} house points. "
                f"The enchantment fades and the passage opens."
            )

        correct_answer = question.choices[question.correct_index]
        return (
            f"Wrong! The answer was: {correct_answer}\n"
            f"The magic holds firm. You must find another way…"
        )

    def get_status(self) -> str:
        """Return current position, score, and a Fog-of-War ASCII grid.

        Visibility rules:
        - '@' marks the player's current position.
        - '.' marks a visited (explored) clearing.
        - 'X' marks the exit, only if the exit cell has been visited.
        - '??' marks unexplored fog.
        """
        pos = self.player.position
        open_dirs = self._maze.get_open_directions(pos)
        dirs_text = ", ".join(d.value for d in open_dirs) if open_dirs else "none"

        w, h = self._maze.width, self._maze.height
        visited = self.player.visited_cells
        col_width = 4
        horiz = "+" + (("-" * col_width + "+") * w)
        rows: list[str] = [horiz]
        for r in range(h):
            cells: list[str] = []
            for c in range(w):
                cell_pos = Position(r, c)
                if cell_pos == pos:
                    token = " @  "
                elif cell_pos not in visited:
                    token = " ?? "
                elif self._maze.is_exit(cell_pos):
                    token = " X  "
                else:
                    token = " .  "
                cells.append(token)
            rows.append("|" + "|".join(cells) + "|")
            rows.append(horiz)

        grid_text = "\n".join(rows)
        return (
            f"{grid_text}\n"
            f"House Points : {self.player.score}\n"
            f"Spells Cast  : {len(self.player.questions_answered)}\n"
            f"Passages     : {dirs_text}"
        )

    def get_map_data(self) -> MapData:
        """Return a structured map snapshot for programmatic UI consumption.

        Delegates to Maze.get_map_data() with the current player state.
        """
        return self._maze.get_map_data(self.player.position, self.player.visited_cells)

    @property
    def questions_exhausted(self) -> bool:
        """True when every available question has been answered."""
        return self._question_repo.get_random_question(
            exclude=self.player.questions_answered
        ) is None

    def save_game(self) -> None:
        """Persist current state to the DB."""
        self._game_repo.save_game(self._to_game_state_row())

    def quit_game(self) -> None:
        """Save in-progress state and record a (non-completed) score entry."""
        if self.game_active:
            self.save_game()
        score_row = ScoreRow(
            player_name=self.player.name,
            score=self.player.score,
            total_questions=len(self.player.questions_answered),
            correct_answers=self.player.score // POINTS_PER_CORRECT,
            completed=False,
            timestamp=_now_iso(),
        )
        self._score_repo.save_score(score_row)

    # ── Map rendering (fog-of-war) ─────────────────────────────────────────────

    def _render_map(self) -> str:
        """Return the fog-of-war map string by delegating to view.render_map.

        The lazy import keeps view.py optional for headless tests.
        """
        from view import render_map  # noqa: PLC0415

        return render_map(
            maze=self._maze,
            player_pos=self.player.position,
            visited=self.player.visited_cells,
            exit_pos=self._maze.exit_pos,
        )

    # ── Translation Helpers (private) ─────────────────────────────────────────

    def _to_game_state_row(self) -> GameStateRow:
        """Decompose domain objects → DB primitives.

        Position → (player_row, player_col) as ints.
        visited set[Position] → visited_cells list[list[int]].
        """
        return GameStateRow(
            player_name=self.player.name,
            player_row=self.player.position.row,
            player_col=self.player.position.col,
            score=self.player.score,
            questions_answered=list(self.player.questions_answered),
            maze_id=self._maze_id,
            timestamp=_now_iso(),
            visited_cells=[[p.row, p.col] for p in self.player.visited_cells],
        )

    def _from_game_state_row(self, row: GameStateRow) -> Player:
        """Reconstruct domain objects ← DB primitives (ints → Position)."""
        visited = {
            Position(row=pair[0], col=pair[1])
            for pair in row.visited_cells
            if isinstance(pair, list) and len(pair) == 2
        }
        return Player(
            name=row.player_name,
            position=Position(row=row.player_row, col=row.player_col),
            score=row.score,
            questions_answered=list(row.questions_answered),
            visited_cells=(
                visited
                if visited
                else {Position(row=row.player_row, col=row.player_col)}
            ),
        )

    def _maybe_win(self, prefix: str = "") -> str:
        """Check whether to finalise the win or defer for player confirmation.

        When confirm_exit_enabled is True, the player gets a chance to keep
        exploring instead of ending immediately.
        """
        if self.confirm_exit_enabled:
            self._pending_exit = True
            return (
                f"{prefix}\n\n"
                "You've reached the castle gates!\n"
                "Leave the Forbidden Forest? (y to leave, n to keep exploring)"
            ).strip()
        return self._handle_win()

    def confirm_exit(self, leave: bool) -> str:
        """Respond to the exit confirmation prompt.

        leave=True  → finalise the win (save score, delete saved game).
        leave=False → stay at the exit cell, keep playing.
        """
        self._pending_exit = False
        if leave:
            return self._handle_win()
        return "You decide to keep exploring the forest…"

    def _handle_win(self) -> str:
        """Record victory, clean up saved game, and return win narrative."""
        self.game_active = False
        self.game_won = True
        score_row = ScoreRow(
            player_name=self.player.name,
            score=self.player.score,
            total_questions=len(self.player.questions_answered),
            correct_answers=self.player.score // POINTS_PER_CORRECT,
            completed=True,
            timestamp=_now_iso(),
        )
        self._score_repo.save_score(score_row)
        self._game_repo.delete_game(self.player.name)
        return (
            f"YOU ESCAPED THE FORBIDDEN FOREST!\n"
            f"Congratulations, {self.player.name}! "
            f"The castle gates swing open to welcome you home."
        )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ── Game Loop ──────────────────────────────────────────────────────────────────


def main() -> None:
    """Top-level game loop.  All I/O is routed through view.py.

    Commands:
        north / south / east / west   — attempt to move through a door
        1 / 2 / 3 / 4                — answer a pending question
        status                        — show status panel
        map                           — redraw the fog-of-war map
        save                          — persist game to disk
        scores                        — display high-score table
        quit                          — save and exit
    """
    import view  # local import so tests can import main without a terminal

    view.show_banner()

    repo = SQLModelRepository(_DB_URL)
    seed_questions_if_empty(repo)

    player_name = view.prompt_name()

    saved = repo.load_game(player_name)
    maze = generate_maze(3, 3)
    game = QuizMazeGame(
        player_name=player_name,
        maze=maze,
        game_repo=repo,
        score_repo=repo,
        question_repo=repo,
    )

    game.confirm_exit_enabled = True

    if saved and view.prompt_resume(player_name):
        view.show_message(game.resume_game())
    else:
        repo.reset_questions()
        view.show_message(game.start_new_game())

    view.show_map(
        game._maze, game.player.position, game.player.visited_cells, game._maze.exit_pos
    )
    view.show_help()

    while True:
        if not game.game_active and game.game_won:
            replay = input("\nPlay again? (y/n): ").strip().lower()
            if replay == "y":
                repo.reset_questions()
                maze = generate_maze(5, 5)
                game = QuizMazeGame(
                    player_name=player_name,
                    maze=maze,
                    game_repo=repo,
                    score_repo=repo,
                    question_repo=repo,
                )
                view.show_message(game.start_new_game())
                view.show_map(
                    game._maze,
                    game.player.position,
                    game.player.visited_cells,
                    game._maze.exit_pos,
                )
                view.show_help()
            else:
                view.show_message("Thanks for braving the Forbidden Forest. Farewell!")
                break

        raw = view.prompt_command()

        if not raw:
            continue

        if raw in ("north", "south", "east", "west"):
            result = game.move(raw)
            view.show_message(result)
            if game._pending_exit:
                confirm = input("(y/n): ").strip().lower()
                view.show_message(game.confirm_exit(confirm == "y"))
            if game.game_active:
                view.show_map(
                    game._maze,
                    game.player.position,
                    game.player.visited_cells,
                    game._maze.exit_pos,
                )

        elif raw in ("1", "2", "3", "4"):
            result = game.answer_question(int(raw))
            view.show_message(result)
            if game._pending_exit:
                confirm = input("(y/n): ").strip().lower()
                view.show_message(game.confirm_exit(confirm == "y"))
            if game.game_active and not game._pending_question:
                view.show_map(
                    game._maze,
                    game.player.position,
                    game.player.visited_cells,
                    game._maze.exit_pos,
                )

        elif raw == "status":
            open_dirs = [
                d.value for d in game._maze.get_open_directions(game.player.position)
            ]
            view.show_status(
                pos=game.player.position,
                exit_pos=game._maze.exit_pos,
                score=game.player.score,
                doors=open_dirs,
                questions_answered=len(game.player.questions_answered),
            )
            view.show_map(
                game._maze,
                game.player.position,
                game.player.visited_cells,
                game._maze.exit_pos,
            )

        elif raw == "map":
            view.show_map(
                game._maze,
                game.player.position,
                game.player.visited_cells,
                game._maze.exit_pos,
            )

        elif raw == "save":
            if game.game_active:
                game.save_game()
                view.show_message("Game saved to the Hogwarts records.")
            else:
                view.show_message("No active game to save.")

        elif raw == "scores":
            view.show_scores(repo.get_high_scores(10))

        elif raw == "quit":
            confirm = input("Leave the Forbidden Forest? Your progress will be saved. (y/n): ").strip().lower()
            if confirm == "y":
                game.quit_game()
                view.show_message("Game saved. Farewell, brave adventurer!")
                break
            else:
                view.show_message("You steel your nerves and press on.")

        elif raw in ("help", "?"):
            view.show_help()

        else:
            view.show_message(
                f"Unknown command: '{raw}'.\n"
                "Try: north  south  east  west  |  1 2 3 4  |  "
                "status  map  save  scores  quit"
            )


if __name__ == "__main__":
    main()
