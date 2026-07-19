"""Tick-related type aliases and constants shared by client and server."""
from engine.config import TICK_RATE

TickNumber = int

TICK_DT: float = 1.0 / TICK_RATE   # seconds per server tick
