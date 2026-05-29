import asyncio

import pygame

from server.state import SharedState
from server.app import start_server
from game.race import Race
from game.render import Renderer
from game.audio import AudioManager


# ============================================================
# Point d'entrée du projet
# ============================================================
# Ce fichier lance :
# - le serveur WebSocket pour recevoir les commandes du téléphone
# - la boucle principale du jeu Pygame
# - le rendu graphique
# - le son
# - la création et le redémarrage des courses
# ============================================================


# Nombre d'images par seconde visé.
FPS = 60


def clamp(value: float, mini: float, maxi: float) -> float:
    """
    Limite une valeur entre deux bornes.

    Cette fonction sert à éviter les valeurs trop grandes
    ou trop petites dans les commandes.
    """
    return max(mini, min(maxi, value))


def build_phone_controls(shared_state: SharedState) -> dict:
    """
    Transforme les données reçues du téléphone en commandes de jeu.

    Les données viennent du serveur WebSocket et sont stockées
    dans shared_state.players.
    """
    controls = {}

    for player_id, player_input in shared_state.players.items():
        controls[player_id] = {
            "steer": player_input.steer,
            "throttle": player_input.throttle,
            "brake": player_input.brake,
            "nitro": player_input.nitro,
            "pause_pressed": player_input.pause_pressed,
        }

    return controls


def build_keyboard_controls() -> dict:
    """
    Crée les commandes du joueur à partir du clavier.

    Ce mode est utile pour tester le jeu directement sur PC,
    sans utiliser le téléphone.
    """
    keys = pygame.key.get_pressed()

    return {
        1: {
            # Droite vaut 1, gauche vaut -1.
            "steer": float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT]),

            # Flèche haut : accélération.
            "throttle": float(keys[pygame.K_UP]),

            # Flèche bas : freinage.
            "brake": float(keys[pygame.K_DOWN]),

            # Espace : nitro.
            "nitro": bool(keys[pygame.K_SPACE]),

            # La pause clavier est gérée séparément.
            "pause_pressed": False,
        }
    }


def default_lobby_settings():
    """
    Retourne les paramètres par défaut du lobby.

    Ces valeurs sont utilisées au lancement du jeu
    avant que le joueur ne modifie les options.
    """
    return {
        "player_name": "Player",
        "laps_to_win": 5,
        "bot_difficulty": "medium",
        "bot_count": 4,
        "control_mode": "keyboard",
        "steer_assist": "none",
        "car_damage": True,
        "track_layout": "track_1",
    }


def create_race_from_settings(settings: dict) -> Race:
    """
    Crée une nouvelle course à partir des réglages du lobby.

    Cette fonction est utilisée au premier lancement
    mais aussi quand le joueur redémarre une course.
    """
    return Race(
        player_name=settings["player_name"],
        laps_to_win=settings["laps_to_win"],
        bot_count=settings["bot_count"],
        bot_difficulty=settings["bot_difficulty"],
        car_damage=settings["car_damage"],
        track_layout=settings["track_layout"],
    )


def apply_deadzone(value: float, deadzone: float) -> float:
    """
    Supprime les petites variations autour de zéro.

    Cela évite que la voiture tourne toute seule
    à cause de petits mouvements involontaires du téléphone.
    """
    if abs(value) <= deadzone:
        return 0.0

    sign = 1.0 if value > 0 else -1.0
    scaled = (abs(value) - deadzone) / max(1e-6, 1.0 - deadzone)

    return sign * max(0.0, min(1.0, scaled))


def expo_curve(value: float, expo: float) -> float:
    """
    Applique une courbe exponentielle au signal de direction.

    Le but est de rendre la direction plus douce autour du centre,
    tout en gardant une bonne amplitude quand on incline beaucoup.
    """
    sign = 1.0 if value >= 0 else -1.0
    return sign * (abs(value) ** expo)


def move_toward(current: float, target: float, max_step: float) -> float:
    """
    Déplace progressivement une valeur vers une cible.

    Cela évite les changements trop brusques de direction.
    """
    delta = target - current

    if abs(delta) <= max_step:
        return target

    return current + max_step * (1.0 if delta > 0 else -1.0)


def apply_phone_assist(race: Race, controls: dict, assist_level: str, dt: float) -> dict:
    """
    Applique une assistance de direction pour les commandes téléphone.

    Il existe trois niveaux :
    - none   : aucune assistance
    - medium : direction adoucie
    - full   : direction très stabilisée

    Cette assistance agit sur le signal de direction du joueur 1.
    """
    if assist_level == "none" or 1 not in controls:
        return controls

    player = race.player_car
    player_controls = dict(controls[1])

    raw = float(player_controls.get("steer", 0.0))
    speed = max(0.0, float(player.speed))

    # Stocke l'état progressif de l'assistance directement dans la voiture.
    if not hasattr(player, "assist_steer_state"):
        player.assist_steer_state = 0.0

    if assist_level == "medium":
        # Assistance moyenne : garde une bonne réactivité.
        deadzone = 0.06
        expo = 1.18
        low_speed_cap = 0.92
        high_speed_cap = 0.68
        cap_speed = 220.0
        rise_rate = 3.6
        fall_rate = 5.2
        center_rate = 6.0

    elif assist_level == "full":
        # Assistance forte : réduit davantage les mouvements brusques.
        deadzone = 0.12
        expo = 1.35
        low_speed_cap = 0.72
        high_speed_cap = 0.46
        cap_speed = 220.0
        rise_rate = 2.3
        fall_rate = 3.8
        center_rate = 5.2

    else:
        return controls

    # Nettoyage et adoucissement du signal brut.
    shaped = apply_deadzone(raw, deadzone)
    shaped = expo_curve(shaped, expo)

    # Plus la voiture va vite, plus la direction est limitée.
    k = min(1.0, speed / cap_speed)
    steer_cap = low_speed_cap + (high_speed_cap - low_speed_cap) * k

    target = max(-steer_cap, min(steer_cap, shaped))
    current = player.assist_steer_state

    # Retour au centre ou déplacement progressif vers la cible.
    if abs(target) < 1e-4:
        next_value = move_toward(current, 0.0, center_rate * dt)
    elif abs(target) > abs(current):
        next_value = move_toward(current, target, rise_rate * dt)
    else:
        next_value = move_toward(current, target, fall_rate * dt)

    player.assist_steer_state = next_value
    player_controls["steer"] = next_value

    # On remplace uniquement les commandes du joueur 1.
    new_controls = dict(controls)
    new_controls[1] = player_controls

    return new_controls


async def game_loop(shared_state: SharedState):
    """
    Boucle principale du jeu.

    Elle s'occupe de :
    - lire les événements Pygame
    - gérer le lobby
    - lancer ou relancer la course
    - lire les commandes clavier ou téléphone
    - mettre à jour la course
    - gérer l'audio
    - dessiner l'image finale
    """
    renderer = Renderer()
    audio = AudioManager()

    running = True
    app_state = "main_lobby"

    lobby_settings = default_lobby_settings()
    race = None
    pause_latch = False

    # Variables du compte à rebours de départ.
    countdown_total = 0.0
    countdown_value_prev = None
    race_started = False

    def reset_countdown():
        """
        Réinitialise le compte à rebours avant le départ.
        """
        nonlocal countdown_total, countdown_value_prev, race_started

        countdown_total = 4.0
        countdown_value_prev = None
        race_started = False

    def launch_race(settings: dict):
        """
        Crée une nouvelle course et prépare le départ.
        """
        nonlocal race, pause_latch, app_state

        race = create_race_from_settings(settings)
        pause_latch = False

        # Coupe les sons de l'ancienne course.
        audio.stop_all()
        audio.set_paused(False)

        # Nettoie une éventuelle demande de restart venue du téléphone.
        shared_state.players[1].restart_pressed = False

        reset_countdown()
        app_state = "race"

    while running:
        # Temps écoulé depuis la dernière image.
        dt = renderer.tick(FPS)
        mouse_pos = pygame.mouse.get_pos()

        # -----------------------------
        # Gestion des événements
        # -----------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Événements du lobby principal.
            if app_state == "main_lobby":
                action = renderer.handle_main_lobby_event(event, lobby_settings)

                if action == "start":
                    launch_race(lobby_settings)

                elif action == "quick_start":
                    # Mode de test rapide pour lancer une petite course.
                    lobby_settings = {
                        "player_name": "Admin",
                        "laps_to_win": 3,
                        "bot_difficulty": "easy",
                        "bot_count": 2,
                        "control_mode": "keyboard",
                        "steer_assist": "none",
                        "car_damage": False,
                        "track_layout": "track_2",
                    }
                    launch_race(lobby_settings)

            # Événements après fin de course.
            elif app_state == "race" and race is not None:
                action = renderer.handle_race_event(event, race)

                if action == "restart":
                    launch_race(lobby_settings)

        # -----------------------------
        # Affichage du lobby
        # -----------------------------
        if app_state == "main_lobby":
            renderer.draw_main_lobby(lobby_settings, mouse_pos)
            await asyncio.sleep(0)
            continue

        # Sécurité : si aucune course n'existe, retour au lobby.
        if race is None:
            app_state = "main_lobby"
            await asyncio.sleep(0)
            continue

        player_state = shared_state.players[1]
        control_mode = lobby_settings["control_mode"]

        keys = pygame.key.get_pressed()

        # ESC permet de revenir au lobby pendant une course.
        if keys[pygame.K_ESCAPE]:
            audio.stop_all()
            app_state = "main_lobby"
            await asyncio.sleep(0)
            continue

        # -----------------------------
        # Lecture des commandes
        # -----------------------------
        if control_mode == "keyboard":
            controls = build_keyboard_controls()
            pause_now = keys[pygame.K_p]
            restart_now = keys[pygame.K_r]

        else:
            controls = build_phone_controls(shared_state)
            pause_now = any(c["pause_pressed"] for c in controls.values())
            restart_now = player_state.restart_pressed

            # Assistance de direction uniquement en mode téléphone.
            controls = apply_phone_assist(
                race,
                controls,
                lobby_settings["steer_assist"],
                dt,
            )

        # Redémarrage manuel de la course.
        if restart_now:
            launch_race(lobby_settings)
            player_state.restart_pressed = False

        # -----------------------------
        # Audio
        # -----------------------------
        audio.set_muted(player_state.mute)
        audio.set_master_volume(player_state.volume)

        # Le latch évite que la pause s'active plusieurs fois
        # pendant qu'un bouton reste appuyé.
        if pause_now and not pause_latch:
            race.toggle_pause()

        pause_latch = pause_now
        audio.set_paused(race.paused)

        # -----------------------------
        # Compte à rebours et course
        # -----------------------------
        countdown_text = None

        if not race.paused and not race.finished and not race.game_over:
            if not race_started:
                countdown_total -= dt

                if countdown_total > 1.0:
                    number = int(countdown_total)
                    countdown_text = str(number)

                    # Bip pour 3, 2, 1.
                    if number != countdown_value_prev and number in (3, 2, 1):
                        audio.play_countdown_beep(number)
                        countdown_value_prev = number

                elif countdown_total > 0.0:
                    countdown_text = "GO"

                    # Son de départ.
                    if countdown_value_prev != "GO":
                        audio.play_go()
                        countdown_value_prev = "GO"

                else:
                    race_started = True

            else:
                race.update(dt, controls)

        # -----------------------------
        # Collisions
        # -----------------------------
        for ev in race.pop_crash_events():
            renderer.trigger_crash_effect(ev["x"], ev["y"], ev["impact"])
            audio.play_crash(ev["impact"])

        # -----------------------------
        # Son moteur
        # -----------------------------
        player = race.player_car

        if race_started and not race.paused and not race.finished and not race.game_over:
            audio.update_engine(player.speed)
        else:
            audio.stop_engine_loop()

        # -----------------------------
        # Rendu final
        # -----------------------------
        renderer.draw(race, shared_state, countdown_text=countdown_text)

        # Rend la main à asyncio pour laisser le serveur fonctionner.
        await asyncio.sleep(0)

    # Nettoyage à la fermeture du jeu.
    audio.stop_all()
    pygame.quit()


async def main():
    """
    Lance le serveur puis démarre la boucle de jeu.

    Le serveur et Pygame fonctionnent ensemble grâce à asyncio.
    """
    shared_state = SharedState()
    runner = await start_server(shared_state)

    try:
        await game_loop(shared_state)
    finally:
        # Arrête proprement le serveur web.
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())