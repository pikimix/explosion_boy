TILE_SIZE = 48          # pixels per tile
GRID_COLS = 25
GRID_ROWS = 21
WINDOW_W = TILE_SIZE * GRID_COLS   # 1200
WINDOW_H = TILE_SIZE * GRID_ROWS   # 1008
WINDOW_TITLE = "Explosion Boy"

TARGET_FPS = 60
TICK_RATE = 20          # server authoritative ticks per second
DEFAULT_PORT = 9000
MAX_PLAYERS = 12

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

# 12 spawn points on a 25×21 grid — ordered so N-player games use first N
SPAWN_POINTS: list[tuple[int, int]] = [
    (1, 1),   (23, 1),   (1, 19),  (23, 19),   # corners
    (12, 1),  (12, 19),  (1, 10),  (23, 10),   # mid-edges
    (6, 5),   (18, 5),   (6, 15),  (18, 15),   # inner ring
]

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
]
