const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const GAME_SERVER = process.env.GAME_SERVER_URL || 'http://localhost:8765';

// Derive WebSocket target from HTTP target
const WS_TARGET = GAME_SERVER.replace(/^http/, 'ws');

// Proxy API calls to game server (BEFORE static files)
app.use('/api', createProxyMiddleware({
  target: GAME_SERVER,
  changeOrigin: true,
}));

// Proxy WebSocket connections to game server
const wsProxy = createProxyMiddleware({
  target: WS_TARGET,
  changeOrigin: true,
  ws: true,
  // Required for ACA: prevent proxy from buffering and allow raw WebSocket frames
  onProxyReqWs: (proxyReq, req, socket, options, head) => {
    // Keep connection alive through ACA's load balancer
    proxyReq.setHeader('Connection', 'Upgrade');
    proxyReq.setHeader('Upgrade', 'websocket');
  },
  // Log proxy errors for debugging
  onError: (err, req, res) => {
    console.error('[WS Proxy] Error:', err.message);
  },
});
app.use('/ws', wsProxy);

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const server = app.listen(PORT, () => {
  console.log(`Frontend server running on http://localhost:${PORT}`);
  console.log(`Proxying game server at ${GAME_SERVER}`);
  console.log(`WebSocket target: ${WS_TARGET}`);
});

// Explicitly handle WebSocket upgrade at the HTTP server level
// This is critical for Azure Container Apps where the upgrade
// must be handled before Express middleware times out
server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/ws')) {
    wsProxy.upgrade(req, socket, head);
  } else {
    socket.destroy();
  }
});
