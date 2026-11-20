let ws = null;
let currentGuildId = null;
const listeners = new Set();
let reconnectTimer = null;
let webPingTimer = null;
let backoff = 1000;

function sendWebPing() {
  if (ws && ws.readyState === WebSocket.OPEN && !document.hidden) {
    try {
      ws.send(JSON.stringify({ t: 'ping', echo: performance.now() }));
    } catch (_) {}
  }
}

export function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws`;

  try {
    ws = new WebSocket(url);
  } catch (err) {
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    backoff = 1000;
    if (currentGuildId) {
      subscribeToGuild(currentGuildId);
    }
    for (const fn of listeners) {
      try { fn({ kind: 'ws_connected' }); } catch (_) {}
    }
    sendWebPing();
    if (webPingTimer) clearInterval(webPingTimer);
    webPingTimer = setInterval(sendWebPing, 5000);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && data.t === 'pong') {
        const rtt = Math.max(1, Math.round(performance.now() - (data.echo || performance.now())));
        for (const fn of listeners) {
          try { fn({ kind: 'web_ping', data: { rttMs: rtt } }); } catch (_) {}
        }
        return;
      }
      for (const fn of listeners) {
        fn(data);
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    ws = null;
    if (webPingTimer) {
      clearInterval(webPingTimer);
      webPingTimer = null;
    }
    scheduleReconnect();
  };

  ws.onerror = () => {
    if (ws) ws.close();
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
    backoff = Math.min(backoff * 1.5, 10000);
  }, backoff);
}

export function subscribeToGuild(guildId) {
  currentGuildId = guildId;
  if (ws && ws.readyState === WebSocket.OPEN && currentGuildId) {
    ws.send(JSON.stringify({ sub: currentGuildId }));
  }
}

export function addWsListener(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

export function isWsConnected() {
  return Boolean(ws && ws.readyState === WebSocket.OPEN);
}

