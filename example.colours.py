# Explosion Boy — local colour overrides
# Copy this file to colours.py and uncomment / edit the values you want to change.
# colours.py is gitignored so your changes won't affect other players.
#
# All colours are (R, G, B, A) tuples; values 0–255.
# The alpha channel controls transparency — use 255 for fully opaque.

# ── Tiles ──────────────────────────────────────────────────────────────────────
# SOLID_WALL_COLOUR  = (64,  64,  64,  255)   # dark grey
# SOFT_BLOCK_COLOUR  = (139, 69,  19,  255)   # saddle brown
# EMPTY_TILE_COLOUR  = (211, 211, 211, 255)   # light grey

# ── Bombs ──────────────────────────────────────────────────────────────────────
# BOMB_BASE_COLOUR   = (30,  30,  30,  255)   # resting colour
# BOMB_PULSE_COLOUR  = (255, 220, 0,   255)   # peak of fuse pulse

# ── Explosions ─────────────────────────────────────────────────────────────────
# EXPLOSION_COLOUR   = (255, 180, 0,   200)   # semi-transparent orange

# ── Powerups ───────────────────────────────────────────────────────────────────
# Keyed by PowerupKind value: 1 = extra bomb, 2 = blast radius up.
# POWERUP_COLOURS = {
#     1: (255, 215, 0,   255),   # gold
#     2: (255, 69,  0,   255),   # orange-red
# }

# ── Players ────────────────────────────────────────────────────────────────────
# List of up to 16 colours, one per player slot (index = player ID mod 16).
# PLAYER_COLOURS = [
#     (220, 50,  50,  255),   # red
#     (50,  120, 220, 255),   # blue
#     (50,  200, 80,  255),   # green
#     (230, 180, 40,  255),   # yellow
#     (180, 80,  220, 255),   # purple
#     (240, 130, 40,  255),   # orange
#     (40,  210, 210, 255),   # cyan
#     (230, 100, 160, 255),   # pink
#     (150, 100, 60,  255),   # brown
#     (150, 150, 150, 255),   # grey
#     (80,  160, 100, 255),   # teal
#     (200, 200, 80,  255),   # lime
#     (220, 50,  150, 255),   # magenta
#     (50,  160, 240, 255),   # sky blue
#     (180, 120, 60,  255),   # tan
#     (120, 60,  180, 255),   # violet
# ]
