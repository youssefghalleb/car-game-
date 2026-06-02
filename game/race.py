from config import PLAYER_COLORS, SINGLE_PLAYER
from game.car import Car
from game.track import Track
from game.ai import BotDriver


# ============================================================
# Gestion complète d'une course
# ============================================================
# Ce fichier gère :
# - la création du circuit
# - le placement du joueur et des bots
# - les tours
# - les sorties de piste
# - le mauvais sens
# - les collisions
# - la fin de course et le classement
# ============================================================


# Noms utilisés pour les bots.
BOT_F1_NAMES = [
    "Verstappen",
    "Hamilton",
    "Leclerc",
    "Norris",
    "Russell",
    "Alonso",
    "Piastri",
    "Sainz",
    "Gasly",
    "Albon",
]

CHECKPOINT_WARNING_SECONDS = 2.2
MIN_VALID_LAP_PROGRESS = 0.78


class Race:
    """
    Représente une course complète.

    Une course contient :
    - un circuit
    - une voiture joueur
    - plusieurs voitures bots
    - les règles de tours
    - les collisions
    - les conditions de fin
    """

    def __init__(
        self,
        player_name="Player",
        players=None,
        laps_to_win=5,
        bot_count=4,
        bot_difficulty="medium",
        car_damage=True,
        track_layout="track_1",
        race_mode="sprint",
    ):
        """
        Initialise une nouvelle course avec les paramètres choisis dans le lobby.
        """

        # Création du circuit sélectionné.
        self.track = Track(track_layout)

        # États principaux de la course.
        self.paused = False
        self.finished = False
        self.game_over = False

        # Classement sauvegardé à la fin de la course.
        self.results_snapshot = None

        # Liste des collisions à envoyer au rendu et à l'audio.
        self.crash_events = []

        # Paramètres généraux de la course.
        self.player_entries = players or [{"id": "P1", "name": player_name, "color_index": 0}]
        self.player_name = self.player_entries[0]["name"] if self.player_entries else player_name
        self.laps_to_win = laps_to_win
        self.race_mode = race_mode
        if self.race_mode in ("practice", "time_trial"):
            bot_count = 0
        elif self.race_mode == "elimination" and len(self.player_entries) < 2:
            bot_count = max(1, bot_count)
        self.bot_count = min(4, bot_count)
        self.bot_difficulty = bot_difficulty
        self.car_damage = car_damage
        self.track_layout = track_layout
        self.elimination_timer = 25.0
        self.elimination_interval = 25.0

        # Liste de toutes les voitures présentes dans la course.
        self.cars = []

        # Dictionnaire des pilotes automatiques des bots.
        self.bot_drivers = {}

        # ----------------------------------------------------
        # Création des bots
        # ----------------------------------------------------
        if SINGLE_PLAYER:
            # Paramètres spécifiques au circuit démo.
            if self.track_layout == "track_2":
                lane_biases = [-18.0, 0.0, 18.0, -32.0]
                pace_factors = [0.985, 0.995, 1.0, 0.99]
                styles = ["balanced", "balanced", "traction", "balanced"]

            # Paramètres spécifiques au circuit principal.
            else:
                lane_biases = [-30.0, -8.0, 14.0, 34.0]
                pace_factors = [0.995, 1.0, 1.01, 1.005]
                styles = ["balanced", "balanced", "late_braker", "traction"]

            for i in range(self.bot_count):
                player_id = f"BOT{i + 1}"

                bx, by, angle = self.track.get_grid_position(i)

                # Nom du bot.
                bot_name = BOT_F1_NAMES[i] if i < len(BOT_F1_NAMES) else f"Bot {i + 1}"

                # Création de la voiture du bot.
                bot = Car(
                    bx,
                    by,
                    angle,
                    PLAYER_COLORS[min(i + 1, len(PLAYER_COLORS) - 1)],
                    player_id,
                )

                # Marque cette voiture comme bot.
                bot.is_bot = True
                bot.display_name = bot_name
                bot.track_progress = 0.0
                bot.wrong_way_timer = 0.0
                self._init_checkpoint_state(bot)

                self.cars.append(bot)

                # Personnalisation du comportement du bot.
                bias = lane_biases[i] if i < len(lane_biases) else 0.0
                pace = pace_factors[i] if i < len(pace_factors) else 1.0
                style = styles[i] if i < len(styles) else "balanced"

                # Création du pilote automatique associé au bot.
                driver = BotDriver(
                    self.track,
                    bot_difficulty,
                    lane_bias=bias,
                    pace_factor=pace,
                    style=style,
                )

                # Synchronise l'IA avec la position réelle du bot.
                driver.sync_to_car(bot)

                self.bot_drivers[player_id] = driver

        # ----------------------------------------------------
        # Création des voitures des joueurs
        # ----------------------------------------------------

        self.player_cars = []

        for index, entry in enumerate(self.player_entries):
            px, py, angle = self.track.get_grid_position(self.bot_count + index)

            color_index = int(entry.get("color_index", index)) % len(PLAYER_COLORS)
            player = Car(px, py, angle, PLAYER_COLORS[color_index], str(entry["id"]))
            player.is_bot = False
            player.display_name = entry.get("name", f"Player {index + 1}")
            player.track_progress = 0.0
            player.wrong_way_timer = 0.0
            self._init_checkpoint_state(player)

            self.cars.append(player)
            self.player_cars.append(player)

        self.player_car = self.player_cars[0] if self.player_cars else None

        # Calcule immédiatement la progression initiale de toutes les voitures.
        self._refresh_progress_all()

    def _init_checkpoint_state(self, car):
        progress = self.track.get_progress_from_start(car.x, car.y)
        checkpoint = self.track.get_checkpoint_index(car.x, car.y)
        car.current_checkpoint = checkpoint
        car.last_valid_checkpoint = checkpoint
        car.visited_checkpoints = {checkpoint}
        car.lap_peak_progress = progress
        car.shortcut_warning_timer = 0.0
        car.invalid_lap_warning_timer = 0.0
        car.off_track_warning_timer = 0.0

    def _reset_lap_checkpoints(self, car):
        progress = self.track.get_progress_from_start(car.x, car.y)
        checkpoint = self.track.get_checkpoint_index(car.x, car.y)
        car.current_checkpoint = checkpoint
        car.last_valid_checkpoint = checkpoint
        car.visited_checkpoints = {checkpoint}
        car.lap_peak_progress = progress

    def _has_valid_lap_checkpoints(self, car) -> bool:
        if getattr(car, "is_bot", False):
            return True

        peak_progress = getattr(car, "lap_peak_progress", 0.0)
        visited = getattr(car, "visited_checkpoints", set())
        minimum_checkpoints = max(2, self.track.checkpoint_count - 2)
        return peak_progress >= MIN_VALID_LAP_PROGRESS and len(visited) >= minimum_checkpoints

    def _update_checkpoint_state(self, car):
        progress = self.track.get_progress_from_start(car.x, car.y)
        if car.lap_timing_started:
            car.lap_peak_progress = max(getattr(car, "lap_peak_progress", 0.0), progress)

        checkpoint = self.track.get_checkpoint_index(car.x, car.y)
        previous = getattr(car, "current_checkpoint", checkpoint)
        count = self.track.checkpoint_count
        if checkpoint == previous:
            return

        forward_delta = (checkpoint - previous) % count
        reverse_delta = (previous - checkpoint) % count

        if forward_delta and forward_delta <= max(2, count // 2):
            car.current_checkpoint = checkpoint
            car.last_valid_checkpoint = checkpoint
            for step in range(1, forward_delta + 1):
                car.visited_checkpoints.add((previous + step) % count)
            return

        if reverse_delta and reverse_delta <= max(2, count // 2):
            car.current_checkpoint = checkpoint
            car.wrong_way_timer = max(getattr(car, "wrong_way_timer", 0.0), 0.15)
            return

        if not getattr(car, "is_bot", False):
            car.shortcut_warning_timer = CHECKPOINT_WARNING_SECONDS
            car.current_checkpoint = checkpoint

    def pop_crash_events(self):
        """
        Récupère les collisions en attente puis vide la liste.

        Le rendu et l'audio utilisent ces événements pour déclencher :
        - un effet visuel
        - un son de collision
        """
        events = self.crash_events[:]
        self.crash_events.clear()
        return events

    def toggle_pause(self):
        """
        Active ou désactive la pause.
        """
        self.paused = not self.paused

    def _nearest_track_progress(self, car):
        """
        Calcule la progression d'une voiture sur la piste.

        La progression est une valeur entre 0 et 1 :
        - 0 correspond au début du tour
        - 1 correspond presque à la fin du tour
        """
        idx = self.track._nearest_centerline_index(car.x, car.y)
        n = len(self.track.centerline)

        return idx / max(1, n - 1)

    def _refresh_progress_all(self):
        """
        Met à jour la progression de toutes les voitures.

        Pour les bots, on utilise la progression de leur pilote automatique.
        Pour le joueur, on utilise sa position réelle sur la piste.
        """
        for car in self.cars:
            if getattr(car, "is_bot", False):
                driver = self.bot_drivers.get(car.player_id)

                if driver is not None:
                    n = len(self.track.centerline)
                    car.track_progress = (driver.progress % n) / max(1, n - 1)
                else:
                    car.track_progress = self._nearest_track_progress(car)

            else:
                car.track_progress = self._nearest_track_progress(car)

    def _respawn_player_with_penalty(
        self,
        car,
        time_penalty: float,
        impact_penalty: float = 0.0,
        prefer_checkpoint: bool = False,
    ):
        """
        Replace une voiture sur la piste avec une pénalité.

        Cette méthode est utilisée quand le joueur :
        - sort de la piste
        - roule en sens inverse
        - franchit mal la ligne de départ

        Le respawn tient compte de la position par rapport à la ligne
        pour éviter de donner un tour gratuitement.
        """

        if prefer_checkpoint and hasattr(car, "last_valid_checkpoint"):
            rx, ry, ra = self.track.get_checkpoint_respawn(car.last_valid_checkpoint)
        else:
            # Vérifie si la voiture était déjà après la ligne de départ.
            after_start = car.lap_timing_started or self.track.is_after_start_line(car.x, car.y)

            # Récupère le point de respawn adapté à la zone actuelle.
            rx, ry, ra = self.track.get_penalty_respawn(
                car.x,
                car.y,
                after_start=after_start,
            )

        # Replace la voiture.
        car.reset_to(rx, ry, ra)

        # Applique des dégâts si l'option est activée.
        if self.car_damage and impact_penalty > 0.0:
            car.apply_collision_penalty(impact_penalty)

        # Ajoute une pénalité de temps.
        car.total_time += time_penalty
        self._reset_lap_checkpoints(car)

        # Si toutes les voitures humaines sont détruites, la partie est terminée.
        if (
            self.car_damage
            and self.player_cars
            and all(player.destroyed for player in self.player_cars)
        ):
            self.game_over = True

    def _check_wrong_direction(self, car, dt: float):
        """
        Détecte si le joueur roule dans le mauvais sens.

        La méthode compare :
        - la direction de déplacement de la voiture
        - la direction normale de la piste

        Si le joueur reste trop longtemps en sens inverse,
        il est replacé sur la piste avec une pénalité.
        """

        # Les bots ne sont pas concernés.
        if getattr(car, "is_bot", False):
            return

        # Avant le début du chronométrage, on ne détecte pas le mauvais sens.
        if not car.lap_timing_started:
            car.wrong_way_timer = 0.0
            return

        # À faible vitesse, la détection serait trop instable.
        if car.speed < 35:
            car.wrong_way_timer = 0.0
            return

        # Direction locale de la piste.
        tx, ty = self.track.get_track_tangent(car.x, car.y)

        # Direction réelle du déplacement de la voiture.
        heading_x = car.vel_x
        heading_y = car.vel_y

        heading_norm = (heading_x * heading_x + heading_y * heading_y) ** 0.5

        # Si la voiture ne bouge presque pas, on ignore.
        if heading_norm < 1e-6:
            car.wrong_way_timer = 0.0
            return

        heading_x /= heading_norm
        heading_y /= heading_norm

        # Produit scalaire :
        # positif  = même sens que la piste
        # négatif = sens opposé
        dot = heading_x * tx + heading_y * ty

        if dot < -0.35:
            car.wrong_way_timer += dt
        else:
            car.wrong_way_timer = max(0.0, car.wrong_way_timer - dt * 2.0)

        # Si le mauvais sens dure assez longtemps, respawn.
        if car.wrong_way_timer >= 0.45:
            self._respawn_player_with_penalty(
                car,
                time_penalty=3.0,
                impact_penalty=8.0,
                prefer_checkpoint=True,
            )
            car.wrong_way_timer = 0.0

    def _handle_crossing(self, car, old_pos):
        """
        Gère le passage de la ligne départ/arrivée.

        La méthode vérifie :
        - si la voiture a traversé la ligne
        - dans quel sens elle l'a traversée
        - si un nouveau tour doit être compté
        """

        # Empêche un double comptage juste après un respawn.
        if car.start_line_cooldown > 0.0:
            return

        crossing = self.track.crossed_start_finish_direction(old_pos, (car.x, car.y))

        if crossing != 0:
            # Évite de compter plusieurs passages sur la même traversée.
            if not car.crossed_start_recently:
                if crossing > 0:
                    # Premier passage correct : le chrono commence.
                    if not car.lap_timing_started:
                        car.lap_timing_started = True
                        car.current_lap_time = 0.0
                        car.lap = 1
                        self._reset_lap_checkpoints(car)

                    # Passage suivant : un tour est terminé.
                    else:
                        if not self._has_valid_lap_checkpoints(car):
                            if not getattr(car, "is_bot", False):
                                car.invalid_lap_warning_timer = CHECKPOINT_WARNING_SECONDS
                                if self.race_mode == "practice":
                                    self._reset_lap_checkpoints(car)
                                else:
                                    self._respawn_player_with_penalty(
                                        car,
                                        time_penalty=3.0,
                                        impact_penalty=6.0,
                                        prefer_checkpoint=True,
                                    )
                            car.crossed_start_recently = True
                            return

                        completed = car.current_lap_time
                        car.last_lap_time = completed

                        # Mise à jour du meilleur tour.
                        if car.best_lap_time is None or completed < car.best_lap_time:
                            car.best_lap_time = completed

                        car.completed_laps += 1

                        # Mode-specific completion rules.
                        if self.race_mode in ("sprint", "time_trial") and car.completed_laps >= self.laps_to_win:
                            car.finished = True
                        else:
                            car.lap = car.completed_laps + 1
                            car.current_lap_time = 0.0
                            self._reset_lap_checkpoints(car)

                # Passage de la ligne dans le mauvais sens.
                else:
                    if car.lap_timing_started and not getattr(car, "is_bot", False):
                        self._respawn_player_with_penalty(
                            car,
                            time_penalty=3.0,
                            prefer_checkpoint=True,
                        )

                car.crossed_start_recently = True

        else:
            car.crossed_start_recently = False

    def update(self, dt: float, controls_by_player: dict):
        """
        Met à jour toute la course à chaque image.

        Cette méthode :
        - déplace le joueur
        - déplace les bots
        - vérifie les sorties de piste
        - vérifie le mauvais sens
        - vérifie les passages de ligne
        - gère les collisions
        - met à jour le classement
        """

        # Si la course n'est pas active, rien ne bouge.
        if self.paused or self.finished or self.game_over:
            return

        for car in self.cars:
            # Une voiture finie ou détruite ne bouge plus.
            if car.finished or car.destroyed:
                continue

            # Position avant mouvement, utilisée pour détecter la ligne.
            old_pos = (car.x, car.y)

            # Mise à jour des bots.
            if getattr(car, "is_bot", False):
                self.bot_drivers[car.player_id].update_car(
                    car,
                    dt,
                    all_cars=self.cars,
                )
                self._update_checkpoint_state(car)

            # Mise à jour du joueur.
            else:
                control = controls_by_player.get(car.player_id, {})
                car.update(dt, control)
                car.shortcut_warning_timer = max(
                    0.0,
                    getattr(car, "shortcut_warning_timer", 0.0) - dt,
                )
                car.invalid_lap_warning_timer = max(
                    0.0,
                    getattr(car, "invalid_lap_warning_timer", 0.0) - dt,
                )
                car.off_track_warning_timer = max(
                    0.0,
                    getattr(car, "off_track_warning_timer", 0.0) - dt,
                )

                # Sortie de piste : respawn avec pénalité.
                if self.track.is_off_track(car.x, car.y):
                    car.off_track_warning_timer = CHECKPOINT_WARNING_SECONDS
                    self._respawn_player_with_penalty(
                        car,
                        time_penalty=2.5,
                        impact_penalty=10.0,
                        prefer_checkpoint=True,
                    )
                    continue

                self._update_checkpoint_state(car)

                # Vérification du mauvais sens.
                self._check_wrong_direction(car, dt)

                # Si tous les joueurs sont détruits, la partie est terminée.
                if (
                    self.car_damage
                    and self.player_cars
                    and all(player.destroyed for player in self.player_cars)
                ):
                    self.game_over = True
                    continue

            # Passage de la ligne départ/arrivée.
            self._handle_crossing(car, old_pos)

            # Temps total en course.
            car.total_time += dt

            # Temps du tour actuel.
            if car.lap_timing_started and not car.finished:
                car.current_lap_time += dt

        # Collisions entre voitures.
        self.handle_car_collisions()

        if self.race_mode == "elimination":
            self._update_elimination(dt)

        # Progression de chaque voiture sur le circuit.
        self._refresh_progress_all()

        # Game over si tous les joueurs humains sont détruits.
        if (
            self.player_cars
            and self.car_damage
            and all(player.destroyed for player in self.player_cars)
        ):
            self.game_over = True

        if self.race_mode == "sprint" and any(car.finished for car in self.cars):
            self.finished = True
            if self.results_snapshot is None:
                self.results_snapshot = self.get_leaderboard()

        elif self.race_mode == "time_trial" and self.player_cars and all(
            car.finished or car.destroyed for car in self.player_cars
        ):
            self.finished = True
            if self.results_snapshot is None:
                self.results_snapshot = self.get_leaderboard()

    def _update_elimination(self, dt: float):
        active = [car for car in self.cars if not car.finished and not car.destroyed]
        if len(active) <= 1:
            if len(active) == 1:
                active[0].finished = True
            self.finished = True
            if self.results_snapshot is None:
                self.results_snapshot = self.get_leaderboard()
            return

        self.elimination_timer -= dt
        if self.elimination_timer > 0:
            return

        self.elimination_timer = self.elimination_interval
        last = sorted(
            active,
            key=lambda c: (
                getattr(c, "completed_laps", 0),
                getattr(c, "track_progress", 0.0),
                -getattr(c, "total_time", 0.0),
            ),
        )[0]
        last.finished = True
        last.speed = 0.0
        last.vel_x = 0.0
        last.vel_y = 0.0

    def handle_car_collisions(self):
        """
        Détecte et traite les collisions entre voitures.

        Les collisions :
        - séparent les voitures
        - ralentissent les voitures
        - appliquent des dégâts si l'option est activée
        - créent un événement visuel et sonore
        """

        # Comparaison de chaque paire de voitures.
        for i in range(len(self.cars)):
            for j in range(i + 1, len(self.cars)):
                a = self.cars[i]
                b = self.cars[j]

                # Voiture détruite : pas de collision.
                if a.destroyed or b.destroyed:
                    continue

                a_is_bot = getattr(a, "is_bot", False)
                b_is_bot = getattr(b, "is_bot", False)

                # On ignore les collisions entre deux bots.
                # Cela évite qu'ils se bloquent entre eux.
                if a_is_bot and b_is_bot:
                    continue

                dx = b.x - a.x
                dy = b.y - a.y
                dist_sq = dx * dx + dy * dy

                # Distance minimale avant collision.
                min_dist = 28

                if dist_sq <= min_dist * min_dist:
                    # Intensité du choc selon la différence de vitesse.
                    impact = abs(a.speed - b.speed) + 14.0

                    # Dégâts optionnels.
                    if self.car_damage:
                        a.apply_collision_penalty(impact)
                        b.apply_collision_penalty(impact)

                    # Cas rare où les deux voitures sont exactement au même endroit.
                    if dx == 0 and dy == 0:
                        dx, dy = 1, 0

                    # Direction normale de séparation.
                    length = max((dx * dx + dy * dy) ** 0.5, 0.001)
                    nx = dx / length
                    ny = dy / length

                    # Repousse les deux voitures pour éviter qu'elles restent collées.
                    push = 12
                    a.x -= nx * push
                    a.y -= ny * push
                    b.x += nx * push
                    b.y += ny * push

                    # Centre de l'impact pour les effets visuels.
                    cx = (a.x + b.x) / 2
                    cy = (a.y + b.y) / 2

                    self.crash_events.append({
                        "x": cx,
                        "y": cy,
                        "impact": impact,
                    })

                    # Si un bot a été déplacé, son IA doit être resynchronisée.
                    if a_is_bot and not a.destroyed:
                        self.bot_drivers[a.player_id].sync_to_car(a)

                    if b_is_bot and not b.destroyed:
                        self.bot_drivers[b.player_id].sync_to_car(b)

    def get_leaderboard(self):
        """
        Retourne le classement actuel.

        Priorité du tri :
        1. nombre de tours terminés
        2. progression dans le tour actuel
        3. temps total le plus faible
        """
        if self.race_mode == "elimination":
            return sorted(
                self.cars,
                key=lambda c: (
                    c.finished or c.destroyed,
                    -c.completed_laps,
                    -getattr(c, "track_progress", 0.0),
                    c.total_time,
                ),
            )

        return sorted(
            self.cars,
            key=lambda c: (
                -c.completed_laps,
                -getattr(c, "track_progress", 0.0),
                c.total_time,
            ),
        )
