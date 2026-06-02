import math


# ============================================================
# Intelligence artificielle des bots
# ============================================================
# Ce fichier gère la conduite automatique des voitures adverses.
#
# Chaque bot suit la ligne centrale du circuit, mais peut aussi :
# - adapter sa vitesse avant les virages
# - choisir une trajectoire légèrement décalée
# - dépasser une voiture plus lente
# - éviter les situations trop risquées côte à côte
# - recevoir un bonus de vitesse en ligne droite
# ============================================================


class BotDriver:
    """
    Pilote automatique utilisé par une voiture bot.

    Le bot ne simule pas exactement les mêmes commandes que le joueur.
    Il suit une trajectoire calculée sur la ligne centrale du circuit,
    avec quelques ajustements pour donner un comportement plus naturel.
    """

    def __init__(
        self,
        track,
        difficulty="hard",
        lane_bias=0.0,
        pace_factor=1.0,
        style="balanced",
    ):
        """
        Initialise le comportement du bot.

        track :
            circuit sur lequel le bot roule

        difficulty :
            niveau de difficulté du bot

        lane_bias :
            décalage latéral de trajectoire

        pace_factor :
            facteur qui rend le bot légèrement plus lent ou plus rapide

        style :
            style de conduite du bot
        """

        # Circuit utilisé par le bot.
        self.track = track

        # Niveau de difficulté choisi.
        self.difficulty = difficulty

        # Progression du bot sur la ligne centrale.
        self.progress = 0.0

        # Vitesse actuelle du bot.
        self.speed = 0.0

        # Décalage de voie pour éviter que tous les bots roulent pareil.
        self.lane_bias = lane_bias

        # Ajustement individuel du rythme.
        self.pace_factor = pace_factor

        # Style de conduite : balanced, late_braker, traction, cautious.
        self.style = style

        # Chronomètre du bonus de vitesse en ligne droite.
        self.drs_timer = 0.0

        # État du dépassement.
        self.overtake_mode = False
        self.overtake_timer = 0.0
        self.overtake_side = 0.0
        self.overtake_target_id = None

        # Paramètres principaux selon la difficulté.
        self.params = {
            "easy": {
                "top_speed": 228.0,
                "accel": 96.0,
                "brake": 116.0,
                "corner_factor": 1.22,
                "drs_bonus": 16.0,
                "lane_keep": 0.92,
                "overtake_bonus": 18.0,
                "commit_time": 1.7,
            },
            "medium": {
                "top_speed": 262.0,
                "accel": 114.0,
                "brake": 128.0,
                "corner_factor": 1.28,
                "drs_bonus": 22.0,
                "lane_keep": 0.95,
                "overtake_bonus": 26.0,
                "commit_time": 2.1,
            },
            "hard": {
                "top_speed": 292.0,
                "accel": 132.0,
                "brake": 122.0,
                "corner_factor": 1.34,
                "drs_bonus": 28.0,
                "lane_keep": 0.98,
                "overtake_bonus": 34.0,
                "commit_time": 2.5,
            },
            "expert": {
                "top_speed": 314.0,
                "accel": 144.0,
                "brake": 118.0,
                "corner_factor": 1.40,
                "drs_bonus": 34.0,
                "lane_keep": 1.0,
                "overtake_bonus": 42.0,
                "commit_time": 2.8,
            },
        }[difficulty]

    def _normalize_angle(self, angle):
        """
        Ramène un angle entre -180 et 180 degrés.

        Cela permet de comparer proprement deux directions.
        """
        while angle > 180:
            angle -= 360

        while angle < -180:
            angle += 360

        return angle

    def _distance(self, a, b):
        """
        Calcule la distance entre deux points.
        """
        return math.hypot(b[0] - a[0], b[1] - a[1])

    def _curvature_ahead(self, idx):
        """
        Estime la courbure de la piste devant le bot.

        Plus la valeur est grande, plus le virage à venir est serré.
        Cette information sert à réduire la vitesse avant les virages.
        """

        pts = self.track.centerline
        n = len(pts)

        # Points regardés devant le bot.
        sample_offsets = [4, 8, 12, 18]

        total = 0.0
        prev_angle = None

        for off in sample_offsets:
            a = pts[(idx + off - 2) % n]
            b = pts[(idx + off) % n]

            angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

            if prev_angle is not None:
                total += abs(self._normalize_angle(angle - prev_angle))

            prev_angle = angle

        return total

    def _style_adjusted_target_speed(self, idx):
        """
        Calcule la vitesse cible selon :
        - la difficulté
        - la courbure de la piste
        - le style de conduite du bot
        """

        curvature = self._curvature_ahead(idx)
        base = self.params["top_speed"] * self.pace_factor

        # Un late braker freine plus tard.
        if self.style == "late_braker":
            corner_factor = self.params["corner_factor"] * 0.92

        # Un bot traction conserve mieux sa vitesse.
        elif self.style == "traction":
            corner_factor = self.params["corner_factor"] * 0.98

        # Un bot prudent ralentit plus.
        elif self.style == "cautious":
            corner_factor = self.params["corner_factor"] * 1.10

        # Style normal.
        else:
            corner_factor = self.params["corner_factor"]

        # Plus la courbure est forte, plus la vitesse cible baisse.
        target = base - curvature * corner_factor

        return max(160.0, min(base, target))

    def _nearest_index(self, x, y):
        """
        Trouve le point de la ligne centrale le plus proche d'une position.

        Cette méthode permet de synchroniser une voiture avec la piste.
        """

        pts = self.track.centerline
        best_i = 0
        best_d2 = None

        for i, (px, py) in enumerate(pts):
            d2 = (px - x) ** 2 + (py - y) ** 2

            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best_i = i

        return best_i

    def _offset_point(self, idx, offset):
        """
        Crée un point décalé latéralement par rapport à la ligne centrale.

        Cela permet aux bots de ne pas tous rouler exactement
        au centre de la piste.
        """

        pts = self.track.centerline
        n = len(pts)

        p_prev = pts[(idx - 1) % n]
        p_cur = pts[idx % n]
        p_next = pts[(idx + 1) % n]

        # Direction locale de la piste.
        vx = p_next[0] - p_prev[0]
        vy = p_next[1] - p_prev[1]

        ln = math.hypot(vx, vy)

        if ln == 0:
            return p_cur

        vx /= ln
        vy /= ln

        # Normale à la piste.
        nx = -vy
        ny = vx

        return (p_cur[0] + nx * offset, p_cur[1] + ny * offset)

    def _progress_gap(self, my_progress, other_progress, n):
        """
        Calcule l'écart de progression entre deux voitures.

        Le circuit est fermé, donc on corrige l'écart
        quand une voiture passe de la fin au début du tour.
        """

        gap = other_progress - my_progress

        while gap < 0:
            gap += n

        return gap

    def _find_car_ahead_on_track(self, car, all_cars):
        """
        Cherche une voiture proche devant le bot.

        Cette fonction sert à déclencher un dépassement
        ou un bonus de vitesse.
        """

        if not all_cars:
            return None, None

        n = len(self.track.centerline)
        best_car = None
        best_gap = None

        # Progression actuelle du bot.
        my_progress = getattr(car, "bot_progress_proxy", self.progress)

        for other in all_cars:
            if other is car:
                continue

            # Progression de l'autre voiture.
            other_progress = getattr(other, "bot_progress_proxy", None)

            if other_progress is None:
                other_progress = float(self._nearest_index(other.x, other.y))

            gap = self._progress_gap(my_progress, other_progress, n)

            # On ne garde que les voitures proches devant.
            if 0 < gap < 48:
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    best_car = other

        return best_car, best_gap

    def _find_side_by_side_risk(self, car, all_cars):
        """
        Détecte si une voiture est trop proche sur le côté.

        Le bot ralentit légèrement dans cette situation
        pour éviter de pousser directement une autre voiture.
        """

        if not all_cars:
            return None

        heading = math.radians(car.angle_deg)
        fx = math.cos(heading)
        fy = math.sin(heading)

        my_progress = getattr(car, "bot_progress_proxy", self.progress)
        n = len(self.track.centerline)

        best = None
        best_score = None

        for other in all_cars:
            if other is car:
                continue

            other_progress = getattr(other, "bot_progress_proxy", None)

            if other_progress is None:
                other_progress = float(self._nearest_index(other.x, other.y))

            ahead_gap = self._progress_gap(my_progress, other_progress, n)
            behind_gap = self._progress_gap(other_progress, my_progress, n)

            signed_gap = ahead_gap if ahead_gap < behind_gap else -behind_gap

            # Position de l'autre voiture dans le repère du bot.
            rx = other.x - car.x
            ry = other.y - car.y

            longitudinal_world = fx * rx + fy * ry
            lateral_world = (-fy * rx) + (fx * ry)

            abs_long_track = abs(signed_gap)
            abs_long_world = abs(longitudinal_world)
            abs_lat_world = abs(lateral_world)

            # Situation côte à côte proche.
            if abs_long_track < 8 and abs_long_world < 60 and abs_lat_world < 34:
                score = abs_long_track + abs_lat_world * 0.2

                if best_score is None or score < best_score:
                    best_score = score
                    best = {
                        "car": other,
                        "signed_gap": signed_gap,
                        "longitudinal_world": longitudinal_world,
                        "lateral_world": lateral_world,
                    }

        return best

    def _start_overtake_if_needed(self, car, all_cars):
        """
        Lance un dépassement si une voiture plus lente est proche devant.
        """

        ahead_car, gap = self._find_car_ahead_on_track(car, all_cars)

        if ahead_car is None or gap is None:
            return

        # Pas de dépassement si un virage arrive.
        curvature = self._curvature_ahead(int(self.progress) % len(self.track.centerline))

        if curvature > 18:
            return

        # Pas de dépassement si la voiture devant est déjà plus rapide.
        if self.speed + 4 < getattr(ahead_car, "speed", 0):
            return

        # Choix du côté de dépassement.
        heading = math.radians(car.angle_deg)
        fx = math.cos(heading)
        fy = math.sin(heading)

        rx = ahead_car.x - car.x
        ry = ahead_car.y - car.y

        lateral = (-fy * rx) + (fx * ry)

        self.overtake_side = -1.0 if lateral >= 0 else 1.0
        self.overtake_mode = True
        self.overtake_timer = self.params["commit_time"]
        self.overtake_target_id = ahead_car.player_id

    def _update_overtake_state(self, car, all_cars, dt):
        """
        Met à jour l'état d'un dépassement en cours.

        Le bot conserve son engagement pendant un court moment,
        puis revient progressivement à une trajectoire normale.
        """

        if not self.overtake_mode:
            self._start_overtake_if_needed(car, all_cars)
            return

        self.overtake_timer -= dt

        # Retrouve la voiture ciblée par le dépassement.
        target_car = None

        if all_cars and self.overtake_target_id is not None:
            for other in all_cars:
                if other.player_id == self.overtake_target_id:
                    target_car = other
                    break

        # Si la cible n'existe plus, on termine le dépassement.
        if target_car is None:
            if self.overtake_timer <= 0:
                self.overtake_mode = False
                self.overtake_side = 0.0
                self.overtake_target_id = None

            return

        my_progress = getattr(car, "bot_progress_proxy", self.progress)

        other_progress = getattr(target_car, "bot_progress_proxy", None)

        if other_progress is None:
            other_progress = float(self._nearest_index(target_car.x, target_car.y))

        n = len(self.track.centerline)

        # Si le bot a dépassé la cible, le dépassement se termine bientôt.
        behind_gap = self._progress_gap(other_progress, my_progress, n)

        if 5 < behind_gap < 34:
            self.overtake_timer = min(self.overtake_timer, 0.8)

        if self.overtake_timer <= 0:
            self.overtake_mode = False
            self.overtake_side = 0.0
            self.overtake_target_id = None

    def _update_drs(self, car, all_cars, idx, dt):
        """
        Simule un petit bonus de vitesse en ligne droite.

        Ce bonus s'active quand le bot est proche d'une voiture devant lui
        et que la piste n'est pas trop courbée.
        """

        curvature = self._curvature_ahead(idx)

        # Pas de bonus dans les virages.
        if curvature > 11:
            self.drs_timer = max(0.0, self.drs_timer - 2.0 * dt)
            return 0.0

        ahead_car, gap = self._find_car_ahead_on_track(car, all_cars)

        # Accumulation du bonus si une voiture est proche devant.
        if ahead_car is not None and gap is not None and gap < 28:
            self.drs_timer = min(1.8, self.drs_timer + dt)
        else:
            self.drs_timer = max(0.0, self.drs_timer - dt)

        if self.drs_timer > 0.10:
            return self.params["drs_bonus"]

        return 0.0

    def _realign_before_corner(self, idx):
        """
        Réduit le décalage latéral avant un virage.

        Le bot se rapproche du centre de la piste
        pour mieux prendre la courbe.
        """

        curvature = self._curvature_ahead(idx)

        if curvature < 10:
            return self.params["lane_keep"]

        if curvature < 18:
            return 0.90

        return 0.76

    def sync_to_car(self, car):
        """
        Synchronise le pilote automatique avec la voiture réelle.

        Cette méthode est utile après :
        - un placement initial
        - une collision
        - un déplacement forcé du bot
        """

        self.progress = float(self._nearest_index(car.x, car.y))
        self.speed = max(0.0, car.speed)

        # Cette valeur est utilisée pour comparer les progressions.
        car.bot_progress_proxy = self.progress

    def update_car(self, car, dt, all_cars=None):
        """
        Met à jour la voiture bot.

        Contrairement au joueur, le bot n'utilise pas directement
        accélération/frein/direction. Sa position est déplacée
        le long d'une trajectoire calculée sur le circuit.
        """

        pts = self.track.centerline
        n = len(pts)

        idx = int(self.progress) % n

        # Met à jour un éventuel dépassement.
        self._update_overtake_state(car, all_cars, dt)

        # Vitesse cible selon la piste et le style.
        target_speed = self._style_adjusted_target_speed(idx)

        # Petit ralentissement dans une zone spécifique du circuit.
        r = idx / max(1, n - 1)
        in_second_corner = 0.10 <= r < 0.18

        if in_second_corner:
            target_speed -= 2.0

        # Bonus de vitesse en ligne droite.
        target_speed += self._update_drs(car, all_cars, idx, dt)

        # Bonus supplémentaire pendant un dépassement.
        if self.overtake_mode:
            target_speed += self.params["overtake_bonus"]

        # Aide au départ pour éviter que les bots restent trop lents.
        if self.speed < 70.0:
            target_speed = max(target_speed, self.params["top_speed"] * 0.72)

        overlap = None
        safety_hold = False

        # Évite une prudence excessive juste au lancement.
        if self.speed > 85.0:
            overlap = self._find_side_by_side_risk(car, all_cars)

        # Ralentissement léger si une voiture est trop proche sur le côté.
        if overlap is not None:
            other = overlap["car"]
            signed_gap = overlap["signed_gap"]
            other_speed = getattr(other, "speed", 0.0)

            if signed_gap > -2.0:
                safety_hold = True
                target_speed = min(target_speed, other_speed + 6.0)

                if signed_gap >= 0.0:
                    target_speed = min(target_speed, max(150.0, other_speed + 3.0))

        # Limite maximale absolue du bot.
        absolute_cap = (
            self.params["top_speed"] * self.pace_factor
            + self.params["drs_bonus"]
            + self.params["overtake_bonus"]
        )

        # Accélération ou freinage vers la vitesse cible.
        if self.speed < target_speed:
            accel_scale = 1.0

            if safety_hold:
                accel_scale = 0.72

            self.speed += self.params["accel"] * accel_scale * dt

        else:
            brake_scale = 0.72

            if safety_hold:
                brake_scale = 0.82

            self.speed -= self.params["brake"] * brake_scale * dt

        # Limitation finale de la vitesse.
        self.speed = max(0.0, min(absolute_cap, self.speed))

        # Distance à parcourir pendant cette image.
        travel = self.speed * dt

        # Avance sur les segments de la ligne centrale.
        while travel > 0:
            idx = int(self.progress) % n
            next_idx = (idx + 1) % n

            p1 = pts[idx]
            p2 = pts[next_idx]

            seg_len = self._distance(p1, p2)
            local_t = self.progress - int(self.progress)

            remaining_on_seg = max(0.001, seg_len * (1.0 - local_t))

            if travel < remaining_on_seg:
                step_t = travel / seg_len
                self.progress += step_t
                travel = 0

            else:
                self.progress = float(next_idx)
                travel -= remaining_on_seg

        # Position actuelle sur la piste.
        idx = int(self.progress) % n
        next_idx = (idx + 1) % n

        # Le bot se recentre plus ou moins selon le virage à venir.
        realign = self._realign_before_corner(idx)

        # Décalage latéral normal.
        total_offset = self.lane_bias * realign

        # Décalage supplémentaire pendant un dépassement.
        if self.overtake_mode:
            total_offset += self.overtake_side * 34.0 * realign

        # Réduction du décalage si situation dangereuse.
        if safety_hold:
            total_offset *= 0.78

        # Limite pour rester sur la piste.
        max_offset = self.track.road_half_width * 0.42
        total_offset = max(-max_offset, min(max_offset, total_offset))

        # Points décalés utilisés comme trajectoire.
        p1 = self._offset_point(idx, total_offset)
        p2 = self._offset_point(next_idx, total_offset)

        t = self.progress - int(self.progress)

        # Interpolation entre deux points de la trajectoire.
        car.x = p1[0] + (p2[0] - p1[0]) * t
        car.y = p1[1] + (p2[1] - p1[1]) * t

        # Orientation du bot dans le sens de la piste.
        car.angle_deg = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))

        # Synchronisation de la vitesse affichée.
        car.speed = self.speed

        # Progression utilisée par les autres systèmes.
        car.bot_progress_proxy = self.progress
