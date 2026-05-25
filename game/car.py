import math

from config import (
    ACCEL_FORCE,
    BRAKE_FORCE,
    COAST_DRAG,
    ROLLING_RESISTANCE,
    MAX_SPEED,
    MAX_REVERSE_SPEED,
    STEER_RATE,
    MIN_STEER_SPEED,
    NITRO_FORCE,
    NITRO_CONSUMPTION,
    NITRO_REGEN,
    MAX_NITRO,
    MAX_HEALTH,
    COLLISION_DAMAGE_SCALE,
    COLLISION_SLOWDOWN_FACTOR,
)


# ============================================================
# Modèle physique d'une voiture
# ============================================================
# Ce fichier gère :
# - la position de la voiture
# - sa vitesse
# - sa direction
# - son accélération
# - son freinage
# - la nitro
# - les dégâts
# - une approximation du drift et de l'adhérence
# ============================================================


class Car:
    """
    Représente une voiture du jeu.

    La même classe est utilisée pour :
    - la voiture du joueur
    - les voitures contrôlées par l'IA
    """

    def __init__(self, x: float, y: float, angle_deg: float, color, player_id: int):
        """
        Initialise une voiture à une position donnée.

        x, y :
            position de départ dans le monde

        angle_deg :
            orientation initiale de la voiture en degrés

        color :
            couleur utilisée pour dessiner la voiture

        player_id :
            identifiant du joueur ou du bot
        """

        # Position de la voiture dans le monde.
        self.x = x
        self.y = y

        # Angle de la voiture en degrés.
        self.angle_deg = angle_deg

        # Vitesse affichée de la voiture.
        self.speed = 0.0

        # Dimensions utilisées pour la logique et les collisions.
        self.width = 24
        self.length = 46

        # Apparence et identification.
        self.color = color
        self.player_id = player_id

        # Ressources de la voiture.
        self.nitro = MAX_NITRO
        self.health = MAX_HEALTH

        # Informations de course.
        self.completed_laps = 0
        self.lap = 1
        self.finished = False
        self.total_time = 0.0
        self.current_lap_time = 0.0
        self.last_lap_time = 0.0
        self.best_lap_time = None

        # Gestion du passage de la ligne départ/arrivée.
        self.lap_timing_started = False
        self.crossed_start_recently = False
        self.start_line_cooldown = 0.0

        # Données liées à la rotation.
        self.prev_angle_deg = angle_deg
        self.angular_velocity = 0.0

        # Type de voiture.
        self.is_bot = False
        self.display_name = f"Car {player_id}"
        self.track_progress = 0.0

        # Vitesse sous forme vectorielle.
        self.vel_x = 0.0
        self.vel_y = 0.0

        # État de destruction.
        self.destroyed = False

    def update(self, dt: float, control: dict):
        """
        Met à jour la physique de la voiture.

        Cette méthode est appelée à chaque image du jeu.

        dt :
            temps écoulé depuis la dernière image

        control :
            dictionnaire contenant les commandes :
            - steer
            - throttle
            - brake
            - nitro
        """

        # Une voiture terminée ou détruite ne bouge plus.
        if self.finished or self.destroyed:
            return

        # Cooldown après respawn pour éviter un double passage de ligne.
        if self.start_line_cooldown > 0.0:
            self.start_line_cooldown = max(0.0, self.start_line_cooldown - dt)

        # Lecture des commandes.
        steer_input = float(control.get("steer", 0.0))
        throttle = float(control.get("throttle", 0.0))
        brake = float(control.get("brake", 0.0))
        use_nitro = bool(control.get("nitro", False))

        # Direction avant de la voiture.
        heading_rad = math.radians(self.angle_deg)
        forward_x = math.cos(heading_rad)
        forward_y = math.sin(heading_rad)

        # Direction latérale de la voiture.
        right_x = -forward_y
        right_y = forward_x

        # Décomposition de la vitesse :
        # - vitesse vers l'avant
        # - vitesse latérale
        forward_speed = self.vel_x * forward_x + self.vel_y * forward_y
        lateral_speed = self.vel_x * right_x + self.vel_y * right_y

        # Valeurs utiles pour adapter les forces selon la vitesse.
        speed_abs = abs(forward_speed)
        speed_ratio = min(1.0, speed_abs / MAX_SPEED)

        # Plus la voiture est rapide, moins l'accélération est forte.
        accel_factor = 1.0 - 0.36 * speed_ratio
        drive_force = throttle * ACCEL_FORCE * accel_factor

        # Application de la nitro si elle est disponible.
        if use_nitro and self.nitro > 0.0 and throttle > 0.1:
            nitro_factor = 1.0 - 0.26 * speed_ratio
            drive_force += NITRO_FORCE * nitro_factor
            self.nitro = max(0.0, self.nitro - NITRO_CONSUMPTION * dt)

        else:
            # Régénération progressive de la nitro.
            self.nitro = min(MAX_NITRO, self.nitro + NITRO_REGEN * dt)

        # Le frein est moins puissant en marche arrière.
        if forward_speed >= 0:
            brake_force = brake * BRAKE_FORCE
        else:
            brake_force = brake * BRAKE_FORCE * 0.45

        # Accélération.
        forward_speed += drive_force * dt

        # Freinage.
        if forward_speed > 0:
            forward_speed = max(0.0, forward_speed - brake_force * dt)
        else:
            forward_speed = min(0.0, forward_speed + brake_force * dt)

        # Perte naturelle de vitesse quand on n'accélère pas.
        if throttle < 0.01:
            forward_speed *= COAST_DRAG

        # Résistance permanente au roulement.
        forward_speed *= ROLLING_RESISTANCE

        # Limitation de la vitesse.
        forward_speed = max(MAX_REVERSE_SPEED, min(MAX_SPEED, forward_speed))

        # La direction devient plus efficace avec la vitesse.
        steer_strength = min(1.0, speed_abs / max(MIN_STEER_SPEED, 1.0))

        # À haute vitesse, la voiture tourne moins facilement.
        understeer_factor = 1.0 - 0.28 * min(1.0, speed_abs / 260.0)

        # Perte d'adhérence arrière si on accélère fort en braquant.
        rear_traction_loss = abs(steer_input) * throttle * min(1.0, speed_abs / 220.0)

        # Effet principal de la direction.
        steer_effect = steer_input * STEER_RATE * steer_strength * understeer_factor

        # Réduction du braquage en cas de surcharge à haute vitesse.
        overload = (
            max(0.0, (speed_abs - 180.0) / 120.0)
            * max(0.0, abs(steer_input) - 0.18)
        )
        steer_effect *= max(0.62, 1.0 - 0.32 * overload)

        # En marche arrière, la direction est inversée et réduite.
        if forward_speed < 0:
            steer_effect *= -0.55

        # Mise à jour de l'angle.
        self.prev_angle_deg = self.angle_deg
        self.angle_deg += steer_effect * dt

        # Vitesse de rotation de la voiture.
        self.angular_velocity = (
            self.angle_deg - self.prev_angle_deg
        ) / max(dt, 1e-6)

        # Adhérence latérale.
        lateral_grip = 8.4

        # À haute vitesse, l'adhérence diminue légèrement.
        lateral_grip *= 1.0 - 0.12 * min(1.0, speed_abs / 260.0)

        # Si l'arrière perd de la traction, l'adhérence diminue.
        lateral_grip *= 1.0 - 0.17 * rear_traction_loss

        # Le freinage stabilise légèrement la voiture.
        lateral_grip *= 1.0 + 0.06 * brake

        # Ajustement du retour d'adhérence selon l'intensité du braquage.
        correction_factor = max(0.0, abs(steer_input) - 0.12) / 0.88
        effective_lateral_damping = lateral_grip * (0.82 + 0.18 * correction_factor)

        # Réduction progressive de la vitesse latérale.
        lateral_speed -= lateral_speed * min(1.0, effective_lateral_damping * dt)

        # Rapport de glisse.
        slip_ratio = abs(lateral_speed) / max(35.0, speed_abs)

        # Si la voiture glisse trop, elle perd un peu de vitesse.
        if slip_ratio > 0.24 and speed_abs > 95:
            scrub = min(0.09, (slip_ratio - 0.24) * 0.15)
            forward_speed *= (1.0 - scrub)

        # Effet de survirage léger quand l'arrière perd de l'adhérence.
        if rear_traction_loss > 0.34:
            lateral_speed += self.angular_velocity * 0.007 * rear_traction_loss

        # Reconstruction de la vitesse globale à partir des composantes.
        self.vel_x = forward_x * forward_speed + right_x * lateral_speed
        self.vel_y = forward_y * forward_speed + right_y * lateral_speed

        # Mise à jour de la position.
        self.x += self.vel_x * dt
        self.y += self.vel_y * dt

        # Vitesse affichée, toujours positive.
        self.speed = max(0.0, forward_speed)

        # Arrêt progressif quand la voiture est presque immobile.
        if abs(self.speed) < 1.0 and throttle < 0.01 and brake < 0.01:
            self.speed = 0.0
            self.vel_x *= 0.92
            self.vel_y *= 0.92

    def apply_collision_penalty(self, impact_strength: float):
        """
        Applique les conséquences d'une collision.

        Une collision :
        - ralentit la voiture
        - réduit sa vie
        - peut la détruire si la vie tombe à zéro
        """

        # Ralentissement brutal après l'impact.
        self.speed *= COLLISION_SLOWDOWN_FACTOR
        self.vel_x *= COLLISION_SLOWDOWN_FACTOR
        self.vel_y *= COLLISION_SLOWDOWN_FACTOR

        # Conversion de la force d'impact en dégâts.
        damage = impact_strength * COLLISION_DAMAGE_SCALE
        self.health = max(0.0, self.health - damage)

        # Destruction si la vie est épuisée.
        if self.health <= 0:
            self.destroyed = True
            self.speed = 0.0
            self.vel_x = 0.0
            self.vel_y = 0.0

    def reset_to(self, x: float, y: float, angle_deg: float):
        """
        Replace la voiture à une position donnée.

        Cette méthode est utilisée après :
        - une sortie de piste
        - un mauvais sens
        - une pénalité
        """

        # Une voiture détruite ne peut pas être replacée.
        if self.destroyed:
            return

        # Nouvelle position et orientation.
        self.x = x
        self.y = y
        self.angle_deg = angle_deg
        self.prev_angle_deg = angle_deg

        # Réinitialisation du mouvement.
        self.angular_velocity = 0.0
        self.speed = 0.0
        self.vel_x = 0.0
        self.vel_y = 0.0

        # Évite un double comptage de ligne après respawn.
        self.crossed_start_recently = False
        self.start_line_cooldown = 0.95

    def rect_for_collision(self):
        """
        Retourne un rectangle simple autour de la voiture.

        Cette méthode peut servir pour des collisions approximatives.
        """
        return (
            self.x - self.length / 2,
            self.y - self.width / 2,
            self.length,
            self.width,
        )