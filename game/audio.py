import math
import random
from array import array

import pygame


# ============================================================
# Gestion audio du jeu
# ============================================================
# Ce fichier gère :
# - le son du moteur
# - les bips du compte à rebours
# - le son de départ
# - les collisions
# - le volume général
# - le mode muet
# - la pause audio
#
# Les sons sont générés directement par le programme.
# Il n'est donc pas nécessaire d'avoir des fichiers audio externes.
# ============================================================


class AudioManager:
    """
    Gère tous les sons du jeu.

    La classe utilise pygame.mixer pour produire et jouer les sons.
    Le moteur est composé de plusieurs couches sonores mélangées
    selon la vitesse de la voiture.
    """

    def __init__(self):
        """
        Initialise le système audio.

        Si pygame.mixer ne peut pas démarrer, le jeu continue
        sans son au lieu de planter.
        """

        # Indique si l'audio est disponible.
        self.enabled = False

        # Fréquence d'échantillonnage utilisée pour générer les sons.
        self.sample_rate = 22050

        # Réglages généraux du son.
        self.master_volume = 1.0
        self.muted = False
        self.paused = False

        # État du son moteur.
        self.engine_playing = False

        # Canaux audio utilisés pour les couches moteur.
        self.channels = {}

        # Sons moteur générés au lancement.
        self.engine_layers = {}

        # Volume de base de chaque couche moteur.
        self.engine_base_volumes = {
            "idle": 0.0,
            "low": 0.0,
            "mid": 0.0,
            "high": 0.0,
        }

        try:
            # Initialisation du mixer audio.
            pygame.mixer.init(
                frequency=self.sample_rate,
                size=-16,
                channels=2,
                buffer=512,
            )

            # Nombre total de canaux disponibles.
            pygame.mixer.set_num_channels(16)

            # Canaux réservés aux différentes couches du moteur.
            self.channels = {
                "engine_idle": pygame.mixer.Channel(0),
                "engine_low": pygame.mixer.Channel(1),
                "engine_mid": pygame.mixer.Channel(2),
                "engine_high": pygame.mixer.Channel(3),
            }

            # Création des quatre couches du moteur.
            self.engine_layers = {
                "idle": self._make_engine_loop(
                    base_freq=42,
                    duration=0.55,
                    volume=0.42,
                    harmonics=[1.0, 0.45, 0.18],
                    noise_amount=0.015,
                    pulse_amount=0.08,
                ),
                "low": self._make_engine_loop(
                    base_freq=58,
                    duration=0.50,
                    volume=0.42,
                    harmonics=[1.0, 0.55, 0.22],
                    noise_amount=0.02,
                    pulse_amount=0.10,
                ),
                "mid": self._make_engine_loop(
                    base_freq=82,
                    duration=0.42,
                    volume=0.38,
                    harmonics=[1.0, 0.62, 0.28, 0.12],
                    noise_amount=0.018,
                    pulse_amount=0.12,
                ),
                "high": self._make_engine_loop(
                    base_freq=118,
                    duration=0.32,
                    volume=0.32,
                    harmonics=[1.0, 0.70, 0.35, 0.18],
                    noise_amount=0.014,
                    pulse_amount=0.14,
                ),
            }

            # L'audio est prêt.
            self.enabled = True

            # Petit son de confirmation au démarrage.
            cue = self._make_tone(660, 0.08, 0.18)
            cue.set_volume(0.4)
            cue.play()

        except Exception as exc:
            # Si l'audio échoue, le jeu continue sans son.
            print("[AUDIO] Mixer init failed:", exc)
            self.enabled = False

    # ------------------------------------------------------------
    # Réglages audio généraux
    # ------------------------------------------------------------

    def _effective_volume(self, base_volume: float) -> float:
        """
        Calcule le volume réel d'un son.

        Le volume final dépend :
        - du volume de base du son
        - du volume général
        - du mode muet
        """

        if self.muted:
            return 0.0

        return max(0.0, min(1.0, base_volume * self.master_volume))

    def _apply_engine_volumes(self):
        """
        Applique le volume calculé aux couches du moteur.
        """

        if not self.enabled:
            return

        mapping = {
            "idle": "engine_idle",
            "low": "engine_low",
            "mid": "engine_mid",
            "high": "engine_high",
        }

        for layer_name, channel_name in mapping.items():
            ch = self.channels[channel_name]
            ch.set_volume(
                self._effective_volume(self.engine_base_volumes[layer_name])
            )

    def set_master_volume(self, volume: float):
        """
        Modifie le volume général du jeu.

        La valeur est limitée entre 0 et 1.
        """

        self.master_volume = max(0.0, min(1.0, volume))
        self._apply_engine_volumes()

    def set_muted(self, muted: bool):
        """
        Active ou désactive le mode muet.
        """

        self.muted = bool(muted)
        self._apply_engine_volumes()

    def set_paused(self, paused: bool):
        """
        Met tous les sons en pause ou les reprend.

        Cette méthode est appelée quand le joueur met le jeu en pause.
        """

        if not self.enabled:
            return

        paused = bool(paused)

        # Inutile de refaire l'action si l'état ne change pas.
        if paused == self.paused:
            return

        self.paused = paused

        if paused:
            pygame.mixer.pause()
        else:
            pygame.mixer.unpause()
            self._apply_engine_volumes()

    def stop_all(self):
        """
        Arrête tous les sons du jeu.
        """

        if not self.enabled:
            return

        pygame.mixer.stop()
        self.engine_playing = False

        # Remet les volumes moteur à zéro.
        for key in self.engine_base_volumes:
            self.engine_base_volumes[key] = 0.0

    def stop_engine_loop(self):
        """
        Arrête uniquement la boucle du moteur.
        """

        if not self.enabled:
            return

        for name in ("engine_idle", "engine_low", "engine_mid", "engine_high"):
            self.channels[name].stop()

        self.engine_playing = False

        for key in self.engine_base_volumes:
            self.engine_base_volumes[key] = 0.0

    def _play_on_free_channel(self, sound: pygame.mixer.Sound, volume: float):
        """
        Joue un son court sur un canal libre.

        Cette méthode est utilisée pour les sons ponctuels :
        - bip
        - départ
        - collision
        """

        if not self.enabled or self.paused:
            return

        ch = pygame.mixer.find_channel()

        if ch is None:
            return

        ch.set_volume(self._effective_volume(volume))
        ch.play(sound)

    # ------------------------------------------------------------
    # Génération des sons
    # ------------------------------------------------------------

    def _make_tone(self, frequency=440, duration=0.12, volume=0.35):
        """
        Génère un son pur à une fréquence donnée.

        Ce type de son est utilisé pour :
        - les bips du compte à rebours
        - le son de départ
        """

        n_samples = max(1, int(self.sample_rate * duration))
        amp = int(32767 * volume)
        buf = array("h")

        for i in range(n_samples):
            t = i / self.sample_rate
            value = math.sin(2 * math.pi * frequency * t)

            # Conversion en entier 16 bits.
            buf.append(int(max(-32767, min(32767, amp * value))))

        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _make_noise_burst(self, duration=0.08, volume=0.45):
        """
        Génère un bruit court.

        Ce son sert principalement à simuler les collisions.
        """

        n_samples = max(1, int(self.sample_rate * duration))
        amp = int(32767 * volume)
        buf = array("h")

        last = 0.0

        for i in range(n_samples):
            t = i / self.sample_rate

            # Bruit aléatoire.
            white = random.uniform(-1.0, 1.0)

            # Filtrage simple pour éviter un bruit trop agressif.
            last = 0.86 * last + 0.14 * white

            # Enveloppe décroissante : le son disparaît progressivement.
            env = max(0.0, 1.0 - (t / duration))
            env = env * env

            sample = amp * last * env
            buf.append(int(max(-32767, min(32767, sample))))

        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _make_engine_loop(
        self,
        base_freq: float,
        duration: float,
        volume: float,
        harmonics: list[float],
        noise_amount: float,
        pulse_amount: float,
    ):
        """
        Génère une boucle sonore de moteur.

        Le son est construit avec :
        - une fréquence de base
        - plusieurs harmoniques
        - un léger bruit
        - une pulsation pour rappeler un moteur thermique
        """

        n_samples = max(1, int(self.sample_rate * duration))
        amp = 32767 * volume
        buf = array("h")

        # Décalages aléatoires pour éviter un son trop artificiel.
        phase_offsets = [random.uniform(0.0, math.tau) for _ in harmonics]

        for i in range(n_samples):
            t = i / self.sample_rate
            phase_ratio = i / max(1, n_samples - 1)

            s = 0.0

            # Addition des harmoniques.
            for h_idx, h_amp in enumerate(harmonics, start=1):
                freq = base_freq * h_idx
                s += h_amp * math.sin(
                    2 * math.pi * freq * t + phase_offsets[h_idx - 1]
                )

            # Pulsation pour donner un effet de combustion.
            pulse = math.sin(2 * math.pi * base_freq * 0.5 * t)
            pulse = 0.55 + 0.45 * pulse
            s *= (1.0 - pulse_amount) + pulse_amount * pulse

            # Léger bruit pour enrichir le son.
            noise = random.uniform(-1.0, 1.0) * noise_amount
            s += noise

            # Fondu aux extrémités pour éviter un clic dans la boucle.
            edge = min(phase_ratio, 1.0 - phase_ratio)
            edge = min(1.0, edge / 0.08)
            s *= edge

            sample = int(max(-32767, min(32767, amp * s)))
            buf.append(sample)

        return pygame.mixer.Sound(buffer=buf.tobytes())

    # ------------------------------------------------------------
    # Sons courts
    # ------------------------------------------------------------

    def play_countdown_beep(self, number: int):
        """
        Joue un bip pendant le compte à rebours.

        Les bips deviennent plus aigus quand le départ approche.
        """

        if not self.enabled or self.paused:
            return

        freq_map = {
            3: 520,
            2: 620,
            1: 720,
        }

        sound = self._make_tone(freq_map.get(number, 600), 0.12, 0.22)
        self._play_on_free_channel(sound, 0.9)

    def play_go(self):
        """
        Joue le son du départ.
        """

        if not self.enabled or self.paused:
            return

        sound = self._make_tone(920, 0.20, 0.24)
        self._play_on_free_channel(sound, 1.0)

    def play_victory(self):
        """
        Joue un court son de victoire.

        Cette méthode existe pour une éventuelle animation de fin.
        """

        if not self.enabled or self.paused:
            return

        s1 = self._make_tone(660, 0.10, 0.20)
        s2 = self._make_tone(880, 0.10, 0.20)
        s3 = self._make_tone(1040, 0.20, 0.20)

        self._play_on_free_channel(s1, 1.0)
        pygame.time.delay(100)

        self._play_on_free_channel(s2, 1.0)
        pygame.time.delay(100)

        self._play_on_free_channel(s3, 1.0)

    def play_crash(self, impact_strength: float):
        """
        Joue un son de collision.

        Plus l'impact est fort, plus le son est fort et long.
        """

        if not self.enabled or self.paused:
            return

        volume = min(0.85, 0.18 + impact_strength / 140.0)
        duration = 0.04 + min(0.08, impact_strength / 500.0)

        sound = self._make_noise_burst(duration=duration, volume=volume)
        self._play_on_free_channel(sound, 1.0)

    # ------------------------------------------------------------
    # Son du moteur
    # ------------------------------------------------------------

    def _ensure_engine_started(self):
        """
        Lance les couches moteur si elles ne jouent pas encore.
        """

        if not self.enabled or self.engine_playing:
            return

        self.channels["engine_idle"].play(self.engine_layers["idle"], loops=-1)
        self.channels["engine_low"].play(self.engine_layers["low"], loops=-1)
        self.channels["engine_mid"].play(self.engine_layers["mid"], loops=-1)
        self.channels["engine_high"].play(self.engine_layers["high"], loops=-1)

        self.engine_playing = True

    def _blend(self, speed: float):
        """
        Calcule le mélange des couches moteur selon la vitesse.

        À basse vitesse :
        - couche idle dominante

        À vitesse moyenne :
        - couches low et mid

        À haute vitesse :
        - couche high plus présente
        """

        s = max(0.0, min(320.0, speed))

        idle = 0.0
        low = 0.0
        mid = 0.0
        high = 0.0

        if s < 15:
            idle = 0.55

        elif s < 50:
            k = (s - 15) / 35.0
            idle = 0.55 * (1.0 - k)
            low = 0.45 * k + 0.15

        elif s < 110:
            k = (s - 50) / 60.0
            low = 0.65 * (1.0 - k) + 0.25
            mid = 0.55 * k

        elif s < 190:
            k = (s - 110) / 80.0
            low = 0.20 * (1.0 - k)
            mid = 0.65
            high = 0.30 * k

        else:
            k = (s - 190) / 130.0
            mid = 0.65 * (1.0 - 0.35 * k)
            high = 0.25 + 0.55 * k

        return {
            "idle": max(0.0, idle),
            "low": max(0.0, low),
            "mid": max(0.0, mid),
            "high": max(0.0, high),
        }

    def update_engine(self, speed: float):
        """
        Met à jour le son du moteur selon la vitesse.

        Cette méthode est appelée en continu pendant la course.
        """

        if not self.enabled or self.paused:
            return

        speed = max(0.0, speed)

        # À très basse vitesse, on coupe le moteur pour éviter un bruit permanent.
        if speed < 4.0:
            if self.engine_playing:
                self.stop_engine_loop()
            return

        # Démarre les boucles moteur si nécessaire.
        self._ensure_engine_started()

        # Mélange des couches selon la vitesse.
        weights = self._blend(speed)

        # Volume global du moteur.
        overall = 0.18 + 0.52 * min(1.0, speed / 320.0)

        self.engine_base_volumes["idle"] = weights["idle"] * overall
        self.engine_base_volumes["low"] = weights["low"] * overall
        self.engine_base_volumes["mid"] = weights["mid"] * overall
        self.engine_base_volumes["high"] = weights["high"] * overall

        # Applique les nouveaux volumes.
        self._apply_engine_volumes()