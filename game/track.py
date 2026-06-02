import math


# ============================================================
# Gestion des circuits
# ============================================================
# Ce fichier gère :
# - la création des tracés
# - la ligne centrale du circuit
# - la largeur de la route
# - les positions de départ
# - les zones hors piste
# - les respawns après pénalité
# - le passage de la ligne départ/arrivée
# ============================================================


class Track:
    """
    Représente un circuit complet.

    Le circuit est construit à partir de points de contrôle.
    Ces points sont ensuite lissés pour obtenir une trajectoire plus propre.
    """

    def __init__(self, layout_name="track_1"):
        """
        Initialise un circuit.

        layout_name :
            "track_1" = circuit principal
            "track_2" = circuit de démonstration
        """

        self.layout_name = layout_name

        # Choix du circuit et de ses dimensions.
        if layout_name == "track_2":
            self.world_width = 4400
            self.world_height = 2500
            self.road_half_width = 112
            base_points = self._build_track_2_points()

        else:
            self.world_width = 3400
            self.world_height = 1900
            self.road_half_width = 58
            base_points = self._build_track_1_points()

        # Ligne centrale lissée du circuit.
        self.centerline = self._chaikin_closed(base_points, iterations=2)
        self.checkpoint_count = 8

        # Position de la ligne de départ selon le circuit.
        if self.layout_name == "track_2":
            self.start_index = self._nearest_centerline_index_to_point(2450, 2260)
        else:
            self.start_index = 2

        # Point exact de la ligne de départ.
        self.start_pos = self.centerline[self.start_index]

        # Point précédent utilisé pour connaître le sens de la piste.
        self.prev_start_pos = self.centerline[
            (self.start_index - 1) % len(self.centerline)
        ]

        # Pre-compute squared road half-width for fast collision checks.
        self._road_hw_sq = self.road_half_width ** 2

        self.spawn_positions = {
            1: self.get_grid_position(0),
            2: self.get_grid_position(1),
        }

    def _build_track_1_points(self):
        """
        Retourne les points de contrôle du circuit principal.

        Ces points définissent la forme globale du tracé.
        """
        return [
            (1540, 760),
            (1850, 790),
            (2200, 825),
            (2550, 860),
            (2870, 890),
            (3070, 930),
            (3160, 1010),
            (3190, 1110),
            (3160, 1210),
            (3090, 1290),
            (2970, 1340),
            (2730, 1360),
            (2420, 1360),
            (2090, 1345),
            (1760, 1325),
            (1450, 1300),
            (1220, 1280),
            (1110, 1270),
            (1050, 1255),
            (1035, 1215),
            (1065, 1185),
            (980, 1185),
            (830, 1190),
            (690, 1185),
            (560, 1160),
            (450, 1100),
            (360, 1010),
            (300, 900),
            (265, 760),
            (245, 600),
            (235, 430),
            (230, 280),
            (220, 205),
            (190, 190),
            (175, 170),
            (170, 145),
            (185, 110),
            (250, 70),
            (370, 58),
            (520, 60),
            (690, 68),
            (860, 82),
            (940, 190),
            (1030, 340),
            (1140, 500),
            (1260, 650),
            (1390, 800),
        ]

    def _build_track_2_points(self):
        """
        Retourne les points de contrôle du circuit de démonstration.
        """
        return [
            (1200, 860),
            (1520, 790),
            (1970, 740),
            (2470, 735),
            (3000, 740),
            (3380, 815),
            (3660, 1020),
            (3810, 1330),
            (3810, 1670),
            (3660, 1980),
            (3380, 2180),
            (3000, 2260),
            (2480, 2265),
            (1960, 2265),
            (1460, 2235),
            (1030, 2120),
            (720, 1900),
            (560, 1580),
            (560, 1210),
            (650, 980),
            (830, 860),
            (1010, 850),
        ]

    def _chaikin_closed(self, points, iterations=2):
        """
        Lisse une courbe fermée avec l'algorithme de Chaikin.

        Le but est d'obtenir un circuit plus arrondi
        à partir de points de contrôle assez anguleux.
        """

        pts = points[:]

        for _ in range(iterations):
            new_pts = []
            n = len(pts)

            for i in range(n):
                p0 = pts[i]
                p1 = pts[(i + 1) % n]

                # Premier point intermédiaire.
                q = (
                    0.75 * p0[0] + 0.25 * p1[0],
                    0.75 * p0[1] + 0.25 * p1[1],
                )

                # Deuxième point intermédiaire.
                r = (
                    0.25 * p0[0] + 0.75 * p1[0],
                    0.25 * p0[1] + 0.75 * p1[1],
                )

                new_pts.append(q)
                new_pts.append(r)

            pts = new_pts

        return pts

    def _segment_angle(self, a, b):
        """
        Calcule l'angle d'un segment entre deux points.
        """
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

    def _nearest_centerline_index_to_point(self, x: float, y: float) -> int:
        """
        Trouve l'indice du point de ligne centrale le plus proche.
        """

        best_i = 0
        best_d2 = None

        for i, (cx, cy) in enumerate(self.centerline):
            d2 = (cx - x) ** 2 + (cy - y) ** 2

            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best_i = i

        return best_i

    def _start_basis(self):
        """
        Calcule la base locale de la ligne de départ.

        Retourne :
        - tx, ty : vecteur tangent à la piste
        - nx, ny : vecteur normal à la piste
        """

        before = self.prev_start_pos
        center = self.start_pos

        dx = center[0] - before[0]
        dy = center[1] - before[1]

        tangent_len = math.hypot(dx, dy)

        if tangent_len == 0:
            return 1.0, 0.0, 0.0, 1.0

        tx = dx / tangent_len
        ty = dy / tangent_len

        nx = -ty
        ny = tx

        return tx, ty, nx, ny

    def get_start_basis(self):
        """
        Retourne la base locale du départ.

        Cette méthode est utilisée par Race pour placer les voitures.
        """
        return self._start_basis()

    def _basis_at_index(self, idx: int):
        n = len(self.centerline)
        a = self.centerline[idx % n]
        b = self.centerline[(idx + 1) % n]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return 1.0, 0.0, 0.0, 1.0, 0.0

        tx = dx / length
        ty = dy / length
        nx = -ty
        ny = tx
        angle = math.degrees(math.atan2(ty, tx))
        return tx, ty, nx, ny, angle

    def _walk_centerline(self, start_idx: int, distance: float, direction: int):
        """
        Avance sur la ligne centrale.

        direction = 1 avance dans le sens de course.
        direction = -1 recule avant le point donné.
        """
        n = len(self.centerline)
        idx = start_idx % n
        remaining = max(0.0, distance)

        while remaining > 0.0:
            next_idx = (idx + direction) % n
            ax, ay = self.centerline[idx]
            bx, by = self.centerline[next_idx]
            segment_len = math.hypot(bx - ax, by - ay)

            if segment_len <= 1e-6:
                idx = next_idx
                continue

            if remaining <= segment_len:
                t = remaining / segment_len
                x = ax + (bx - ax) * t
                y = ay + (by - ay) * t
                basis_idx = idx if direction > 0 else next_idx
                return x, y, basis_idx

            remaining -= segment_len
            idx = next_idx

        x, y = self.centerline[idx]
        return x, y, idx

    def _safe_pose(self, center_x: float, center_y: float, basis_idx: int, lateral_offset: float = 0.0):
        tx, ty, nx, ny, angle = self._basis_at_index(basis_idx)
        max_offset = max(0.0, self.road_half_width - 30.0)
        offset = max(-max_offset, min(max_offset, lateral_offset))

        for scale in (1.0, 0.75, 0.5, 0.25, 0.0):
            x = center_x + nx * offset * scale
            y = center_y + ny * offset * scale
            if self.is_on_road(x, y):
                return x, y, angle

        return center_x, center_y, angle

    def get_grid_position(self, slot_index: int):
        """
        Retourne une position de grille sûre, alignée sur la piste.
        """
        if self.layout_name == "track_2":
            front_offset = 150.0
            row_gap = 88.0
            lane_gap = 70.0
        else:
            front_offset = 92.0
            row_gap = 66.0
            lane_gap = 38.0

        row = slot_index // 2
        col = slot_index % 2
        side = -0.5 if col == 0 else 0.5
        if row % 2 == 1:
            side *= -1

        center_x, center_y, basis_idx = self._walk_centerline(
            self.start_index,
            front_offset + row * row_gap,
            direction=-1,
        )
        return self._safe_pose(center_x, center_y, basis_idx, side * lane_gap)

    def _point_to_segment_dist_sq(self, px, py, ax, ay, bx, by):
        """
        Calcule le carré de la distance d'un point à un segment.
        """
        abx = bx - ax
        aby = by - ay
        ab_len_sq = abx * abx + aby * aby

        if ab_len_sq == 0:
            return (px - ax) ** 2 + (py - ay) ** 2

        t = ((px - ax) * abx + (py - ay) * aby) / ab_len_sq
        t = max(0.0, min(1.0, t))

        proj_x = ax + t * abx
        proj_y = ay + t * aby

        return (px - proj_x) ** 2 + (py - proj_y) ** 2

    def is_on_road(self, x: float, y: float) -> bool:
        """
        Vérifie si un point est sur la route.

        Utilise la distance au segment de ligne centrale le plus proche.
        """

        if x < 0 or y < 0 or x >= self.world_width or y >= self.world_height:
            return False

        n = len(self.centerline)
        for i in range(n):
            ax, ay = self.centerline[i]
            bx, by = self.centerline[(i + 1) % n]

            if self._point_to_segment_dist_sq(x, y, ax, ay, bx, by) <= self._road_hw_sq:
                return True

        return False

    def is_off_track(self, x: float, y: float) -> bool:
        """
        Vérifie si un point est hors piste.
        """
        return not self.is_on_road(x, y)

    def get_spawn(self, player_id: int):
        """
        Retourne la position de départ associée à un joueur.
        """
        return self.spawn_positions.get(player_id, self.spawn_positions[1])

    def _nearest_centerline_index(self, x: float, y: float) -> int:
        """
        Version interne pour trouver le point de piste le plus proche.
        """
        return self._nearest_centerline_index_to_point(x, y)

    def get_track_tangent(self, x: float, y: float):
        """
        Retourne la direction locale de la piste.

        Cette direction sert notamment à détecter si le joueur roule
        dans le bon sens.
        """

        idx = self._nearest_centerline_index(x, y)
        n = len(self.centerline)

        a = self.centerline[idx]
        b = self.centerline[(idx + 1) % n]

        dx = b[0] - a[0]
        dy = b[1] - a[1]

        norm = math.hypot(dx, dy)

        if norm == 0:
            return (1.0, 0.0)

        return (dx / norm, dy / norm)

    def get_progress_from_start(self, x: float, y: float) -> float:
        """
        Calcule la progression sur le circuit depuis la ligne de départ.

        La valeur retournée est comprise entre 0 et 1.
        """

        idx = self._nearest_centerline_index(x, y)
        n = len(self.centerline)

        rel = (idx - self.start_index) % n

        return rel / max(1, n)

    def get_checkpoint_index(self, x: float, y: float) -> int:
        """
        Retourne l'indice de checkpoint logique correspondant à la position.
        """
        progress = self.get_progress_from_start(x, y)
        return max(0, min(self.checkpoint_count - 1, int(progress * self.checkpoint_count)))

    def get_checkpoint_respawn(self, checkpoint_index: int, lateral_offset: float = 0.0):
        """
        Retourne un respawn sûr aligné avec un checkpoint validé.
        """
        checkpoint = max(0, min(self.checkpoint_count - 1, int(checkpoint_index)))
        n = len(self.centerline)
        idx = (self.start_index + int((checkpoint / self.checkpoint_count) * n)) % n
        center_x, center_y = self.centerline[idx]
        return self._safe_pose(center_x, center_y, idx, lateral_offset)

    def is_after_start_line(self, x: float, y: float) -> bool:
        """
        Vérifie si un point est après la ligne de départ.

        Le test utilise une projection sur la tangente de la piste.
        """

        tx, ty, _, _ = self._start_basis()
        sx, sy = self.start_pos

        vx = x - sx
        vy = y - sy

        return (vx * tx + vy * ty) > 0.0

    def get_penalty_respawn(self, x: float, y: float, after_start: bool = False):
        """
        Choisit un point de respawn après une pénalité.

        Le point choisi dépend :
        - de la position du joueur sur le circuit
        - du circuit utilisé
        - du fait qu'il soit déjà passé après la ligne de départ

        Le but est d'éviter les bugs de tour gratuit.
        """

        idx = self._nearest_centerline_index(x, y)
        n = len(self.centerline)
        rel = (idx - self.start_index) % n
        min_after_start = max(2, int(n * 0.035))

        if after_start and rel < min_after_start:
            idx = (self.start_index + min_after_start) % n
            center_x, center_y = self.centerline[idx]
            return self._safe_pose(center_x, center_y, idx, 0.0)

        back_distance = 140.0 if self.layout_name == "track_2" else 95.0
        center_x, center_y, basis_idx = self._walk_centerline(idx, back_distance, direction=-1)
        return self._safe_pose(center_x, center_y, basis_idx, 0.0)

    def crossed_start_finish_direction(self, old_pos: tuple, new_pos: tuple) -> int:
        """
        Détecte si la voiture a franchi la ligne départ/arrivée.

        Retourne :
        -  1 si la ligne est franchie dans le bon sens
        - -1 si elle est franchie dans le mauvais sens
        -  0 si elle n'est pas franchie
        """

        line_center = self.start_pos
        tx, ty, nx, ny = self._start_basis()

        # Longueur de la ligne de départ.
        line_half_len = 80 if self.layout_name == "track_1" else 150

        # Extrémités de la ligne.
        ax = line_center[0] - nx * line_half_len
        ay = line_center[1] - ny * line_half_len

        bx = line_center[0] + nx * line_half_len
        by = line_center[1] + ny * line_half_len

        # Si le segment de déplacement ne coupe pas la ligne,
        # il n'y a pas de passage.
        if not self._segments_intersect(old_pos, new_pos, (ax, ay), (bx, by)):
            return 0

        # Direction du déplacement.
        move_x = new_pos[0] - old_pos[0]
        move_y = new_pos[1] - old_pos[1]

        # Produit scalaire avec la direction normale du circuit.
        dot = move_x * tx + move_y * ty

        if dot > 0:
            return 1

        if dot < 0:
            return -1

        return 0

    def _segments_intersect(self, p1, p2, q1, q2):
        """
        Vérifie si deux segments se croisent.

        Cette méthode est utilisée pour détecter le passage
        de la ligne départ/arrivée.
        """

        def ccw(a, b, c):
            return (c[1] - a[1]) * (b[0] - a[0]) > (
                b[1] - a[1]
            ) * (c[0] - a[0])

        return (
            ccw(p1, q1, q2) != ccw(p2, q1, q2)
            and ccw(p1, p2, q1) != ccw(p1, p2, q2)
        )

    def get_drawing_data(self):
        """
        Retourne les données nécessaires pour dessiner le circuit côté client.
        """
        return {
            "centerline": self.centerline,
            "road_half_width": self.road_half_width,
            "world_width": self.world_width,
            "world_height": self.world_height,
            "start_pos": self.start_pos,
            "start_basis": self._start_basis(),
            "layout_name": self.layout_name,
        }
