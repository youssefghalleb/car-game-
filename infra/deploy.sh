#!/bin/bash
# Deploy script for Azure Container Apps
# Prerequisites: az CLI logged in, Docker installed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RESOURCE_GROUP="${RESOURCE_GROUP:-cargame-rg}"
LOCATION="${LOCATION:-swedencentral}"
APP_NAME="${APP_NAME:-cargame}"
ACR_NAME="${APP_NAME}acr"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"

if [[ ! "$APP_NAME" =~ ^[a-z0-9]{2,47}$ ]]; then
  echo "APP_NAME must be 2-47 lowercase letters/numbers so the ACR name is valid: ${ACR_NAME}" >&2
  exit 1
fi

echo "=== Deploying Car Game to Azure Container Apps ==="

# Create resource group
echo "Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Create ACR before the app deployment so the images can be pushed first.
if ! az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
  echo "Creating Azure Container Registry..."
  az acr create \
    --name "$ACR_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Basic \
    --admin-enabled true \
    --output none
fi

ACR_SERVER=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer --output tsv)
GAME_SERVER_IMAGE="$ACR_SERVER/${APP_NAME}-gameserver:$IMAGE_TAG"
FRONTEND_IMAGE="$ACR_SERVER/${APP_NAME}-frontend:$IMAGE_TAG"

echo "ACR: $ACR_SERVER"
echo "Image tag: $IMAGE_TAG"

# Login to ACR
echo "Logging into ACR..."
az acr login --name "$ACR_NAME"

# Build and push images
echo "Building game server image..."
docker build -f "$REPO_ROOT/Dockerfile.gameserver" -t "$GAME_SERVER_IMAGE" "$REPO_ROOT"
docker push "$GAME_SERVER_IMAGE"

echo "Building frontend image..."
docker build -f "$REPO_ROOT/Dockerfile.frontend" -t "$FRONTEND_IMAGE" "$REPO_ROOT"
docker push "$FRONTEND_IMAGE"

# Deploy infrastructure and point Container Apps at images that now exist.
echo "Deploying infrastructure (Bicep)..."
DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$SCRIPT_DIR/main.bicep" \
  --parameters appName="$APP_NAME" gameServerImage="$GAME_SERVER_IMAGE" frontendImage="$FRONTEND_IMAGE" \
  --query "properties.outputs" \
  --output json)

FRONTEND_URL=$(echo "$DEPLOY_OUTPUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['frontendUrl']['value'])")

echo ""
echo "=== Deployment complete ==="
echo "Frontend URL: $FRONTEND_URL"
echo ""
