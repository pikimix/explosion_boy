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
