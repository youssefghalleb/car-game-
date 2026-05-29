import socket
import random
import math

import pygame

from config import WIDTH, HEIGHT, COLOR_TEXT, SERVER_PORT


# ============================================================
# Affichage graphique du jeu
# ============================================================
# Ce fichier gère :
# - la fenêtre Pygame
# - le lobby principal
# - l'affichage de la course
# - la caméra qui suit la voiture
# - le HUD
# - la mini-carte
# - le graphe des signaux du téléphone
# - les effets de drift et de collision
# ============================================================


def get_local_ip() -> str:
    """
    Récupère l'adresse IP locale de l'ordinateur.

    Cette adresse est affichée dans le jeu pour permettre
    au téléphone de se connecter au contrôleur mobile.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        # Connexion fictive utilisée uniquement pour connaître l'IP locale.
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]

    except Exception:
        # Valeur de secours si aucune IP réseau n'est trouvée.
        ip = "127.0.0.1"

    finally:
        sock.close()

    return ip


class Renderer:
    """
    Classe responsable de tout l'affichage du jeu.

    Elle contient :
    - les méthodes de dessin
    - la gestion visuelle du lobby
    - la caméra
    - les panneaux d'informations
    - les effets visuels
    """

    def __init__(self):
        """
        Initialise Pygame, la fenêtre, les polices et les états visuels.
        """

        pygame.init()
        pygame.display.set_caption("Race Game - Single Player + Bots")

        # Fenêtre principale.
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

        # Horloge utilisée pour contrôler les FPS.
        self.clock = pygame.time.Clock()

        # Polices utilisées dans l'interface.
        self.font = pygame.font.SysFont("Arial", 22)
        self.font_small = pygame.font.SysFont("Arial", 18)
        self.font_big = pygame.font.SysFont("Arial", 30)
        self.font_huge = pygame.font.SysFont("Arial", 42)
        self.font_title = pygame.font.SysFont("Arial", 26, bold=True)

        # Adresse IP affichée dans le HUD.
        self.ip = get_local_ip()

        # Particules et effets visuels.
        self.drift_particles = []
        self.crash_particles = []

        # Tremblement caméra après collision.
        self.shake_timer = 0.0
        self.shake_strength = 0.0

        # Flash rouge après collision.
        self.flash_timer = 0.0
        self.flash_strength = 0.0

        # Boutons interactifs du lobby et de la fin de course.
        self.lobby_buttons = {}
        self.race_buttons = {}

        # Historique des signaux du téléphone affichés dans le graphe.
        self.raw_history = []
        self.filtered_history = []
        self.optimized_history = []
        self.signal_history_max = 180

    def tick(self, fps: int):
        """
        Attend le temps nécessaire pour respecter les FPS.

        Retourne le temps écoulé depuis la dernière image, en secondes.
        """
        return self.clock.tick(fps) / 1000.0

    def trigger_crash_effect(self, x: float, y: float, impact_strength: float):
        """
        Crée les effets visuels d'une collision.

        Plus l'impact est fort, plus il y a :
        - de particules
        - de tremblement
        - de flash rouge
        """

        count = min(18, 6 + int(impact_strength / 6.0))

        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 120) + impact_strength * 1.2
            size = random.uniform(2, 4)

            self.crash_particles.append({
                "x": x,
                "y": y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": random.uniform(0.20, 0.40),
                "radius": size,
                "color": random.choice([
                    (255, 210, 80),
                    (255, 150, 40),
                    (180, 180, 180),
                ]),
            })

        # Secousse de caméra.
        self.shake_timer = max(self.shake_timer, 0.18)
        self.shake_strength = max(
            self.shake_strength,
            min(14.0, 2.0 + impact_strength * 0.12),
        )

        # Flash rouge.
        self.flash_timer = max(self.flash_timer, 0.10)
        self.flash_strength = max(
            self.flash_strength,
            min(110.0, 20.0 + impact_strength * 1.2),
        )

    def update_signal_history(self, shared_state):
        """
        Ajoute les dernières valeurs du capteur à l'historique.

        Ces valeurs sont ensuite affichées dans le graphe :
        - signal brut
        - signal filtré
        - signal final optimisé
        """

        player = shared_state.players[1]

        self.raw_history.append(player.raw_sensor)
        self.filtered_history.append(player.filtered_sensor)
        self.optimized_history.append(player.optimized_signal)

        # Garde seulement les dernières valeurs pour éviter une liste infinie.
        if len(self.raw_history) > self.signal_history_max:
            self.raw_history.pop(0)
            self.filtered_history.pop(0)
            self.optimized_history.pop(0)

    # ------------------------------------------------------------
    # Lobby principal
    # ------------------------------------------------------------

    def handle_main_lobby_event(self, event, settings):
        """
        Gère les interactions dans le lobby principal.

        Le joueur peut :
        - écrire son nom
        - changer le nombre de tours
        - changer le nombre de bots
        - changer la difficulté
        - choisir clavier ou téléphone
        - activer/désactiver les dégâts
        - choisir le circuit
        - lancer la course
        """

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                settings["player_name"] = settings["player_name"][:-1]

            elif event.key == pygame.K_RETURN:
                return "start"

            else:
                ch = event.unicode

                if ch.isprintable() and len(settings["player_name"]) < 16:
                    settings["player_name"] += ch

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            for key, rect in self.lobby_buttons.items():
                if rect.collidepoint(mx, my):
                    if key == "laps_minus":
                        settings["laps_to_win"] = max(1, settings["laps_to_win"] - 1)

                    elif key == "laps_plus":
                        settings["laps_to_win"] = min(20, settings["laps_to_win"] + 1)

                    elif key == "bots_minus":
                        settings["bot_count"] = max(1, settings["bot_count"] - 1)

                    elif key == "bots_plus":
                        settings["bot_count"] = min(4, settings["bot_count"] + 1)

                    elif key == "difficulty":
                        vals = ["easy", "medium", "hard"]
                        i = vals.index(settings["bot_difficulty"])
                        settings["bot_difficulty"] = vals[(i + 1) % len(vals)]

                    elif key == "control":
                        settings["control_mode"] = (
                            "phone"
                            if settings["control_mode"] == "keyboard"
                            else "keyboard"
                        )

                    elif key == "assist":
                        vals = ["none", "medium", "full"]
                        i = vals.index(settings["steer_assist"])
                        settings["steer_assist"] = vals[(i + 1) % len(vals)]

                    elif key == "damage":
                        settings["car_damage"] = not settings["car_damage"]

                    elif key == "track":
                        vals = ["track_1", "track_2"]
                        i = vals.index(settings["track_layout"])
                        settings["track_layout"] = vals[(i + 1) % len(vals)]

                    elif key == "start":
                        return "start"

                    elif key == "quick_start":
                        return "quick_start"

        return None

    def draw_main_lobby(self, settings, mouse_pos):
        """
        Dessine l'écran du lobby principal.
        """

        self.screen.fill((10, 12, 18))
        self.lobby_buttons = {}

        # Fond décoratif léger.
        bg = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        for x in range(0, WIDTH, 80):
            alpha = 30 if (x // 80) % 2 == 0 else 18
            pygame.draw.rect(bg, (18, 32, 24, alpha), (x, 0, 40, HEIGHT))

        self.screen.blit(bg, (0, 0))

        # Titre.
        title = self.font_huge.render("Main Lobby", True, (245, 245, 245))
        self.screen.blit(title, (80, 50))

        subtitle = self.font.render(
            "Configure race settings before launching",
            True,
            (200, 210, 220),
        )
        self.screen.blit(subtitle, (82, 98))

        # Panneau principal.
        panel = pygame.Rect(70, 140, WIDTH - 140, HEIGHT - 180)
        self.draw_glass_panel(panel.x, panel.y, panel.width, panel.height, radius=26, alpha=190)

        left_x = panel.x + 40
        y = panel.y + 28

        # Nom du joueur.
        self.draw_setting_label("Player Name", left_x, y)

        input_rect = pygame.Rect(left_x, y + 24, 420, 42)
        shown_name = settings["player_name"] if settings["player_name"] else "Type your name"
        self.draw_input(input_rect, shown_name)

        # Nombre de tours.
        y += 82
        self.draw_setting_label("Laps", left_x, y)
        self.draw_stepper(left_x, y + 24, "laps", settings["laps_to_win"], mouse_pos)

        # Nombre de bots.
        y += 82
        self.draw_setting_label("Bot Count", left_x, y)
        self.draw_stepper(left_x, y + 24, "bots", settings["bot_count"], mouse_pos)

        # Difficulté.
        y += 82
        self.draw_setting_label("Bot Difficulty", left_x, y)
        self.draw_button(
            "difficulty",
            pygame.Rect(left_x, y + 24, 240, 42),
            f"{settings['bot_difficulty'].upper()}",
            mouse_pos,
            fill=(72, 94, 122),
        )

        # Mode de contrôle.
        y += 82
        self.draw_setting_label("Control Mode", left_x, y)
        self.draw_button(
            "control",
            pygame.Rect(left_x, y + 24, 240, 42),
            settings["control_mode"].upper(),
            mouse_pos,
            fill=(82, 108, 82),
        )

        # Assistance de direction téléphone.
        y += 82
        self.draw_setting_label("Phone Steering Assist", left_x, y)
        self.draw_button(
            "assist",
            pygame.Rect(left_x, y + 24, 240, 42),
            settings["steer_assist"].upper(),
            mouse_pos,
            fill=(96, 96, 146) if settings["control_mode"] == "phone" else (70, 70, 70),
        )

        # Dégâts.
        y += 82
        self.draw_setting_label("Car Damage", left_x, y)
        self.draw_button(
            "damage",
            pygame.Rect(left_x, y + 24, 240, 42),
            "ON" if settings["car_damage"] else "OFF",
            mouse_pos,
            fill=(128, 78, 78) if settings["car_damage"] else (78, 118, 78),
        )

        # Choix du circuit.
        y += 82
        self.draw_setting_label("Track", left_x, y)
        self.draw_button(
            "track",
            pygame.Rect(left_x, y + 24, 280, 42),
            "TRACK 1" if settings["track_layout"] == "track_1" else "TRACK 2 (DEMO)",
            mouse_pos,
            fill=(88, 88, 138),
        )

        # Résumé des réglages à droite.
        right_x = int(panel.x + panel.width * 0.56)
        info_y = panel.y + 30

        title2 = self.font_title.render("Selected Setup", True, (245, 245, 245))
        self.screen.blit(title2, (right_x, info_y))

        preview_lines = [
            f"Name: {settings['player_name'] or 'Player'}",
            f"Laps: {settings['laps_to_win']}",
            f"Bots: {settings['bot_count']}",
            f"Difficulty: {settings['bot_difficulty']}",
            f"Control: {settings['control_mode']}",
            f"Phone assist: {settings['steer_assist']}",
            f"Car damage: {'on' if settings['car_damage'] else 'off'}",
            f"Track: {'track 1' if settings['track_layout'] == 'track_1' else 'track 2 (demo)'}",
            "",
            "Quick Start launches a short easy demo.",
            "ENTER = start",
            "ESC during race = back to lobby",
        ]

        yy = info_y + 42

        for line in preview_lines:
            surf = self.font_small.render(line, True, (220, 225, 230))
            self.screen.blit(surf, (right_x, yy))
            yy += 24

        # Boutons de lancement.
        start_rect = pygame.Rect(panel.x + 40, panel.bottom - 70, 240, 48)
        quick_rect = pygame.Rect(panel.x + 300, panel.bottom - 70, 280, 48)

        self.draw_button("start", start_rect, "Start Race", mouse_pos, fill=(60, 136, 96))
        self.draw_button("quick_start", quick_rect, "Quick Start (Admin)", mouse_pos, fill=(114, 84, 168))

        pygame.display.flip()

    def draw_setting_label(self, text, x, y):
        """
        Dessine le titre d'un réglage dans le lobby.
        """
        surf = self.font.render(text, True, (240, 240, 240))
        self.screen.blit(surf, (x, y))

    def draw_input(self, rect, text):
        """
        Dessine le champ du nom du joueur.
        """
        pygame.draw.rect(self.screen, (28, 34, 40), rect, border_radius=10)
        pygame.draw.rect(self.screen, (95, 105, 116), rect, 2, border_radius=10)

        surf = self.font.render(text, True, (240, 240, 240))
        self.screen.blit(surf, (rect.x + 12, rect.y + 8))

    def draw_stepper(self, x, y, prefix, value, mouse_pos):
        """
        Dessine un réglage numérique avec boutons - et +.
        """

        minus_rect = pygame.Rect(x, y, 42, 42)
        value_rect = pygame.Rect(x + 54, y, 120, 42)
        plus_rect = pygame.Rect(x + 186, y, 42, 42)

        self.draw_button(f"{prefix}_minus", minus_rect, "-", mouse_pos, fill=(76, 76, 84))

        pygame.draw.rect(self.screen, (28, 34, 40), value_rect, border_radius=10)
        pygame.draw.rect(self.screen, (95, 105, 116), value_rect, 2, border_radius=10)

        val = self.font.render(str(value), True, (245, 245, 245))
        val_rect = val.get_rect(center=value_rect.center)
        self.screen.blit(val, val_rect)

        self.draw_button(f"{prefix}_plus", plus_rect, "+", mouse_pos, fill=(76, 76, 84))

    def draw_button(self, key, rect, text, mouse_pos, fill=(70, 90, 120)):
        """
        Dessine un bouton rectangulaire.

        Le bouton change légèrement de couleur au survol.
        """

        is_hover = rect.collidepoint(mouse_pos)
        color = tuple(min(255, c + 18) for c in fill) if is_hover else fill

        pygame.draw.rect(self.screen, color, rect, border_radius=12)
        pygame.draw.rect(self.screen, (120, 128, 140), rect, 2, border_radius=12)

        surf = self.font.render(text, True, (245, 245, 245))
        surf_rect = surf.get_rect(center=rect.center)
        self.screen.blit(surf, surf_rect)

        # Dans le lobby, cette liste sert à détecter les clics.
        self.lobby_buttons[key] = rect

    # ------------------------------------------------------------
    # Vue de course
    # ------------------------------------------------------------

    def handle_race_event(self, event, race):
        """
        Gère les clics après la fin de la course.

        Pour l'instant, le bouton principal est Restart.
        """

        if not race.finished and not race.game_over:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            for key, rect in self.race_buttons.items():
                if rect.collidepoint(mx, my):
                    return key

        return None

    def get_layout(self):
        """
        Calcule les zones principales de l'interface.

        La fenêtre est divisée en :
        - bandeau supérieur
        - zone de jeu
        - panneau latéral
        - HUD inférieur
        - indication de direction
        """

        margin = 18
        top_h = 92
        bottom_h = 122
        side_w = 282
        turn_hint_h = 58
        gap = 18

        game_x = margin
        game_y = top_h + gap + turn_hint_h + gap
        game_w = WIDTH - side_w - margin * 3
        game_h = HEIGHT - game_y - bottom_h - margin * 2

        side_x = WIDTH - side_w - margin
        side_y = top_h + gap
        side_h = HEIGHT - top_h - bottom_h - margin * 3

        bottom_y = HEIGHT - bottom_h - margin

        return {
            "margin": margin,
            "top_h": top_h,
            "bottom_h": bottom_h,
            "side_w": side_w,
            "turn_hint_h": turn_hint_h,
            "gap": gap,
            "game_rect": pygame.Rect(game_x, game_y, game_w, game_h),
            "top_rect": pygame.Rect(margin, margin, WIDTH - margin * 2, top_h),
            "side_rect": pygame.Rect(side_x, side_y, side_w, side_h),
            "bottom_rect": pygame.Rect(margin, bottom_y, WIDTH - side_w - margin * 3, bottom_h),
        }

    def draw(self, race, shared_state, countdown_text=None):
        """
        Dessine une image complète de la course.

        Ordre général :
        1. dessin du monde
        2. effets visuels
        3. voitures
        4. caméra
        5. HUD et panneaux
        6. messages centraux
        """

        self.update_signal_history(shared_state)
        layout = self.get_layout()

        # Surface du monde complet.
        world_surface = pygame.Surface(
            (race.track.world_width, race.track.world_height),
            pygame.SRCALPHA,
        )

        # Circuit.
        race.track.draw_world(world_surface)

        # Effets de drift.
        self.update_drift_effects(race, 1 / 60)
        self.draw_drift_effects(world_surface)

        # Effets de collision.
        self.update_crash_particles(1 / 60)
        self.draw_crash_particles(world_surface)

        # Voitures.
        for car in race.cars:
            self.draw_car(world_surface, car)

        # Caméra centrée autour du joueur.
        camera_target = race.player_car
        game_view = self.build_follow_camera_view(
            world_surface,
            race,
            camera_target,
            layout["game_rect"],
        )

        self.screen.fill((10, 10, 12))
        self.screen.blit(game_view, layout["game_rect"].topleft)

        # Flash rouge après impact.
        if self.flash_timer > 0:
            overlay = pygame.Surface(
                (layout["game_rect"].width, layout["game_rect"].height),
                pygame.SRCALPHA,
            )

            alpha = int(self.flash_strength)
            overlay.fill((255, 70, 70, alpha))
            self.screen.blit(overlay, layout["game_rect"].topleft)

            self.flash_timer -= 1 / 60
            self.flash_strength *= 0.75

        # Interface.
        self.draw_top_banner(race, layout)
        self.draw_bottom_hud(race, layout)
        self.draw_side_panel(race, shared_state, layout)
        self.draw_direction_hint(race, layout)

        # Compte à rebours.
        if countdown_text is not None:
            self.draw_center_message(countdown_text, layout["game_rect"])

        # États particuliers.
        if race.paused:
            self.draw_center_message("PAUSE", layout["game_rect"])

        if race.game_over:
            self.draw_center_message("GAME OVER", layout["game_rect"])

        if race.finished:
            winner = race.get_leaderboard()[0]
            self.draw_center_message(f"Winner: {winner.display_name}", layout["game_rect"])
            self.draw_results_panel(race)

        pygame.display.flip()

    def build_follow_camera_view(self, world_surface, race, camera_target, game_rect):
        """
        Crée une vue caméra qui suit la voiture du joueur.

        La caméra regarde légèrement devant la voiture
        pour mieux anticiper la route.
        """

        zoom = 0.70 if race.track.layout_name == "track_1" else 0.62

        view_w = int(game_rect.width / zoom)
        view_h = int(game_rect.height / zoom)

        # Direction de la voiture.
        angle_rad = math.radians(camera_target.angle_deg)
        forward_x = math.cos(angle_rad)
        forward_y = math.sin(angle_rad)

        # Décalage de caméra vers l'avant selon la vitesse.
        look_ahead = min(160, max(65, camera_target.speed * 0.72))

        target_x = camera_target.x + forward_x * look_ahead
        target_y = camera_target.y + forward_y * look_ahead

        # Position désirée de la voiture dans l'écran.
        desired_x = game_rect.width * 0.42
        desired_y = game_rect.height * 0.58

        desired_world_x = desired_x / zoom
        desired_world_y = desired_y / zoom

        cam_x = int(target_x - desired_world_x)
        cam_y = int(target_y - desired_world_y)

        # Limite la caméra aux bords du monde.
        cam_x = max(0, min(cam_x, race.track.world_width - view_w))
        cam_y = max(0, min(cam_y, race.track.world_height - view_h))

        # Découpe la zone visible puis l'agrandit à l'écran.
        view = world_surface.subsurface(pygame.Rect(cam_x, cam_y, view_w, view_h))
        view = pygame.transform.smoothscale(view, (game_rect.width, game_rect.height))

        final_surface = pygame.Surface(
            (game_rect.width, game_rect.height),
            pygame.SRCALPHA,
        )

        # Secousse après collision.
        shake_x = 0
        shake_y = 0

        if self.shake_timer > 0:
            shake_x = int(random.uniform(-self.shake_strength, self.shake_strength))
            shake_y = int(random.uniform(-self.shake_strength, self.shake_strength))

            self.shake_timer -= 1 / 60
            self.shake_strength *= 0.88

        final_surface.blit(view, (shake_x, shake_y))

        return final_surface

    # ------------------------------------------------------------
    # Effets de drift
    # ------------------------------------------------------------

    def update_drift_effects(self, race, dt):
        """
        Met à jour les effets de drift.

        Si une voiture a une forte vitesse latérale,
        on ajoute de la fumée et des traces de pneus.
        """

        for car in race.cars:
            if not hasattr(car, "vel_x"):
                continue

            heading_rad = pygame.math.Vector2(1, 0).rotate(car.angle_deg)
            forward_x = heading_rad.x
            forward_y = heading_rad.y

            right_x = -forward_y
            right_y = forward_x

            lateral_speed = car.vel_x * right_x + car.vel_y * right_y
            slip = abs(lateral_speed)

            if slip > 24 and car.speed > 95:
                self.spawn_drift_particles(car, slip)

        # Supprime les particules mortes.
        alive = []

        for p in self.drift_particles:
            p["life"] -= dt

            if p["kind"] == "smoke":
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                p["radius"] += p["grow"] * dt

            if p["life"] > 0:
                alive.append(p)

        self.drift_particles = alive

    def spawn_drift_particles(self, car, slip):
        """
        Crée les particules de drift derrière les roues arrière.
        """

        angle_rad = pygame.math.Vector2(1, 0).rotate(car.angle_deg)

        fx = angle_rad.x
        fy = angle_rad.y

        rx = -fy
        ry = fx

        # Position approximative de l'arrière de la voiture.
        rear_x = car.x - fx * (car.length * 0.30)
        rear_y = car.y - fy * (car.length * 0.30)

        # Positions des deux roues arrière.
        left_tire = (
            rear_x + rx * (car.width * 0.35),
            rear_y + ry * (car.width * 0.35),
        )

        right_tire = (
            rear_x - rx * (car.width * 0.35),
            rear_y - ry * (car.width * 0.35),
        )

        # Fumée légère.
        for tx, ty in (left_tire, right_tire):
            self.drift_particles.append({
                "kind": "smoke",
                "x": tx + random.uniform(-1.5, 1.5),
                "y": ty + random.uniform(-1.5, 1.5),
                "vx": random.uniform(-5, 5),
                "vy": random.uniform(-5, 5),
                "radius": random.uniform(2.0, 3.5),
                "grow": random.uniform(4, 8),
                "life": random.uniform(0.12, 0.22),
                "alpha": min(85, 20 + int(slip * 1.2)),
            })

        # Traces de pneus si la glisse est plus forte.
        if slip > 34:
            for tx, ty in (left_tire, right_tire):
                self.drift_particles.append({
                    "kind": "skid",
                    "x": tx,
                    "y": ty,
                    "x2": tx - fx * random.uniform(7, 11),
                    "y2": ty - fy * random.uniform(7, 11),
                    "life": 0.30,
                    "alpha": min(95, 18 + int(slip * 1.1)),
                })

    def draw_drift_effects(self, surface: pygame.Surface):
        """
        Dessine les particules de drift sur le monde.
        """

        for p in self.drift_particles:
            if p["kind"] == "smoke":
                alpha = int(p["alpha"] * max(0.0, p["life"] / 0.22))

                ps = pygame.Surface((32, 32), pygame.SRCALPHA)
                pygame.draw.circle(
                    ps,
                    (170, 170, 170, alpha),
                    (16, 16),
                    int(p["radius"]),
                )

                surface.blit(ps, (p["x"] - 16, p["y"] - 16))

            else:
                alpha = int(p["alpha"] * max(0.0, p["life"] / 0.30))

                pygame.draw.line(
                    surface,
                    (18, 18, 18, alpha),
                    (p["x"], p["y"]),
                    (p["x2"], p["y2"]),
                    2,
                )

    # ------------------------------------------------------------
    # Effets de collision
    # ------------------------------------------------------------

    def update_crash_particles(self, dt):
        """
        Met à jour les particules de collision.
        """

        alive = []

        for p in self.crash_particles:
            p["life"] -= dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vx"] *= 0.90
            p["vy"] *= 0.90

            if p["life"] > 0:
                alive.append(p)

        self.crash_particles = alive

    def draw_crash_particles(self, surface: pygame.Surface):
        """
        Dessine les particules créées par les collisions.
        """

        for p in self.crash_particles:
            alpha = int(255 * min(1.0, p["life"] / 0.40))

            ps = pygame.Surface((20, 20), pygame.SRCALPHA)

            pygame.draw.circle(
                ps,
                (*p["color"], alpha),
                (10, 10),
                int(p["radius"]),
            )

            surface.blit(ps, (p["x"] - 10, p["y"] - 10))

    # ------------------------------------------------------------
    # Dessin des voitures
    # ------------------------------------------------------------

    def draw_car(self, surface: pygame.Surface, car):
        """
        Dessine une voiture de type monoplace vue du dessus.
        """

        # Dimensions du sprite local.
        sprite_w = 72
        sprite_h = 34
        cy = sprite_h // 2

        base = pygame.Surface((sprite_w, sprite_h), pygame.SRCALPHA)

        body = car.color
        dark = (20, 20, 20)
        glass = (170, 205, 235)
        light = (235, 235, 235)

        # Ombre sous la voiture.
        pygame.draw.ellipse(
            base,
            (0, 0, 0, 45),
            (6, 8, sprite_w - 12, sprite_h - 16),
        )

        # Aileron arrière.
        pygame.draw.rect(base, dark, (0, cy - 13, 16, 4), border_radius=2)
        pygame.draw.rect(base, dark, (0, cy + 9, 16, 4), border_radius=2)
        pygame.draw.rect(base, dark, (6, cy - 11, 6, 22), border_radius=2)

        # Partie arrière.
        pygame.draw.rect(base, body, (10, cy - 7, 16, 14), border_radius=4)

        # Corps principal.
        body_pts = [
            (26, cy - 9),
            (38, cy - 14),
            (52, cy - 13),
            (64, cy - 8),
            (68, cy - 4),
            (68, cy + 4),
            (64, cy + 8),
            (52, cy + 13),
            (38, cy + 14),
            (26, cy + 9),
        ]
        pygame.draw.polygon(base, body, body_pts)

        # Nez de la voiture.
        nose = [
            (68, cy - 4),
            (72, cy),
            (68, cy + 4),
        ]
        pygame.draw.polygon(base, body, nose)

        # Aileron avant.
        wing_x = 64
        wing_width = 8

        pygame.draw.rect(base, dark, (wing_x, cy - 13, 2, 26), border_radius=1)
        pygame.draw.rect(base, dark, (wing_x + 3, cy - 13, 2, 26), border_radius=1)

        pygame.draw.rect(
            base,
            dark,
            (wing_x + 5, cy - 13, wing_width, 4),
            border_radius=2,
        )
        pygame.draw.rect(
            base,
            dark,
            (wing_x + 5, cy + 9, wing_width, 4),
            border_radius=2,
        )

        # Petites plaques latérales de l'aileron.
        pygame.draw.rect(
            base,
            dark,
            (wing_x + 5 + wing_width - 1, cy - 16, 2, 4),
            border_radius=1,
        )
        pygame.draw.rect(
            base,
            dark,
            (wing_x + 5 + wing_width - 1, cy + 12, 2, 4),
            border_radius=1,
        )

        # Cockpit.
        pygame.draw.rect(base, glass, (42, cy - 6, 12, 12), border_radius=4)
        pygame.draw.rect(base, dark, (48, cy - 10, 3, 20), border_radius=2)

        # Roues.
        wheels = [
            pygame.Rect(14, 2, 14, 10),
            pygame.Rect(14, sprite_h - 12, 14, 10),
            pygame.Rect(54, 2, 14, 10),
            pygame.Rect(54, sprite_h - 12, 14, 10),
        ]

        for rect in wheels:
            pygame.draw.ellipse(base, dark, rect)
            pygame.draw.ellipse(base, (70, 70, 70), rect, 2)

        # Suspensions simplifiées.
        pygame.draw.line(base, dark, (28, cy - 6), (20, 6), 2)
        pygame.draw.line(base, dark, (28, cy + 6), (20, sprite_h - 6), 2)
        pygame.draw.line(base, dark, (60, cy - 6), (62, 6), 2)
        pygame.draw.line(base, dark, (60, cy + 6), (62, sprite_h - 6), 2)

        # Reflet central.
        pygame.draw.line(base, light, (12, cy), (66, cy), 1)

        # Rotation du sprite selon l'angle de la voiture.
        rotated = pygame.transform.rotate(base, -car.angle_deg)
        rect = rotated.get_rect(center=(car.x, car.y))

        surface.blit(rotated, rect)

    # ------------------------------------------------------------
    # Éléments d'interface
    # ------------------------------------------------------------

    def draw_glass_panel(self, x, y, w, h, radius=18, alpha=188):
        """
        Dessine un panneau semi-transparent.
        """

        panel = pygame.Surface((w, h), pygame.SRCALPHA)

        pygame.draw.rect(
            panel,
            (18, 22, 28, alpha),
            (0, 0, w, h),
            border_radius=radius,
        )

        pygame.draw.rect(
            panel,
            (90, 96, 110, 210),
            (0, 0, w, h),
            2,
            border_radius=radius,
        )

        self.screen.blit(panel, (x, y))

    def draw_bar(self, x, y, w, h, value, color):
        """
        Dessine une barre de progression.

        value doit être comprise entre 0 et 1.
        """

        pygame.draw.rect(self.screen, (36, 40, 46), (x, y, w, h), border_radius=7)

        fill_w = int(w * max(0.0, min(1.0, value)))

        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (x, y, fill_w, h), border_radius=7)

        pygame.draw.rect(self.screen, (95, 95, 102), (x, y, w, h), 1, border_radius=7)

    def draw_top_banner(self, race, layout):
        """
        Dessine la bannière supérieure de la course.
        """

        player = race.player_car
        r = layout["top_rect"]

        best_lap_text = "--.--" if player.best_lap_time is None else f"{player.best_lap_time:.2f}s"
        last_lap_text = "--.--" if player.last_lap_time == 0 else f"{player.last_lap_time:.2f}s"

        current_lap_display = min(player.completed_laps + 1, race.laps_to_win)

        self.draw_glass_panel(r.x, r.y, r.width, r.height, radius=20, alpha=175)

        title = self.font_title.render("Race Control HUD", True, (245, 245, 245))
        self.screen.blit(title, (r.x + 20, r.y + 12))

        line1 = [
            "Mode: race",
            f"Track: {'1' if race.track.layout_name == 'track_1' else '2'}",
            f"Speed: {max(0, int(player.speed))} km/h",
            f"Lap: {current_lap_display}/{race.laps_to_win}",
            f"Health: {int(player.health)}",
        ]

        line2 = [
            f"Current: {player.current_lap_time:.2f}s" if player.lap_timing_started else "Current: --.--",
            f"Last: {last_lap_text}",
            f"Best: {best_lap_text}",
            f"Damage: {'on' if race.car_damage else 'off'}",
            f"Bots: {race.bot_count}",
        ]

        lx = r.x + 20
        ly1 = r.y + 46
        ly2 = r.y + 68
        gap = 220

        for i, text in enumerate(line1):
            surf = self.font_small.render(text, True, COLOR_TEXT)
            self.screen.blit(surf, (lx + i * gap, ly1))

        for i, text in enumerate(line2):
            surf = self.font_small.render(text, True, COLOR_TEXT)
            self.screen.blit(surf, (lx + i * gap, ly2))

        # Avertissement si le joueur roule dans le mauvais sens.
        if hasattr(player, "wrong_way_timer") and player.wrong_way_timer > 0.15:
            warn = self.font_big.render("WRONG WAY", True, (255, 95, 95))
            warn_rect = warn.get_rect(
                midright=(r.x + r.width - 26, r.y + r.height // 2 + 4),
            )
            self.screen.blit(warn, warn_rect)

    def draw_bottom_hud(self, race, layout):
        """
        Dessine le HUD inférieur.

        Il contient :
        - l'adresse du serveur
        - l'état des dégâts
        - le circuit
        - les jauges moteur, vie et nitro
        - les raccourcis clavier
        """

        player = race.player_car
        r = layout["bottom_rect"]

        self.draw_glass_panel(r.x, r.y, r.width, r.height, radius=20, alpha=182)

        left_x = r.x + 20
        top_y = r.y + 14

        # Adresse serveur pour le téléphone.
        server_text = self.font_small.render(
            f"Server: http://{self.ip}:{SERVER_PORT}",
            True,
            COLOR_TEXT,
        )
        self.screen.blit(server_text, (left_x, top_y))

        damage_text = self.font_small.render(
            f"Car damage: {'ON' if race.car_damage else 'OFF'}",
            True,
            COLOR_TEXT,
        )
        self.screen.blit(damage_text, (left_x, top_y + 26))

        track_text = self.font_small.render(
            f"Track: {'Track 1' if race.track.layout_name == 'track_1' else 'Track 2 Demo'}",
            True,
            COLOR_TEXT,
        )
        self.screen.blit(track_text, (left_x, top_y + 52))

        # Jauges.
        bar_block_x = left_x + 430

        self.screen.blit(self.font_small.render("Engine", True, COLOR_TEXT), (bar_block_x, top_y))
        effective_sound = min(1.0, max(0.0, player.speed / 320.0))
        self.draw_bar(bar_block_x + 70, top_y + 2, 250, 16, effective_sound, (89, 196, 255))

        self.screen.blit(self.font_small.render("Health", True, COLOR_TEXT), (bar_block_x, top_y + 30))
        self.draw_bar(
            bar_block_x + 70,
            top_y + 32,
            250,
            16,
            max(0.0, min(1.0, player.health / 100.0)),
            (108, 219, 126),
        )

        nitro_level = min(1.0, max(0.0, player.nitro / 100.0))
        self.screen.blit(self.font_small.render("Nitro", True, COLOR_TEXT), (bar_block_x, top_y + 60))
        self.draw_bar(bar_block_x + 70, top_y + 62, 250, 16, nitro_level, (255, 169, 74))

        help_lines = [
            "Keyboard: arrows / SPACE / P / R / ESC",
            "Phone: tilt steer + hold accel button",
        ]

        hy = r.y + 74

        for line in help_lines:
            surf = self.font_small.render(line, True, (220, 220, 220))
            self.screen.blit(surf, (left_x, hy))
            hy += 20

    def draw_signal_graph(self, x, y, w, h):
        """
        Dessine le graphe des signaux du téléphone.

        Rouge : signal brut
        Bleu  : signal filtré
        Vert  : signal final utilisé pour la direction
        """

        panel = pygame.Surface((w, h), pygame.SRCALPHA)

        pygame.draw.rect(panel, (22, 26, 32, 150), (0, 0, w, h), border_radius=14)
        pygame.draw.rect(panel, (90, 96, 110, 200), (0, 0, w, h), 1, border_radius=14)

        mid_y = h // 2

        # Axe horizontal central.
        pygame.draw.line(panel, (70, 76, 86), (8, mid_y), (w - 8, mid_y), 1)

        def draw_series(series, color, clamp_val):
            """
            Dessine une série de valeurs dans le graphe.
            """

            if len(series) < 2:
                return

            pts = []

            for i, value in enumerate(series[-self.signal_history_max:]):
                px = int(8 + (w - 16) * (i / max(1, self.signal_history_max - 1)))

                norm = max(-clamp_val, min(clamp_val, value)) / clamp_val
                py = int(mid_y - norm * (h * 0.38))

                pts.append((px, py))

            if len(pts) >= 2:
                pygame.draw.lines(panel, color, False, pts, 2)

        draw_series(self.raw_history, (255, 90, 90), 35.0)
        draw_series(self.filtered_history, (90, 170, 255), 35.0)
        draw_series(self.optimized_history, (90, 255, 140), 1.0)

        title = self.font_small.render("Phone signals", True, (240, 240, 240))
        panel.blit(title, (10, 6))

        legend1 = self.font_small.render("Raw", True, (255, 90, 90))
        legend2 = self.font_small.render("Filtered", True, (90, 170, 255))
        legend3 = self.font_small.render("Optimized", True, (90, 255, 140))

        panel.blit(legend1, (10, h - 24))
        panel.blit(legend2, (70, h - 24))
        panel.blit(legend3, (160, h - 24))

        self.screen.blit(panel, (x, y))

    def draw_side_panel(self, race, shared_state, layout):
        """
        Dessine le panneau latéral droit.

        Il contient :
        - la mini-carte
        - le graphe des signaux
        - le classement
        """

        r = layout["side_rect"]

        self.draw_glass_panel(r.x, r.y, r.width, r.height, radius=20, alpha=180)

        title = self.font_title.render("Race Overview", True, (245, 245, 245))
        self.screen.blit(title, (r.x + 18, r.y + 14))

        self.draw_minimap(race, r.x + 16, r.y + 54, r.width - 32, 150)
        self.draw_signal_graph(r.x + 16, r.y + 214, r.width - 32, 140)

        sep_y = r.y + 372
        pygame.draw.line(
            self.screen,
            (90, 96, 110),
            (r.x + 16, sep_y),
            (r.x + r.width - 16, sep_y),
            1,
        )

        rank_title = self.font.render("Leaderboard", True, COLOR_TEXT)
        self.screen.blit(rank_title, (r.x + 18, sep_y + 14))

        board = race.get_leaderboard()
        row_y = sep_y + 46

        for i, car in enumerate(board[:8], start=1):
            dot_color = (255, 255, 255) if car.player_id == 1 else car.color
            pygame.draw.circle(self.screen, dot_color, (r.x + 24, row_y + 8), 5)

            name = car.display_name[:16]
            txt = f"{i}. {name}"
            lap_txt = f"L{car.completed_laps}"

            surf1 = self.font_small.render(txt, True, COLOR_TEXT)
            surf2 = self.font_small.render(lap_txt, True, (210, 210, 210))

            self.screen.blit(surf1, (r.x + 38, row_y))
            self.screen.blit(surf2, (r.x + r.width - 52, row_y))

            row_y += 24

            if row_y > r.y + r.height - 30:
                break

    def draw_direction_hint(self, race, layout):
        """
        Affiche une indication sur la prochaine direction.

        Le système compare :
        - l'angle actuel de la voiture
        - l'orientation de la piste devant elle
        """

        player = race.player_car
        idx = race.track._nearest_centerline_index(player.x, player.y)

        lookahead = 18
        n = len(race.track.centerline)

        p_now = race.track.centerline[idx]
        p_future = race.track.centerline[(idx + lookahead) % n]

        track_angle = math.degrees(
            math.atan2(p_future[1] - p_now[1], p_future[0] - p_now[0]),
        )

        delta = (track_angle - player.angle_deg + 540) % 360 - 180

        if abs(delta) < 12:
            hint = "STRAIGHT"
            color = (240, 240, 240)

        elif delta > 0:
            hint = "TURN RIGHT"
            color = (111, 203, 255)

        else:
            hint = "TURN LEFT"
            color = (255, 190, 102)

        w, h = 250, 58

        x = layout["game_rect"].x + layout["game_rect"].width // 2 - w // 2
        y = layout["top_rect"].bottom + layout["gap"]

        self.draw_glass_panel(x, y, w, h, radius=18, alpha=185)

        txt = self.font_big.render(hint, True, color)
        rect = txt.get_rect(center=(x + w // 2, y + h // 2))

        self.screen.blit(txt, rect)

    def draw_minimap(self, race, x, y, w, h):
        """
        Dessine la mini-carte de la course.
        """

        panel = pygame.Surface((w, h), pygame.SRCALPHA)

        pygame.draw.rect(panel, (22, 26, 32, 150), (0, 0, w, h), border_radius=14)
        pygame.draw.rect(panel, (90, 96, 110, 200), (0, 0, w, h), 1, border_radius=14)

        margin = 14

        sx = (w - 2 * margin) / race.track.world_width
        sy = (h - 2 * margin) / race.track.world_height
        scale = min(sx, sy)

        pts = [
            (margin + px * scale, margin + py * scale)
            for (px, py) in race.track.centerline
        ]

        # Tracé du circuit.
        if len(pts) >= 2:
            pygame.draw.lines(panel, (180, 180, 180), True, pts, 6)
            pygame.draw.lines(panel, (70, 70, 70), True, pts, 4)

        # Position des voitures.
        for car in race.cars:
            mx = margin + car.x * scale
            my = margin + car.y * scale

            radius = 5 if car.player_id == 1 else 4
            color = (255, 255, 255) if car.player_id == 1 else car.color

            pygame.draw.circle(panel, color, (int(mx), int(my)), radius)

        title = self.font_small.render("Mini-map", True, (240, 240, 240))
        panel.blit(title, (12, 8))

        self.screen.blit(panel, (x, y))

    def draw_results_panel(self, race):
        """
        Affiche le panneau des résultats à la fin de la course.
        """

        board = race.results_snapshot if race.results_snapshot is not None else race.get_leaderboard()

        w, h = 700, 340
        x = (WIDTH - w) // 2
        y = (HEIGHT - h) // 2 + 40

        mouse_pos = pygame.mouse.get_pos()

        self.draw_glass_panel(x, y, w, h, radius=22, alpha=220)

        # Boutons propres à l'écran de résultats.
        self.race_buttons = {}

        title = self.font_huge.render("Race Results", True, COLOR_TEXT)
        self.screen.blit(title, (x + 24, y + 18))

        header = self.font.render(
            "Pos  Driver                 Total        Best Lap",
            True,
            COLOR_TEXT,
        )
        self.screen.blit(header, (x + 24, y + 80))

        row_y = y + 118

        for i, car in enumerate(board, start=1):
            best_lap = "--.--" if car.best_lap_time is None else f"{car.best_lap_time:.2f}s"
            total = f"{car.total_time:.2f}s"

            txt = f"{i:<4} {car.display_name[:20]:<20} {total:<12} {best_lap}"

            surf = self.font.render(txt, True, COLOR_TEXT)
            self.screen.blit(surf, (x + 24, row_y))

            row_y += 32

        # Bouton de redémarrage.
        restart_rect = pygame.Rect(x + w - 210, y + h - 60, 170, 40)

        self.draw_button(
            "restart",
            restart_rect,
            "Restart",
            mouse_pos,
            fill=(60, 136, 96),
        )

        self.race_buttons["restart"] = restart_rect

    def draw_center_message(self, text: str, game_rect):
        """
        Affiche un message au centre de la zone de jeu.

        Utilisé pour :
        - le compte à rebours
        - PAUSE
        - GAME OVER
        - le gagnant
        """

        surf = self.font_huge.render(text, True, (255, 255, 255))
        rect = surf.get_rect(center=game_rect.center)

        bg = pygame.Rect(
            rect.x - 24,
            rect.y - 18,
            rect.width + 48,
            rect.height + 36,
        )

        pygame.draw.rect(self.screen, (0, 0, 0), bg, border_radius=16)
        pygame.draw.rect(self.screen, (220, 220, 220), bg, width=2, border_radius=16)

        self.screen.blit(surf, rect)