import { WebSocketServer } from 'ws';
import { config } from '../config.js';
import { getSessionFromCookieHeader } from '../session.js';
import { agentEvents } from '../agent/events.js';
import { requestAgent, isAgentConnected } from '../agent/connection.js';

export function setupBrowserWebSocketServer() {
  const wss = new WebSocketServer({ noServer: true });

  wss.on('connection', (ws, req, session) => {
    let subscribedGuildId = null;
    let isAlive = true;

    ws.on('pong', () => {
      isAlive = true;
    });

    const pingInterval = setInterval(() => {
      if (!isAlive) {
        ws.terminate();
        return;
      }
      isAlive = false;
      ws.ping();
    }, 30000);

    const onAgentEvent = (evt) => {
      if (!evt || !evt.kind) return;
      // Global events (lifecycle, downloads) broadcast to all authenticated browsers
      if (evt.kind === 'lifecycle' || evt.kind === 'download_progress' || !evt.guildId) {
        try {
          ws.send(JSON.stringify(evt));
        } catch (_) {}
        return;
      }

      // Guild-specific events (state, queue)
      if (subscribedGuildId && String(evt.guildId) === String(subscribedGuildId)) {
        try {
          ws.send(JSON.stringify(evt));
        } catch (_) {}
      }
    };

    agentEvents.on('event', onAgentEvent);

    ws.on('message', async (data) => {
      try {
        const msg = JSON.parse(data.toString('utf-8'));
        if (msg.t === 'ping') {
          ws.send(JSON.stringify({ t: 'pong', echo: msg.echo }));
          return;
        }
        if (msg.sub) {
          const requestedGuildId = String(msg.sub);
          // Verify user access via me call
          if (isAgentConnected() && session.user?.id) {
            try {
              const meData = await requestAgent('me', session.user.id, null, {});
              const allowedGuild = meData.isOwner || (meData.guilds || []).some(g => String(g.id) === requestedGuildId);
              if (allowedGuild) {
                subscribedGuildId = requestedGuildId;
                ws.send(JSON.stringify({ t: 'subscribed', guildId: subscribedGuildId }));
              } else {
                ws.send(JSON.stringify({ t: 'error', error: 'Forbidden guild subscription' }));
              }
            } catch (_) {
              subscribedGuildId = requestedGuildId;
              ws.send(JSON.stringify({ t: 'subscribed', guildId: subscribedGuildId }));
            }
          } else {
            subscribedGuildId = requestedGuildId;
            ws.send(JSON.stringify({ t: 'subscribed', guildId: subscribedGuildId }));
          }
        }
      } catch (_) {}
    });

    const cleanup = () => {
      clearInterval(pingInterval);
      agentEvents.off('event', onAgentEvent);
    };

    ws.on('close', cleanup);
    ws.on('error', cleanup);
  });

  return wss;
}

