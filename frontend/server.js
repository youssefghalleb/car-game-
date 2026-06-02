const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const GAME_SERVER = process.env.GAME_SERVER_URL || 'http://localhost:8765';
const PUBLIC_GAME_SERVER_WS_URL = process.env.PUBLIC_GAME_SERVER_WS_URL || '';

// Derive WebSocket target from HTTP target
const WS_TARGET = GAME_SERVER.replace(/^http/, 'ws');

app.get('/api/config', (_req, res) => {
  res.json({
    gameServerWsUrl: PUBLIC_GAME_SERVER_WS_URL,
  });
});

// Proxy API calls to game server (BEFORE static files)
app.use('/api', createProxyMiddleware({
  target: GAME_SERVER,
  changeOrigin: true,
  pathRewrite: (path) => `/api${path}`,
}));

// Proxy WebSocket connections to game server
const wsProxy = createProxyMiddleware({
  target: WS_TARGET,
  changeOrigin: true,
  ws: true,
  xfwd: true,
  timeout: 0,
  proxyTimeout: 0,
  on: {
    // http-proxy-middleware v3 exposes event hooks under the `on` option.
    proxyReqWs: (_proxyReq, req) => {
      console.log(`[WS Proxy] upgrade ${req.url} -> ${WS_TARGET}`);
    },
    error: (err, req) => {
      console.error('[WS Proxy] Error:', req?.url, err.message);
    },
    open: (_proxySocket) => {
      console.log('[WS Proxy] target socket opened');
    },
    close: (_res, socket) => {
      console.log(`[WS Proxy] socket closed destroyed=${socket?.destroyed ?? 'unknown'}`);
    },
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
