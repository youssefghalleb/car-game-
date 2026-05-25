# ============================================================
# Configuration globale du jeu
# ============================================================
# Ce fichier centralise les paramètres principaux :
# - taille de la fenêtre
# - fréquence d'affichage
# - serveur du contrôleur mobile
# - mode de jeu
# - physique des voitures
# - couleurs utilisées pour l'affichage
# ============================================================


# -----------------------------
# Fenêtre et performances
# -----------------------------

# Dimensions de la fenêtre Pygame.
WIDTH = 1720
HEIGHT = 960

# Nombre d'images par seconde visé.
FPS = 60


# -----------------------------
# Serveur mobile
# -----------------------------

# Adresse d'écoute du serveur.
# "0.0.0.0" permet aux autres appareils du réseau local de se connecter.
SERVER_HOST = "0.0.0.0"

# Port utilisé par le serveur HTTP/WebSocket.
SERVER_PORT = 8765


# -----------------------------
# Mode de jeu
# -----------------------------

# Active le mode solo avec des bots.
SINGLE_PLAYER = True

# Nombre de bots présents dans la course.
BOT_COUNT = 3

# Difficulté de chaque bot.
# Chaque élément correspond à un bot.
BOT_DIFFICULTIES = ["hard", "hard", "hard"]


# -----------------------------
# Physique de la voiture
# -----------------------------

# Vitesse maximale en marche avant.
MAX_SPEED = 320.0

# Vitesse maximale en marche arrière.
MAX_REVERSE_SPEED = -45.0

# Force d'accélération.
ACCEL_FORCE = 175.0

# Force de freinage.
BRAKE_FORCE = 250.0

# Perte de vitesse lorsque le joueur n'accélère pas.
COAST_DRAG = 0.991

# Résistance permanente au roulement.
ROLLING_RESISTANCE = 0.996

# Vitesse de rotation de la voiture lors du braquage.
STEER_RATE = 115.0

# Vitesse minimale à partir de laquelle la direction devient efficace.
MIN_STEER_SPEED = 20.0


# -----------------------------
# Nitro
# -----------------------------

# Force supplémentaire donnée par la nitro.
NITRO_FORCE = 70.0

# Quantité de nitro consommée par seconde.
NITRO_CONSUMPTION = 16.0

# Quantité de nitro régénérée par seconde.
NITRO_REGEN = 5.0

# Capacité maximale de nitro.
MAX_NITRO = 100.0


# -----------------------------
# Dégâts et collisions
# -----------------------------

# Vie maximale de la voiture.
MAX_HEALTH = 100.0

# Coefficient qui transforme la force d'impact en dégâts.
COLLISION_DAMAGE_SCALE = 0.08

# Ralentissement appliqué après une collision.
COLLISION_SLOWDOWN_FACTOR = 0.5


# -----------------------------
# Course
# -----------------------------

# Nombre de tours nécessaires pour gagner.
LAPS_TO_WIN = 10


# -----------------------------
# Couleurs générales
# -----------------------------

# Couleur de fond.
COLOR_BG = (22, 24, 28)

# Couleur de l'herbe.
COLOR_GRASS = (45, 90, 48)

# Couleur de la route.
COLOR_ROAD = (72, 74, 78)

# Couleur des bordures de piste.
COLOR_BORDER = (210, 210, 210)

# Couleur des lignes de voie.
COLOR_LANE = (235, 215, 90)

# Couleur principale du texte.
COLOR_TEXT = (242, 242, 242)

# Couleur des panneaux d'interface.
COLOR_PANEL = (18, 20, 24)


# -----------------------------
# Couleurs des voitures
# -----------------------------

# La première couleur est celle du joueur.
# Les suivantes sont utilisées pour les bots.
PLAYER_COLORS = [
    (190, 30, 30),      # Joueur : rouge foncé
    (40, 110, 210),     # Bot 1 : bleu
    (235, 170, 40),     # Bot 2 : orange
    (145, 90, 200),     # Bot 3 : violet
    (50, 170, 120),     # Bot 4 : vert
]