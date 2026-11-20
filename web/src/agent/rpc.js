import crypto from 'node:crypto';

const pendingRequests = new Map();

const LONG_TIMEOUT_ACTIONS = new Set(['play', 'play.local', 'bot.start', 'bot.restart']);
const UPLOAD_END_TIMEOUT_ACTIONS = new Set(['upload.end']);

export function getTimeoutForAction(action) {
  if (UPLOAD_END_TIMEOUT_ACTIONS.has(action)) return 120000;
  if (LONG_TIMEOUT_ACTIONS.has(action)) return 60000;
  return 10000;
}

export function sendAgentRequest(ws, action, userId, guildId, params = {}, customTimeout = null) {
  return new Promise((resolve, reject) => {
    if (!ws || ws.readyState !== ws.OPEN) {
      const err = new Error('Bot agent is not connected');
      err.code = 'BOT_OFFLINE';
      return reject(err);
    }

    const id = crypto.randomUUID();
    const timeoutMs = customTimeout || getTimeoutForAction(action);

    const timeoutId = setTimeout(() => {
      pendingRequests.delete(id);
      const err = new Error(`Request timed out after ${timeoutMs}ms`);
      err.code = 'TIMEOUT';
      reject(err);
    }, timeoutMs);

    pendingRequests.set(id, { resolve, reject, timeoutId });

    const msg = {
      t: 'req',
      id,
      userId: String(userId),
      action,
      guildId: guildId ? String(guildId) : null,
      params
    };

    try {
      ws.send(JSON.stringify(msg));
    } catch (err) {
      clearTimeout(timeoutId);
      pendingRequests.delete(id);
      reject(err);
    }
  });
}

export function handleAgentResponse(msg) {
  const { id } = msg;
  if (!id || !pendingRequests.has(id)) return;

  const { resolve, reject, timeoutId } = pendingRequests.get(id);
  clearTimeout(timeoutId);
  pendingRequests.delete(id);

  if (msg.ok) {
    resolve(msg.data);
  } else {
    const err = new Error(msg.error || 'Agent request failed');
    err.code = msg.code || 'INTERNAL';
    reject(err);
  }
}

export function rejectAllPending(reason = 'Agent disconnected') {
  for (const [id, { reject, timeoutId }] of pendingRequests.entries()) {
    clearTimeout(timeoutId);
    const err = new Error(reason);
    err.code = 'BOT_OFFLINE';
    reject(err);
  }
  pendingRequests.clear();
}

