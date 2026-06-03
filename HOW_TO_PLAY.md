# How to Play Car Race

Car Race is a real-time multiplayer browser racing game with a monitor view and optional phone controllers. The monitor shows the lobby, race, leaderboard, minimap, HUD, and results. A phone controller can pair to one specific player and drive only that player.

## Table of Contents

1. Game Setup
2. Lobby Flow
3. Phone Controller Pairing
4. Controller Interface
5. Keyboard and Touch Fallback
6. Race Modes
7. Lobby Settings
8. Race HUD
9. Track Rules and Penalties
10. Game Controls
11. Records and Ghosts
12. Driving Tips
13. Troubleshooting
14. Test Checklist

## 1. Game Setup

Open the game:

- Azure: `https://cargame-frontend.purpleriver-82827e89.swedencentral.azurecontainerapps.io`
- Local development: `http://localhost:3000`

The game has two main surfaces:

- **Monitor / display page**: the main browser page used to create rooms, show the race, and render the track.
- **Controller page**: `controller.html`, usually opened on a phone using the QR code shown in the lobby.

The controller does not create a new player. It pairs to an existing player using:

- `roomId`
- `playerId`
- `role = controller`

## 2. Lobby Flow

### Create a Room

1. Open the game on the monitor.
2. Enter your player name.
3. Leave `Room Code` empty.
4. Choose race settings.
5. Click `Join Game`.

The game creates a room code. The first driver in the room becomes the host.

### Join an Existing Room

1. Open the game on another monitor/browser.
2. Enter your name.
3. Enter the existing room code.
4. Click `Join Game`.

### Ready and Start

Each driver has a monitor/display connection and, for normal phone play, a controller connection.

To start:

1. Each driver clicks `Ready` on the monitor.
2. Each controller should also be paired and ready.
3. The host clicks `Start Race`.

If the race cannot start, the lobby shows blockers such as a missing controller, disconnected monitor, or player not ready.

### Spectating

Use `Spectate` to join a room without taking a driving slot. Spectators can watch the lobby and race but do not control a car.

## 3. Phone Controller Pairing

After a driver joins, the lobby shows a controller pairing card with:

- Room ID
- Player ID
- Controller link
- QR code

Open the controller page on the phone by scanning the QR code or using the link.

Example:

```text
controller.html?room=RACE123&player=P1
```

The controller page auto-fills:

- `Room ID`
- `Player ID`

You can also enter a player name for the phone controller. Then tap `Connect`.

### Pairing States

The controller page shows clear status:

- `Not connected`: no active socket.
- `Connecting`: opening the WebSocket.
- `Connected`: socket opened and pairing is being registered.
- `Controller paired`: the phone is attached to the matching player.
- `Pairing failed`: the player or room did not match, or the server rejected the connection.
- `Disconnected`: socket closed.
- `Reconnecting`: temporary disconnect recovery is in progress.

### Important Pairing Rule

The controller always joins with:

```json
{
  "action": "join",
  "role": "controller",
  "player_id": "P1"
}
```

It never joins as a display. It never creates a separate player. It only sends input for the player matching the room and player ID.

## 4. Controller Interface

The phone controller is designed as a mobile gamepad.

### Pairing Section

Fields:

- `Room ID`
- `Player ID`
- `Player Name`
- steering mode

Buttons:

- `Connect`
- `Disconnect`

### Drive Section

Main controls:

- `Throttle`
- `Brake`
- `Nitro`
- steering display
- touch steering slider
- speed readout
- health readout

### Steering Modes

The controller supports:

- `Tilt steering`: steer by tilting the phone.
- `Touch steering`: steer with the slider.

Use `Enable Motion` before tilt steering. Some phones require a permission prompt before motion sensors work.

### Sensor Options

Available sensor controls:

- axis selection: `Gamma`, `Beta`, `Alpha`
- sensitivity
- dead zone
- invert axis
- smoothing
- reset calibration

### Calibration Wizard

Use the calibration wizard when steering feels off.

Steps:

1. Hold the phone centered and save center.
2. Tilt left and save left.
3. Tilt right and save right.
4. Save calibration.

This teaches the controller what “center”, “left”, and “right” mean for your grip and phone orientation.

### Haptics

If the phone supports vibration, the controller vibrates for:

- successful connection
- countdown
- race start
- nitro activation
- collision
- off-track / warning states
- finish line

If vibration is unsupported, the controller keeps working normally.

### Controller Audio

The controller has lightweight audio feedback:

- `Mute`
- volume slider
- sound effects on/off

Controller audio is optional and separate from the monitor’s race audio.

### Debug Panel

The debug panel is collapsed by default. Open it when diagnosing a controller issue.

It shows:

- room
- player
- WebSocket status
- last input sent
- steering value
- throttle/brake/nitro state
- ping field when available
- socket state

## 5. Keyboard and Touch Fallback

If no phone controller is linked to your player, the monitor page can send keyboard input.

| Action | Keys |
| --- | --- |
| Accelerate | Up Arrow or W |
| Brake | Down Arrow or S |
| Steer Left | Left Arrow or A |
| Steer Right | Right Arrow or D |
| Nitro | Space |

On touch displays, the monitor may show simple touch buttons for gas, brake, and nitro. For the best multiplayer experience, use the phone controller.

## 6. Race Modes

### Sprint

Sprint is the main race mode.

Goal: finish the selected number of laps first.

Features:

- multiplayer-friendly
- bots can be enabled
- leaderboard and minimap are important
- selected lap count matters

Best for normal races with friends or bots.

### Time Trial

Time Trial is a solo lap-time mode.

Goal: drive clean, fast laps and beat your own best time.

Features:

- no bots
- no traffic
- good for learning braking points
- supports personal records and ghosts

Best for improving lap times.

### Practice

Practice is a free driving mode.

Goal: learn the track without race pressure.

Features:

- no bots
- no fixed competitive finish pressure
- good for testing steering assist and phone calibration
- useful before trying Sprint or Time Trial

Best for warmups and learning corners.

### Elimination

Elimination is a survival race.

Goal: stay ahead when elimination pressure hits.

Features:

- bots can be enabled
- if there are too few human players, the game can add bot pressure
- lap count is not used like Sprint
- staying out of last place matters

Best for chaotic races and pressure sessions.

## 7. Lobby Settings

### Mode

Choose:

- `Sprint`
- `Time Trial`
- `Practice`
- `Elimination`

### Track

Choose:

- `Circuit 1`
- `Circuit 2`

Each track has a different rhythm. Practice one before chasing speed on both.

### Laps

Used mainly by Sprint and Time Trial.

Options in the current UI:

- 3
- 5
- 10

Practice and Elimination do not use laps the same way.

### Bots

Bots can be used in:

- Sprint
- Elimination

Bots are disabled for:

- Time Trial
- Practice

### Difficulty

Bot difficulty:

- `Easy`
- `Medium`
- `Hard`
- `Expert`

### Damage

Damage can be on or off.

When damage is on:

- hard crashes reduce health
- low health makes mistakes more costly
- repeated crashes can seriously hurt race pace

### Steering

Monitor-side steering assist options:

- `Direct`: raw steering.
- `Assist`: smoother, easier control.
- `Stable`: strongest smoothing for beginners or twitchy inputs.

If your car feels too nervous, try `Assist` or `Stable`.

## 8. Race HUD

During a race, the monitor shows:

- position
- lap/progress
- speed
- time
- nitro bar
- health bar
- leaderboard
- minimap
- race warnings

### Leaderboard

The leaderboard shows current order and progress. In Sprint, it reflects laps and track progress. In solo modes, use it with lap timing and records.

### Minimap

The minimap shows:

- track shape
- car positions
- nearby opponents

Use it to anticipate traffic and understand where you are on the circuit.

### Race Warnings

Warnings can include:

- `Wrong way`
- `Shortcut penalty`
- `Checkpoint missed`
- off-track warning behavior

Correct the problem quickly to avoid losing time or being respawned.

## 9. Track Rules and Penalties

The game tracks progress using checkpoints and direction.

### Checkpoints

Clean laps require passing the expected checkpoint sequence. Crossing the line after skipping too much of the track may not count.

### Wrong Way

Driving backward around the track triggers `Wrong way`. If you keep going the wrong direction, the game can respawn you near a valid checkpoint.

### Shortcut Penalty

Cutting too much of the track can trigger a shortcut warning or invalidate progress.

### Checkpoint Missed

If you cross the finish line without enough valid checkpoint progress, the lap may be rejected.

### Off Track

Leaving the road can slow your race, trigger warnings, or cause a penalty respawn depending on the situation.

### Collisions

Collisions reduce speed. With damage enabled, hard impacts also reduce health.

## 10. Game Controls

### Monitor Race Buttons

The monitor race UI includes:

- `Pause`
- `Resume`
- `Restart`
- `Reset`
- `Quit`
- `Ghost On` / `Ghost Off`
- `Mute`
- volume and FX controls
- sound quality selector

### Phone Controller Game Buttons

The phone controller includes:

- `Ready`
- `Pause`
- `Resume`
- `Restart`
- `Quit`
- `Respawn`

The controller only sends commands to the server. It does not implement race logic by itself.

Current note: the controller’s `Respawn` button sends the existing server `reset` command. It is a race reset/respawn-style command, not separate custom car logic.

## 11. Records and Ghosts

Personal records are saved in the browser.

Tracked items include:

- best lap
- best race time
- races completed
- wins
- podiums
- achievements

In Practice and Time Trial, ghost paths can help compare your current driving line against a previous lap. Use `Ghost On` or `Ghost Off` on the monitor to control this display.

## 12. Driving Tips

### Brake Before Turning

The car turns better when it is not entering a corner too fast. Brake while straight, then turn.

### Win the Exit

A clean corner exit is usually faster than a wild corner entry. Straighten the car before using full throttle and nitro.

### Use Nitro Carefully

Good nitro moments:

- long straights
- clean corner exits
- safe overtakes
- recovery after a slow section

Bad nitro moments:

- right before sharp corners
- while sliding
- while pointed at a wall
- in traffic with no room

### Calibrate the Phone

If tilt steering feels wrong:

1. Enable motion.
2. Start calibration.
3. Save center, left, and right.
4. Adjust sensitivity, dead zone, and smoothing.

### Use the Right Mode to Improve

- Practice: learn the road.
- Time Trial: improve lap times.
- Sprint: race under pressure.
- Elimination: learn survival and recovery.

## 13. Troubleshooting

### Controller Does Not Pair

Check:

- the monitor joined the room first
- the controller URL has the correct `room` and `player`
- the controller status reaches `Controller paired`
- the player ID exists in the lobby
- you did not open a stale QR code from another room

If needed, disconnect and reconnect the controller.

### Extra Player Appears

The phone controller should not create a player. If an extra player appears, you likely opened the main game page instead of `controller.html`.

Use the QR code or controller link from the lobby.

### Race Will Not Start

Common blockers:

- a monitor is not ready
- a controller is missing
- a controller is not ready
- you are not the host
- the room is still in another race state

### Steering Feels Wrong

Try:

- recalibrating the phone
- switching axis between Gamma, Beta, and Alpha
- lowering sensitivity
- increasing dead zone
- increasing smoothing
- using touch steering instead of tilt
- using `Assist` or `Stable` steering on the monitor settings

### Motion Permission Does Not Work

Some mobile browsers require tapping `Enable Motion` and accepting a permission prompt. If the prompt is denied, tilt steering will not work until permission is allowed again.

### Vibration Does Not Work

Not all phones or browsers support vibration. The controller will still work without haptics.

### Keyboard Input Does Not Move the Car

If a phone controller is linked to your player, the monitor stops sending keyboard input for that player. Use the controller, or disconnect it to return to keyboard fallback.

### Nitro Feels Weak

Nitro works best when the car is straight and already accelerating. Avoid using it while turning hard or sliding.

## 14. Test Checklist

Use this checklist after deployment or before a play session:

1. Open the monitor on PC or iPad.
2. Create a room.
3. Note the room ID and player ID.
4. Open the phone controller link or scan the QR code.
5. Confirm room ID and player ID are auto-filled.
6. Tap `Connect`.
7. Confirm the controller says `Controller paired`.
8. Confirm the lobby shows the controller linked to the same player.
9. Confirm no extra player was created.
10. Test tilt or touch steering.
11. Test throttle, brake, and nitro.
12. Test ready, pause, resume, restart, and respawn/reset.
13. Test calibration, sensitivity, dead zone, invert, and smoothing.
14. Start a race and confirm the correct car moves.

## Quick Reference

| Need | Use |
| --- | --- |
| Create a race | Main monitor page |
| Pair phone | Lobby QR code |
| Phone URL format | `controller.html?room=ROOM&player=P1` |
| Main race | Sprint |
| Solo lap times | Time Trial |
| Learn track | Practice |
| Survival pressure | Elimination |
| Fix tilt steering | Calibration wizard |
| Reduce twitchy steering | Smoothing, dead zone, Assist/Stable |
| Diagnose pairing | Debug panel |

Drive clean first. Speed comes after the car is under control.
