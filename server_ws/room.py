import asyncio
import time
import json

from game.race import Race


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


class PlayerSlot:
    """Représente un joueur connecté dans une salle."""

    def __init__(self, player_id: int, name: str, ws):
        self.player_id = player_id
        self.name = name
        self.ws = ws
        self.steer = 0.0
        self.throttle = 0.0
        self.brake = 0.0
        self.nitro = False
        self.ready = False


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
        self.players: dict[int, PlayerSlot] = {}
        self.race: Race | None = None
        self.settings = {
            "laps_to_win": 5,
            "bot_count": 2,
            "bot_difficulty": "medium",
            "car_damage": True,
            "track_layout": "track_1",
        }
        self._next_player_id = 1
        self._game_task: asyncio.Task | None = None
        self._countdown = 0.0

    @property
    def player_count(self):
        return len(self.players)

    def add_player(self, name: str, ws) -> int | None:
        """Ajoute un joueur à la salle. Retourne l'ID ou None si plein."""
        if self.player_count >= MAX_PLAYERS:
            return None
        if self.state != "lobby":
            return None

        player_id = self._next_player_id
        self._next_player_id += 1
        self.players[player_id] = PlayerSlot(player_id, name, ws)
        return player_id

    def remove_player(self, player_id: int):
        """Retire un joueur de la salle."""
        self.players.pop(player_id, None)
        if self.player_count == 0:
            self._stop_game()

    def update_input(self, player_id: int, data: dict):
        """Met à jour les entrées d'un joueur."""
        slot = self.players.get(player_id)
        if slot is None:
            return
        slot.steer = max(-1.0, min(1.0, float(data.get("steer", 0.0))))
        slot.throttle = max(0.0, min(1.0, float(data.get("throttle", 0.0))))
        slot.brake = max(0.0, min(1.0, float(data.get("brake", 0.0))))
        slot.nitro = bool(data.get("nitro", False))

    def start_race(self):
        """Lance le décompte puis la course."""
        if self.state != "lobby":
            print(f"[Room {self.room_id}] Cannot start: state is '{self.state}', not 'lobby'")
            return
        self.state = "countdown"
        self._countdown = 4.0
        try:
            self._create_race()
            print(f"[Room {self.room_id}] Race created successfully")
        except Exception as e:
            print(f"[Room {self.room_id}] ERROR creating race: {e}")
            import traceback
            traceback.print_exc()
            self.state = "lobby"

    def _create_race(self):
        """Crée la course avec les joueurs actuels."""
        self.race = Race(
            player_name="Player 1",
            laps_to_win=self.settings["laps_to_win"],
            bot_count=self.settings["bot_count"],
            bot_difficulty=self.settings["bot_difficulty"],
            car_damage=self.settings["car_damage"],
            track_layout=self.settings["track_layout"],
        )

    def tick(self, dt: float):
        """Avance d'un pas de simulation."""
        if self.state == "countdown":
            self._countdown -= dt
            if self._countdown <= 0:
                self.state = "racing"

        elif self.state == "racing" and self.race is not None:
            controls = {}
            for pid, slot in self.players.items():
                controls[pid] = {
                    "steer": slot.steer,
                    "throttle": slot.throttle,
                    "brake": slot.brake,
                    "nitro": slot.nitro,
                }
            self.race.update(dt, controls)

            if self.race.finished or self.race.game_over:
                self.state = "finished"

    def get_state_snapshot(self) -> dict:
        """Retourne l'état complet de la salle pour le broadcast."""
        snapshot = {
            "room_id": self.room_id,
            "state": self.state,
            "players": {
                str(pid): {"name": s.name, "ready": s.ready}
                for pid, s in self.players.items()
            },
            "settings": self.settings,
        }

        if self.state == "countdown":
            snapshot["countdown"] = max(0, int(self._countdown))

        if self.race is not None:
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
                    "finished": car.finished,
                    "destroyed": car.destroyed,
                    "is_bot": getattr(car, "is_bot", False),
                    "name": getattr(car, "display_name", f"Player {car.player_id}"),
                    "color": car.color,
                })
            snapshot["cars"] = cars
            snapshot["crash_events"] = self.race.pop_crash_events()
            snapshot["laps_to_win"] = self.race.laps_to_win

            if self.race.finished and self.race.results_snapshot:
                snapshot["leaderboard"] = [
                    {
                        "name": getattr(c, "display_name", f"P{c.player_id}"),
                        "laps": c.completed_laps,
                        "time": round(c.total_time, 2),
                    }
                    for c in self.race.results_snapshot
                ]

        if self.race is not None:
            track = self.race.track
            snapshot["track"] = track.get_drawing_data()

        return snapshot

    def _stop_game(self):
        """Arrête la boucle de jeu."""
        if self._game_task and not self._game_task.done():
            self._game_task.cancel()
        self.race = None
        self.state = "lobby"
