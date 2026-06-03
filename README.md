# Car Game - Multiplayer Web Racing

Car Game is a real-time multiplayer racing game built for a browser monitor and optional phone controllers. The monitor renders the race, lobby, HUD, minimap, leaderboard, QR pairing, and results. Each phone controller pairs to one existing player and sends input only for that player.

The project is deployed with Azure Container Apps using two containers:

- `frontend`: Node.js/Express static web server and WebSocket proxy.
- `gameserver`: Python/aiohttp authoritative race server.

Live Azure frontend:

```text
https://cargame-frontend.purpleriver-82827e89.swedencentral.azurecontainerapps.io
```

For player instructions, see:

- [QUICK_PLAY.md](QUICK_PLAY.md)
- [HOW_TO_PLAY.md](HOW_TO_PLAY.md)

## Table of Contents

1. Features
2. How to Run Locally
3. How to Deploy
4. Architecture
5. WebSocket Protocol
6. Game Systems
7. Project Structure
8. Configuration
9. Testing and Verification
10. Troubleshooting
11. Known Bugs and Limitations
12. Next Features

## Features

- Real-time multiplayer rooms.
- Browser-based monitor/display page.
- Mobile phone controller page with QR-code pairing.
- Controller pairing by `roomId + playerId + role=controller`.
- Keyboard fallback when no controller is linked.
- Sprint, Time Trial, Practice, and Elimination race modes.
- Two tracks: Circuit 1 and Circuit 2.
- Bots with adjustable difficulty.
- Car physics with throttle, brake, steering, nitro, collisions, damage, off-track penalties, and respawn.
- HUD with lap, speed, nitro, health, leaderboard, race warnings, and minimap.
- Race state broadcasting optimized for browser play.
- Azure Container Apps deployment with ACR images.
- WebSocket support through the frontend proxy or direct public game server URL.
- Track 2 anti-cheat for wrong-way and skipped-checkpoint behavior.

## How to Run Locally

### Prerequisites

Install:

- Docker Desktop
- Docker Compose

Optional for manual mode:

- Python 3.11+
- Node.js 20+
- npm

### Recommended: Docker Compose

From the repository root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:3000
```

Useful local URLs:

```text
Monitor/game page:     http://localhost:3000
Controller page:       http://localhost:3000/controller.html
Example controller:    http://localhost:3000/controller.html?room=RACE123&player=P1
Game server WebSocket: ws://localhost:8765/ws/<ROOM_ID>
Frontend config:       http://localhost:3000/api/config
```

Stop the stack:

```bash
docker compose down
```

### Manual Development Mode

Terminal 1, start the Python game server:

```bash
pip install -r requirements.txt
python -m server_ws.game_server
```

Terminal 2, start the frontend:

```bash
cd frontend
npm install
npm start
```

Open:

```text
http://localhost:3000
```

### Local Play Flow

1. Open `http://localhost:3000` on the monitor device.
2. Enter a player name.
3. Leave room code empty to create a room, or enter an existing room code.
4. Select mode, track, laps, bots, difficulty, damage, and assist.
5. Click `Join Game`.
6. Scan the controller QR code on a phone.
7. Confirm the controller page auto-fills room and player.
8. Tap `Connect`.
9. Wait for `Controller paired`.
10. Ready up and start the race.

## How to Deploy

Deployment uses:

- Azure Resource Group
- Azure Container Registry
- Azure Container Apps Environment
- Azure Container App for the gameserver
- Azure Container App for the frontend
- Log Analytics workspace

The deployment script builds images locally, pushes them to ACR, deploys/updates infrastructure with Bicep, and prints the public frontend URL.

### Prerequisites

Install and authenticate:

```bash
az login
docker --version
```

Docker Desktop must be running.

### Deploy With the Script

From the repository root:

```bash
cd infra
bash deploy.sh
```

Default values:

```bash
RESOURCE_GROUP=cargame-rg
LOCATION=swedencentral
APP_NAME=cargame
IMAGE_TAG=<timestamp>
```

Override values if needed:

```bash
RESOURCE_GROUP=my-rg LOCATION=swedencentral APP_NAME=mycargame bash infra/deploy.sh
```

`APP_NAME` must be 2-47 lowercase letters/numbers because it is used to create the ACR name.

### What the Script Does

1. Creates or reuses the Azure resource group.
2. Creates or reuses Azure Container Registry.
3. Logs in to ACR.
4. Builds the gameserver image from `Dockerfile.gameserver`.
5. Pushes the gameserver image.
6. Builds the frontend image from `Dockerfile.frontend`.
7. Pushes the frontend image.
8. Deploys `infra/main.bicep`.
9. Configures the frontend with:
   - `GAME_SERVER_URL=https://<gameserver-fqdn>`
   - `PUBLIC_GAME_SERVER_WS_URL=wss://<gameserver-fqdn>`
   - `PORT=3000`
10. Prints the frontend URL.

### Manual Image Update

Use this when infrastructure already exists and only the images need updating.

```bash
APP_NAME=cargame
RESOURCE_GROUP=cargame-rg
IMAGE_TAG=$(date +%Y%m%d%H%M%S)
ACR_NAME="${APP_NAME}acr"

az acr login --name "$ACR_NAME"
ACR_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer \
  --output tsv)

docker build -f Dockerfile.gameserver -t "$ACR_SERVER/${APP_NAME}-gameserver:$IMAGE_TAG" .
docker push "$ACR_SERVER/${APP_NAME}-gameserver:$IMAGE_TAG"

docker build -f Dockerfile.frontend -t "$ACR_SERVER/${APP_NAME}-frontend:$IMAGE_TAG" .
docker push "$ACR_SERVER/${APP_NAME}-frontend:$IMAGE_TAG"

az containerapp update \
  --name "${APP_NAME}-gameserver" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$ACR_SERVER/${APP_NAME}-gameserver:$IMAGE_TAG"

az containerapp update \
  --name "${APP_NAME}-frontend" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$ACR_SERVER/${APP_NAME}-frontend:$IMAGE_TAG"
```

### Azure Design Notes

- Gameserver `maxReplicas` is intentionally `1` because active rooms live in process memory.
- Frontend can scale up to `10` replicas.
- Sticky sessions are enabled for WebSocket reliability.
- The frontend exposes `/api/config` so browsers can use the correct public WebSocket URL.
- The frontend also proxies `/ws` for local development and fallback setups.

## Architecture

High-level runtime:

```text
Phone Controller
  controller.html + controller.js
        |
        | WebSocket join role=controller
        v
Python Game Server <---------------- Monitor Browser
  aiohttp WebSocket                  index.html + JS modules
  rooms + race loop                         |
        ^                                   |
        | state snapshots                   |
        +-----------------------------------+

Node.js Frontend
  static files
  /api/config
  /api proxy
  /ws proxy
```

Azure runtime:

```text
Internet
  |
  +--> Frontend Container App :3000
  |      - serves HTML/CSS/JS
  |      - returns /api/config
  |      - can proxy /ws locally/fallback
  |
  +--> Gameserver Container App :8765
         - authoritative rooms
         - WebSocket connections
         - physics, AI, laps, checkpoints
```

### Frontend Container

Files:

- `frontend/server.js`
- `frontend/public/index.html`
- `frontend/public/controller.html`
- `frontend/public/css/style.css`
- `frontend/public/js/*.js`

Responsibilities:

- Serve the monitor page.
- Serve the controller page.
- Serve static assets.
- Provide `/api/config`.
- Proxy `/api` to the gameserver.
- Proxy `/ws` WebSocket upgrades when needed.

### Gameserver Container

Files:

- `server_ws/game_server.py`
- `server_ws/room.py`
- `server_ws/shared_pairing.py`
- `game/race.py`
- `game/car.py`
- `game/track.py`
- `game/ai.py`

Responsibilities:

- Own room state.
- Register display, controller, and spectator connections.
- Run simulation at `60 Hz`.
- Broadcast state around `24 Hz`.
- Enforce race rules.
- Apply physics, collision, off-track, wrong-way, checkpoint, and finish-line logic.
- Send smaller telemetry messages to controllers.

### Pairing Model

The monitor/display creates the player slot. The controller only attaches to that slot.

Display join:

```json
{
  "action": "join",
  "role": "display",
  "name": "Player",
  "player_id": null
}
```

Controller join:

```json
{
  "action": "join",
  "role": "controller",
  "player_id": "P1",
  "name": "Controller"
}
```

The server associates controller input with:

```text
room_id + player_id
```

The controller must never create a new player. If the player does not exist, the server returns `player_not_found`.

### State Flow

1. Monitor joins room as `display`.
2. Server creates or reconnects a `PlayerSlot`.
3. Server returns `room_id` and `player_id`.
4. Lobby builds a controller URL:

```text
/controller.html?room=<ROOM_ID>&player=<PLAYER_ID>
```

5. Phone opens controller URL.
6. Controller auto-fills room/player from URL params.
7. Controller joins as `role=controller`.
8. Server attaches controller to matching player.
9. Controller sends input messages.
10. Server applies input to that player's car.
11. Server broadcasts state to displays and telemetry to controllers.

## WebSocket Protocol

### URL

Local:

```text
ws://localhost:8765/ws/<ROOM_ID>
```

Azure:

```text
wss://<gameserver-container-app-fqdn>/ws/<ROOM_ID>
```

The frontend returns the public URL from:

```text
GET /api/config
```

### Main Client Messages

Join:

```json
{
  "action": "join",
  "role": "display|controller|spectator",
  "name": "Player",
  "player_id": "P1"
}
```

Input:

```json
{
  "action": "input",
  "steer": 0.0,
  "throttle": 1,
  "brake": 0,
  "nitro": false
}
```

Ready:

```json
{
  "action": "ready",
  "ready": true
}
```

Race commands:

```json
{ "action": "start" }
{ "action": "pause" }
{ "action": "resume" }
{ "action": "restart" }
{ "action": "reset" }
{ "action": "quit" }
```

Settings, host only while in lobby:

```json
{
  "action": "settings",
  "race_mode": "sprint",
  "track_layout": "track_2",
  "laps_to_win": 5,
  "bot_count": 2,
  "bot_difficulty": "medium",
  "car_damage": true,
  "steer_assist": "assist"
}
```

### Server Messages

Joined:

```json
{
  "action": "joined",
  "role": "display",
  "connection_id": "abcd1234",
  "player_id": "P1",
  "room_id": "RACE123"
}
```

Error:

```json
{
  "error": "player_not_found"
}
```

Display state snapshots contain:

- room state
- settings
- players
- cars
- track data when needed
- crash events
- leaderboard-related fields

Controller telemetry contains a smaller player-specific payload:

- speed
- health
- nitro
- countdown/race state
- wrong-way/off-track/checkpoint warnings
- finish state

## Game Systems

### Race Modes

| Mode | Description |
| --- | --- |
| Sprint | Standard multiplayer race. First car to complete selected laps ends the race. Bots can be enabled. |
| Time Trial | Solo performance mode. Bots are disabled. Goal is clean lap/race time. |
| Practice | Solo free-drive mode. Useful for learning track, controller calibration, and physics. |
| Elimination | Survival mode. The last active car is periodically eliminated until one remains. Bots can be enabled when needed. |

### Track Rules and Anti-Cheat

The authoritative race server enforces:

- off-track detection
- wrong-way detection
- start/finish direction
- checkpoint order
- invalid lap warnings
- penalty respawns

Track 2 has extra protection because its shape previously allowed wrong-way/shortcut behavior. Human players must pass checkpoints in order. Skipping checkpoints or driving backward invalidates the current lap and can trigger a penalty respawn.

### Controller

The phone controller supports:

- room/player auto-fill from URL parameters
- connect/disconnect/reconnect
- connection status indicators
- large mobile controls
- throttle, brake, nitro
- touch steering
- tilt steering
- axis selection
- sensitivity
- dead zone
- invert axis
- smoothing
- calibration wizard
- haptics where supported
- optional controller-side audio
- debug panel

### Rendering

The browser monitor uses HTML5 Canvas 2D. Rendering is intentionally lightweight:

- cached track rendering
- interpolated car state
- HUD/minimap overlays
- collision/off-track visual feedback
- optimized device pixel ratio for browser performance

## Project Structure

```text
.
├── Dockerfile.frontend
├── Dockerfile.gameserver
├── docker-compose.yml
├── requirements.txt
├── config.py
├── frontend/
│   ├── package.json
│   ├── server.js
│   └── public/
│       ├── index.html
│       ├── controller.html
│       ├── css/
│       │   └── style.css
│       └── js/
│           ├── audio.js
│           ├── client.js
│           ├── controller.js
│           ├── hud.js
│           ├── input.js
│           ├── lobby.js
│           ├── main.js
│           └── renderer.js
├── game/
│   ├── ai.py
│   ├── car.py
│   ├── race.py
│   ├── render.py
│   └── track.py
├── server_ws/
│   ├── game_server.py
│   ├── room.py
│   └── shared_pairing.py
├── infra/
│   ├── deploy.sh
│   └── main.bicep
├── QUICK_PLAY.md
└── HOW_TO_PLAY.md
```

## Configuration

### Frontend Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `3000` | Frontend HTTP port. |
| `GAME_SERVER_URL` | `http://localhost:8765` | Internal HTTP URL used by the frontend proxy. |
| `PUBLIC_GAME_SERVER_WS_URL` | empty | Public WebSocket base URL returned to browsers. |
| `DEBUG_PROXY` | `0` | Enables frontend proxy debug logs. |

### Gameserver Constants

Defined in `server_ws/game_server.py`:

| Constant | Value | Purpose |
| --- | --- | --- |
| `TICK_RATE` | `60` | Simulation tick rate. |
| `BROADCAST_RATE` | `24` | Display state broadcast rate. |
| `LOBBY_REFRESH_RATE` | `4` | Lobby/pairing refresh rate. |
| `WS_HEARTBEAT_SECONDS` | `20` | WebSocket heartbeat. |
| `STATE_SEND_TIMEOUT_SECONDS` | `1.0` | Send timeout for slow clients. |

Defined in `config.py`:

| Setting | Purpose |
| --- | --- |
| `SERVER_HOST`, `SERVER_PORT` | Game server bind address and port. |
| `MAX_SPEED`, `ACCEL_FORCE`, `BRAKE_FORCE` | Core car physics. |
| `NITRO_FORCE`, `NITRO_CONSUMPTION`, `NITRO_REGEN` | Nitro behavior. |
| `MAX_HEALTH`, `COLLISION_DAMAGE_SCALE` | Damage behavior. |
| `PLAYER_COLORS` | Driver/bot colors. |

### Pairing Store

`server_ws/shared_pairing.py` uses a small SQLite file for recent display/controller pairing records:

```text
/tmp/car_game_pairing.sqlite
```

Override with:

```bash
PAIRING_DB_PATH=/path/to/pairing.sqlite
```

This is mainly used to keep pairing/input resilient around reconnects and local process boundaries. It is not a durable production database.

## Testing and Verification

### Syntax Checks

Python:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/car-game-pycache \
  python3 -m py_compile game/race.py game/track.py game/car.py
```

Controller JavaScript with Docker:

```bash
docker run --rm \
  -v "$PWD:/app" \
  -w /app \
  node:20-alpine \
  node --check frontend/public/js/controller.js
```

### Local Stack Smoke Test

```bash
docker compose up --build -d
docker compose ps
```

Open:

```text
http://localhost:3000
```

Verify:

1. Monitor creates a room.
2. Player ID is shown.
3. Controller QR/link includes `room` and `player`.
4. Controller connects and status becomes `Controller paired`.
5. No extra player is created.
6. Throttle/brake/steer/nitro affect the correct car.
7. Multiplayer still works with more than one player.
8. Track 2 wrong-way driving triggers warning/penalty instead of counting progress.

### Azure Smoke Test

After deployment:

1. Open the Azure frontend URL.
2. Create a room.
3. Join as a driver.
4. Scan QR code on phone.
5. Confirm controller auto-fills room/player.
6. Connect controller.
7. Start race.
8. Confirm WebSocket stays connected.
9. Confirm controller input reaches the correct car.
10. Check Azure Container App logs if anything fails.

Useful Azure commands:

```bash
az containerapp show \
  --name cargame-frontend \
  --resource-group cargame-rg \
  --query properties.configuration.ingress.fqdn \
  --output tsv

az containerapp logs show \
  --name cargame-gameserver \
  --resource-group cargame-rg \
  --follow
```

## Troubleshooting

### Controller Does Not Pair

Check:

- The monitor joined the room first.
- The controller URL has both `room` and `player`.
- The controller status does not say `Player not found`.
- The controller is using `role=controller`.
- The WebSocket URL is `ws://` locally and `wss://` on Azure.
- `/api/config` returns the expected public WebSocket base URL.
- The gameserver container is running.

Enable controller logs:

```bash
DEBUG_CONTROLLER=1 python -m server_ws.game_server
```

### WebSocket 1006 on Azure

Common causes:

- wrong `PUBLIC_GAME_SERVER_WS_URL`
- using `ws://` from an HTTPS page instead of `wss://`
- frontend proxy not handling upgrade
- gameserver container app not reachable
- missing sticky sessions
- container app revision not updated

Check:

```bash
az containerapp show --name cargame-gameserver --resource-group cargame-rg
az containerapp logs show --name cargame-gameserver --resource-group cargame-rg --follow
az containerapp logs show --name cargame-frontend --resource-group cargame-rg --follow
```

### Race Freezes on Countdown

Likely areas:

- room loop not running
- ready/start blockers
- gameserver exception
- container revision running old image
- frontend displaying cached state

Check gameserver logs first.

### Controller Page Too Large on Phone

The controller page uses responsive breakpoints and compact paired mode. If it still overflows:

- test portrait and landscape
- check browser zoom
- confirm latest frontend image was deployed
- rebuild frontend image after CSS changes

### Push to GitHub Fails With 403

If GitHub CLI shows a token with no scopes, refresh it:

```bash
gh auth refresh -h github.com -s repo
git push origin main
```

## Known Bugs and Limitations

- Gameserver rooms live in memory, so Azure gameserver scale is limited to one replica.
- If the gameserver restarts, active rooms are lost.
- The SQLite pairing store is temporary and not a durable multiplayer backend.
- Controller haptics depend on phone/browser support and may not work on every device.
- Motion sensor permission behavior differs across iOS/Android browsers.
- QR code generation uses an external QR service, so QR display depends on external availability.
- Very slow client networks may still feel jittery with multiple players.
- Spectator and controller reconnects are supported, but long disconnects can still require rejoining.
- The game has no authentication; room codes are the only room separation.
- Race records are lightweight/local to the current server process unless extended.
- Azure deployment currently depends on local Docker builds from `infra/deploy.sh`.
- Old Pygame-oriented files remain in the repository for legacy/local code history and are not part of the Azure web runtime.

## Next Features

Recommended next work, in priority order:

1. Add a durable room/session store so the gameserver can scale beyond one replica.
2. Add automated integration tests for display/controller pairing and race start.
3. Add Playwright/mobile viewport tests for controller responsiveness.
4. Replace external QR generation with a local QR implementation.
5. Add structured metrics for latency, tick time, broadcast time, and dropped sends.
6. Add better reconnect UX for players who lose phone/controller connection mid-race.
7. Improve Track 2 boundaries and visual anti-cheat feedback.
8. Add a lobby admin panel for host controls and player removal.
9. Add persistent race records and player profiles.
10. Add replay/ghost lap support for Time Trial.
11. Add more tracks and track selection previews.
12. Add a presentation/demo mode with scripted camera and simplified setup.

## Presentation Summary

Car Game demonstrates a complete real-time multiplayer system:

- The browser monitor focuses on rendering and user interface.
- The phone controller focuses on input.
- The Python server is authoritative for game state and anti-cheat.
- Azure Container Apps hosts both containers with public WebSocket access.
- The architecture is intentionally simple enough for a school/project demo while still showing real production concepts: containerization, WebSockets, server-authoritative simulation, deployment automation, environment-based configuration, and mobile pairing.
