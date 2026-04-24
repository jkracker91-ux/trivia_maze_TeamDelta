"""pygame_3d.py — First-person raycasting 3D entry point for Forbidden Forest.

Pure pygame raycasting (no extra libraries).  The same QuizMazeGame engine
powers the game logic; this module is a drop-in replacement for pygame_main.py.

Run with:   python pygame_3d.py

Controls
  Left / Right arrows  Rotate view
  Up arrow / W         Move forward (triggers game.move in faced direction)
  A / D                Strafe left / right
  1  2  3  4           Answer pending gate question
  Ctrl+S               Save game
  Tab                  High-score table
  M                    Toggle minimap
  Music                Toggle button (click only)
  ESC                  Save and quit
"""

from __future__ import annotations

import array
import math
import random
import sys
import textwrap
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import pygame

from db import SQLModelRepository, seed_questions_if_empty
from main import QuizMazeGame
from maze import Direction, Position, generate_maze

# ── Paths ──────────────────────────────────────────────────────────────────────

_HERE           = Path(__file__).parent
_QUESTIONS_PATH = _HERE / "questions.json"
_DB_URL         = "sqlite:///" + str(_HERE / "game_data.db")
_BGM_MP3_PROJECT = _HERE / "assets" / "forbidden-forest-theme-complete.mp3"
_BGM_MP3_FALLBACK = Path(r"c:\Users\jkrac\Downloads\forbidden-forest-theme-complete.mp3")


def _resolve_bgm_mp3_path() -> Path | None:
    """Return the first existing path for the BGM MP3, or None if neither exists."""
    for p in (_BGM_MP3_PROJECT, _BGM_MP3_FALLBACK):
        if p.exists():
            return p
    return None


# ── Window / viewport ──────────────────────────────────────────────────────────

WIN_W, WIN_H = 1060, 660
TITLE_H      = 48
BOTTOM_H     = 52
VIEW_W       = 680                        # 3-D viewport width
VIEW_H       = WIN_H - TITLE_H - BOTTOM_H  # 3-D viewport height
VIEW_X       = 0
VIEW_Y       = TITLE_H
STATUS_X     = VIEW_W + 8
STATUS_W     = WIN_W - STATUS_X - 6

RAYCOLS      = 200          # horizontal ray resolution (higher = sharper but slower)
STRIP_PX     = VIEW_W / RAYCOLS  # pixel width of each strip
FOV_HALF     = math.tan(math.radians(33))   # half-FOV → ~66 ° total
MAX_DEPTH    = 10.0         # ray cutoff distance
FPS          = 60
MAX_MSG      = 8
MAX_HEARTS   = 3
MAZE_SIZES   = [(3, 3), (5, 5), (7, 7)]
MOVE_SPEED   = 0.055
TURN_SPEED   = 0.040
MOUSE_SENS   = 0.003        # radians per pixel of horizontal mouse movement
WALK_SPEED   = 1.8          # cells per second for smooth walk animation
COLLIDE_R    = 0.22         # player collision radius in world units

# Minimap constants
MINI_CELL    = 10           # px per cell in minimap
MINI_X       = VIEW_X + 8
MINI_Y       = VIEW_Y + VIEW_H - 8   # anchored at bottom-left of viewport

# ── Colour palette ─────────────────────────────────────────────────────────────

C_BG         = ( 12,  10,  25)
C_CEIL       = (  6,  14,   6)   # dark forest canopy
C_FLOOR      = ( 20,  16,  10)   # dark soil
C_WALL_X     = ( 72,  56, 108)   # x-side (east/west) wall — slightly lit
C_WALL_Y     = ( 48,  36,  72)   # y-side (north/south) wall — slightly dark
C_DOOR_X     = (140,  90,  30)   # locked door — amber tint (x-side)
C_DOOR_Y     = (110,  70,  22)   # locked door — amber tint (y-side)
C_PANEL_BG   = ( 20,  16,  42)
C_PANEL_EDGE = ( 75,  58, 138)
C_DIVIDER    = ( 55,  42, 100)
C_TEXT       = (210, 200, 240)
C_DIM        = (120, 110, 165)
C_GOLD       = (245, 200,  30)
C_GREEN      = ( 80, 220,  90)
C_RED        = (220,  75,  75)
C_AMBER      = (255, 175,  45)
C_TITLE_CLR  = (195, 160, 255)
C_HEART      = (220,  55,  75)
C_HEART_LOST = ( 55,  40,  70)
C_FOG_PASS   = ( 50, 180, 100)   # enchanted green passage fog
C_MIST       = ( 20,  32,  18)   # dark forest mist (ground fog & distance target)

# ── State machine ──────────────────────────────────────────────────────────────


class _State(Enum):
    MENU         = auto()
    PLAYING      = auto()
    QUESTION     = auto()
    WIN          = auto()
    SCORES       = auto()
    NO_HEARTS    = auto()
    QUIT_CONFIRM = auto()
    EXIT_CONFIRM = auto()


# ── 3-D player ─────────────────────────────────────────────────────────────────


@dataclass
class _Cam:
    """Floating-point player position and orientation for the raycaster."""
    x:       float   # world-x  = column (rightward)
    y:       float   # world-y  = row    (downward)
    dir_x:   float   # direction unit vector
    dir_y:   float
    plane_x: float   # camera plane (perpendicular to dir, length = FOV_HALF)
    plane_y: float

    @property
    def cell(self) -> Position:
        return Position(int(self.y), int(self.x))

    @property
    def angle(self) -> float:
        return math.atan2(self.dir_y, self.dir_x)

    def rotate(self, da: float) -> None:
        cos_a, sin_a = math.cos(da), math.sin(da)
        self.dir_x, self.dir_y = (
            self.dir_x * cos_a - self.dir_y * sin_a,
            self.dir_x * sin_a + self.dir_y * cos_a,
        )
        self.plane_x, self.plane_y = (
            self.plane_x * cos_a - self.plane_y * sin_a,
            self.plane_x * sin_a + self.plane_y * cos_a,
        )


def _make_cam(pos: Position, face_row: int, face_col: int) -> _Cam:
    """Create a camera centred in *pos*, facing toward (face_row, face_col)."""
    cx = pos.col + 0.5
    cy = pos.row + 0.5
    dx = (face_col + 0.5) - cx
    dy = (face_row + 0.5) - cy
    length = math.hypot(dx, dy) or 1.0
    dx /= length
    dy /= length
    return _Cam(
        x=cx, y=cy,
        dir_x=dx, dir_y=dy,
        plane_x=-dy * FOV_HALF,
        plane_y= dx * FOV_HALF,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Sound synthesis
# ══════════════════════════════════════════════════════════════════════════════

_SAMPLE_RATE = 22050


def _synth(
    freq: float,
    dur: float,
    vol: float = 0.35,
    attack: float = 0.01,
    decay_exp: float = 4.0,
) -> pygame.mixer.Sound:
    """Generate a mono 16-bit sine tone with exponential decay."""
    n = int(_SAMPLE_RATE * dur)
    buf = array.array("h")
    for i in range(n):
        t   = i / _SAMPLE_RATE
        env = min(1.0, t / max(attack, 1e-6)) * math.exp(-decay_exp * t / dur)
        buf.append(int(vol * 32767 * math.sin(2 * math.pi * freq * t) * env))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _synth_chord(
    freqs: list[float],
    dur: float,
    vol: float = 0.25,
) -> pygame.mixer.Sound:
    """Mix multiple tones sequentially (arpeggio)."""
    seg = dur / len(freqs)
    n   = int(_SAMPLE_RATE * dur)
    buf = array.array("h")
    for i in range(n):
        t   = i / _SAMPLE_RATE
        idx = min(len(freqs) - 1, int(t / seg))
        f   = freqs[idx]
        t0  = t - idx * seg
        env = math.exp(-5.0 * t0 / seg)
        buf.append(int(vol * 32767 * math.sin(2 * math.pi * f * t0) * env))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _synth_thunder() -> pygame.mixer.Sound:
    """Synthesize a thunder clap: sharp crack followed by a long low-frequency rumble."""
    dur  = 3.2
    n    = int(_SAMPLE_RATE * dur)
    buf  = array.array("h")
    prev = 0.0   # low-pass accumulator
    for i in range(n):
        t = i / _SAMPLE_RATE
        # Sharp crack — broadband noise that decays very quickly
        crack = random.uniform(-1, 1) * math.exp(-55 * t) * 0.80
        # Rumble — low-pass-filtered noise with a slow exponential decay
        raw   = random.uniform(-1, 1)
        prev  = prev * 0.91 + raw * 0.09          # simple IIR low-pass
        rumble = prev * math.exp(-1.1 * t) * 0.55
        sample = max(-1.0, min(1.0, crack + rumble))
        buf.append(int(sample * 32767 * 0.65))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _synth_bgm_loop() -> pygame.mixer.Sound:
    """Synthesize a dark atmospheric forest ambient loop (~16 s, loops seamlessly).

    Layers: low bass drone (A1 + E2 fifth), upper shimmer (A3 vibrato),
    and a slow descending/ascending A-minor-pentatonic melody motif.
    """
    dur  = 16.0
    n    = int(_SAMPLE_RATE * dur)
    buf  = array.array("h")

    # Melody: (start_t, note_dur, freq_Hz, volume)
    melody_notes = [
        ( 0.0, 2.5, 196.0, 0.13),   # G3
        ( 2.5, 2.5, 164.8, 0.12),   # E3
        ( 5.0, 3.0, 146.8, 0.11),   # D3
        ( 8.0, 2.5, 130.8, 0.13),   # C3
        (10.5, 2.5, 110.0, 0.14),   # A2
        (13.0, 3.0, 146.8, 0.11),   # D3  (rises back — loops into G3)
    ]

    for i in range(n):
        t = i / _SAMPLE_RATE

        # Bass drone: perfect fifth (A1 + E2), amplitude-modulated slowly
        drone_env = 0.22 + 0.04 * math.sin(2 * math.pi * 0.09 * t)
        d1 = math.sin(2 * math.pi * 55.0  * t)
        d2 = math.sin(2 * math.pi * 82.4  * t)   # E2 — perfect fifth above A1
        d3 = math.sin(2 * math.pi * 55.15 * t)   # slightly detuned for thickness
        drone = (d1 * 0.5 + d2 * 0.3 + d3 * 0.2) * drone_env * 0.28

        # Upper shimmer: A3 with slow vibrato
        vib   = math.sin(2 * math.pi * 0.22 * t) * 1.8   # ±1.8 Hz vibrato
        shim  = math.sin(2 * math.pi * (220.0 + vib) * t)
        shim *= 0.05 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.13 * t))

        # Melody layer
        mel = 0.0
        for start, nd, freq, vol in melody_notes:
            if start <= t < start + nd:
                tn  = t - start
                env = math.exp(-1.8 * tn / nd) * math.sin(math.pi * tn / nd) ** 0.4
                mel += math.sin(2 * math.pi * freq * tn) * env * vol

        sample = max(-1.0, min(1.0, drone + shim + mel))
        buf.append(int(sample * 32767 * 0.70))

    return pygame.mixer.Sound(buffer=buf.tobytes())


def _make_sounds() -> dict[str, pygame.mixer.Sound]:
    return {
        "step":      _synth(90,  0.12, vol=0.30, decay_exp=8),
        "bump":      _synth(60,  0.18, vol=0.40, decay_exp=6),
        "door":      _synth(180, 0.25, vol=0.30, decay_exp=3),
        "correct":   _synth_chord([261, 329, 392, 523], 0.55, vol=0.28),
        "wrong":     _synth_chord([220, 196, 174], 0.45, vol=0.28),
        "win":       _synth_chord([261, 329, 392, 523, 659, 784], 1.2, vol=0.30),
        "no_hearts": _synth_chord([220, 185, 155, 130], 0.8, vol=0.32),
        "thunder":   _synth_thunder(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Procedural tree sprite
# ══════════════════════════════════════════════════════════════════════════════


def _make_tree_sprite(w: int = 40, h: int = 80) -> pygame.Surface:
    """Create a simple dark conifer sprite on a transparent background."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    trunk_w  = max(3, w // 6)
    trunk_x  = (w - trunk_w) // 2
    trunk_y  = h * 2 // 3
    trunk_h  = h - trunk_y
    pygame.draw.rect(surf, (55, 35, 18), (trunk_x, trunk_y, trunk_w, trunk_h))

    # Three-tier foliage: each circle slightly offset and smaller
    tiers = [
        (w // 2, h * 3 // 5, h * 2 // 5, ( 10,  48,  10)),
        (w // 2, h * 2 // 5, h * 3 // 8, ( 14,  58,  14)),
        (w // 2, h * 1 // 4, h * 1 // 4, ( 18,  68,  18)),
    ]
    for cx, cy, r, colour in tiers:
        pygame.draw.circle(surf, colour, (cx, cy), r)
        # Dark centre for depth
        pygame.draw.circle(surf, (6, 30, 6), (cx, cy), max(2, r // 3))

    return surf


def _generate_trees(maze: object, seed: int = 42) -> list[tuple[float, float]]:
    """Scatter 0-2 trees per cell, kept near walls to clear passageways."""
    rng    = random.Random(seed)
    trees  = []
    width  = maze.width
    height = maze.height
    for r in range(height):
        for c in range(width):
            n = rng.randint(0, 2)
            for _ in range(n):
                # Place at one of the four wall-hugging corners
                fx = c + rng.choice([0.12, 0.82]) + rng.uniform(-0.04, 0.04)
                fy = r + rng.choice([0.12, 0.82]) + rng.uniform(-0.04, 0.04)
                fx = max(c + 0.08, min(c + 0.92, fx))
                fy = max(r + 0.08, min(r + 0.92, fy))
                trees.append((fx, fy))
    return trees


# ══════════════════════════════════════════════════════════════════════════════
# Raycasting engine
# ══════════════════════════════════════════════════════════════════════════════


def _fog_blend(base: tuple, dist: float) -> tuple:
    """Blend *base* toward the forest mist colour as distance increases."""
    t = min(1.0, dist / MAX_DEPTH) ** 1.6
    return (
        int(base[0] * (1 - t) + C_MIST[0] * t),
        int(base[1] * (1 - t) + C_MIST[1] * t),
        int(base[2] * (1 - t) + C_MIST[2] * t),
    )


def _wall_between(r1: int, c1: int, r2: int, c2: int, maze) -> bool:
    """True if there is a wall (no passage) between adjacent cells."""
    if r1 == r2:
        if c2 == c1 + 1:
            return not maze.can_move(Position(r1, c1), Direction.EAST)
        if c2 == c1 - 1:
            return not maze.can_move(Position(r1, c1), Direction.WEST)
    elif c1 == c2:
        if r2 == r1 + 1:
            return not maze.can_move(Position(r1, c1), Direction.SOUTH)
        if r2 == r1 - 1:
            return not maze.can_move(Position(r1, c1), Direction.NORTH)
    return True


def _is_door_wall(r1: int, c1: int, r2: int, c2: int, maze) -> bool:
    """True if the boundary exists AND the passage is gated (locked door)."""
    if r1 == r2:
        if c2 == c1 + 1:
            return maze.can_move(Position(r1, c1), Direction.EAST) and maze.is_gated(Position(r1, c1), Direction.EAST)
        if c2 == c1 - 1:
            return maze.can_move(Position(r1, c1), Direction.WEST) and maze.is_gated(Position(r1, c1), Direction.WEST)
    elif c1 == c2:
        if r2 == r1 + 1:
            return maze.can_move(Position(r1, c1), Direction.SOUTH) and maze.is_gated(Position(r1, c1), Direction.SOUTH)
        if r2 == r1 - 1:
            return maze.can_move(Position(r1, c1), Direction.NORTH) and maze.is_gated(Position(r1, c1), Direction.NORTH)
    return False


def _raycast_frame(
    surf:    pygame.Surface,
    cam:     _Cam,
    maze,
    visited: set[Position],
) -> tuple[list[float], list[tuple[int, float, int, bool, bool]]]:
    """
    Draw ceiling, floor, and walls for one frame.
    Returns (zbuffer, fog_hits) where fog_hits contains
    (col, perp_dist, side, target_visited, gated) for each passage boundary.
    """
    maze_w = maze.width
    maze_h = maze.height

    # ── Ceiling & floor gradients ──────────────────────────────────────────────
    half_h = VIEW_H // 2
    # Ceiling band (dark green/canopy)
    pygame.draw.rect(surf, C_CEIL,  (VIEW_X, VIEW_Y, VIEW_W, half_h))
    # Floor band (dark soil)
    pygame.draw.rect(surf, C_FLOOR, (VIEW_X, VIEW_Y + half_h, VIEW_W, VIEW_H - half_h))

    # Subtle vertical fade on ceiling and floor for depth
    for row_offset in range(0, half_h, 4):
        alpha = int(180 * (1 - row_offset / half_h))
        fade  = pygame.Surface((VIEW_W, 4), pygame.SRCALPHA)
        fade.fill((0, 0, 0, alpha))
        surf.blit(fade, (VIEW_X, VIEW_Y + row_offset))
        surf.blit(fade, (VIEW_X, VIEW_Y + VIEW_H - row_offset - 4))

    zbuffer: list[float] = [MAX_DEPTH] * RAYCOLS
    fog_hits: list[tuple[int, float, int, bool, bool]] = []

    # ── Wall strips ────────────────────────────────────────────────────────────
    for col in range(RAYCOLS):
        cam_x    = 2.0 * col / RAYCOLS - 1.0
        ray_dx   = cam.dir_x + cam.plane_x * cam_x
        ray_dy   = cam.dir_y + cam.plane_y * cam_x

        map_x = int(cam.x)
        map_y = int(cam.y)

        ddx = 1e30 if ray_dx == 0 else abs(1.0 / ray_dx)
        ddy = 1e30 if ray_dy == 0 else abs(1.0 / ray_dy)

        if ray_dx < 0:
            step_x   = -1
            side_dx  = (cam.x - map_x) * ddx
        else:
            step_x   =  1
            side_dx  = (map_x + 1.0 - cam.x) * ddx

        if ray_dy < 0:
            step_y   = -1
            side_dy  = (cam.y - map_y) * ddy
        else:
            step_y   =  1
            side_dy  = (map_y + 1.0 - cam.y) * ddy

        hit = False
        side = 0
        is_door = False

        while not hit:
            if side_dx < side_dy:
                side_dx += ddx
                prev_x   = map_x
                map_x   += step_x
                side     = 0
            else:
                side_dy += ddy
                prev_y   = map_y
                map_y   += step_y
                side     = 1

            # Boundary wall check
            if side == 0:
                r1, c1 = map_y,        prev_x
                r2, c2 = map_y,        map_x
            else:
                r1, c1 = prev_y,       map_x
                r2, c2 = map_y,        map_x

            # Out-of-bounds = solid boundary wall
            if not (0 <= map_x < maze_w and 0 <= map_y < maze_h):
                hit = True
                is_door = False
            elif _wall_between(r1, c1, r2, c2, maze):
                hit = True
                is_door = False
            else:
                if side == 0:
                    p_dist = side_dx - ddx
                else:
                    p_dist = side_dy - ddy
                target_vis = Position(r2, c2) in visited
                gated = _is_door_wall(r1, c1, r2, c2, maze)
                fog_hits.append((col, max(0.001, p_dist), side, target_vis, gated))

        # Perpendicular distance (removes fish-eye)
        if side == 0:
            perp = side_dx - ddx
        else:
            perp = side_dy - ddy

        perp = max(0.001, perp)
        zbuffer[col] = perp

        # Wall height
        wall_h   = int(VIEW_H / perp)
        wall_top = max(0, VIEW_H // 2 - wall_h // 2)
        wall_bot = min(VIEW_H, VIEW_H // 2 + wall_h // 2)

        # Base wall colour: x-side (east/west) slightly brighter, y-side darker
        base = C_WALL_X if side == 0 else C_WALL_Y
        colour = _fog_blend(base, perp)

        strip_x = VIEW_X + int(col * STRIP_PX)
        strip_w = max(1, int((col + 1) * STRIP_PX) - int(col * STRIP_PX))
        pygame.draw.rect(
            surf, colour,
            (strip_x, VIEW_Y + wall_top, strip_w, max(1, wall_bot - wall_top)),
        )

    return zbuffer, fog_hits


# ══════════════════════════════════════════════════════════════════════════════
# Passage fog rendering
# ══════════════════════════════════════════════════════════════════════════════


def _draw_passage_fog(
    surf:     pygame.Surface,
    fog_hits: list[tuple[int, float, int, bool, bool]],
    questions_exhausted: bool = False,
) -> None:
    """Render enchanted fog strips at passage boundaries between cells.

    Fog is only drawn for passages that are gated AND whose target cell
    has not yet been visited AND there are still questions left to ask.
    """
    if not fog_hits or questions_exhausted:
        return

    ticks = pygame.time.get_ticks() / 1000.0
    fog_surf = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)

    for col, perp, side, target_vis, gated in fog_hits:
        if target_vis or not gated:
            continue

        fog_h   = int(VIEW_H / perp)
        fog_top = max(0, VIEW_H // 2 - fog_h // 2)
        fog_bot = min(VIEW_H, VIEW_H // 2 + fog_h // 2)
        h       = max(1, fog_bot - fog_top)

        dist_factor = 1.0 - min(1.0, perp / MAX_DEPTH)
        base_alpha  = int(180 * dist_factor) + 30

        shimmer = 0.80 + 0.20 * math.sin(ticks * 3.0 + col * 0.12)
        alpha   = max(0, min(255, int(base_alpha * shimmer)))

        r, g, b = C_FOG_PASS
        if side == 1:
            r, g, b = int(r * 0.85), int(g * 0.85), int(b * 0.85)

        strip_x = int(col * STRIP_PX)
        strip_w = max(1, int((col + 1) * STRIP_PX) - int(col * STRIP_PX))

        pygame.draw.rect(
            fog_surf, (r, g, b, alpha),
            (strip_x, fog_top, strip_w, h),
        )

    surf.blit(fog_surf, (VIEW_X, VIEW_Y))


# ══════════════════════════════════════════════════════════════════════════════
# Exit cell floor tint
# ══════════════════════════════════════════════════════════════════════════════

C_EXIT_FLOOR = (180, 155, 40)


def _draw_exit_floor(
    surf:     pygame.Surface,
    exit_pos: Position,
    cam:      _Cam,
    zbuffer:  list[float],
) -> None:
    """Tint the floor of the exit cell with a warm golden colour.

    Uses per-column floor-casting: for each screen column, walk each
    scanline below the wall hit and check whether the world-space floor
    coordinate falls inside the exit cell.  If so, blend a golden overlay.
    """
    ex_c, ex_r = exit_pos.col, exit_pos.row
    half_h = VIEW_H // 2

    step = 3
    for col in range(0, RAYCOLS, step):
        cam_x  = 2.0 * col / RAYCOLS - 1.0
        ray_dx = cam.dir_x + cam.plane_x * cam_x
        ray_dy = cam.dir_y + cam.plane_y * cam_x

        wall_dist = zbuffer[col]
        wall_bot  = min(VIEW_H, half_h + int(VIEW_H / (2.0 * max(0.001, wall_dist))))

        strip_x = VIEW_X + int(col * STRIP_PX)
        strip_w = max(1, int(step * STRIP_PX))

        for y in range(wall_bot, VIEW_H, 4):
            row_dist = VIEW_H / (2.0 * max(1, y - half_h))
            floor_x = cam.x + row_dist * ray_dx
            floor_y = cam.y + row_dist * ray_dy
            fx, fy = int(floor_x), int(floor_y)

            if fx == ex_c and fy == ex_r:
                fog = min(1.0, row_dist / MAX_DEPTH) ** 1.4
                base_alpha = int(90 * (1.0 - fog))
                if base_alpha < 5:
                    continue
                tint = pygame.Surface((strip_w, 4), pygame.SRCALPHA)
                tint.fill((*C_EXIT_FLOOR, base_alpha))
                surf.blit(tint, (strip_x, VIEW_Y + y))


# ══════════════════════════════════════════════════════════════════════════════
# Tree sprite rendering
# ══════════════════════════════════════════════════════════════════════════════


def _draw_trees(
    surf:        pygame.Surface,
    tree_sprite: pygame.Surface,
    trees:       list[tuple[float, float]],
    cam:         _Cam,
    zbuffer:     list[float],
    visited:     set[Position],
) -> None:
    """Billboard-render tree sprites using the Z-buffer for occlusion."""
    inv_det = cam.dir_x * cam.plane_y - cam.dir_y * cam.plane_x
    if abs(inv_det) < 1e-6:
        return

    # Sort farthest-first for painter's algorithm
    def _dist(t: tuple[float, float]) -> float:
        return (t[0] - cam.x) ** 2 + (t[1] - cam.y) ** 2

    for tx, ty in sorted(trees, key=_dist, reverse=True):
        # Only render trees in visited cells (fog of war)
        cell = Position(int(ty), int(tx))
        if cell not in visited:
            continue

        dx = tx - cam.x
        dy = ty - cam.y

        # Transform to camera space
        t_x =  cam.plane_y * dx - cam.plane_x * dy
        t_z = -cam.dir_y   * dx + cam.dir_x   * dy   # depth in camera space

        if t_z <= 0.05:
            continue   # behind camera

        # Screen centre-x of sprite
        screen_cx = int(VIEW_W / 2.0 * (1.0 + t_x / t_z))

        # Sprite screen height / width (tall narrow tree)
        sprite_h = min(VIEW_H * 2, abs(int(VIEW_H / t_z)))
        sprite_w = sprite_h // 2

        start_x = screen_cx - sprite_w // 2
        end_x   = screen_cx + sprite_w // 2
        start_y = VIEW_H // 2 - sprite_h // 2
        end_y   = VIEW_H // 2 + sprite_h // 2

        clip_l  = max(0, start_x)
        clip_r  = min(RAYCOLS, end_x)

        if clip_l >= clip_r:
            continue

        # Fog factor based on depth
        fog = min(1.0, t_z / MAX_DEPTH) ** 1.6

        # Scale sprite surface to screen size
        draw_w = max(1, end_x - start_x)
        draw_h = max(1, end_y - start_y)
        try:
            scaled = pygame.transform.scale(tree_sprite, (draw_w, draw_h))
        except Exception:
            continue

        # Apply fog darkening
        if fog > 0.05:
            dark = pygame.Surface((draw_w, draw_h), pygame.SRCALPHA)
            dark.fill((0, 0, 0, int(255 * fog)))
            scaled.blit(dark, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        # Draw per-column with Z-buffer check
        tree_top = VIEW_Y + max(0, start_y)
        tree_h   = min(VIEW_H, end_y) - max(0, start_y)
        src_y    = max(0, -start_y)

        for col in range(clip_l, clip_r):
            if zbuffer[col] < t_z:
                continue   # wall closer than tree
            src_x    = int((col - start_x) * draw_w / max(1, end_x - start_x))
            src_x    = max(0, min(draw_w - 1, src_x))
            surf.blit(
                scaled,
                (VIEW_X + int(col * STRIP_PX), tree_top),
                area=(src_x, src_y, max(1, int(STRIP_PX)), tree_h),
            )


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# Atmospheric forest fog (ground mist, drifting wisps, ceiling mist)
# ══════════════════════════════════════════════════════════════════════════════

# Wisp definitions: (base_x_frac, base_y_frac, width, height, drift_speed, alpha, phase)
_WISPS = [
    (0.12, 0.73, 200, 42, 0.07, 52, 0.0),
    (0.38, 0.81, 260, 38, 0.05, 44, 1.3),
    (0.65, 0.69, 170, 34, 0.11, 48, 2.6),
    (0.28, 0.62, 220, 30, 0.06, 36, 3.9),
    (0.72, 0.77, 180, 36, 0.09, 42, 0.7),
    (0.88, 0.57, 130, 26, 0.08, 32, 2.0),
    (0.08, 0.86, 210, 40, 0.04, 50, 4.2),
    (0.52, 0.52, 155, 24, 0.12, 28, 1.6),
    (0.82, 0.88, 240, 44, 0.06, 38, 3.1),
    (0.45, 0.65, 145, 28, 0.10, 34, 0.4),
]


def _draw_forest_fog(surf: pygame.Surface, time_t: float) -> None:
    """Draw animated atmospheric fog: ground mist, drifting wisps, ceiling mist."""

    # ── Ground fog gradient ─────────────────────────────────────────────────
    # Fog rises ~40 % of the viewport height from the floor, with a slow wave
    fog_h   = int(VIEW_H * 0.40)
    n_bands = 22
    band_h  = max(1, fog_h // n_bands)
    wave    = math.sin(time_t * 0.35) * 0.06   # gentle density pulse

    ground_surf = pygame.Surface((VIEW_W, fog_h), pygame.SRCALPHA)
    for i in range(n_bands):
        progress = 1.0 - i / n_bands           # 1 at floor, 0 at top
        alpha    = int(max(0, min(200, (progress ** 1.7 + wave) * 165)))
        y        = fog_h - (i + 1) * band_h
        ground_surf.fill((*C_MIST, alpha), (0, y, VIEW_W, band_h + 1))
    surf.blit(ground_surf, (VIEW_X, VIEW_Y + VIEW_H - fog_h))

    # ── Drifting wisps ──────────────────────────────────────────────────────
    wisp_surf = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    for bx, by, w, h, speed, base_alpha, phase in _WISPS:
        drift_x = math.sin(time_t * speed       + phase) * 70
        drift_y = math.cos(time_t * speed * 0.6 + phase) * 18
        cx = int(bx * VIEW_W + drift_x)
        cy = int(by * VIEW_H + drift_y)
        pulse  = math.sin(time_t * 0.28 + phase) * 0.18
        alpha  = int(max(0, min(110, base_alpha * (1 + pulse))))
        pygame.draw.ellipse(wisp_surf, (*C_MIST, alpha),
                            (cx - w // 2, cy - h // 2, w, h))
        # Second softer halo around each wisp
        halo_a = alpha // 3
        pygame.draw.ellipse(wisp_surf, (*C_MIST, halo_a),
                            (cx - w * 3 // 4, cy - h, w * 3 // 2, h * 2))
    surf.blit(wisp_surf, (VIEW_X, VIEW_Y))

    # ── Ceiling mist ────────────────────────────────────────────────────────
    mist_h    = int(VIEW_H * 0.18)
    mist_surf = pygame.Surface((VIEW_W, mist_h), pygame.SRCALPHA)
    for i in range(mist_h):
        progress = 1.0 - i / mist_h            # 1 at top, 0 further down
        alpha    = int(progress ** 2.2 * 70)
        mist_surf.fill((*C_MIST, alpha), (0, i, VIEW_W, 1))
    surf.blit(mist_surf, (VIEW_X, VIEW_Y))


# ══════════════════════════════════════════════════════════════════════════════
# First-person wand / hand overlay
# ══════════════════════════════════════════════════════════════════════════════


def _draw_wand(surf: pygame.Surface, walk_phase: float, is_walking: bool) -> None:
    """Draw a bobbing wizard wand in the lower-right corner of the 3-D viewport.

    The wand bobs vertically while the player is walking, and rests at idle
    position when still — giving the feel of a first-person character.
    """
    bob   = math.sin(walk_phase * math.pi * 2) * 14 if is_walking else 0.0
    sway  = math.sin(walk_phase * math.pi) * 6 if is_walking else 0.0

    # Anchor: lower-right of the 3-D viewport
    base_x = VIEW_X + VIEW_W - 70
    base_y = VIEW_Y + VIEW_H - 30 + int(bob)

    # Wand shaft (slightly angled up-left like a held staff)
    tip_x = base_x - 55 + int(sway)
    tip_y = base_y - 110

    # Shadow hand / sleeve at base
    sleeve_pts = [
        (base_x - 18, base_y + 10),
        (base_x + 22, base_y + 10),
        (base_x + 18, base_y - 20),
        (base_x - 14, base_y - 20),
    ]
    pygame.draw.polygon(surf, ( 55,  35,  95), sleeve_pts)
    pygame.draw.polygon(surf, ( 72,  50, 118), sleeve_pts, 1)

    # Grip wrap (dark bands around lower wand)
    for i in range(3):
        gy = base_y - 10 - i * 12
        gx = base_x - 4 - i * 4
        pygame.draw.line(surf, (100, 75, 40), (gx, gy), (gx - 8, gy - 10), 3)

    # Wand shaft
    pygame.draw.line(surf, (185, 145, 72), (base_x - 4, base_y - 5), (tip_x, tip_y), 5)
    pygame.draw.line(surf, (210, 170, 95), (base_x - 5, base_y - 6), (tip_x + 1, tip_y + 1), 2)

    # Glow at tip (pulsing)
    glow_r = int(5 + math.sin(walk_phase * math.pi * 3) * 2)
    pygame.draw.circle(surf, (255, 230, 120), (tip_x, tip_y), glow_r + 3)
    pygame.draw.circle(surf, (255, 255, 200), (tip_x, tip_y), glow_r)

    # Sparkle particles around tip
    phase_i = int(walk_phase * 6) % 5
    sparks = [(-8, -6), (7, -8), (-5, 8), (9, 4), (-10, 2)]
    for i, (sx, sy) in enumerate(sparks):
        if i == phase_i:
            alpha = 200
        else:
            alpha = max(0, 200 - abs(i - phase_i) * 60)
        if alpha > 30:
            c = (255, 240, 160)
            pygame.draw.circle(surf, c, (tip_x + sx, tip_y + sy), 2)


# Minimap overlay
# ══════════════════════════════════════════════════════════════════════════════


def _draw_minimap(
    surf: pygame.Surface,
    game: QuizMazeGame,
    cam:  _Cam,
) -> None:
    """Draw a small top-down fog-of-war minimap in the bottom-left corner."""
    maze    = game._maze
    visited = game.player.visited_cells
    w, h    = maze.width, maze.height
    total_w = w * MINI_CELL
    total_h = h * MINI_CELL
    mx      = MINI_X
    my      = MINI_Y - total_h

    # Background
    bg = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 160))
    surf.blit(bg, (mx, my))

    for r in range(h):
        for c in range(w):
            pos = Position(r, c)
            rx  = mx + c * MINI_CELL
            ry  = my + r * MINI_CELL
            if pos == game.player.position:
                colour = (245, 200, 30)
            elif maze.is_exit(pos) and pos in visited:
                colour = (80, 220, 90)
            elif pos in visited:
                colour = (80, 65, 120)
            else:
                colour = (18, 15, 35)
            pygame.draw.rect(surf, colour, (rx + 1, ry + 1, MINI_CELL - 2, MINI_CELL - 2))

    # Player direction arrow
    px_screen = mx + (cam.x - 0) * MINI_CELL
    py_screen = my + (cam.y - 0) * MINI_CELL
    arrow_len = MINI_CELL * 0.9
    pygame.draw.line(
        surf, (255, 220, 80),
        (int(px_screen), int(py_screen)),
        (int(px_screen + cam.dir_x * arrow_len), int(py_screen + cam.dir_y * arrow_len)),
        2,
    )

    # Border
    pygame.draw.rect(surf, C_PANEL_EDGE, (mx, my, total_w, total_h), 1)


# ══════════════════════════════════════════════════════════════════════════════
# Generic drawing helpers  (self-contained, no import from pygame_main)
# ══════════════════════════════════════════════════════════════════════════════


def _blit_text(
    surf: pygame.Surface,
    msg: str,
    font: pygame.font.Font,
    colour: tuple,
    x: int,
    y: int,
    max_w: int = 0,
) -> int:
    if max_w and font.size(msg)[0] > max_w:
        while msg and font.size(msg + "…")[0] > max_w:
            msg = msg[:-1]
        msg += "…"
    surf.blit(font.render(msg, True, colour), (x, y))
    return y + font.get_linesize()


def _blit_wrapped(surf, msg, font, colour, x, y, max_w):
    chars = max(1, max_w // max(1, font.size("W")[0]))
    for line in textwrap.wrap(msg, chars) or [" "]:
        y = _blit_text(surf, line, font, colour, x, y)
    return y


def _hline(surf, y, x1, x2, colour=None):
    pygame.draw.line(surf, colour or C_DIVIDER, (x1, y), (x2, y))


def _box(surf, rect, fill, border, radius=6):
    pygame.draw.rect(surf, fill,   rect, border_radius=radius)
    pygame.draw.rect(surf, border, rect, 2, border_radius=radius)


def _draw_heart_icon(surf, cx, cy, size, filled):
    c = C_HEART if filled else C_HEART_LOST
    r = max(2, size // 3)
    pygame.draw.circle(surf, c, (cx - r, cy - r // 2), r)
    pygame.draw.circle(surf, c, (cx + r, cy - r // 2), r)
    pygame.draw.polygon(surf, c, [
        (cx - r * 2 + 2, cy),
        (cx + r * 2 - 2, cy),
        (cx,             cy + r * 2),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# HUD — hearts & facing direction (overlaid on 3-D view)
# ══════════════════════════════════════════════════════════════════════════════


_FACING_NAMES = {
    "north": "North  ↑",
    "south": "South  ↓",
    "east":  "East   →",
    "west":  "West   ←",
}


def _draw_hud(
    surf:   pygame.Surface,
    game:   QuizMazeGame,
    hearts: int,
    cam:    _Cam,
    fonts:  dict,
) -> None:
    """Hearts + facing compass drawn on top of the 3-D view."""
    small = fonts["small"]

    hx, hy = VIEW_X + 8, VIEW_Y + 6
    for i in range(MAX_HEARTS):
        _draw_heart_icon(surf, hx + i * 28 + 10, hy + 10, 9, i < hearts)

    dir_name = _snap_direction(cam.angle)
    badge_txt = _FACING_NAMES.get(dir_name, dir_name)
    surf.blit(
        small.render(badge_txt, True, C_GOLD),
        (VIEW_X + VIEW_W - small.size(badge_txt)[0] - 8, VIEW_Y + 6),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Status panel (right side)
# ══════════════════════════════════════════════════════════════════════════════


def _draw_status_panel(
    surf:     pygame.Surface,
    game:     QuizMazeGame,
    messages: deque,
    hearts:   int,
    music_on: bool,
    sfx_on:   bool,
    fonts:    dict,
) -> None:
    bold  = fonts["bold"]
    body  = fonts["body"]
    small = fonts["small"]

    panel_rect = pygame.Rect(STATUS_X, TITLE_H, STATUS_W, WIN_H - TITLE_H - BOTTOM_H)
    _box(surf, panel_rect, C_PANEL_BG, C_PANEL_EDGE, radius=8)

    x = STATUS_X + 14
    y = TITLE_H + 10

    y = _blit_text(surf, "MARAUDER'S MAP", bold, C_TITLE_CLR, x, y)
    _hline(surf, y + 2, STATUS_X + 8, STATUS_X + STATUS_W - 8)
    y += 10

    # Lives row
    lives_lbl = "Courage  "
    surf.blit(body.render(lives_lbl, True, C_TEXT), (x, y))
    lx = x + body.size(lives_lbl)[0]
    for i in range(MAX_HEARTS):
        _draw_heart_icon(surf, lx + i * 24 + 10, y + 9, 8, i < hearts)
    y += body.get_linesize() + 4

    pos      = game.player.position
    exit_pos = game._maze.exit_pos
    rd = exit_pos.row - pos.row
    cd = exit_pos.col - pos.col
    manhattan = abs(rd) + abs(cd)

    if manhattan == 0:
        compass = "The castle gates shimmer before you!"
    elif manhattan <= 2:
        compass = "You sense Hogwarts is very close…"
    elif manhattan <= 4:
        compass = "The forest thins — Hogwarts draws nearer."
    else:
        compass = "The forest stretches on. Keep moving…"

    y = _blit_text(surf, f"House Points   {game.player.score}", body, C_GOLD, x, y)
    y = _blit_text(surf, f"Spells Cast    {len(game.player.questions_answered)}", body, C_TEXT, x, y)
    y += 2

    open_dirs = game._maze.get_open_directions(pos)
    dir_names = {
        "N": "North", "S": "South", "E": "East", "W": "West",
    }
    if open_dirs:
        doors_str = "  ".join(dir_names.get(d.value.upper()[:1], d.value) for d in open_dirs)
    else:
        doors_str = "sealed"
    y = _blit_text(surf, f"Passages   {doors_str}", body, C_AMBER, x, y)
    y += 4
    y = _blit_wrapped(surf, compass, body, C_DIM, x, y, STATUS_W - 28)
    y += 6

    _hline(surf, y, STATUS_X + 8, STATUS_X + STATUS_W - 8)
    y += 8

    y = _blit_text(surf, "OWL POST", bold, C_TITLE_CLR, x, y)
    msg_bottom = panel_rect.bottom - 44
    for msg in messages:
        if y > msg_bottom - small.get_linesize():
            break
        if any(msg.startswith(p) for p in ("Correct", "The fog", "The enchantment",
                                             "Your knowledge", "YOU ESCAPED")):
            mc = C_GREEN
        elif any(msg.startswith(p) for p in ("Wrong", "The magic holds",
                                              "There is no", "No active")):
            mc = C_RED
        elif any(msg.startswith(p) for p in ("Game saved", "Welcome")):
            mc = C_AMBER
        else:
            mc = C_TEXT
        y = _blit_wrapped(surf, msg, small, mc, x, y, STATUS_W - 22)

    # Music + SFX toggle buttons at panel bottom (stacked)
    global _music_btn_rect_game, _sfx_btn_rect_game
    btnw = STATUS_W - 28
    btnh = 28
    btnx = STATUS_X + 14
    sfx_y   = panel_rect.bottom - btnh - 6
    music_y = sfx_y - btnh - 6

    _music_btn_rect_game = pygame.Rect(btnx, music_y, btnw, btnh)
    music_label = "♫  Music: ON" if music_on else "♫  Music: OFF"
    music_col   = C_GREEN if music_on else C_RED
    _box(surf, _music_btn_rect_game, (28, 22, 58), music_col, radius=6)
    _blit_text(surf, music_label, small, music_col,
               btnx + (btnw - small.size(music_label)[0]) // 2,
               music_y + (btnh - small.get_linesize()) // 2)

    _sfx_btn_rect_game = pygame.Rect(btnx, sfx_y, btnw, btnh)
    sfx_label = "SFX: ON" if sfx_on else "SFX: OFF"
    sfx_col   = C_GREEN if sfx_on else C_RED
    _box(surf, _sfx_btn_rect_game, (28, 22, 58), sfx_col, radius=6)
    _blit_text(surf, sfx_label, small, sfx_col,
               btnx + (btnw - small.size(sfx_label)[0]) // 2,
               sfx_y + (btnh - small.get_linesize()) // 2)


# ══════════════════════════════════════════════════════════════════════════════
# Question overlay (on top of 3-D view)
# ══════════════════════════════════════════════════════════════════════════════


def _draw_question_overlay(
    surf:  pygame.Surface,
    game:  QuizMazeGame,
    fonts: dict,
) -> None:
    q    = game._pending_question
    dir_ = game._pending_direction
    if q is None:
        return

    bold  = fonts["bold"]
    body  = fonts["body"]
    small = fonts["small"]

    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    overlay.fill((6, 4, 16, 210))
    surf.blit(overlay, (VIEW_X, VIEW_Y))

    panel_h   = 280
    panel_y   = VIEW_Y + (VIEW_H - panel_h) // 2
    panel_rect = pygame.Rect(VIEW_X + 10, panel_y, VIEW_W - 20, panel_h)
    _box(surf, panel_rect, (18, 12, 42), C_AMBER, radius=10)

    x = panel_rect.x + 16
    y = panel_rect.y + 12
    dir_name = dir_.value.upper() if dir_ else "?"
    y = _blit_text(surf, f"LOCKED DOOR  —  To the {dir_name}", bold, C_AMBER, x, y)
    y += 2
    _hline(surf, y, panel_rect.x + 8, panel_rect.right - 8, C_AMBER)
    y += 8
    surf.blit(small.render(f"[ {q.category.upper()} ]", True, C_GOLD), (x, y))
    y += small.get_linesize() + 4
    y = _blit_wrapped(surf, q.text, body, C_TEXT, x, y, panel_rect.width - 32)
    y += 8
    for i, choice in enumerate(q.choices, 1):
        y = _blit_wrapped(surf, f" {i}.  {choice}", body, C_TEXT, x, y, panel_rect.width - 32)
    y += 6
    hint = "Press  1  2  3  4  to answer"
    _blit_text(surf, hint, small, C_DIM,
               panel_rect.x + (panel_rect.width - small.size(hint)[0]) // 2, y)


# ══════════════════════════════════════════════════════════════════════════════
# Quit confirmation overlay
# ══════════════════════════════════════════════════════════════════════════════


def _draw_quit_confirm(
    surf:  pygame.Surface,
    fonts: dict,
) -> None:
    """Semi-transparent overlay asking the player to confirm quitting."""
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    overlay.fill((6, 4, 16, 200))
    surf.blit(overlay, (VIEW_X, VIEW_Y))

    bold  = fonts["bold"]
    body  = fonts["body"]

    panel_w, panel_h = 400, 140
    panel_x = VIEW_X + (VIEW_W - panel_w) // 2
    panel_y = VIEW_Y + (VIEW_H - panel_h) // 2
    panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    _box(surf, panel_rect, (18, 12, 42), C_AMBER, radius=10)

    x = panel_rect.x + 20
    y = panel_rect.y + 18
    y = _blit_text(surf, "LEAVE THE FOREST?", bold, C_AMBER, x, y)
    y += 8
    y = _blit_text(surf, "Your progress will be saved.", body, C_TEXT, x, y)
    y += 14
    hint = "[ Y ]  Yes, save & quit       [ N ]  Stay"
    _blit_text(surf, hint, body, C_DIM, x, y)


def _draw_exit_confirm(
    surf:  pygame.Surface,
    fonts: dict,
) -> None:
    """Semi-transparent overlay asking the player to confirm leaving via the exit."""
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    overlay.fill((6, 4, 16, 200))
    surf.blit(overlay, (VIEW_X, VIEW_Y))

    bold  = fonts["bold"]
    body  = fonts["body"]

    panel_w, panel_h = 440, 160
    panel_x = VIEW_X + (VIEW_W - panel_w) // 2
    panel_y = VIEW_Y + (VIEW_H - panel_h) // 2
    panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    _box(surf, panel_rect, (18, 12, 42), C_GOLD, radius=10)

    x = panel_rect.x + 20
    y = panel_rect.y + 18
    y = _blit_text(surf, "THE CASTLE GATES!", bold, C_GOLD, x, y)
    y += 6
    y = _blit_text(surf, "You've reached the exit.", body, C_TEXT, x, y)
    y += 4
    y = _blit_text(surf, "Leave the Forbidden Forest?", body, C_TEXT, x, y)
    y += 14
    hint = "[ Y ]  Leave & finish       [ N ]  Keep exploring"
    _blit_text(surf, hint, body, C_DIM, x, y)


# ══════════════════════════════════════════════════════════════════════════════
# Full-screen views: MENU, WIN, NO_HEARTS, SCORES
# ══════════════════════════════════════════════════════════════════════════════


_music_btn_rect      = pygame.Rect(0, 0, 0, 0)
_music_btn_rect_game = pygame.Rect(0, 0, 0, 0)
_sfx_btn_rect        = pygame.Rect(0, 0, 0, 0)
_sfx_btn_rect_game   = pygame.Rect(0, 0, 0, 0)
_size_left_rect      = pygame.Rect(0, 0, 0, 0)
_size_right_rect     = pygame.Rect(0, 0, 0, 0)


def _draw_menu(surf, name_buf, has_saved, size_idx, music_on, sfx_on, fonts):
    global _music_btn_rect
    surf.fill(C_BG)
    title = fonts["title"]
    bold  = fonts["bold"]
    body  = fonts["body"]
    small = fonts["small"]
    cx, y = WIN_W // 2, 75

    h1 = "FORBIDDEN FOREST"
    y  = _blit_text(surf, h1, title, C_TITLE_CLR, cx - title.size(h1)[0] // 2, y)
    h2 = "QUIZ MAZE  —  Hogwarts Edition  [ 3-D MODE ]"
    y  = _blit_text(surf, h2, bold, C_GOLD, cx - bold.size(h2)[0] // 2, y)
    y += 18
    pr = "Enter your Hogwarts name:"
    y  = _blit_text(surf, pr, body, C_TEXT, cx - body.size(pr)[0] // 2, y)
    y += 6
    cursor   = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
    display  = name_buf + cursor
    bw, bh   = 360, 38
    box_rect = pygame.Rect(cx - bw // 2, y, bw, bh)
    _box(surf, box_rect, (28, 22, 58), C_PANEL_EDGE, radius=6)
    _blit_text(surf, display, body, C_GOLD, box_rect.x + 12, box_rect.y + 9)
    y += bh + 14

    # Maze size selector
    global _size_left_rect, _size_right_rect
    sz_label = "Maze size:"
    y = _blit_text(surf, sz_label, body, C_TEXT, cx - body.size(sz_label)[0] // 2, y)
    y += 4
    sw, sh = 280, 36
    btn_w = 44
    sz_rect = pygame.Rect(cx - sw // 2, y, sw, sh)

    _size_left_rect  = pygame.Rect(sz_rect.x, sz_rect.y, btn_w, sh)
    _size_right_rect = pygame.Rect(sz_rect.right - btn_w, sz_rect.y, btn_w, sh)

    _box(surf, sz_rect, (28, 22, 58), C_PANEL_EDGE, radius=6)
    _box(surf, _size_left_rect, (38, 30, 68), C_GOLD, radius=6)
    _box(surf, _size_right_rect, (38, 30, 68), C_GOLD, radius=6)

    arr_l = "◄"
    _blit_text(surf, arr_l, bold, C_GOLD,
               _size_left_rect.x + (btn_w - bold.size(arr_l)[0]) // 2,
               _size_left_rect.y + (sh - bold.get_linesize()) // 2)
    arr_r = "►"
    _blit_text(surf, arr_r, bold, C_GOLD,
               _size_right_rect.x + (btn_w - bold.size(arr_r)[0]) // 2,
               _size_right_rect.y + (sh - bold.get_linesize()) // 2)

    mw, mh = MAZE_SIZES[size_idx]
    sz_text = f"{mw} x {mh}"
    _blit_text(surf, sz_text, bold, C_GOLD,
               cx - bold.size(sz_text)[0] // 2,
               sz_rect.y + (sh - bold.get_linesize()) // 2)
    y += sh + 4
    _blit_text(surf, "click arrows or ← →", small, C_DIM,
               cx - small.size("click arrows or ← →")[0] // 2, y)
    y += small.get_linesize() + 12

    # Music + SFX toggle buttons (side by side)
    global _sfx_btn_rect
    btnw, btnh = 190, 36
    gap = 10
    total_w = btnw * 2 + gap
    bx = cx - total_w // 2

    music_label = "♫  Music: ON" if music_on else "♫  Music: OFF"
    music_col   = C_GREEN if music_on else C_RED
    _music_btn_rect = pygame.Rect(bx, y, btnw, btnh)
    _box(surf, _music_btn_rect, (28, 22, 58), music_col, radius=6)
    _blit_text(surf, music_label, bold, music_col,
               _music_btn_rect.x + (btnw - bold.size(music_label)[0]) // 2,
               _music_btn_rect.y + (btnh - bold.get_linesize()) // 2)

    sfx_label = "SFX: ON" if sfx_on else "SFX: OFF"
    sfx_col   = C_GREEN if sfx_on else C_RED
    _sfx_btn_rect = pygame.Rect(bx + btnw + gap, y, btnw, btnh)
    _box(surf, _sfx_btn_rect, (28, 22, 58), sfx_col, radius=6)
    _blit_text(surf, sfx_label, bold, sfx_col,
               _sfx_btn_rect.x + (btnw - bold.size(sfx_label)[0]) // 2,
               _sfx_btn_rect.y + (btnh - bold.get_linesize()) // 2)
    y += btnh + 14

    hint = "Press ENTER to begin"
    _blit_text(surf, hint, small, C_DIM, cx - small.size(hint)[0] // 2, y)
    if has_saved and name_buf.strip():
        y += small.get_linesize() + 4
        s2 = "( saved game found — press ENTER to resume )"
        _blit_text(surf, s2, small, C_AMBER, cx - small.size(s2)[0] // 2, y)


def _draw_win(surf, game, fonts):
    surf.fill(C_BG)
    title = fonts["title"]
    bold  = fonts["bold"]
    body  = fonts["body"]
    small = fonts["small"]
    cx, y = WIN_W // 2, 115
    h1 = "YOU ESCAPED!"
    y  = _blit_text(surf, h1, title, C_GOLD, cx - title.size(h1)[0] // 2, y)
    h2 = "THE FORBIDDEN FOREST IS BEHIND YOU"
    y  = _blit_text(surf, h2, bold, C_GREEN, cx - bold.size(h2)[0] // 2, y)
    y += 24
    for label, value in [
        ("Witch / Wizard",     game.player.name),
        ("House Points",       str(game.player.score)),
        ("Spells Cast",        str(len(game.player.questions_answered))),
    ]:
        line = f"{label:<24} {value}"
        y = _blit_text(surf, line, body, C_TEXT, cx - body.size(line)[0] // 2, y)
        y += 4
    y += 20
    hint = "[ R ]  Play again      [ ESC ]  Quit"
    _blit_text(surf, hint, small, C_DIM, cx - small.size(hint)[0] // 2, y)


def _draw_no_hearts(surf, player_name, fonts):
    surf.fill(C_BG)
    title = fonts["title"]
    bold  = fonts["bold"]
    body  = fonts["body"]
    small = fonts["small"]
    cx, y = WIN_W // 2, 105
    h1 = "THE FOREST CLAIMS YOU"
    y  = _blit_text(surf, h1, title, C_HEART, cx - title.size(h1)[0] // 2, y)
    h2 = "All three lives lost."
    y  = _blit_text(surf, h2, bold, C_RED, cx - bold.size(h2)[0] // 2, y)
    y += 20
    for i in range(MAX_HEARTS):
        _draw_heart_icon(surf, cx - 52 + i * 52, y + 18, 16, False)
    y += 52
    msg = f"Courage, {player_name}. A new maze awaits…"
    y = _blit_text(surf, msg, body, C_TEXT, cx - body.size(msg)[0] // 2, y)
    y += 8
    hint = "Press any key to continue"
    _blit_text(surf, hint, small, C_DIM, cx - small.size(hint)[0] // 2, y)


def _draw_scores(surf, scores, fonts):
    surf.fill(C_BG)
    title = fonts["title"]
    bold  = fonts["bold"]
    body  = fonts["body"]
    small = fonts["small"]
    cx, y = WIN_W // 2, 60
    h1 = "HALL OF MAGICAL ACHIEVEMENT"
    y  = _blit_text(surf, h1, title, C_GOLD, cx - title.size(h1)[0] // 2, y)
    y += 18
    if not scores:
        msg = "No scores recorded yet."
        _blit_text(surf, msg, body, C_DIM, cx - body.size(msg)[0] // 2, y)
    else:
        hdr = f"  {'#':<4}  {'Name':<22}  {'Score':>7}  Status"
        y = _blit_text(surf, hdr, bold, C_TITLE_CLR, cx - bold.size(hdr)[0] // 2, y)
        _hline(surf, y + 2, cx - 240, cx + 240)
        y += 10
        for rank, s in enumerate(scores, 1):
            status_str = "Completed" if s.completed else "Quit"
            col        = C_GREEN if s.completed else C_DIM
            row        = f"  {rank:<4}  {s.player_name:<22}  {s.score:>7}  {status_str}"
            y = _blit_text(surf, row, body, col, cx - body.size(row)[0] // 2, y)
            y += 2
    y += 28
    back = "Press any key to return"
    _blit_text(surf, back, small, C_DIM, cx - small.size(back)[0] // 2, y)


# ══════════════════════════════════════════════════════════════════════════════
# Persistent chrome: title bar & controls bar
# ══════════════════════════════════════════════════════════════════════════════


def _draw_title_bar(surf, fonts):
    pygame.draw.rect(surf, C_PANEL_BG, (0, 0, WIN_W, TITLE_H))
    pygame.draw.line(surf, C_PANEL_EDGE, (0, TITLE_H - 1), (WIN_W, TITLE_H - 1))
    bold  = fonts["bold"]
    label = "  ✦  FORBIDDEN FOREST QUIZ MAZE  —  Hogwarts Edition  [ 3-D ]  ✦"
    _blit_text(surf, label, bold, C_TITLE_CLR, 8, (TITLE_H - bold.get_linesize()) // 2)


def _draw_controls_bar(surf, state, fonts):
    y0 = WIN_H - BOTTOM_H
    pygame.draw.rect(surf, C_PANEL_BG, (0, y0, WIN_W, BOTTOM_H))
    pygame.draw.line(surf, C_PANEL_EDGE, (0, y0), (WIN_W, y0))
    small = fonts["small"]
    lh = small.get_linesize()

    hints_line1 = {
        _State.MENU:         "  [ Enter ] Begin         [ ← → ] Maze size         [ ESC ] Quit",
        _State.PLAYING:      "  [ Mouse / ←→ ] Look    [ ↑ / W ] Move    [ A / D ] Strafe    [ 1-4 ] Answer",
        _State.QUESTION:     "  [ 1 ]  [ 2 ]  [ 3 ]  [ 4 ]  —  Choose your answer",
        _State.WIN:          "  [ R ] Play again    [ ESC ] Quit",
        _State.SCORES:       "  [ Any key ] Return to game",
        _State.NO_HEARTS:    "  [ Any key ] Begin new maze",
        _State.EXIT_CONFIRM: "  [ Y ] Leave the forest    [ N / ESC ] Keep exploring",
        _State.QUIT_CONFIRM: "  [ Y ] Save & quit    [ N / ESC ] Stay",
    }
    hints_line2 = {
        _State.PLAYING:   "  [ Ctrl+S ] Save    [ M ] Map    Music: click toggle button    [ Tab ] Scores    [ ESC ] Quit",
    }

    line1 = hints_line1.get(state, "")
    line2 = hints_line2.get(state, "")

    if line2:
        _blit_text(surf, line1, small, C_DIM, 0, y0 + 4)
        _blit_text(surf, line2, small, C_DIM, 0, y0 + 4 + lh)
    else:
        _blit_text(surf, line1, small, C_DIM, 0, y0 + (BOTTOM_H - lh) // 2)


# ══════════════════════════════════════════════════════════════════════════════
# Movement helpers
# ══════════════════════════════════════════════════════════════════════════════


def _snap_direction(angle: float) -> str:
    """Return the cardinal direction closest to *angle* radians."""
    a = angle % (2 * math.pi)
    if a < 0:
        a += 2 * math.pi
    # angle 0=east, π/2=south, π=west, 3π/2=north
    if a < math.pi / 4 or a >= 7 * math.pi / 4:
        return "east"
    if a < 3 * math.pi / 4:
        return "south"
    if a < 5 * math.pi / 4:
        return "west"
    return "north"


def _try_move(cam: _Cam, dx: float, dy: float, maze) -> bool:
    """Attempt to slide *cam* by (dx, dy); returns True if any movement happened."""
    new_x = cam.x + dx
    new_y = cam.y + dy
    w, h  = maze.width, maze.height
    moved = False

    # Try x independently (wall sliding)
    cx_new = int(new_x)
    cy_cur = int(cam.y)
    if 0 <= cx_new < w and 0 <= cy_cur < h:
        if not _wall_between(cy_cur, int(cam.x), cy_cur, cx_new, maze):
            cam.x = new_x
            moved = True

    # Try y independently
    cx_cur = int(cam.x)
    cy_new = int(new_y)
    if 0 <= cx_cur < w and 0 <= cy_new < h:
        if not _wall_between(int(cam.y), cx_cur, cy_new, cx_cur, maze):
            cam.y = new_y
            moved = True

    return moved


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    pygame.mixer.pre_init(_SAMPLE_RATE, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption("Forbidden Forest Quiz Maze — 3-D Edition")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    clock  = pygame.time.Clock()

    # ── Fonts ──────────────────────────────────────────────────────────────────
    try:
        def _f(size, bold=False):
            return pygame.font.SysFont("Consolas", size, bold=bold)
        fonts = {
            "title": _f(36, bold=True),
            "bold":  _f(18, bold=True),
            "body":  _f(16),
            "small": _f(13),
        }
    except Exception:
        fonts = {
            "title": pygame.font.Font(None, 52),
            "bold":  pygame.font.Font(None, 28),
            "body":  pygame.font.Font(None, 24),
            "small": pygame.font.Font(None, 20),
        }

    # ── Sound ──────────────────────────────────────────────────────────────────
    pygame.mixer.set_num_channels(16)
    sounds   = _make_sounds()

    # BGM: prefer MP3 file; fall back to procedural ambient loop
    bgm_is_music_file = False
    bgm_proc_sound:   pygame.mixer.Sound    | None = None
    bgm_proc_channel: pygame.mixer.Channel  | None = None

    bgm_mp3_path = _resolve_bgm_mp3_path()
    if bgm_mp3_path is not None:
        try:
            pygame.mixer.music.load(str(bgm_mp3_path))
            pygame.mixer.music.set_volume(0.5)
            bgm_is_music_file = True
        except Exception:
            bgm_is_music_file = False

    if not bgm_is_music_file:
        # Generate procedural ambient loop (runs once at startup)
        bgm_proc_sound   = _synth_bgm_loop()
        bgm_proc_sound.set_volume(0.45)
        bgm_proc_channel = pygame.mixer.Channel(15)

    # ── Unified BGM helpers ─────────────────────────────────────────────────
    def _bgm_play() -> None:
        if bgm_is_music_file:
            pygame.mixer.music.play(loops=-1)
        elif bgm_proc_channel and bgm_proc_sound:
            bgm_proc_channel.play(bgm_proc_sound, loops=-1)

    def _bgm_stop() -> None:
        if bgm_is_music_file:
            pygame.mixer.music.stop()
        elif bgm_proc_channel:
            bgm_proc_channel.stop()

    def _bgm_pause() -> None:
        if bgm_is_music_file:
            pygame.mixer.music.pause()
        elif bgm_proc_channel:
            bgm_proc_channel.pause()

    def _bgm_unpause() -> None:
        if bgm_is_music_file:
            pygame.mixer.music.unpause()
        elif bgm_proc_channel and bgm_proc_sound:
            if bgm_proc_channel.get_busy():
                bgm_proc_channel.unpause()
            else:
                bgm_proc_channel.play(bgm_proc_sound, loops=-1)

    # ── Repository ─────────────────────────────────────────────────────────────
    repo = SQLModelRepository(_DB_URL)
    seed_questions_if_empty(repo)

    # ── State ──────────────────────────────────────────────────────────────────
    state:        _State              = _State.MENU
    game:         QuizMazeGame | None = None
    cam:          _Cam | None         = None
    messages:     deque               = deque(maxlen=MAX_MSG)
    name_buf:     str                 = ""
    has_saved:    bool                = False
    scores_cache: list                = []
    hearts:          int                 = MAX_HEARTS
    show_minimap:    bool                = True
    walk_target:     tuple[float, float] | None = None
    walk_phase:      float               = 0.0   # continuous walk cycle for wand bob
    size_idx:        int                 = 1      # index into MAZE_SIZES (default 5x5)
    music_on:        bool                = True
    sfx_on:          bool                = True
    # Lightning / thunder state
    lightning_cooldown: float            = random.uniform(8, 18)   # seconds until next strike
    lightning_events:   list             = []    # [(start, end, alpha), …] for current flash
    lightning_t:        float            = 0.0   # time elapsed since flash was triggered
    thunder_delay:      float            = 0.0   # countdown before thunder sound plays

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _push(msg: str) -> None:
        lines = [ln.strip() for ln in msg.strip().splitlines() if ln.strip()]
        for line in reversed(lines):
            messages.appendleft(line)

    def _start_session(name: str, resume: bool, maze_w: int = 5, maze_h: int = 5) -> None:
        nonlocal game, cam, hearts, walk_target, walk_phase
        maze = generate_maze(maze_w, maze_h)
        game = QuizMazeGame(
            player_name=name, maze=maze,
            game_repo=repo, score_repo=repo, question_repo=repo,
        )
        game.confirm_exit_enabled = True
        if resume and repo.load_game(name):
            _push(game.resume_game())
        else:
            _push(game.start_new_game())
        hearts      = MAX_HEARTS
        walk_target = None
        walk_phase  = 0.0
        start       = game._maze.start
        cam         = _make_cam(start, maze.height // 2, maze.width // 2)

    def _trigger_lightning() -> None:
        """Set up a new lightning strike: multi-flicker flash + delayed thunder."""
        nonlocal lightning_events, lightning_t, thunder_delay, lightning_cooldown
        # Build a sequence of (start, end, alpha) flicker intervals
        flickers = [(0.00, 0.07, 210), (0.11, 0.18, 160)]
        if random.random() < 0.45:          # 45 % chance of a third flicker
            flickers.append((0.26, 0.32, 110))
        lightning_events   = flickers
        lightning_t        = 0.0
        thunder_delay      = random.uniform(0.4, 2.8)   # simulated distance
        lightning_cooldown = random.uniform(10, 28)

    def _play_sound(key: str) -> None:
        if not sfx_on:
            return
        snd = sounds.get(key)
        if snd:
            snd.play()

    # ── Event loop ─────────────────────────────────────────────────────────────
    while True:
        dt = clock.tick(FPS) / 1000.0  # delta time in seconds

        _prev_state = state
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if game and game.game_active:
                    game.quit_game()
                pygame.quit()
                sys.exit()

            # ── MENU ──────────────────────────────────────────────────────────
            if state == _State.MENU:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if _size_left_rect.collidepoint(event.pos):
                        size_idx = (size_idx - 1) % len(MAZE_SIZES)
                    elif _size_right_rect.collidepoint(event.pos):
                        size_idx = (size_idx + 1) % len(MAZE_SIZES)
                    elif _music_btn_rect.collidepoint(event.pos):
                        music_on = not music_on
                        if music_on:
                            _bgm_unpause()
                        else:
                            _bgm_pause()
                    elif _sfx_btn_rect.collidepoint(event.pos):
                        sfx_on = not sfx_on

                elif event.type == pygame.KEYDOWN:
                    old = name_buf.strip()
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    elif event.key == pygame.K_RETURN and name_buf.strip():
                        saved = repo.load_game(name_buf.strip())
                        mw, mh = MAZE_SIZES[size_idx]
                        _start_session(name_buf.strip(), resume=bool(saved), maze_w=mw, maze_h=mh)
                        state = _State.PLAYING
                    elif event.key == pygame.K_LEFT:
                        size_idx = (size_idx - 1) % len(MAZE_SIZES)
                    elif event.key == pygame.K_RIGHT:
                        size_idx = (size_idx + 1) % len(MAZE_SIZES)
                    elif event.key == pygame.K_BACKSPACE:
                        name_buf = name_buf[:-1]
                    elif event.unicode and event.unicode.isprintable() and len(name_buf) < 24:
                        name_buf += event.unicode
                    new = name_buf.strip()
                    if new != old:
                        has_saved = bool(new) and repo.load_game(new) is not None

            # ── PLAYING ───────────────────────────────────────────────────────
            elif state == _State.PLAYING:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if _music_btn_rect_game.collidepoint(event.pos):
                        music_on = not music_on
                        if music_on:
                            _bgm_unpause()
                        else:
                            _bgm_pause()
                    elif _sfx_btn_rect_game.collidepoint(event.pos):
                        sfx_on = not sfx_on

                elif event.type == pygame.KEYDOWN:
                    key = event.key
                    mod = event.mod

                    # Move forward (snapped to faced direction)
                    if key in (pygame.K_UP, pygame.K_w) and not (mod & pygame.KMOD_CTRL) and walk_target is None:
                        direction_str = _snap_direction(cam.angle)
                        result = game.move(direction_str)
                        _push(result)
                        _play_sound("bump" if "wall" in result.lower() or "no door" in result.lower() else
                                    "door" if game._pending_question else
                                    "step")
                        if game._pending_question:
                            state = _State.QUESTION
                        elif game._pending_exit:
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)
                            state = _State.EXIT_CONFIRM
                        elif game.game_won:
                            _play_sound("win")
                            state = _State.WIN
                        else:
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)

                    # Strafe left (A)
                    elif key == pygame.K_a and not (mod & pygame.KMOD_CTRL) and walk_target is None:
                        strafe_dir = (_snap_direction((cam.angle - math.pi / 2) % (2 * math.pi)))
                        result = game.move(strafe_dir)
                        _push(result)
                        if game._pending_question:
                            state = _State.QUESTION
                        elif game._pending_exit:
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)
                            state = _State.EXIT_CONFIRM
                        elif game.game_won:
                            _play_sound("win"); state = _State.WIN
                        else:
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)

                    # Strafe right (D)
                    elif key == pygame.K_d and not (mod & pygame.KMOD_CTRL) and walk_target is None:
                        strafe_dir = (_snap_direction((cam.angle + math.pi / 2) % (2 * math.pi)))
                        result = game.move(strafe_dir)
                        _push(result)
                        if game._pending_question:
                            state = _State.QUESTION
                        elif game._pending_exit:
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)
                            state = _State.EXIT_CONFIRM
                        elif game.game_won:
                            _play_sound("win"); state = _State.WIN
                        else:
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)

                    elif key == pygame.K_s and (mod & pygame.KMOD_CTRL):
                        game.save_game()
                        _push("Game saved to the Hogwarts records.")

                    elif key == pygame.K_m:
                        show_minimap = not show_minimap

                    elif key == pygame.K_TAB:
                        scores_cache = repo.get_high_scores(10)
                        state = _State.SCORES

                    elif key == pygame.K_ESCAPE:
                        state = _State.QUIT_CONFIRM

            # ── QUESTION ──────────────────────────────────────────────────────
            elif state == _State.QUESTION:
                if event.type == pygame.KEYDOWN:
                    ans = {
                        pygame.K_1: 1, pygame.K_KP1: 1,
                        pygame.K_2: 2, pygame.K_KP2: 2,
                        pygame.K_3: 3, pygame.K_KP3: 3,
                        pygame.K_4: 4, pygame.K_KP4: 4,
                    }.get(event.key)
                    if ans is not None:
                        result = game.answer_question(ans)
                        _push(result)
                        if game._pending_exit:
                            _play_sound("correct")
                            new_pos = game.player.position
                            walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)
                            state = _State.EXIT_CONFIRM
                        elif game.game_won:
                            _play_sound("win"); state = _State.WIN
                        elif not game._pending_question:
                            if result.startswith("Wrong"):
                                _play_sound("wrong")
                                hearts -= 1
                                if hearts <= 0:
                                    _play_sound("no_hearts")
                                    state = _State.NO_HEARTS
                                else:
                                    state = _State.PLAYING
                            else:
                                _play_sound("correct")
                                new_pos = game.player.position
                                walk_target = (new_pos.col + 0.5, new_pos.row + 0.5)
                                state = _State.PLAYING

            # ── WIN ───────────────────────────────────────────────────────────
            elif state == _State.WIN:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        messages.clear()
                        mw, mh = MAZE_SIZES[size_idx]
                        _start_session(game.player.name, resume=False, maze_w=mw, maze_h=mh)
                        state = _State.PLAYING
                    elif event.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()

            # ── NO_HEARTS ─────────────────────────────────────────────────────
            elif state == _State.NO_HEARTS:
                if event.type == pygame.KEYDOWN:
                    messages.clear()
                    mw, mh = MAZE_SIZES[size_idx]
                    _start_session(game.player.name, resume=False, maze_w=mw, maze_h=mh)
                    state = _State.PLAYING

            # ── SCORES ────────────────────────────────────────────────────────
            elif state == _State.SCORES:
                if event.type == pygame.KEYDOWN:
                    state = _State.PLAYING

            # ── EXIT_CONFIRM ─────────────────────────────────────────────────
            elif state == _State.EXIT_CONFIRM:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_y, pygame.K_RETURN):
                        result = game.confirm_exit(True)
                        _push(result)
                        _play_sound("win")
                        state = _State.WIN
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        result = game.confirm_exit(False)
                        _push(result)
                        state = _State.PLAYING

            # ── QUIT_CONFIRM ─────────────────────────────────────────────────
            elif state == _State.QUIT_CONFIRM:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_y, pygame.K_RETURN):
                        game.quit_game()
                        pygame.quit()
                        sys.exit()
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        state = _State.PLAYING

        # ── BGM state transitions ──────────────────────────────────────────────
        if _prev_state != state:
            if state == _State.PLAYING:
                if _prev_state in (_State.MENU, _State.WIN, _State.NO_HEARTS):
                    if music_on:
                        _bgm_play()
            elif state in (_State.WIN, _State.NO_HEARTS):
                _bgm_stop()

        # ── Mouse grab management ──────────────────────────────────────────────
        if _prev_state != state:
            if state == _State.PLAYING:
                pygame.event.set_grab(True)
                pygame.mouse.set_visible(False)
                pygame.mouse.get_rel()          # flush stale delta
            elif _prev_state == _State.PLAYING or state in (_State.QUIT_CONFIRM, _State.EXIT_CONFIRM):
                pygame.event.set_grab(False)
                pygame.mouse.set_visible(True)

        # ── Smooth walk interpolation (ease-out) ──────────────────────────────
        if walk_target is not None and cam:
            walk_phase += dt * WALK_SPEED
            tx, ty = walk_target
            dx = tx - cam.x
            dy = ty - cam.y
            dist = math.hypot(dx, dy)
            if dist < 0.01:
                cam.x, cam.y = tx, ty
                walk_target = None
            else:
                ease = max(0.4, dist)
                step = min(WALK_SPEED * ease * dt, dist)
                cam.x += dx / dist * step
                cam.y += dy / dist * step

        # ── Lightning & thunder update ─────────────────────────────────────────
        if state == _State.PLAYING:
            lightning_cooldown -= dt
            if lightning_cooldown <= 0:
                _trigger_lightning()

        if lightning_events:
            lightning_t += dt
            # Expire events whose end time has passed
            lightning_events = [e for e in lightning_events if lightning_t <= e[1] + 0.04]

        if thunder_delay > 0:
            thunder_delay -= dt
            if thunder_delay <= 0:
                _play_sound("thunder")
                thunder_delay = 0.0

        # ── Continuous rotation (held keys + mouse) ────────────────────────────
        if state == _State.PLAYING and cam:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LEFT]:
                cam.rotate(-TURN_SPEED)
            if keys[pygame.K_RIGHT]:
                cam.rotate(TURN_SPEED)

            mouse_dx, _ = pygame.mouse.get_rel()
            if mouse_dx:
                cam.rotate(mouse_dx * MOUSE_SENS)

        # ── Render ─────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        if state == _State.MENU:
            _draw_menu(screen, name_buf, has_saved, size_idx, music_on, sfx_on, fonts)

        elif state == _State.WIN:
            _draw_win(screen, game, fonts)

        elif state == _State.NO_HEARTS:
            _draw_no_hearts(screen, game.player.name, fonts)

        elif state == _State.SCORES:
            _draw_scores(screen, scores_cache, fonts)

        else:  # PLAYING, QUESTION, QUIT_CONFIRM, or EXIT_CONFIRM
            # 3-D raycasting frame
            zbuffer, fog_hits = _raycast_frame(
                screen, cam, game._maze, game.player.visited_cells,
            )

            # Lightning flash overlay
            flash_alpha = 0
            for start, end, alpha in lightning_events:
                if start <= lightning_t <= end + 0.04:
                    progress   = (lightning_t - start) / max(0.001, end - start)
                    fade       = 1.0 - abs(progress * 2 - 1)   # ramps up then down
                    flash_alpha = max(flash_alpha, int(alpha * fade))
            if flash_alpha > 5:
                flash_surf = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
                flash_surf.fill((210, 225, 255, flash_alpha))
                screen.blit(flash_surf, (VIEW_X, VIEW_Y))

            # Enchanted fog at passage boundaries (lifts when questions run out)
            _draw_passage_fog(screen, fog_hits, game.questions_exhausted)

            # Golden floor tint at the exit cell
            _draw_exit_floor(screen, game._maze.exit_pos, cam, zbuffer)

            # Atmospheric forest fog (ground mist, wisps, ceiling mist)
            _draw_forest_fog(screen, pygame.time.get_ticks() / 1000.0)

            # Minimap overlay
            if show_minimap:
                _draw_minimap(screen, game, cam)

            # First-person wand / hand
            _draw_wand(screen, walk_phase, walk_target is not None)

            # HUD overlay (hearts + facing direction)
            _draw_hud(screen, game, hearts, cam, fonts)

            # Status panel
            _draw_status_panel(screen, game, messages, hearts, music_on, sfx_on, fonts)

            # Question panel (if active)
            if state == _State.QUESTION:
                _draw_question_overlay(screen, game, fonts)

            # Exit confirmation overlay
            if state == _State.EXIT_CONFIRM:
                _draw_exit_confirm(screen, fonts)

            # Quit confirmation overlay
            if state == _State.QUIT_CONFIRM:
                _draw_quit_confirm(screen, fonts)

        # Persistent chrome on every in-game frame
        if state not in (_State.MENU, _State.WIN, _State.NO_HEARTS, _State.SCORES):
            _draw_title_bar(screen, fonts)
        _draw_controls_bar(screen, state, fonts)

        pygame.display.flip()


if __name__ == "__main__":
    main()
