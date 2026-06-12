TILE_SIZE = 48          # pixels per tile
GRID_COLS = 29
GRID_ROWS = 25
WINDOW_W = 1200         # fixed screen resolution, independent of map size
WINDOW_H = 900
WINDOW_TITLE = "Explosion Boy"

TARGET_FPS = 60
TICK_RATE = 20          # server authoritative ticks per second
INPUT_LEAD_TICKS = 5    # client tick counter runs this many ticks ahead of server
DEFAULT_PORT = 9000
MAX_PLAYERS = 16

BOMB_FUSE_TICKS = 60            # 3 seconds at 20 tps
DEFAULT_BLAST_RADIUS = 2
EXPLOSION_DURATION_TICKS = 10
SOFT_BLOCK_DROP_CHANCE = 0.25

MAX_PLAYER_SPEED = 180.0        # pixels per second
PLAYER_RADIUS = TILE_SIZE * 0.38
BOMB_HALF_SIZE = TILE_SIZE * 0.4
PUSH_IMPULSE = 250.0            # impulse transferred to bomb on contact
BOMB_FRICTION = 3.0
PLAYER_DAMPING = 0.25           # pymunk body velocity damping factor

# 16 spawn points on a 29×25 grid — ordered so N-player games use first N.
# No spawn lands on a pillar (pillars are at even-col AND even-row).
SPAWN_POINTS: list[tuple[int, int]] = [
    (1,   1),  (27,  1),  (1,  23),  (27, 23),   # corners
    (14,  1),  (14, 23),  (1,  12),  (27, 12),   # mid-edges
    (7,   6),  (21,  6),  (7,  18),  (21, 18),   # inner ring 1
    (7,  12),  (21, 12),  (14,  7),  (14, 17),   # inner ring 2
]

# ── Rendering colours ─────────────────────────────────────────────────────────
# All colours are (R, G, B, A) tuples with values 0–255.

SOLID_WALL_COLOUR:  tuple[int, int, int, int] = (64,  64,  64,  255)   # dark grey
SOFT_BLOCK_COLOUR:  tuple[int, int, int, int] = (139, 69,  19,  255)   # saddle brown
EMPTY_TILE_COLOUR:  tuple[int, int, int, int] = (211, 211, 211, 255)   # light grey

EXPLOSION_COLOUR:   tuple[int, int, int, int] = (255, 180, 0,   200)
BOMB_BASE_COLOUR:   tuple[int, int, int, int] = (30,  30,  30,  255)
BOMB_PULSE_COLOUR:  tuple[int, int, int, int] = (255, 220, 0,   255)

# Keyed by PowerupKind value
POWERUP_COLOURS: dict[int, tuple[int, int, int, int]] = {
    1: (255, 215, 0,   255),   # gold        (EXTRA_BOMB)
    2: (255, 69,  0,   255),   # orange-red  (BLAST_UP)
    3: (100, 200, 255, 255),   # sky blue    (SHIELD)
    4: (200, 50,  220, 255),   # purple      (REVERSE_CONTROLS)
    5: (50,  220, 80,  255),   # green       (SPEED_UP)
    6: (60,  60,  60,  255),   # dark grey   (SKULL)
    7: (255, 50,  50,  255),   # bright red  (SUPER_BOMB)
    8: (255, 140, 0,   255),   # deep orange (CLUSTER_BOMB)
    9: (139, 90,  43,  255),   # earthy brown (RUBBLE_BOMB)
}

POWERUP_SYMBOLS: dict[int, str] = {
    1: '+',    # EXTRA_BOMB
    2: '↑',  # BLAST_UP       (↑)
    3: '\U0001f6e1',  # SHIELD     (🛡)
    4: '?',    # REVERSE_CONTROLS
    5: '⚡',  # SPEED_UP      (⚡)
    6: '☠',  # SKULL         (☠)
    7: '★',  # SUPER_BOMB    (★)
    8: '#',    # CLUSTER_BOMB
    9: '\U0001faa8',  # RUBBLE_BOMB   (🪨)
}

PLAYER_COLOURS = [
    (220, 50,  50,  255),   # red
    (50,  120, 220, 255),   # blue
    (50,  200, 80,  255),   # green
    (230, 180, 40,  255),   # yellow
    (180, 80,  220, 255),   # purple
    (240, 130, 40,  255),   # orange
    (40,  210, 210, 255),   # cyan
    (230, 100, 160, 255),   # pink
    (150, 100, 60,  255),   # brown
    (150, 150, 150, 255),   # grey
    (80,  160, 100, 255),   # teal
    (200, 200, 80,  255),   # lime
    (220, 50,  150, 255),   # magenta
    (50,  160, 240, 255),   # sky blue
    (180, 120, 60,  255),   # tan
    (120, 60,  180, 255),   # violet
]

# ── Local colour overrides ─────────────────────────────────────────────────────
# If a colours.py file exists at the project root it is loaded here, letting
# you override any colour constant above without touching this file.
# colours.py is gitignored — see example.colours.py for available options.
try:
    from colours import *  # noqa: F401, F403
except ImportError:
    pass
