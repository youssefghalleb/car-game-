from __future__ import annotations

import asyncio
import math
import os
import time
import json

from game.race import Race
from server_ws import shared_pairing


# ============================================================
# Gestion d'une salle de jeu multijoueur
# ============================================================


# Couleurs disponibles pour les joueurs.
PLAYER_COLORS = [
    (190, 30, 30),
    (40, 110, 210),
    (235, 170, 40),
    (145, 90, 200),
    (50, 170, 120),
    (230, 120, 180),
]

MAX_PLAYERS = 6
COUNTDOWN_SECONDS = 3.0
GO_HOLD_SECONDS = 0.65
REMOTE_INPUT_POLL_RATE = 45
DEBUG_CONTROLLER = os.environ.get("DEBUG_CONTROLLER", "0") == "1"


def log_controller(message: str):
    if DEBUG_CONTROLLER:
        print(f"[ControllerTrace] {message}", flush=True)


class PlayerSlot:
    """Représente une voiture/joueur dans une salle."""

    def __init__(self, player_id: str, name: str, ws, color_index: int):
        self.player_id = player_id
        self.name = name
        self.display_ws = ws
        self.controller_ws = None
        self.disconnected_at = None
        self.color_index = color_index
        self.steer = 0.0
        self.throttle = 0.0
        self.brake = 0.0
        self.nitro = False
        self.ready = False
        self.controller_ready = False
        self.assist_steer_state = 0.0
        self._input_count = 0
        self._last_input_log = 0.0
        self._display_send_task = None
        self._controller_send_task = None
        self._dropped_state_frames = 0
        self._last_send_drop_log = 0.0
        self._last_remote_input_poll = 0.0


class SpectatorSlot:
    def __init__(self, spectator_id: str, name: str, ws):
        self.spectator_id = spectator_id
        self.name = name
        self.ws = ws
        self._display_send_task = None
        self._dropped_state_frames = 0
        self._last_send_drop_log = 0.0


class Room:
    """
    Salle de jeu contenant un lobby et une course.

    Cycle de vie :
    1. Lobby : les joueurs rejoignent
    2. Countdown : décompte avant le départ
    3. Racing : course en cours
    4. Finished : résultats affichés
    """

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.state = "lobby"  # lobby, countdown, racing, finished
        self.players: dict[str, PlayerSlot] = {}
        self.spectators: dict[str, SpectatorSlot] = {}
        self.race: Race | None = None
        self.host_id: str | None = None
        self.chat_messages: list[dict] = []
        self.settings = {
            "laps_to_win": 5,
            "bot_count": 2,
            "bot_difficulty": "medium",
            "car_damage": True,
            "track_layout": "track_1",
            "steer_assist": "none",
            "race_mode": "sprint",
        }
        self._next_player_id = 1
        self._next_spectator_id = 1
        self._game_task: asyncio.Task | None = None
        self._countdown = 0.0

    @property
    def player_count(self):
        return len(self.players)

    @property
    def active_count(self):
        return len(self.players) + len(self.spectators)

    def add_display(self, name: str, ws, requested_player_id: str | None = None) -> tuple[str | None, object | None]:
        """Ajoute ou reconnecte l'écran d'un joueur. Retourne l'ID et l'ancien socket."""
        player_id = self._sanitize_player_id(requested_player_id)
        if player_id and player_id in self.players:
            slot = self.players[player_id]
            old_ws = slot.display_ws
            slot.display_ws = ws
            slot.name = name
            slot.disconnected_at = None
            shared_pairing.register_display(self.room_id, player_id, name)
            log_controller(f"display_reconnect room={self.room_id} player={player_id}")
            return player_id, old_ws

        if self.state != "lobby":
            return None, None

        if self.player_count >= MAX_PLAYERS:
            return None, None

        if not player_id:
            player_id = self._generate_player_id()

        color_index = len(self.players) % len(PLAYER_COLORS)
        self.players[player_id] = PlayerSlot(player_id, name, ws, color_index)
        if self.host_id is None:
            self.host_id = player_id
        shared_pairing.register_display(self.room_id, player_id, name)
        log_controller(f"display_registered room={self.room_id} player={player_id} name={name}")
        return player_id, None

    def add_spectator(self, name: str, ws) -> str:
        spectator_id = self._generate_spectator_id()
        self.spectators[spectator_id] = SpectatorSlot(spectator_id, name, ws)
        log_controller(f"spectator_registered room={self.room_id} spectator={spectator_id} name={name}")
        return spectator_id

    def detach_spectator(self, spectator_id: str, ws=None) -> bool:
        slot = self.spectators.get(str(spectator_id))
        if slot is None:
            return False
        if ws is not None and slot.ws is not ws:
            return False
        self.spectators.pop(str(spectator_id), None)
        return True

    def attach_controller(self, player_id: str, ws) -> tuple[bool, object | None]:
        """Associe un contrôleur à une voiture existante."""
        player_id = self._sanitize_player_id(player_id)
        slot = self.players.get(str(player_id))
        if slot is None:
            log_controller(f"controller_attach_missing_player room={self.room_id} player={player_id}")
            return False, None
        old_ws = slot.controller_ws
        slot.controller_ws = ws
        slot.controller_ready = True
        slot.disconnected_at = None
        shared_pairing.mark_controller(self.room_id, player_id)
        log_controller(f"controller_attached room={self.room_id} player={player_id} replaced={old_ws is not None}")
        return True, old_ws

    def detach_controller(self, player_id: str, ws=None) -> bool:
        slot = self.players.get(str(player_id))
        if slot is None:
            return False
        if ws is not None and slot.controller_ws is not ws:
            return False
        slot.controller_ws = None
        slot.controller_ready = False
        slot.steer = 0.0
        slot.throttle = 0.0
        slot.brake = 0.0
        slot.nitro = False
        shared_pairing.clear_input(self.room_id, player_id)
        if slot.display_ws is None:
            slot.disconnected_at = time.monotonic()
        return True

    def detach_display(self, player_id: str, ws=None) -> bool:
        slot = self.players.get(str(player_id))
        if slot is None:
            return False
        if ws is not None and slot.display_ws is not ws:
            return False
        slot.display_ws = None
        slot.ready = False
        if slot.controller_ws is None:
            slot.disconnected_at = time.monotonic()
        return True

    def remove_player(self, player_id: str):
        """Retire une voiture de la salle quand son écran quitte."""
        self.players.pop(player_id, None)
        if self.host_id == player_id:
            self.host_id = next(iter(self.players.keys()), None)
        if self.player_count == 0:
            self._stop_game()

    def is_host(self, player_id: str | None) -> bool:
        return player_id is not None and player_id == self.host_id

    def add_chat_message(self, sender: str, text: str):
        cleaned = " ".join(str(text or "").strip().split())[:160]
        if not cleaned:
            return
        self.chat_messages.append({
            "sender": sender[:24] or "Player",
            "text": cleaned,
            "time": round(time.time(), 3),
        })
        self.chat_messages = self.chat_messages[-20:]

    def cleanup_inactive_players(self, grace_seconds: float = 30.0):
        now = time.monotonic()
        stale = [
            pid
            for pid, slot in self.players.items()
            if slot.display_ws is None
            and slot.controller_ws is None
            and slot.disconnected_at is not None
            and now - slot.disconnected_at >= grace_seconds
        ]
        for pid in stale:
            self.remove_player(pid)

    def update_input(self, player_id: str, data: dict) -> bool:
        """Met à jour les entrées d'un joueur."""
        player_id = self._sanitize_player_id(player_id)
        slot = self.players.get(str(player_id))
        if slot is None:
            return False
        steer = max(-1.0, min(1.0, float(data.get("steer", 0.0))))
        slot.steer = self._apply_steer_assist(slot, steer)
        slot.throttle = max(0.0, min(1.0, float(data.get("throttle", 0.0))))
        slot.brake = max(0.0, min(1.0, float(data.get("brake", 0.0))))
        slot.nitro = bool(data.get("nitro", False))
        slot._input_count += 1
        now = time.monotonic()
        if slot._input_count == 1 or now - slot._last_input_log >= 2.0:
            slot._last_input_log = now
            log_controller(
                f"input_received room={self.room_id} player={player_id} "
                f"count={slot._input_count} steer={slot.steer:.2f} "
                f"throttle={slot.throttle:.1f} brake={slot.brake:.1f} nitro={slot.nitro}"
            )
        return True

    def set_ready(self, player_id: str, role: str, ready: bool) -> bool:
        player_id = self._sanitize_player_id(player_id)
        slot = self.players.get(str(player_id))
        if slot is None or self.state != "lobby":
            return False
        if role == "controller":
            slot.controller_ready = bool(ready) and slot.controller_ws is not None
        else:
            slot.ready = bool(ready) and slot.display_ws is not None
        return True

    def start_requirements(self) -> list[str]:
        if not self.players:
            return ["No players joined"]

        blockers = []
        for pid, slot in self.players.items():
            if slot.display_ws is None:
                blockers.append(f"{pid}: monitor disconnected")
            if slot.controller_ws is None:
                if not shared_pairing.controller_active(self.room_id, pid):
                    blockers.append(f"{pid}: controller not connected")
            if not slot.ready:
                blockers.append(f"{pid}: monitor not ready")
            if not slot.controller_ready and not shared_pairing.controller_active(self.room_id, pid):
                blockers.append(f"{pid}: controller not ready")
        return blockers

    @property
    def can_start(self) -> bool:
        return self.state == "lobby" and not self.start_requirements()

    def _apply_steer_assist(self, slot: PlayerSlot, steer: float) -> float:
        assist = self.settings.get("steer_assist", "none")
        if assist == "none":
            slot.assist_steer_state = steer
            return steer

        profiles = {
            "medium": {"deadzone": 0.035, "expo": 1.05, "blend": 0.72, "max_step": 0.55},
            "full": {"deadzone": 0.06, "expo": 1.12, "blend": 0.52, "max_step": 0.42},
        }
        profile = profiles.get(assist, profiles["full"])
        deadzone = profile["deadzone"]
        expo = profile["expo"]

        if abs(steer) <= deadzone:
            target = 0.0
        else:
            sign = 1.0 if steer > 0 else -1.0
            shaped = (abs(steer) - deadzone) / max(1e-6, 1.0 - deadzone)
            target = sign * (shaped ** expo)

        if abs(target) < 0.02 and abs(slot.assist_steer_state) < 0.04:
            slot.assist_steer_state = 0.0
            return 0.0

        delta = target - slot.assist_steer_state
        step = max(-profile["max_step"], min(profile["max_step"], delta * profile["blend"]))
        if abs(delta) <= 0.01:
            slot.assist_steer_state = target
        else:
            slot.assist_steer_state += step

        return slot.assist_steer_state

    def start_race(self) -> tuple[bool, list[str]]:
        """Lance le décompte puis la course."""
        if self.state != "lobby":
            print(f"[Room {self.room_id}] Cannot start: state is '{self.state}', not 'lobby'")
            return False, [f"Room is {self.state}"]
        blockers = self.start_requirements()
        if blockers:
            return False, blockers
        self.state = "countdown"
        self._countdown = COUNTDOWN_SECONDS
        try:
            self._create_race()
        except Exception as e:
            print(f"[Room {self.room_id}] ERROR creating race: {e}")
            import traceback
            traceback.print_exc()
            self.state = "lobby"
            return False, ["Race creation failed"]
        return True, []

    def _create_race(self):
        """Crée la course avec les joueurs actuels."""
        self.race = Race(
            players=[
                {
                    "id": pid,
                    "name": slot.name,
                    "color_index": slot.color_index,
                }
                for pid, slot in self.players.items()
            ],
            laps_to_win=self.settings["laps_to_win"],
            bot_count=self.settings["bot_count"],
            bot_difficulty=self.settings["bot_difficulty"],
            car_damage=self.settings["car_damage"],
            track_layout=self.settings["track_layout"],
            race_mode=self.settings["race_mode"],
        )

    def pause_race(self):
        if self.state == "racing" and self.race is not None:
            self.race.paused = True
            self.state = "paused"

    def resume_race(self):
        if self.state == "paused" and self.race is not None:
            self.race.paused = False
            self.state = "racing"

    def restart_race(self):
        if self.players:
            self.state = "countdown"
            self._countdown = COUNTDOWN_SECONDS
            self._create_race()

    def reset_race(self):
        self.restart_race()

    def quit_to_lobby(self):
        self.race = None
        self.state = "lobby"
        self._countdown = 0.0

    def tick(self, dt: float):
        """Avance d'un pas de simulation."""
        if self.state == "countdown":
            self._countdown -= dt
            if self._countdown <= -GO_HOLD_SECONDS:
                self.state = "racing"

        elif self.state == "racing" and self.race is not None:
            controls = {}
            for pid, slot in self.players.items():
                now = time.monotonic()
                if slot.controller_ws is None and now - slot._last_remote_input_poll >= 1.0 / REMOTE_INPUT_POLL_RATE:
                    slot._last_remote_input_poll = now
                    remote_input = shared_pairing.read_input(self.room_id, pid)
                    if remote_input:
                        self.update_input(pid, remote_input)
                controls[pid] = {
                    "steer": slot.steer,
                    "throttle": slot.throttle,
                    "brake": slot.brake,
                    "nitro": slot.nitro,
                }
            self.race.update(dt, controls)

            if self.race.finished or self.race.game_over:
                self.state = "finished"

    def get_state_snapshot(self, include_track: bool = False, include_meta: bool = True) -> dict:
        """Retourne l'état complet de la salle pour le broadcast."""
        snapshot = {
            "room_id": self.room_id,
            "state": self.state,
            "race_mode": self.settings.get("race_mode", "sprint"),
        }

        if include_meta:
            snapshot["players"] = {
                str(pid): {
                    "name": s.name,
                    "host": pid == self.host_id,
                    "ready": s.ready,
                    "controller_ready": s.controller_ready or shared_pairing.controller_active(self.room_id, pid),
                    "controller": s.controller_ws is not None or shared_pairing.controller_active(self.room_id, pid),
                    "display": s.display_ws is not None,
                }
                for pid, s in self.players.items()
            }
            snapshot["host_id"] = self.host_id
            snapshot["spectators"] = {
                sid: {"name": s.name}
                for sid, s in self.spectators.items()
            }
            snapshot["chat"] = self.chat_messages
            blockers = self.start_requirements()
            snapshot["can_start"] = self.state == "lobby" and not blockers
            snapshot["start_blockers"] = blockers
            snapshot["settings"] = self.settings

        if self.state == "countdown":
            snapshot["countdown"] = 0 if self._countdown <= 0 else max(1, math.ceil(self._countdown))

        if self.race is not None:
            track = self.race.track
            cars = []
            for car in self.race.cars:
                cars.append({
                    "id": car.player_id,
                    "x": round(car.x, 1),
                    "y": round(car.y, 1),
                    "angle": round(car.angle_deg, 1),
                    "speed": round(car.speed, 1),
                    "nitro_amount": round(car.nitro, 1),
                    "health": round(car.health, 1),
                    "lap": car.lap,
                    "completed_laps": car.completed_laps,
                    "track_progress": round(getattr(car, "track_progress", 0.0), 4),
                    "checkpoint": getattr(car, "current_checkpoint", 0),
                    "checkpoint_count": getattr(track, "checkpoint_count", 0),
                    "wrong_way": getattr(car, "wrong_way_timer", 0.0) > 0.2,
                    "shortcut_warning": getattr(car, "shortcut_warning_timer", 0.0) > 0.0,
                    "invalid_lap_warning": getattr(car, "invalid_lap_warning_timer", 0.0) > 0.0,
                    "off_track_warning": getattr(car, "off_track_warning_timer", 0.0) > 0.0,
                    "angular_velocity": round(getattr(car, "angular_velocity", 0.0), 1),
                    "current_lap_time": round(car.current_lap_time, 2),
                    "best_lap_time": (
                        round(car.best_lap_time, 2)
                        if car.best_lap_time is not None
                        else None
                    ),
                    "finished": car.finished,
                    "destroyed": car.destroyed,
                    "is_bot": getattr(car, "is_bot", False),
                    "name": getattr(car, "display_name", f"Player {car.player_id}"),
                    "color": car.color,
                })
            snapshot["cars"] = cars
            crash_events = self.race.pop_crash_events()
            if crash_events:
                snapshot["crash_events"] = crash_events
            snapshot["laps_to_win"] = self.race.laps_to_win
            snapshot["race_mode"] = self.race.race_mode
            if self.race.race_mode == "elimination":
                snapshot["elimination_timer"] = max(0, round(self.race.elimination_timer, 1))

            if self.race.finished and self.race.results_snapshot:
                snapshot["leaderboard"] = [
                    {
                        "name": getattr(c, "display_name", f"P{c.player_id}"),
                        "laps": c.completed_laps,
                        "time": round(c.total_time, 2),
                    }
                    for c in self.race.results_snapshot
                ]

        if include_track and self.race is not None:
            snapshot["track"] = track.get_drawing_data()
            snapshot["track_id"] = self.settings["track_layout"]

        return snapshot

    def _stop_game(self):
        """Arrête la boucle de jeu."""
        if self._game_task and not self._game_task.done():
            self._game_task.cancel()
        self.race = None
        self.state = "lobby"

    def _generate_player_id(self) -> str:
        while True:
            player_id = f"P{self._next_player_id}"
            self._next_player_id += 1
            if player_id not in self.players:
                return player_id

    def _generate_spectator_id(self) -> str:
        while True:
            spectator_id = f"S{self._next_spectator_id}"
            self._next_spectator_id += 1
            if spectator_id not in self.spectators:
                return spectator_id

    def _sanitize_player_id(self, player_id: str | None) -> str | None:
        if player_id is None:
            return None
        cleaned = "".join(ch for ch in str(player_id).upper() if ch.isalnum() or ch in ("-", "_"))
        return cleaned[:12] or None
