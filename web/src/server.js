import http from 'node:http';
import { WebSocketServer } from 'ws';
import { app } from './app.js';
import { config } from './config.js';
import { handleAgentConnection } from './agent/connection.js';
import { setupBrowserWebSocketServer } from './ws/browser.js';
import { getSessionFromCookieHeader } from './session.js';

const server = http.createServer(app);

const agentWss = new WebSocketServer({
  noServer: true,
  maxPayload: 2 * 1024 * 1024 // 2 MB limit
});

const browserWss = setupBrowserWebSocketServer();

const expectedOrigin = new URL(config.PUBLIC_URL).origin;

server.on('upgrade', async (req, socket, head) => {
  const url = new URL(req.url, `http://${req.headers.host || '127.0.0.1'}`);
  const pathname = url.pathname;

  if (pathname === '/agent') {
    agentWss.handleUpgrade(req, socket, head, (ws) => {
      handleAgentConnection(ws, req);
    });
    return;
  }

  if (pathname === '/ws') {
    // Origin check
    const origin = req.headers.origin;
    if (origin && origin !== expectedOrigin) {
      socket.write('HTTP/1.1 403 Forbidden\r\n\r\n');
      socket.destroy();
      return;
    }

    // Authenticate session from cookie
    const session = await getSessionFromCookieHeader(req.headers.cookie);
    if (!session || !session.user) {
      socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
      socket.destroy();
      return;
    }

    browserWss.handleUpgrade(req, socket, head, (ws) => {
      browserWss.emit('connection', ws, req, session);
    });
    return;
  }

  socket.write('HTTP/1.1 404 Not Found\r\n\r\n');
  socket.destroy();
});

server.listen(config.PORT, config.HOST, () => {
  console.log(`Web UI server listening on ${config.HOST}:${config.PORT} (PUBLIC_URL=${config.PUBLIC_URL})`);
});

const shutdown = () => {
  console.log('Shutting down Web UI server...');
  server.close(() => {
    console.log('Server stopped.');
    process.exit(0);
  });
};

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

