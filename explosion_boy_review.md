# Explosion Boy — Architecture Review & Performance Recommendations

Repo: https://github.com/pikimix/explosion_boy

## Architecture Overview

Explosion Boy is a server-authoritative, tick-based multiplayer Bomberman-style
game, cleanly split into layers:

- **core/** — pure data: `GameState` (the canonical world snapshot, dataclasses
  only), `components.py` (entities-as-dataclasses: bombs, players, explosions,
  powerups), `serialiser.py` (msgpack encode/decode), `clock.py` (fixed 20Hz
  tick timer).
- **engine/** — low-level infrastructure: `physics.py` (a pymunk wrapper for
  movement/collision), `transport.py` (pluggable TCP/UDP networking),
  `config.py`, `assets.py`, `window.py`.
- **systems/** — stateless functions that mutate `GameState` each tick:
  movement, bombs, explosions, powerups, collision queries, input buffering,
  client prediction.
- **net/** — `server.py` (the authoritative game loop), `client.py`,
  `lobby.py`, `protocol.py` (message types).
- **app/** — the Arcade-based client renderer (`game_view.py`), particle
  system, HUD/UI, sound.

The design follows a classic "functional core, thin shell" pattern: systems
are stateless functions operating on `GameState` + `PhysicsSpace`, the server
loop calls them in sequence each tick, encodes the resulting state, and
broadcasts it. Clients decode it, run a `PredictionEngine` for the local
player, and render. This is a solid, readable foundation — the separation of
concerns is good and most systems are small and testable.

## Performance Feedback

### 1. Client tile-shape rebuild happens every single tick (biggest win)

`game_view._draw_tiles` rebuilds the entire `ShapeElementList` (up to ~725
rectangles) whenever `state.tiles is not self._last_tiles`. But
`decode_state` constructs a brand-new nested `tiles` list on every
`StateUpdateMsg` — so this identity check is *always* true, and the full tile
mesh is rebuilt 20x/sec even though tiles change maybe once every few seconds.

**Fix:** have the server include a tile "version"/dirty counter in the
snapshot (the `tiles_dirty` flag already exists server-side but isn't
serialised), and only rebuild client-side shapes when that version changes.

### 2. `rebuild_static_walls` is called for every destroyed soft block

When one soft block disappears, `PhysicsSpace.rebuild_static_walls` removes
and re-creates *every* static wall shape in the level (potentially 300+
pymunk `Poly` objects), every time. With chain-reaction explosions this can
happen many times in a single tick.

**Fix:** maintain a `{(col, row): shape}` map and incrementally remove/add
just the changed cell's shape instead of rebuilding the whole level.

### 3. Bomb body re-indexing on every removal

`_reindex_bomb_bodies` removes *all* bomb physics bodies and re-adds them
whenever any bomb is removed, just to keep array indices aligned with
`state.bombs`. During a big chain reaction this is O(n²) churn.

**Fix:** use a stable bomb ID (assigned at creation) as the physics-body key
instead of list index, so removals are O(1).

### 4. Full-state broadcast every tick, no delta compression

`encode_state` serialises the *entire* `GameState` (players, bombs,
explosions, rays, powerups, names, colours) every tick and sends it via
unreliable broadcast to all peers. At 20Hz with 16 players this is fine for
now but won't scale gracefully.

**Fix:** consider splitting into a high-frequency channel (positions, bombs,
explosions) and a low-frequency/on-change channel (names, colours, tile
diffs).

### 5. Linear scans in `collision.py`

`cell_has_bomb`, `cell_has_powerup`, `players_at`, and `cell_has_explosion`
are all O(n) over lists. Fine at current scale (small bomb/powerup counts),
but if maps/players grow, maintaining a `{(col, row): obj}` dict alongside the
lists would make these O(1) — a small, low-risk change.

## Structural Notes

- **`core/entity.py` (`EntityRegistry`) is dead code** — it's never imported
  anywhere. The actual `GameState` uses plain dataclasses/lists/dicts, which
  is arguably the *right* call for this game's scale (simpler, more
  serialisation-friendly than a generic ECS). Recommend deleting the unused
  registry to avoid confusing future readers about which pattern is canonical.
- The transport abstraction (`tcp`/`dual`) and headless server are nicely
  decoupled — good for testing and for swapping in a real UDP backend later.
- Worth considering: remote-player position interpolation on the client.
  Right now only the local player gets prediction, so other players will
  visually "tick" at 20Hz inside a 60fps render loop, which can look jittery.
  Not a CPU perf issue, but a visible smoothness one that's easy to fix with a
  simple lerp between the last two snapshots.

## Summary

The codebase is well-organized for its size; the main performance wins are
all about avoiding unnecessary full-rebuilds (tile shapes, physics walls,
bomb bodies) that scale with map/entity size when only a tiny delta actually
changed.
