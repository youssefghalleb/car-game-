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
        laps_to_win=5,
        bot_count=4,
        bot_difficulty="medium",
        car_damage=True,
        track_layout="track_1",
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
        self.player_name = player_name
        self.laps_to_win = laps_to_win
        self.bot_count = min(4, bot_count)
        self.bot_difficulty = bot_difficulty
        self.car_damage = car_damage
        self.track_layout = track_layout

        # Liste de toutes les voitures présentes dans la course.
        self.cars = []

        # Dictionnaire des pilotes automatiques des bots.
        self.bot_drivers = {}

        # Position et orientation de référence au départ.
        start_x, start_y, angle = self.track.get_spawn(1)

        # Base locale de la ligne de départ :
        # tx, ty = direction de la piste
        # nx, ny = direction latérale
        tx, ty, nx, ny = self.track.get_start_basis()

        # ----------------------------------------------------
        # Création des bots
        # ----------------------------------------------------
        if SINGLE_PLAYER:
            # Paramètres spécifiques au circuit démo.
            if self.track_layout == "track_2":
                lane_biases = [-18.0, 0.0, 18.0, -32.0]
                pace_factors = [0.985, 0.995, 1.0, 0.99]
                styles = ["balanced", "balanced", "traction", "balanced"]

                longitudinal_gap = 92.0
                lateral_gap = 30.0
                grid_shift = 0.0

            # Paramètres spécifiques au circuit principal.
            else:
                lane_biases = [-30.0, -8.0, 14.0, 34.0]
                pace_factors = [0.995, 1.0, 1.01, 1.005]
                styles = ["balanced", "balanced", "late_braker", "traction"]

                longitudinal_gap = 84.0
                lateral_gap = 24.0
                grid_shift = 10.0

            for i in range(self.bot_count):
                # Les bots commencent à l'identifiant 2.
                player_id = i + 2

                # Placement en grille sur deux colonnes.
                row = i // 2
                col = i % 2

                # Décalage arrière par rapport à la ligne de départ.
                back = longitudinal_gap * (self.bot_count - i)

                # Décalage latéral pour éviter que les voitures soient alignées.
                side = (-0.5 if col == 0 else 0.5) * lateral_gap
                side += row * 4.0 * (-1 if col == 0 else 1)
                side += grid_shift

                # Position finale du bot.
                bx = start_x - tx * back + nx * side
                by = start_y - ty * back + ny * side

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
        # Création de la voiture du joueur
        # ----------------------------------------------------

        # Le joueur est placé derrière les bots.
        if self.track_layout == "track_2":
            player_back = 92.0 * (self.bot_count + 1)
            player_side = 0.0
        else:
            player_back = 84.0 * (self.bot_count + 1)
            player_side = 10.0

        px = start_x - tx * player_back + nx * player_side
        py = start_y - ty * player_back + ny * player_side

        # Création de la voiture contrôlée par le joueur.
        player = Car(px, py, angle, PLAYER_COLORS[0], 1)
        player.is_bot = False
        player.display_name = player_name
        player.track_progress = 0.0
        player.wrong_way_timer = 0.0

        self.cars.append(player)
        self.player_car = player

        # Calcule immédiatement la progression initiale de toutes les voitures.
        self._refresh_progress_all()

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

        # Si la voiture est détruite, la partie est terminée.
        if self.car_damage and car.destroyed:
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

                    # Passage suivant : un tour est terminé.
                    else:
                        completed = car.current_lap_time
                        car.last_lap_time = completed

                        # Mise à jour du meilleur tour.
                        if car.best_lap_time is None or completed < car.best_lap_time:
                            car.best_lap_time = completed

                        car.completed_laps += 1

                        # Fin de course si le nombre de tours est atteint.
                        if car.completed_laps >= self.laps_to_win:
                            car.finished = True
                        else:
                            car.lap = car.completed_laps + 1
                            car.current_lap_time = 0.0

                # Passage de la ligne dans le mauvais sens.
                else:
                    if car.lap_timing_started and not getattr(car, "is_bot", False):
                        self._respawn_player_with_penalty(car, time_penalty=3.0)

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

            # Mise à jour du joueur.
            else:
                control = controls_by_player.get(car.player_id, {})
                car.update(dt, control)

                # Sortie de piste : respawn avec pénalité.
                if self.track.is_off_track(car.x, car.y):
                    self._respawn_player_with_penalty(
                        car,
                        time_penalty=2.5,
                        impact_penalty=10.0,
                    )
                    continue

                # Vérification du mauvais sens.
                self._check_wrong_direction(car, dt)

                # Si les dégâts sont activés, une voiture détruite finit la partie.
                if self.car_damage and car.destroyed:
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

        # Progression de chaque voiture sur le circuit.
        self._refresh_progress_all()

        # Game over si le joueur est détruit.
        player = self.player_car
        if player is not None and self.car_damage and player.destroyed:
            self.game_over = True

        # Fin de course dès qu'une voiture termine tous les tours.
        if any(car.finished for car in self.cars):
            self.finished = True

            # Sauvegarde le classement final une seule fois.
            if self.results_snapshot is None:
                self.results_snapshot = self.get_leaderboard()

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
        return sorted(
            self.cars,
            key=lambda c: (
                -c.completed_laps,
                -getattr(c, "track_progress", 0.0),
                c.total_time,
            ),
        )