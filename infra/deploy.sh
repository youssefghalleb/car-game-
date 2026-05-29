#!/bin/bash
# Deploy script for Azure Container Apps
# Prerequisites: az CLI logged in, Docker installed

set -e

RESOURCE_GROUP="${RESOURCE_GROUP:-cargame-rg}"
LOCATION="${LOCATION:-westeurope}"
APP_NAME="${APP_NAME:-cargame}"

echo "=== Deploying Car Game to Azure Container Apps ==="

# Create resource group
echo "Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Deploy infrastructure
echo "Deploying infrastructure (Bicep)..."
DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters appName="$APP_NAME" \
  --query "properties.outputs" \
  --output json)

ACR_SERVER=$(echo "$DEPLOY_OUTPUT" | python -c "import json,sys; print(json.load(sys.stdin)['acrLoginServer']['value'])")
FRONTEND_URL=$(echo "$DEPLOY_OUTPUT" | python -c "import json,sys; print(json.load(sys.stdin)['frontendUrl']['value'])")

echo "ACR: $ACR_SERVER"

# Login to ACR
echo "Logging into ACR..."
az acr login --name "${APP_NAME}acr"

# Build and push images
echo "Building game server image..."
docker build -f Dockerfile.gameserver -t "$ACR_SERVER/${APP_NAME}-gameserver:latest" .
docker push "$ACR_SERVER/${APP_NAME}-gameserver:latest"

echo "Building frontend image..."
docker build -f Dockerfile.frontend -t "$ACR_SERVER/${APP_NAME}-frontend:latest" .
docker push "$ACR_SERVER/${APP_NAME}-frontend:latest"

# Update container apps with new images
echo "Updating container apps..."
az containerapp update \
  --name "${APP_NAME}-gameserver" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$ACR_SERVER/${APP_NAME}-gameserver:latest" \
  --output none

az containerapp update \
  --name "${APP_NAME}-frontend" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$ACR_SERVER/${APP_NAME}-frontend:latest" \
  --output none

echo ""
echo "=== Deployment complete ==="
echo "Frontend URL: $FRONTEND_URL"
echo ""
