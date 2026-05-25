from dataclasses import dataclass, field
from typing import Dict


# ============================================================
# État partagé du contrôleur
# ============================================================
# Ce fichier contient les données reçues depuis le téléphone.
# Ces données sont ensuite utilisées par la boucle principale du jeu.
# ============================================================


@dataclass
class PlayerInput:
    """
    Représente toutes les commandes envoyées par un joueur.

    Dans ce projet, le mode principal est le mode solo :
    seul le joueur 1 envoie réellement des données depuis le téléphone.
    """

    # Direction de la voiture.
    # Valeur comprise entre -1 et 1 :
    # -1 = tourner à gauche
    #  0 = aller tout droit
    #  1 = tourner à droite
    steer: float = 0.0

    # Accélération.
    # Valeur comprise entre 0 et 1.
    throttle: float = 0.0

    # Freinage.
    # Valeur comprise entre 0 et 1.
    brake: float = 0.0

    # Activation de la nitro.
    nitro: bool = False

    # Demande de mise en pause.
    pause_pressed: bool = False

    # Indique si le téléphone est connecté au serveur.
    connected: bool = False

    # Active ou désactive le son.
    mute: bool = False

    # Volume général du jeu.
    # Valeur comprise entre 0 et 1.
    volume: float = 1.0

    # Demande de redémarrage de la course.
    restart_pressed: bool = False

    # Valeur brute reçue depuis le capteur du téléphone.
    raw_sensor: float = 0.0

    # Valeur du capteur après filtrage.
    filtered_sensor: float = 0.0

    # Signal final réellement utilisé pour contrôler la direction.
    optimized_signal: float = 0.0


@dataclass
class SharedState:
    """
    Stocke l'état partagé entre :
    - le serveur WebSocket
    - la boucle principale Pygame

    Le serveur modifie ces valeurs quand le téléphone envoie des données.
    Le jeu les lit ensuite pour contrôler la voiture.
    """

    # Dictionnaire contenant les entrées des joueurs.
    # Clé : identifiant du joueur
    # Valeur : commandes du joueur
    players: Dict[int, PlayerInput] = field(default_factory=dict)

    def __post_init__(self):
        """
        Initialise automatiquement le joueur 1.

        Cela évite de devoir créer le joueur manuellement ailleurs
        dans le programme.
        """
        self.players[1] = PlayerInput()