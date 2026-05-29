const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const GAME_SERVER = process.env.GAME_SERVER_URL || 'http://localhost:8765';

// Proxy API calls to game server (BEFORE static files)
const apiProxy = createProxyMiddleware({
  target: GAME_SERVER,
  changeOrigin: true,
  pathFilter: '/api',
});
app.use(apiProxy);

// Proxy WebSocket connections to game server
const wsProxy = createProxyMiddleware({
  target: GAME_SERVER,
  changeOrigin: true,
  pathFilter: '/ws',
  ws: true,
});
app.use(wsProxy);

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const server = app.listen(PORT, () => {
  console.log(`Frontend server running on http://localhost:${PORT}`);
  console.log(`Proxying game server at ${GAME_SERVER}`);
});

// Handle WebSocket upgrade
server.on('upgrade', (req, socket, head) => {
  wsProxy.upgrade(req, socket, head);
});
