# 🏎️ Car Game - Multiplayer Web Racing

A real-time multiplayer car racing game with a JavaScript web interface, Python game server, and Azure Container Apps deployment.

## Architecture

```
Browser (HTML5 Canvas)  ←→  Node.js Frontend  ←→  Python Game Server
       (rendering)          (static + proxy)       (physics, AI, race logic)
```

## Quick Start (Local Development)

### Option 1: Docker Compose (recommended)
```bash
docker-compose up --build
# Open http://localhost:3000
```

### Option 2: Run manually
```bash
# Terminal 1 - Game server
pip install -r requirements.txt
python -m server_ws.game_server

# Terminal 2 - Frontend
cd frontend && npm install && npm start
# Open http://localhost:3000
```

## How to Play

1. Open `http://localhost:3000` in your browser
2. Enter your name and a room code (or leave blank for a new room)
3. Share the room code with friends
4. Configure race settings (track, laps, bots, difficulty)
5. Click **Start Race**
6. Controls: Arrow keys or WASD to drive, Space for nitro

Need the short version? See [QUICK_PLAY.md](QUICK_PLAY.md).

For a full player manual with controls, race modes, HUD details, penalties, and driving strategy, see [HOW_TO_PLAY.md](HOW_TO_PLAY.md).

## Project Structure

```
├── game/                  # Python game logic (headless)
│   ├── car.py            # Car physics
│   ├── race.py           # Race management
│   ├── track.py          # Track geometry & collision
│   └── ai.py            # Bot AI drivers
├── server_ws/            # Python WebSocket game server
│   ├── game_server.py   # Server entry point + game loop
│   └── room.py          # Room/lobby management
├── frontend/             # Node.js + browser client
│   ├── server.js        # Express server (static + WS proxy)
│   └── public/
│       ├── index.html   # Game page
│       ├── css/         # Styles
│       └── js/          # Client modules (renderer, input, lobby, HUD)
├── infra/               # Azure deployment
│   ├── main.bicep       # Container Apps infrastructure
│   └── deploy.sh       # Deployment script
├── .github/workflows/   # CI/CD
├── docker-compose.yml   # Local dev
├── Dockerfile.gameserver
└── Dockerfile.frontend
```

## Deploy to Azure

```bash
# First time: deploy infrastructure + containers
cd infra && bash deploy.sh

# Subsequent: push to main branch triggers GitHub Actions
```

Requires: `AZURE_CREDENTIALS` secret in GitHub repository settings.

### Deploy Images to ACR Manually

```bash
# Set variables
ACR_NAME=cargameacr
RESOURCE_GROUP=cargame-rg

# Login to Azure and ACR
az login
az acr login --name $ACR_NAME

# Get ACR login server
ACR_SERVER=$(az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query loginServer -o tsv)

# Build and push game server image
docker build -f Dockerfile.gameserver -t $ACR_SERVER/cargame-gameserver:latest .
docker push $ACR_SERVER/cargame-gameserver:latest

# Build and push frontend image
docker build -f Dockerfile.frontend -t $ACR_SERVER/cargame-frontend:latest .
docker push $ACR_SERVER/cargame-frontend:latest

# Update running container apps with new images
az containerapp update --name cargame-gameserver --resource-group $RESOURCE_GROUP \
  --image $ACR_SERVER/cargame-gameserver:latest

az containerapp update --name cargame-frontend --resource-group $RESOURCE_GROUP \
  --image $ACR_SERVER/cargame-frontend:latest
```

## Tech Stack

- **Game server**: Python 3.11 + aiohttp (WebSocket)
- **Frontend server**: Node.js + Express
- **Client**: HTML5 Canvas 2D, vanilla JavaScript (ES modules)
- **Infrastructure**: Azure Container Apps, ACR, Bicep
- **CI/CD**: GitHub Actions
