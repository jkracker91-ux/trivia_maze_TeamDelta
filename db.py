"""Persistence layer for Quiz Maze — Harry Potter Edition.

Backed by SQLite via SQLModel. This module has ZERO coupling to maze.py.
It uses only primitives and its own SQLModel models for persistence.
main.py is the sole translation layer between domain objects and DB rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

from sqlalchemy import func
from sqlmodel import Field, Session, SQLModel, create_engine, select


# ── DTO Dataclasses (Public Contract) ────────────────────────────────────────


@dataclass
class QuestionRow:
    """A single trivia question stored in the database."""

    question_id: str
    text: str
    choices: list[str]
    correct_index: int
    category: str


@dataclass
class ScoreRow:
    """A completed game score record."""

    player_name: str
    score: int
    total_questions: int
    correct_answers: int
    completed: bool
    timestamp: str


@dataclass
class GameStateRow:
    """A saved in-progress game.

    CRITICAL DESIGN DECISION: Position is stored as two ints (player_row,
    player_col), NOT as a Position object. The orchestration layer (main.py)
    is responsible for decomposing Position -> (row, col) on save, and
    reconstructing Position(row, col) on load.
    """

    player_name: str
    player_row: int
    player_col: int
    score: int
    questions_answered: list[str]
    maze_id: str
    timestamp: str
    visited_cells: list[list[int]] = field(default_factory=list)


# ── Repository Protocols (Public Contract) ───────────────────────────────────


class GameRepository(Protocol):
    """Interface for saving/loading in-progress games."""

    def save_game(self, state: GameStateRow) -> None: ...

    def load_game(self, player_name: str) -> GameStateRow | None: ...

    def delete_game(self, player_name: str) -> None: ...


class ScoreRepository(Protocol):
    """Interface for recording and retrieving completed game scores."""

    def save_score(self, score: ScoreRow) -> None: ...

    def get_high_scores(self, limit: int = 10) -> list[ScoreRow]: ...

    def get_player_scores(self, player_name: str) -> list[ScoreRow]: ...


class QuestionRepository(Protocol):
    """Interface for retrieving trivia questions."""

    def get_question(self, question_id: str) -> QuestionRow | None: ...

    def get_random_question(
        self, exclude: list[str] | None = None
    ) -> QuestionRow | None: ...

    def get_all_questions(self) -> list[QuestionRow]: ...


# ── Internal SQLModel Table Models (Private) ────────────────────────────────


class _QuestionTable(SQLModel, table=True):
    __tablename__ = "enchanted_questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: str = Field(index=True, unique=True)
    text: str
    choices_json: str
    correct_index: int
    category: str
    has_been_asked: bool = Field(default=False)


class _ScoreTable(SQLModel, table=True):
    __tablename__ = "house_scores"

    id: Optional[int] = Field(default=None, primary_key=True)
    player_name: str = Field(index=True)
    score: int
    total_questions: int
    correct_answers: int
    completed: bool
    timestamp: str


class _GameStateTable(SQLModel, table=True):
    __tablename__ = "game_chronicles"

    id: Optional[int] = Field(default=None, primary_key=True)
    player_name: str = Field(index=True, unique=True)
    player_row: int
    player_col: int
    score: int
    questions_answered_json: str
    maze_id: str
    timestamp: str
    visited_cells_json: str = Field(default="[]")


# ── SQLModelRepository ──────────────────────────────────────────────────────


class SQLModelRepository:
    """ORM-backed repository satisfying all three repository protocols.

    Backed by SQLite via SQLModel. Replaces the walking-skeleton
    JsonRepository with a real relational persistence layer.

    Tables are auto-created on __init__ via SQLModel.metadata.create_all().
    """

    def __init__(self, db_url: str = "sqlite:///game_data.db") -> None:
        self._engine = create_engine(db_url)
        SQLModel.metadata.create_all(self._engine)

    # ── Internal Conversions ─────────────────────────────────────────────

    @staticmethod
    def _to_question_row(row: _QuestionTable) -> QuestionRow:
        return QuestionRow(
            question_id=row.question_id,
            text=row.text,
            choices=json.loads(row.choices_json),
            correct_index=row.correct_index,
            category=row.category,
        )

    @staticmethod
    def _to_score_row(row: _ScoreTable) -> ScoreRow:
        return ScoreRow(
            player_name=row.player_name,
            score=row.score,
            total_questions=row.total_questions,
            correct_answers=row.correct_answers,
            completed=row.completed,
            timestamp=row.timestamp,
        )

    @staticmethod
    def _to_game_state_row(row: _GameStateTable) -> GameStateRow:
        return GameStateRow(
            player_name=row.player_name,
            player_row=row.player_row,
            player_col=row.player_col,
            score=row.score,
            questions_answered=json.loads(row.questions_answered_json),
            maze_id=row.maze_id,
            timestamp=row.timestamp,
            visited_cells=json.loads(row.visited_cells_json),
        )

    # ── GameRepository ───────────────────────────────────────────────────

    def save_game(self, state: GameStateRow) -> None:
        with Session(self._engine) as session:
            existing = session.exec(
                select(_GameStateTable).where(
                    _GameStateTable.player_name == state.player_name
                )
            ).first()
            if existing:
                existing.player_row = state.player_row
                existing.player_col = state.player_col
                existing.score = state.score
                existing.questions_answered_json = json.dumps(
                    state.questions_answered
                )
                existing.maze_id = state.maze_id
                existing.timestamp = state.timestamp
                existing.visited_cells_json = json.dumps(
                    state.visited_cells
                )
            else:
                session.add(
                    _GameStateTable(
                        player_name=state.player_name,
                        player_row=state.player_row,
                        player_col=state.player_col,
                        score=state.score,
                        questions_answered_json=json.dumps(
                            state.questions_answered
                        ),
                        maze_id=state.maze_id,
                        timestamp=state.timestamp,
                        visited_cells_json=json.dumps(
                            state.visited_cells
                        ),
                    )
                )
            session.commit()

    def load_game(self, player_name: str) -> GameStateRow | None:
        with Session(self._engine) as session:
            row = session.exec(
                select(_GameStateTable).where(
                    _GameStateTable.player_name == player_name
                )
            ).first()
            if row is None:
                return None
            return self._to_game_state_row(row)

    def delete_game(self, player_name: str) -> None:
        with Session(self._engine) as session:
            row = session.exec(
                select(_GameStateTable).where(
                    _GameStateTable.player_name == player_name
                )
            ).first()
            if row is not None:
                session.delete(row)
                session.commit()

    # ── ScoreRepository ──────────────────────────────────────────────────

    def save_score(self, score: ScoreRow) -> None:
        with Session(self._engine) as session:
            session.add(
                _ScoreTable(
                    player_name=score.player_name,
                    score=score.score,
                    total_questions=score.total_questions,
                    correct_answers=score.correct_answers,
                    completed=score.completed,
                    timestamp=score.timestamp,
                )
            )
            session.commit()

    def get_high_scores(self, limit: int = 10) -> list[ScoreRow]:
        if limit <= 0:
            return []
        with Session(self._engine) as session:
            rows = session.exec(
                select(_ScoreTable)
                .order_by(_ScoreTable.score.desc())  # type: ignore[union-attr]
                .limit(limit)
            ).all()
            return [self._to_score_row(r) for r in rows]

    def get_player_scores(self, player_name: str) -> list[ScoreRow]:
        with Session(self._engine) as session:
            rows = session.exec(
                select(_ScoreTable).where(
                    _ScoreTable.player_name == player_name
                )
            ).all()
            return [self._to_score_row(r) for r in rows]

    # ── QuestionRepository ───────────────────────────────────────────────

    def get_question(self, question_id: str) -> QuestionRow | None:
        with Session(self._engine) as session:
            row = session.exec(
                select(_QuestionTable).where(
                    _QuestionTable.question_id == question_id
                )
            ).first()
            if row is None:
                return None
            return self._to_question_row(row)

    def get_random_question(
        self, exclude: list[str] | None = None
    ) -> QuestionRow | None:
        with Session(self._engine) as session:
            stmt = select(_QuestionTable)
            if exclude:
                stmt = stmt.where(
                    _QuestionTable.question_id.notin_(exclude)  # type: ignore[union-attr]
                )
            stmt = stmt.order_by(func.random()).limit(1)
            row = session.exec(stmt).first()
            if row is None:
                return None
            return self._to_question_row(row)

    def get_all_questions(self) -> list[QuestionRow]:
        with Session(self._engine) as session:
            rows = session.exec(select(_QuestionTable)).all()
            return [self._to_question_row(r) for r in rows]

    # ── Question Management (not part of any Protocol) ───────────────────

    def reset_questions(self) -> None:
        """Mark every question as not-yet-asked for a fresh game session."""
        with Session(self._engine) as session:
            rows = session.exec(select(_QuestionTable)).all()
            for row in rows:
                row.has_been_asked = False
                session.add(row)
            session.commit()

    def load_questions(self, questions: list[QuestionRow]) -> None:
        """Replace stored questions with the given list (upsert by question_id)."""
        with Session(self._engine) as session:
            existing = session.exec(select(_QuestionTable)).all()
            for row in existing:
                session.delete(row)
            session.commit()

        with Session(self._engine) as session:
            for q in questions:
                session.add(
                    _QuestionTable(
                        question_id=q.question_id,
                        text=q.text,
                        choices_json=json.dumps(q.choices),
                        correct_index=q.correct_index,
                        category=q.category,
                        has_been_asked=False,
                    )
                )
            session.commit()

    def load_questions_from_file(self, filepath: str | Path) -> None:
        """Read a JSON array of question dicts and store them."""
        path = Path(filepath)
        raw = path.read_text(encoding="utf-8")
        entries = json.loads(raw)
        if not isinstance(entries, list):
            return
        questions = [
            QuestionRow(
                question_id=e.get("question_id", ""),
                text=e.get("text", ""),
                choices=e.get("choices", []),
                correct_index=e.get("correct_index", 0),
                category=e.get("category", ""),
            )
            for e in entries
            if isinstance(e, dict)
        ]
        self.load_questions(questions)


# ── Seed Data: Harry Potter Question Bank ────────────────────────────────────


_SEED_QUESTIONS: list[QuestionRow] = [
    # ── Characters ───────────────────────────────────────────────────────
    QuestionRow(
        "q01", "What house is Harry Potter sorted into?",
        ["Slytherin", "Gryffindor", "Ravenclaw", "Hufflepuff"],
        1, "characters",
    ),
    QuestionRow(
        "q02", "Who is the headmaster of Hogwarts at the start of the series?",
        ["Albus Dumbledore", "Minerva McGonagall", "Severus Snape", "Filius Flitwick"],
        0, "characters",
    ),
    QuestionRow(
        "q03", "Who is Harry's godfather?",
        ["Remus Lupin", "James Potter", "Sirius Black", "Arthur Weasley"],
        2, "characters",
    ),
    QuestionRow(
        "q04", "What is the name of Ron Weasley's rat?",
        ["Crookshanks", "Hedwig", "Scabbers", "Errol"],
        2, "characters",
    ),
    QuestionRow(
        "q05", "Who teaches Potions in Harry's first year?",
        ["Horace Slughorn", "Severus Snape", "Remus Lupin", "Gilderoy Lockhart"],
        1, "characters",
    ),
    QuestionRow(
        "q06", "What is Hermione Granger's middle name?",
        ["Jane", "Jean", "Rose", "Ann"],
        1, "characters",
    ),
    # ── Spells ───────────────────────────────────────────────────────────
    QuestionRow(
        "q07", "What is the spell for disarming an opponent?",
        ["Stupefy", "Accio", "Expelliarmus", "Lumos"],
        2, "spells",
    ),
    QuestionRow(
        "q08", "What spell produces light from the tip of a wand?",
        ["Lumos", "Nox", "Incendio", "Protego"],
        0, "spells",
    ),
    QuestionRow(
        "q09", "Which spell is known as the Killing Curse?",
        ["Crucio", "Imperio", "Avada Kedavra", "Sectumsempra"],
        2, "spells",
    ),
    QuestionRow(
        "q10", "What does the spell 'Accio' do?",
        ["Unlocks doors", "Summons objects", "Creates fire", "Erases memory"],
        1, "spells",
    ),
    QuestionRow(
        "q11", "Which spell is used to open locked doors?",
        ["Alohomora", "Colloportus", "Reducto", "Diffindo"],
        0, "spells",
    ),
    QuestionRow(
        "q12", "What spell creates a shield to deflect minor curses?",
        ["Expecto Patronum", "Protego", "Stupefy", "Impedimenta"],
        1, "spells",
    ),
    # ── Potions ──────────────────────────────────────────────────────────
    QuestionRow(
        "q13", "What potion grants good luck?",
        ["Polyjuice Potion", "Veritaserum", "Amortentia", "Felix Felicis"],
        3, "potions",
    ),
    QuestionRow(
        "q14", "Which potion allows a witch or wizard to assume the form of another?",
        ["Felix Felicis", "Wolfsbane Potion", "Polyjuice Potion", "Draught of Living Death"],
        2, "potions",
    ),
    QuestionRow(
        "q15", "What is the most powerful love potion in the wizarding world?",
        ["Amortentia", "Felix Felicis", "Veritaserum", "Elixir of Life"],
        0, "potions",
    ),
    QuestionRow(
        "q16", "Which potion is a truth serum?",
        ["Polyjuice Potion", "Wolfsbane Potion", "Veritaserum", "Pepperup Potion"],
        2, "potions",
    ),
    QuestionRow(
        "q17", "What potion does Professor Lupin take to control his werewolf transformations?",
        ["Draught of Peace", "Wolfsbane Potion", "Skele-Gro", "Pepperup Potion"],
        1, "potions",
    ),
    # ── Creatures ─────────────────────────────────────────────────────────
    QuestionRow(
        "q18", "What creature is half eagle and half horse?",
        ["Thestral", "Griffin", "Hippogriff", "Niffler"],
        2, "creatures",
    ),
    QuestionRow(
        "q19", "What is the name of Hermione's cat?",
        ["Scabbers", "Crookshanks", "Hedwig", "Pigwidgeon"],
        1, "creatures",
    ),
    QuestionRow(
        "q20", "What type of creature is Aragog?",
        ["Basilisk", "Acromantula", "Thestral", "Hippogriff"],
        1, "creatures",
    ),
    QuestionRow(
        "q21", "Which creatures guard the wizard prison Azkaban?",
        ["Death Eaters", "Dementors", "Inferi", "Boggarts"],
        1, "creatures",
    ),
    QuestionRow(
        "q22", "What animal can Harry speak to because he is a Parselmouth?",
        ["Owls", "Spiders", "Snakes", "Rats"],
        2, "creatures",
    ),
    QuestionRow(
        "q23", "What is the name of Hagrid's three-headed dog?",
        ["Fang", "Norbert", "Fluffy", "Buckbeak"],
        2, "creatures",
    ),
    # ── Locations ─────────────────────────────────────────────────────────
    QuestionRow(
        "q24", "What is the name of the train that takes students to Hogwarts?",
        ["Knight Bus", "Hogwarts Express", "Durmstrang Ship", "Beauxbatons Carriage"],
        1, "locations",
    ),
    QuestionRow(
        "q25", "Which platform at King's Cross does the Hogwarts Express depart from?",
        ["Platform 7", "Platform 10", "Platform 12", "Platform 9 3/4"],
        3, "locations",
    ),
    QuestionRow(
        "q26", "What is the name of the village near Hogwarts that students can visit?",
        ["Godric's Hollow", "Diagon Alley", "Hogsmeade", "Ottery St Catchpole"],
        2, "locations",
    ),
    QuestionRow(
        "q27", "Where do wizards go to buy their school supplies?",
        ["Knockturn Alley", "Hogsmeade", "Diagon Alley", "The Leaky Cauldron"],
        2, "locations",
    ),
    QuestionRow(
        "q28", "In which room does the Yule Ball take place?",
        ["Room of Requirement", "Great Hall", "Astronomy Tower", "Quidditch Pitch"],
        1, "locations",
    ),
    QuestionRow(
        "q29", "Where is the entrance to the Chamber of Secrets?",
        ["Dumbledore's office", "The library", "Moaning Myrtle's bathroom", "The Forbidden Forest"],
        2, "locations",
    ),
    QuestionRow(
        "q30", "What is the name of the pub that serves as the gateway to Diagon Alley?",
        ["The Three Broomsticks", "The Hog's Head", "The Leaky Cauldron", "Madam Puddifoot's"],
        2, "locations",
    ),
]


def seed_questions_if_empty(repo: SQLModelRepository) -> None:
    """Populate the question bank with themed seed data if it is empty."""
    if not repo.get_all_questions():
        repo.load_questions(_SEED_QUESTIONS)
