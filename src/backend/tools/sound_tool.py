"""
play_sound and search_sounds tools.

play_sound:  Mara calls with a preset name or raw bfxr params dict.
             Returns a special result that the frontend intercepts to trigger playback.

search_sounds: semantic search over the sound library by description.
"""
from __future__ import annotations

import json
import sqlite3
import struct

from ..providers.azure import get_embedding

BUILTIN_PRESETS = [
    {
        "name": "coin",
        "description": "Retro coin pickup — bright, short, upward chirp with a punchy sustain.",
        "params": {"waveType": "square", "startFrequency": 660, "slide": 200, "attackTime": 0, "sustainTime": 0.06, "sustainPunch": 0.5, "decayTime": 0.12, "squareDuty": 0.5, "masterVolume": 0.5},
    },
    {
        "name": "laser",
        "description": "Sci-fi laser shot — sharp downward frequency slide on a sawtooth wave.",
        "params": {"waveType": "sawtooth", "startFrequency": 880, "slide": -600, "attackTime": 0, "sustainTime": 0.08, "sustainPunch": 0.2, "decayTime": 0.15, "masterVolume": 0.45},
    },
    {
        "name": "powerup",
        "description": "Power-up jingle — rising arpeggio with a warm square tone and long sustain.",
        "params": {"waveType": "square", "startFrequency": 330, "slide": 120, "changeAmount": 1.5, "changeTime": 0.12, "attackTime": 0.01, "sustainTime": 0.25, "sustainPunch": 0.3, "decayTime": 0.2, "squareDuty": 0.4, "masterVolume": 0.5},
    },
    {
        "name": "blip",
        "description": "Short UI blip — quick neutral click, useful for confirmations or selections.",
        "params": {"waveType": "square", "startFrequency": 520, "attackTime": 0, "sustainTime": 0.02, "sustainPunch": 0, "decayTime": 0.05, "squareDuty": 0.5, "masterVolume": 0.4},
    },
    {
        "name": "explosion",
        "description": "Rumbling explosion — low noise burst with heavy low-pass filter and slow decay.",
        "params": {"waveType": "noise", "startFrequency": 120, "attackTime": 0, "sustainTime": 0.15, "sustainPunch": 0.6, "decayTime": 0.45, "lpFilterCutoff": 0.35, "lpFilterResonance": 0.3, "masterVolume": 0.6},
    },
    {
        "name": "dial-up",
        "description": "Dial-up modem handshake — rapid multi-tone chirp sequence with vibrato.",
        "params": {"waveType": "sine", "startFrequency": 1200, "slide": -80, "changeAmount": 0.75, "changeTime": 0.08, "vibratoDepth": 0.15, "vibratoSpeed": 18, "attackTime": 0, "sustainTime": 0.35, "decayTime": 0.1, "repeatSpeed": 0.12, "masterVolume": 0.4},
    },
    {
        "name": "startup",
        "description": "Warm startup chime — gentle sine sweep rising to a bright resolving tone.",
        "params": {"waveType": "sine", "startFrequency": 280, "slide": 180, "changeAmount": 1.25, "changeTime": 0.18, "attackTime": 0.04, "sustainTime": 0.3, "sustainPunch": 0.1, "decayTime": 0.35, "masterVolume": 0.45},
    },
]


def _pack(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


async def seed_sounds(conn: sqlite3.Connection) -> None:
    """Insert builtin presets and embed their descriptions if not already present."""
    for preset in BUILTIN_PRESETS:
        existing = conn.execute("SELECT name FROM sounds WHERE name = ?", (preset["name"],)).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO sounds (name, description, params, is_builtin) VALUES (?, ?, ?, 1)",
            (preset["name"], preset["description"], json.dumps(preset["params"])),
        )
        conn.commit()
        try:
            vec = await get_embedding(preset["description"])
            conn.execute(
                "INSERT OR REPLACE INTO sound_embeddings (name, embedding) VALUES (?, ?)",
                (preset["name"], _pack(vec)),
            )
            conn.commit()
        except Exception:
            pass  # embeddings are optional — search falls back to LIKE


def get_sound(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT name, description, params, is_builtin FROM sounds WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return {"name": row["name"], "description": row["description"], "params": json.loads(row["params"]), "is_builtin": bool(row["is_builtin"])}


def list_sounds(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT name, description, params, is_builtin FROM sounds ORDER BY is_builtin DESC, name").fetchall()
    return [{"name": r["name"], "description": r["description"], "params": json.loads(r["params"]), "is_builtin": bool(r["is_builtin"])} for r in rows]


async def search_sounds(conn: sqlite3.Connection, query: str, top_k: int = 4) -> list[dict]:
    """Semantic search over sound descriptions. Falls back to LIKE if embeddings unavailable."""
    try:
        vec = await get_embedding(query)
        rows = conn.execute(
            """
            SELECT s.name, s.description, s.params, s.is_builtin,
                   distance
            FROM sound_embeddings se
            JOIN sounds s ON s.name = se.name
            WHERE embedding MATCH ?
            AND k = ?
            ORDER BY distance
            """,
            (_pack(vec), top_k),
        ).fetchall()
        return [{"name": r["name"], "description": r["description"], "params": json.loads(r["params"])} for r in rows]
    except Exception:
        rows = conn.execute(
            "SELECT name, description, params FROM sounds WHERE description LIKE ? LIMIT ?",
            (f"%{query}%", top_k),
        ).fetchall()
        return [{"name": r["name"], "description": r["description"], "params": json.loads(r["params"])} for r in rows]


async def execute_play_sound(conn: sqlite3.Connection, args: dict) -> dict:
    name = args.get("name")
    raw_params = args.get("params")

    if raw_params:
        return {"action": "play_sound", "params": raw_params, "name": name or "custom"}

    if name:
        sound = get_sound(conn, name)
        if not sound:
            return {"error": f"Sound '{name}' not found. Use search_sounds to find available sounds."}
        return {"action": "play_sound", "params": sound["params"], "name": name}

    return {"error": "Provide either a preset 'name' or a 'params' object."}


async def execute_search_sounds(conn: sqlite3.Connection, args: dict) -> dict:
    query = args.get("query", "")
    results = await search_sounds(conn, query)
    return {"results": results}
