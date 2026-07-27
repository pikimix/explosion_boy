# Explosion Boy

A networked multiplayer game. An authoritative Python server manages all game logic, and clients connect to play via a GUI powered by the Arcade library.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

Clone the repo, and from the repo root run uv sync:

```bash
uv sync
```

## Running the Game

### 1. Start the Server

```bash
uv run python run_server.py
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Address to bind |
| `--port` | `9000` | Port to listen on |
| `--backend` | `tcp` | Transport backend |

Environment variables `SERVER_HOST`, `SERVER_PORT`, and `SERVER_BACKEND` are used as fallbacks if flags are not provided.

### 2. Start the Client

```bash
uv run python run_client.py
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Server address |
| `--port` | `9000` | Server port |
| `--name` | `Player` | Your display name |
| `--backend` | `tcp` | Transport backend |

#### Example: connecting to a remote server

```bash
uv run python run_client.py --host 192.168.1.10 --port 9000 --name Alice
```

### Game Flow

1. Launch the server, then connect with two or more clients.
2. Each client lands in the lobby — press **Ready** when you want to start.
3. Once all players are ready the game begins.
4. Place bombs to destroy soft blocks and eliminate other players.
5. Collect powerups dropped from destroyed blocks (extra bombs or increased blast radius).
6. Last player standing wins. The server then resets to the lobby for another round.

## Customisation

### Colours

You can override the colours of tiles, bombs, explosions, powerups, and players without editing the tracked source files.

Copy the example file to the project root:

```bash
cp example.colours.py colours.py
```

Then open `colours.py` and uncomment any values you want to change, for example:

```python
SOFT_BLOCK_COLOUR = (80, 120, 60, 255)   # olive green instead of brown
EXPLOSION_COLOUR  = (255, 50,  50, 200)  # red explosions
```

All colours are `(R, G, B, A)` tuples with values 0–255. The alpha channel controls transparency — use 255 for fully opaque.

`colours.py` is gitignored so your changes stay local. See [example.colours.py](example.colours.py) for the full list of available constants and their defaults.

## Running the Server in Docker

### Using Docker Compose (recommended)

Copy the example environment file and edit as needed:

```bash
cp example.env .env
```

The defaults in `example.env` are:

```
SERVER_HOST=0.0.0.0
SERVER_PORT=9000
SERVER_BACKEND=tcp
HOST_PORT=9000
```
SERVER_HOST, SERVER_PORT and SERVER_BACKEND all pass through to the run_server.py as above, HOST_PORT is the port that will be exposed by Docker, and used by clients to connect to the server. This does not need to match the SERVER_PORT.


Then bring the server up:

```bash
docker compose up -d
```

To stop it:

```bash
docker compose down
```

Logs:

```bash
docker compose logs -f
```

### Using Docker Directly

Build the image:

```bash
docker build -t explosion-boy-server .
```

Run it:

```bash
docker run -d \
  -p 9000:9000 \
  -e SERVER_HOST=0.0.0.0 \
  -e SERVER_PORT=9000 \
  -e SERVER_BACKEND=tcp \
  --name explosion-boy \
  explosion-boy-server
```

Once the server is running in Docker, connect clients on the same machine or network:

```bash
uv run python run_client.py --host 127.0.0.1 --port 9000 --name Alice
```

## Profiling

Two independent tools are available for investigating server performance. They don't depend on each other — use either one alone, or both together.

### Tick-timing stats

Pass `--profile` (or set `SERVER_PROFILE=1`) to have the server print a summary line to its log roughly once a second:

```bash
uv run python run_server.py --profile
# or, with Docker Compose, set SERVER_PROFILE=1 in .env and:
docker compose up -d
docker compose logs -f server
```

```
[12:03:45.123] [profile] tick avg=1.42ms max=8.91ms detonation_avg=0.67ms encode_avg=0.31ms | players=16 bombs=47 explosions=12 rays=8
```

This is cheap, always-safe-to-leave-on instrumentation baked into the code — it doesn't require py-spy, ptrace, or any container capability.

### Flamegraph profiling with py-spy

`py-spy` is a sampling profiler that attaches to a running process from outside — no code changes or `--profile` flag required, and it works whether or not `SERVER_PROFILE` is enabled. It's included as a regular project dependency, so it's already present in the Docker image and in your local `uv` environment, and the same commands work for profiling the client as well as the server.

Recording is started and stopped on demand — attach whenever you like, and press `Ctrl-C` to stop; `py-spy record` catches the interrupt and writes out everything it sampled before exiting, so there's no need to know the recording length in advance.

#### In Docker

Running it against a containerised server requires the `SYS_PTRACE` capability, since Docker's default seccomp profile blocks the `ptrace` syscall py-spy needs. `docker-compose.yml` already grants this (`cap_add: [SYS_PTRACE]`); if you run the image with plain `docker run` instead, add `--cap-add=SYS_PTRACE` to the command.

Useful if the server has already been running for a while (e.g. through several games) and you only want to capture one specific match:

```bash
docker exec -it <container> ps aux | grep run_server.py   # find the PID
docker exec -it <container> uv run py-spy record -o /app/profiles/match-N.svg --pid <PID> --nonblocking --rate 100
```

The `uv run` prefix is needed because `py-spy` lives in the project's virtual environment, not on the container's default `PATH` — `uv run` resolves and activates it from `/app` (the container's working directory). The resulting `match-N.svg` appears directly in `./profiles/` on the host (bind-mounted into the container automatically); open it in a browser.

#### Running directly (no Docker) — server or client

The same technique works for a server or client started with `uv run python run_server.py` / `uv run python run_client.py` — find its PID, then attach:

```bash
ps aux | grep run_server.py   # or run_client.py
uv run py-spy record -o profile.svg --pid <PID> --nonblocking --rate 100
```

You can also use `py-spy top --pid <PID>` for a live view instead of recording to a file, or `py-spy dump --pid <PID>` for a one-off stack snapshot.

Platform notes:
- **macOS** requires root to attach to another process. Resolve the venv's `py-spy` first, then `sudo` that specific path (plain `sudo uv run py-spy ...` won't work reliably, since `sudo` resets the environment `uv` needs):
  ```bash
  sudo "$(uv run which py-spy)" record -o profile.svg --pid <PID> --nonblocking --rate 100
  ```
- **Linux** may also require `sudo`, depending on the kernel's `ptrace_scope` setting (`/proc/sys/kernel/yama/ptrace_scope`) — if attaching fails with a permissions error, prefix the command with `sudo` the same way.
