import json
import os
import sqlite3
import time


DB_PATH = os.environ.get("PAIRING_DB_PATH", "/tmp/car_game_pairing.sqlite")
STALE_SECONDS = 90.0
INPUT_STALE_SECONDS = 0.35


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=0.05)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            room_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            name TEXT NOT NULL,
            display_seen REAL NOT NULL,
            controller_seen REAL,
            input_json TEXT,
            input_seen REAL,
            PRIMARY KEY (room_id, player_id)
        )
        """
    )
    return conn


def _execute(write_fn, fallback=None):
    try:
        with _connect() as conn:
            return write_fn(conn)
    except sqlite3.Error:
        return fallback


def register_display(room_id: str, player_id: str, name: str):
    now = time.time()

    def write(conn):
        conn.execute(
            """
            INSERT INTO players(room_id, player_id, name, display_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(room_id, player_id)
            DO UPDATE SET name=excluded.name, display_seen=excluded.display_seen
            """,
            (room_id, player_id, name, now),
        )

    _execute(write)


def mark_controller(room_id: str, player_id: str):
    now = time.time()

    def write(conn):
        conn.execute(
            """
            UPDATE players
            SET controller_seen=?
            WHERE room_id=? AND player_id=?
            """,
            (now, room_id, player_id),
        )

    _execute(write)


def player_exists(room_id: str, player_id: str) -> bool:
    cutoff = time.time() - STALE_SECONDS

    def read(conn):
        row = conn.execute(
            """
            SELECT 1 FROM players
            WHERE room_id=? AND player_id=? AND display_seen>=?
            """,
            (room_id, player_id, cutoff),
        ).fetchone()
        return row is not None

    return bool(_execute(read, False))


def controller_active(room_id: str, player_id: str) -> bool:
    cutoff = time.time() - STALE_SECONDS

    def read(conn):
        row = conn.execute(
            """
            SELECT 1 FROM players
            WHERE room_id=? AND player_id=? AND controller_seen>=?
            """,
            (room_id, player_id, cutoff),
        ).fetchone()
        return row is not None

    return bool(_execute(read, False))


def write_input(room_id: str, player_id: str, controls: dict):
    now = time.time()
    payload = {
        "steer": controls.get("steer", 0.0),
        "throttle": controls.get("throttle", 0.0),
        "brake": controls.get("brake", 0.0),
        "nitro": controls.get("nitro", False),
    }

    def write(conn):
        conn.execute(
            """
            UPDATE players
            SET controller_seen=?, input_json=?, input_seen=?
            WHERE room_id=? AND player_id=?
            """,
            (now, json.dumps(payload, separators=(",", ":")), now, room_id, player_id),
        )

    _execute(write)


def read_input(room_id: str, player_id: str) -> dict | None:
    cutoff = time.time() - INPUT_STALE_SECONDS

    def read(conn):
        row = conn.execute(
            """
            SELECT input_json FROM players
            WHERE room_id=? AND player_id=? AND input_seen>=?
            """,
            (room_id, player_id, cutoff),
        ).fetchone()
        if not row or not row[0]:
            return None
        return json.loads(row[0])

    return _execute(read)


def clear_input(room_id: str, player_id: str):
    def write(conn):
        conn.execute(
            """
            UPDATE players
            SET input_json=NULL, input_seen=NULL
            WHERE room_id=? AND player_id=?
            """,
            (room_id, player_id),
        )

    _execute(write)


def cleanup():
    cutoff = time.time() - STALE_SECONDS

    def write(conn):
        conn.execute("DELETE FROM players WHERE display_seen<?", (cutoff,))

    _execute(write)
