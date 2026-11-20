import crypto from 'node:crypto';
import { config } from '../config.js';
import { handleAgentResponse, rejectAllPending, sendAgentRequest } from './rpc.js';
import { handleAgentAck } from './uploads.js';
import { agentEvents } from './events.js';

let activeAgentSocket = null;
const failedAttemptsByIp = new Map();

function isRateLimited(ip) {
  const record = failedAttemptsByIp.get(ip);
  if (!record) return false;
  const now = Date.now();
  if (now > record.resetTime) {
    failedAttemptsByIp.delete(ip);
    return false;
  }
  return record.count >= 5;
}

function recordFailure(ip) {
  const now = Date.now();
  let record = failedAttemptsByIp.get(ip);
  if (!record || now > record.resetTime) {
    record = { count: 1, resetTime: now + 15 * 60 * 1000 };
  } else {
    record.count += 1;
  }
  failedAttemptsByIp.set(ip, record);
}

export function isAgentConnected() {
  return Boolean(activeAgentSocket && activeAgentSocket.readyState === activeAgentSocket.OPEN);
}

export function getAgentSocket() {
  return activeAgentSocket;
}

export function requestAgent(action, userId, guildId = null, params = {}) {
  return sendAgentRequest(activeAgentSocket, action, userId, guildId, params);
}

export async function handleAgentConnection(ws, req) {
  const clientIp = req.socket.remoteAddress;

  if (isRateLimited(clientIp)) {
    ws.close(4401, 'Too many failed handshake attempts');
    return;
  }

  let authenticated = false;
  let pingTimer = null;
  let pongReceived = true;

  // Handshake timeout (10s)
  const handshakeTimer = setTimeout(() => {
    if (!authenticated) {
      recordFailure(clientIp);
      ws.close(4401, 'Handshake timeout');
    }
  }, 10000);

  let agentNonce = null;
  let serverNonce = null;

  ws.on('message', async (data, isBinary) => {
    if (isBinary) {
      if (!authenticated) {
        ws.close(4401, 'Unauthorized');
        return;
      }
      // Binary frames for upload are handled by uploads module / agent socket listener
      return;
    }

    let msg;
    try {
      msg = JSON.parse(data.toString('utf-8'));
    } catch (_) {
      ws.close(4400, 'Invalid JSON');
      return;
    }

    if (!authenticated) {
      // Step 1: Agent sent hello
      if (msg.t === 'hello') {
        if (!msg.agentNonce || typeof msg.agentNonce !== 'string') {
          ws.close(4400, 'Missing agentNonce');
          return;
        }
        agentNonce = msg.agentNonce;
        serverNonce = crypto.randomBytes(16).toString('hex');

        // serverProof: HMAC(secret, "server:" + agentNonce)
        const serverProof = crypto.createHmac('sha256', config.AGENT_SECRET)
          .update(`server:${agentNonce}`)
          .digest('hex');

        ws.send(JSON.stringify({
          t: 'challenge',
          serverNonce,
          serverProof
        }));
        return;
      }

      // Step 3: Agent sent auth
      if (msg.t === 'auth') {
        if (!msg.agentProof || !serverNonce) {
          recordFailure(clientIp);
          ws.close(4401, 'Handshake protocol error');
          return;
        }

        const expectedAgentProof = crypto.createHmac('sha256', config.AGENT_SECRET)
          .update(`agent:${serverNonce}`)
          .digest('hex');

        const isMatch = crypto.timingSafeEqual(
          Buffer.from(msg.agentProof, 'utf-8'),
          Buffer.from(expectedAgentProof, 'utf-8')
        );

        if (!isMatch) {
          recordFailure(clientIp);
          ws.close(4401, 'Invalid agent credentials');
          return;
        }

        // Authentication succeeded
        authenticated = true;
        clearTimeout(handshakeTimer);
        console.log('Bot agent authenticated successfully via HMAC challenge handshake.');

        // Replace existing agent connection if one exists
        if (activeAgentSocket && activeAgentSocket !== ws) {
          try {
            activeAgentSocket.close(1000, 'Replaced by new agent connection');
          } catch (_) {}
          rejectAllPending('Replaced by new agent connection');
        }

        activeAgentSocket = ws;
        ws.send(JSON.stringify({ t: 'ready' }));

        // Start ping/pong heartbeat
        pingTimer = setInterval(() => {
          if (!pongReceived) {
            ws.terminate();
            return;
          }
          pongReceived = false;
          ws.ping();
        }, 25000);

        return;
      }

      // Any other message before authentication is rejected
      ws.close(4401, 'Unauthorized');
      return;
    }

    // Authenticated message handling
    if (msg.t === 'res') {
      handleAgentResponse(msg);
    } else if (msg.t === 'ack') {
      handleAgentAck(msg);
    } else if (msg.t === 'evt') {
      agentEvents.emit('event', msg);
      if (msg.kind) {
        agentEvents.emit(msg.kind, msg);
      }
    }
  });

  ws.on('pong', () => {
    pongReceived = true;
  });

  const cleanup = () => {
    clearTimeout(handshakeTimer);
    if (pingTimer) clearInterval(pingTimer);
    if (activeAgentSocket === ws) {
      activeAgentSocket = null;
      rejectAllPending('Agent disconnected');
      agentEvents.emit('lifecycle', {
        t: 'evt',
        kind: 'lifecycle',
        guildId: null,
        data: { state: 'disconnected' }
      });
    }
  };

  ws.on('close', cleanup);
  ws.on('error', cleanup);
}
