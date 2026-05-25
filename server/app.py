import json
from pathlib import Path

from aiohttp import web, WSMsgType

from config import SERVER_HOST, SERVER_PORT
from server.state import SharedState


# ============================================================
# Serveur HTTP + WebSocket
# ============================================================
# Ce fichier gère la communication entre :
# - le téléphone utilisé comme contrôleur
# - le jeu lancé sur l'ordinateur
#
# Le téléphone ouvre une page HTML.
# Cette page envoie ensuite les commandes en temps réel grâce au WebSocket.
# ============================================================


# Dossier racine du projet.
BASE_DIR = Path(__file__).resolve().parent.parent

# Dossier contenant les fichiers web du contrôleur mobile.
WEB_DIR = BASE_DIR / "web"


def clamp(value: float, mini: float, maxi: float) -> float:
    """
    Limite une valeur entre deux bornes.

    Exemple :
    si la direction reçue vaut 1.8, elle est ramenée à 1.0.
    si elle vaut -2.0, elle est ramenée à -1.0.
    """
    return max(mini, min(maxi, value))


async def index_redirect(request: web.Request) -> web.Response:
    """
    Redirige la page d'accueil vers le contrôleur du joueur 1.

    Si l'utilisateur ouvre simplement :
    http://adresse_du_serveur/

    il est automatiquement envoyé vers :
    http://adresse_du_serveur/controller/1
    """
    raise web.HTTPFound("/controller/1")


async def controller_page(request: web.Request) -> web.Response:
    """
    Génère la page HTML du contrôleur mobile.

    Le fichier controller.html contient des zones temporaires :
    - __PLAYER_ID__
    - __STEER_ASSIST__

    Ces zones sont remplacées avant d'envoyer la page au téléphone.
    """
    player_id = int(request.match_info["player_id"])

    # Le projet fonctionne en mode solo.
    # On refuse donc les autres joueurs.
    if player_id != 1:
        return web.Response(text="Mode solo uniquement", status=404)

    file_path = WEB_DIR / "controller.html"

    # Sécurité : vérifie que la page HTML existe bien.
    if not file_path.exists():
        return web.Response(
            text=f"controller.html introuvable: {file_path}",
            status=500,
        )

    # Lecture du fichier HTML.
    html = file_path.read_text(encoding="utf-8")

    # Injection de l'identifiant du joueur dans la page.
    html = html.replace("__PLAYER_ID__", "1")

    # Récupération du niveau d'assistance depuis l'URL.
    # Exemple :
    # /controller/1?assist=medium
    assist_level = request.query.get("assist", "none")

    # Valeurs autorisées pour éviter une entrée invalide.
    if assist_level not in ("none", "medium", "full"):
        assist_level = "none"

    # Injection de l'assistance dans le JavaScript.
    html = html.replace("__STEER_ASSIST__", assist_level)

    return web.Response(text=html, content_type="text/html")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """
    Reçoit les données envoyées par le téléphone.

    Le téléphone envoie régulièrement un message JSON contenant :
    - la direction
    - l'accélération
    - la nitro
    - la pause
    - le volume
    - les signaux des capteurs

    Ces informations sont stockées dans SharedState.
    La boucle Pygame les lit ensuite pour contrôler la voiture.
    """
    state: SharedState = request.app["shared_state"]
    player_id = int(request.match_info["player_id"])

    # Création de la connexion WebSocket.
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Le jeu accepte uniquement le joueur 1.
    if player_id != 1 or player_id not in state.players:
        await ws.send_str(json.dumps({"error": "single_player_only"}))
        await ws.close()
        return ws

    # Raccourci vers les commandes du joueur.
    player = state.players[1]
    player.connected = True

    try:
        async for msg in ws:
            # Message texte venant du téléphone.
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)

                    # Direction : entre -1 et 1.
                    player.steer = clamp(
                        float(data.get("steer", 0.0)),
                        -1.0,
                        1.0,
                    )

                    # Accélération : entre 0 et 1.
                    player.throttle = clamp(
                        float(data.get("throttle", 0.0)),
                        0.0,
                        1.0,
                    )

                    # Freinage : entre 0 et 1.
                    player.brake = clamp(
                        float(data.get("brake", 0.0)),
                        0.0,
                        1.0,
                    )

                    # Boutons envoyés par le téléphone.
                    player.nitro = bool(data.get("nitro", False))
                    player.pause_pressed = bool(data.get("pause_pressed", False))
                    player.mute = bool(data.get("mute", False))
                    player.restart_pressed = bool(data.get("restart_pressed", False))

                    # Volume général : entre 0 et 1.
                    player.volume = clamp(
                        float(data.get("volume", 1.0)),
                        0.0,
                        1.0,
                    )

                    # Signaux du capteur.
                    # Les valeurs brutes sont en degrés.
                    player.raw_sensor = clamp(
                        float(data.get("raw_sensor", 0.0)),
                        -180.0,
                        180.0,
                    )

                    player.filtered_sensor = clamp(
                        float(data.get("filtered_sensor", 0.0)),
                        -180.0,
                        180.0,
                    )

                    # Signal final utilisé par la voiture.
                    player.optimized_signal = clamp(
                        float(data.get("optimized_signal", 0.0)),
                        -1.0,
                        1.0,
                    )

                except Exception as exc:
                    # Une erreur ici ne doit pas arrêter le serveur.
                    print("WS parse error:", exc)

            # Erreur interne du WebSocket.
            elif msg.type == WSMsgType.ERROR:
                print("WebSocket error:", ws.exception())
                break

    finally:
        # Quand le téléphone se déconnecte,
        # on remet les commandes à zéro pour éviter que la voiture continue seule.
        player.connected = False
        player.steer = 0.0
        player.throttle = 0.0
        player.brake = 0.0
        player.nitro = False
        player.pause_pressed = False
        player.restart_pressed = False

        # Réinitialisation des signaux capteurs.
        player.raw_sensor = 0.0
        player.filtered_sensor = 0.0
        player.optimized_signal = 0.0

    return ws


async def health(request: web.Request) -> web.Response:
    """
    Route de test pour vérifier que le serveur fonctionne.

    Si cette route répond "OK", le serveur est bien lancé.
    """
    return web.Response(text="OK")


async def start_server(shared_state: SharedState):
    """
    Crée et démarre le serveur web.

    Le serveur fournit :
    - la page du contrôleur mobile
    - les fichiers statiques HTML/JS
    - la connexion WebSocket
    - une route de test /health
    """
    app = web.Application()

    # L'état partagé est accessible depuis les routes.
    app["shared_state"] = shared_state

    # Routes HTTP.
    app.router.add_get("/", index_redirect)
    app.router.add_get("/health", health)
    app.router.add_get("/controller/{player_id}", controller_page)

    # Route WebSocket.
    app.router.add_get("/ws/{player_id}", websocket_handler)

    # Fichiers statiques : controller.js, CSS éventuel, etc.
    app.router.add_static("/static/", path=str(WEB_DIR), show_index=True)

    # Préparation du serveur.
    runner = web.AppRunner(app)
    await runner.setup()

    # Démarrage du serveur sur l'adresse et le port définis dans config.py.
    site = web.TCPSite(runner, SERVER_HOST, SERVER_PORT)
    await site.start()

    print(f"Server started on http://127.0.0.1:{SERVER_PORT}")

    return runner