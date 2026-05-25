import math

import pygame


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
# - le dessin du circuit
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

        sx, sy = self.start_pos

        # Angle de départ de la voiture.
        angle = self._segment_angle(
            self.centerline[(self.start_index - 1) % len(self.centerline)],
            self.centerline[self.start_index],
        )

        # Base locale au niveau du départ.
        # tx, ty : direction de la piste
        # nx, ny : direction latérale
        tx, ty, nx, ny = self._start_basis()

        # Décalage des positions de départ selon le circuit.
        if self.layout_name == "track_2":
            back_offset = 220.0
            lane_offset = 40.0
        else:
            back_offset = 96.0
            lane_offset = 24.0

        # Position de départ du joueur 1.
        p1x = sx - tx * back_offset - nx * lane_offset
        p1y = sy - ty * back_offset - ny * lane_offset

        # Position de départ du joueur 2 ou référence secondaire.
        p2x = sx - tx * back_offset + nx * lane_offset
        p2y = sy - ty * back_offset + ny * lane_offset

        self.spawn_positions = {
            1: (p1x, p1y, angle),
            2: (p2x, p2y, angle),
        }

        # Surface invisible utilisée pour détecter si une voiture est sur la route.
        self.road_mask_surface = pygame.Surface(
            (self.world_width, self.world_height),
            pygame.SRCALPHA,
        )

        self.road_mask = None
        self._build_road_mask()

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

    def _build_road_mask(self):
        """
        Construit le masque invisible de la route.

        Le masque permet de savoir rapidement si une voiture
        est sur la piste ou hors piste.
        """

        self.road_mask_surface.fill((0, 0, 0, 0))

        # Trace la route principale.
        pygame.draw.lines(
            self.road_mask_surface,
            (255, 255, 255, 255),
            True,
            self.centerline,
            self.road_half_width * 2,
        )

        # Ajoute des cercles pour remplir les virages et jonctions.
        for x, y in self.centerline:
            pygame.draw.circle(
                self.road_mask_surface,
                (255, 255, 255, 255),
                (int(x), int(y)),
                self.road_half_width,
            )

        self.road_mask = pygame.mask.from_surface(self.road_mask_surface)

    def is_on_road(self, x: float, y: float) -> bool:
        """
        Vérifie si un point est sur la route.
        """

        xi, yi = int(x), int(y)

        # En dehors du monde = hors piste.
        if xi < 0 or yi < 0 or xi >= self.world_width or yi >= self.world_height:
            return False

        return self.road_mask.get_at((xi, yi)) == 1

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

        r = self.get_progress_from_start(x, y)

        # ----------------------------------------------------
        # Circuit de démonstration
        # ----------------------------------------------------
        if self.layout_name == "track_2":
            # Le départ est sur la ligne droite du bas.
            pre_start_respawn = (2920, 2262, 180)
            post_start_respawn = (2100, 2265, 180)

            # Si le joueur est déjà après la ligne,
            # on évite de le renvoyer avant la ligne.
            if after_start:
                if r < 0.22:
                    return post_start_respawn

            if 0.00 <= r < 0.18:
                return pre_start_respawn

            if 0.18 <= r < 0.36:
                return (3400, 845, 28)

            if 0.36 <= r < 0.54:
                return (3790, 1500, 90)

            if 0.54 <= r < 0.72:
                return (3050, 2255, 180)

            if 0.72 <= r < 0.88:
                return (1160, 2200, -165)

            return (610, 1450, -95)

        # ----------------------------------------------------
        # Circuit principal
        # ----------------------------------------------------
        if after_start and r < 0.12:
            return (2050, 805, 6)

        if 0.00 <= r < 0.10:
            return (980, 300, 58)

        if 0.10 <= r < 0.18:
            return (2050, 805, 6)

        if 0.18 <= r < 0.34:
            return (2760, 875, 18)

        if 0.34 <= r < 0.50:
            return (3040, 1080, 80)

        if 0.50 <= r < 0.66:
            return (2650, 1355, 180)

        if 0.66 <= r < 0.82:
            return (1700, 1315, 185)

        if 0.82 <= r < 0.92:
            return (760, 1188, 180)

        return (250, 700, -92)

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

    def draw_world(self, surface: pygame.Surface):
        """
        Dessine tout le circuit sur une surface Pygame.

        Cette méthode dessine :
        - l'herbe
        - les motifs de fond
        - les bordures de route
        - la route
        - la ligne de départ
        """

        # Fond herbe.
        surface.fill((45, 90, 48))

        # Motifs verticaux sur l'herbe.
        for x in range(0, self.world_width, 180):
            pygame.draw.rect(
                surface,
                (41, 82, 44),
                (x, 0, 90, self.world_height),
            )

        # Motifs horizontaux sur l'herbe.
        for y in range(0, self.world_height, 220):
            pygame.draw.line(
                surface,
                (36, 74, 39),
                (0, y),
                (self.world_width, y),
                1,
            )

        # Bordure extérieure claire.
        pygame.draw.lines(
            surface,
            (210, 210, 210),
            True,
            self.centerline,
            self.road_half_width * 2 + 10,
        )

        for x, y in self.centerline:
            pygame.draw.circle(
                surface,
                (210, 210, 210),
                (int(x), int(y)),
                self.road_half_width + 5,
            )

        # Route grise.
        pygame.draw.lines(
            surface,
            (72, 74, 78),
            True,
            self.centerline,
            self.road_half_width * 2,
        )

        for x, y in self.centerline:
            pygame.draw.circle(
                surface,
                (72, 74, 78),
                (int(x), int(y)),
                self.road_half_width,
            )

        # Ligne départ/arrivée.
        self._draw_start_line(surface)

    def _draw_start_line(self, surface: pygame.Surface):
        """
        Dessine la ligne départ/arrivée en damier.
        """

        line_center = self.start_pos
        tx, ty, nx, ny = self._start_basis()

        # Dimensions différentes selon le circuit.
        if self.layout_name == "track_2":
            half_len = 128
            thickness = 32
            tile = 20
        else:
            half_len = 58
            thickness = 20
            tile = 14

        start_x = line_center[0] - nx * half_len
        start_y = line_center[1] - ny * half_len

        # Construction du damier.
        for i in range(int((half_len * 2) // tile)):
            for j in range(2):
                color = (255, 255, 255) if (i + j) % 2 == 0 else (20, 20, 20)

                x = start_x + nx * tile * i
                y = start_y + ny * tile * i

                p1 = (x, y)
                p2 = (x + nx * tile, y + ny * tile)
                p3 = (p2[0] + tx * thickness, p2[1] + ty * thickness)
                p4 = (p1[0] + tx * thickness, p1[1] + ty * thickness)

                pygame.draw.polygon(surface, color, [p1, p2, p3, p4])