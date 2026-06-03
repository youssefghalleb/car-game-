# Quick Play

Use this when you want to race immediately.

## 1. Open the Game

- Azure: `https://cargame-frontend.purpleriver-82827e89.swedencentral.azurecontainerapps.io`
- Local dev: `http://localhost:3000`

## 2. Create or Join a Room

1. Enter your player name.
2. Leave `Room Code` empty to create a room, or enter an existing code.
3. Pick mode, track, laps, bots, difficulty, damage, and steering assist.
4. Click `Join Game`.
5. Click `Ready`.
6. If you are host, click `Start Race` once all required players/controllers are ready.

The first driver in a room is the host.

## 3. Connect a Phone Controller

After joining as a driver, the lobby shows a controller card with:

- Room ID
- Player ID
- Controller link
- QR code

On your phone:

1. Scan the QR code or open the controller link.
2. Confirm `Room ID` and `Player ID` are filled in.
3. Tap `Connect`.
4. Wait for `Controller paired`.
5. Use the phone controller to drive that player only.

Example controller link:

```text
controller.html?room=RACE123&player=P1
```

## 4. Drive

### Phone Controller

| Action | Control |
| --- | --- |
| Accelerate | `Throttle` |
| Brake | `Brake` |
| Nitro | `Nitro` |
| Steer | Tilt phone or use touch steering |
| Ready | `Ready` |
| Pause / Resume | `Pause`, `Resume` |
| Restart | `Restart` |
| Respawn / Reset race | `Respawn` |

Use `Enable Motion` before tilt steering. Use the calibration wizard if steering feels off.

### Keyboard Fallback

Keyboard works when no phone controller is linked to your player.

| Action | Keys |
| --- | --- |
| Accelerate | Up Arrow or W |
| Brake | Down Arrow or S |
| Steer | Left/Right Arrow or A/D |
| Nitro | Space |

## 5. Race Modes

| Mode | What It Is |
| --- | --- |
| `Sprint` | Main race. Finish the selected laps first. Bots can join. |
| `Time Trial` | Solo lap-time mode. No bots. Good for records and ghosts. |
| `Practice` | Solo free practice. No fixed race pressure. |
| `Elimination` | Survival mode. Stay ahead when elimination pressure hits. Bots can join. |

## 6. Watch the HUD

- `P1`, `P2`, etc: current position.
- `Lap`: current lap or mode-specific progress.
- `Speed`: current speed.
- Nitro bar: available boost.
- Health bar: car damage if damage is enabled.
- Leaderboard: current order.
- Minimap: track and car positions.

## 7. Avoid Penalties

- `Wrong way`: turn around.
- `Shortcut penalty`: return to the real racing line.
- `Checkpoint missed`: pass the track checkpoints properly.
- `Off track`: get back on the road before losing more time.

## 8. Fast Tips

- Brake before turning.
- Use nitro on straights and clean corner exits.
- Use `Assist` or `Stable` steering if the car twitches.
- Calibrate the phone controller before serious racing.
- In Sprint, consistency beats one lucky fast lap.

For the complete guide, read [HOW_TO_PLAY.md](HOW_TO_PLAY.md).
