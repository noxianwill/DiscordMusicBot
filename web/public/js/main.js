import { api, setCsrfToken } from './api.js';
import { escapeHtml, formatDuration } from './ui.js';
import { registerRoute, handleRouteChange, navigate } from './router.js';
import { connectWebSocket, addWsListener } from './ws.js';

import * as ViewLogin from './views/login.js';
import * as ViewSetup from './views/setup.js';
import * as ViewNoAccess from './views/noaccess.js';
import * as ViewDashboard from './views/dashboard.js';
import * as ViewPlaylists from './views/playlists.js';
import * as ViewCookies from './views/cookies.js';
import * as ViewControl from './views/control.js';
import * as ViewSettings from './views/settings.js';
import * as ViewLogs from './views/logs.js';
import * as ViewLive from './views/live.js';

registerRoute('#login', ViewLogin);
registerRoute('#setup', ViewSetup);
registerRoute('#no-access', ViewNoAccess);
registerRoute('#dashboard', ViewDashboard);
registerRoute('#playlists', ViewPlaylists);
registerRoute('#cookies', ViewCookies);
registerRoute('#control', ViewControl);
registerRoute('#settings', ViewSettings);
registerRoute('#logs', ViewLogs);
registerRoute('#live', ViewLive);

const appState = {
  status: null,
  me: null,
  user: null
};

async function init() {
  try {
    appState.status = await api.get('/api/status');
  } catch (_) {
    appState.status = { oauthConfigured: false, agentConnected: false };
  }

  try {
    const meRes = await api.get('/api/me');
    appState.me = meRes;
    appState.user = meRes.user;
    if (meRes.csrfToken) {
      setCsrfToken(meRes.csrfToken);
    }
  } catch (err) {
    appState.user = null;
  }

  const currentHash = location.hash.split('?')[0];

  if (!appState.user) {
    if (currentHash !== '#setup' && currentHash !== '#login' && currentHash !== '#live') {
      location.hash = '#login';
    }
  } else {
    if (currentHash === '#login' || currentHash === '#setup' || !currentHash) {
      location.hash = '#dashboard';
    }
  }

  renderShell();
  await handleRouteChange(appState);
  window.addEventListener('hashchange', () => handleRouteChange(appState));

  if (appState.user) {
    connectWebSocket();
    addWsListener((evt) => {
      if (evt.kind === 'ping' && evt.data?.latencyMs !== undefined) {
        updateDiscordLatency(evt.data.latencyMs);
      } else if (evt.kind === 'web_ping' && evt.data?.rttMs !== undefined) {
        updateWebLatency(evt.data.rttMs);
      } else if (evt.kind === 'lifecycle') {
        const badge = document.getElementById('header-bot-badge');
        const discordBadge = document.getElementById('header-discord-latency');
        if (badge && evt.data?.state) {
          badge.className = `badge badge-${evt.data.state === 'running' ? 'online' : (evt.data.state === 'starting' ? 'starting' : 'stopped')}`;
          badge.textContent = evt.data.state;
          if (discordBadge) {
            discordBadge.style.display = evt.data.state === 'running' ? 'inline-flex' : 'none';
          }
        }
      }
    });
  }
}

function applyLatencyStyle(elBadge, val) {
  if (val < 100) {
    elBadge.style.background = 'rgba(87, 242, 135, 0.15)';
    elBadge.style.color = 'var(--success)';
  } else if (val < 200) {
    elBadge.style.background = 'rgba(240, 178, 50, 0.15)';
    elBadge.style.color = 'var(--warning)';
  } else {
    elBadge.style.background = 'rgba(218, 55, 60, 0.15)';
    elBadge.style.color = 'var(--danger)';
  }
}

function updateDiscordLatency(ms) {
  const elBadge = document.getElementById('header-discord-latency');
  const elVal = document.getElementById('header-discord-lat-val');
  if (!elBadge || !elVal) return;

  if (ms === null || ms === undefined || isNaN(ms)) {
    elVal.textContent = '--';
    return;
  }

  const val = Math.round(ms);
  elVal.textContent = String(val);
  elBadge.style.display = 'inline-flex';
  applyLatencyStyle(elBadge, val);
}

function updateWebLatency(ms) {
  const elBadge = document.getElementById('header-web-latency');
  const elVal = document.getElementById('header-web-lat-val');
  if (!elBadge || !elVal) return;

  if (ms === null || ms === undefined || isNaN(ms)) {
    elVal.textContent = '--';
    return;
  }

  const val = Math.round(ms);
  elVal.textContent = String(val);
  elBadge.style.display = 'inline-flex';
  applyLatencyStyle(elBadge, val);
}

function renderShell() {
  const appRoot = document.getElementById('app');
  if (!appState.user) {
    appRoot.innerHTML = '<main id="view-container" class="main-content"></main>';
    return;
  }

  const user = appState.user;
  const bot = appState.me?.bot;
  const botStatus = appState.me?.botStatus;
  const isOwner = Boolean(appState.me?.isOwner);

  const botName = bot?.name || 'DiscordMusicBot';
  const botAvatar = bot?.avatar || 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzMxMzM4Ii8+PC9zdmc+';
  const botState = botStatus?.state || (appState.me?.agentConnected ? 'running' : 'stopped');
  const botLatency = appState.me?.bot?.latencyMs ?? appState.me?.latencyMs ?? null;
  const initialLat = botLatency !== null && !isNaN(botLatency) ? Math.round(botLatency) : null;

  let stateBadgeClass = 'badge-stopped';
  if (botState === 'running') stateBadgeClass = 'badge-online';
  else if (botState === 'starting') stateBadgeClass = 'badge-starting';
  else if (botState === 'crashed') stateBadgeClass = 'badge-crashed';

  appRoot.innerHTML = `
    <div class="app-layout">
      <!-- Left Sidebar Navigation -->
      <aside class="sidebar">
        <!-- Brand Header -->
        <div class="sidebar-brand">
          <div class="bot-avatar-wrap">
            <img src="${botAvatar}" class="bot-avatar" alt="Bot Avatar">
            <span class="status-indicator status-${botState}"></span>
          </div>
          <div class="bot-info-wrap">
            <div class="bot-name" title="${escapeHtml(botName)}">${escapeHtml(botName)}</div>
            <div class="bot-meta" style="flex-wrap: wrap; gap: 4px;">
              <span id="header-bot-badge" class="badge ${stateBadgeClass}">${escapeHtml(botState)}</span>
              <span style="font-size: 11px; color: var(--text-muted);">v${escapeHtml(bot?.version || '1.0.0')}</span>
            </div>
            <div class="header-latencies" style="display: flex; align-items: center; gap: 5px; margin-top: 4px; flex-wrap: wrap;">
              <span id="header-discord-latency" class="badge" style="font-size: 10px; font-weight: 600; padding: 1.5px 5.5px; border-radius: 4px; display: ${botState === 'running' ? 'inline-flex' : 'none'}; align-items: center; gap: 3.5px; background: rgba(87, 242, 135, 0.15); color: var(--success); cursor: help;" title="Bot ⟷ Discord: Heartbeat latency between the bot and Discord voice servers">
                <span style="display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: currentColor;"></span>
                <span>Bot: <strong id="header-discord-lat-val">${initialLat !== null ? initialLat : '--'}</strong>ms</span>
              </span>
              <span id="header-web-latency" class="badge" style="font-size: 10px; font-weight: 600; padding: 1.5px 5.5px; border-radius: 4px; display: inline-flex; align-items: center; gap: 3.5px; background: rgba(88, 101, 242, 0.15); color: #a5b3f7; cursor: help;" title="You ⟷ Web UI: Live round-trip ping between your browser and this web panel">
                <span style="display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: currentColor;"></span>
                <span>You: <strong id="header-web-lat-val">--</strong>ms</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Sidebar Navigation Menu -->
        <nav class="sidebar-nav">
          <div class="nav-section-title">MAIN MENU</div>
          <a href="#dashboard" class="nav-link">
            <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
            <span>Dashboard</span>
          </a>
          <a href="#playlists" class="nav-link">
            <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><polygon points="12 11 12 17 17 14"></polygon></svg>
            <span>Local Playlists</span>
          </a>

          ${isOwner ? `
            <div class="nav-section-title" style="margin-top: 1.5rem;">ADMINISTRATION</div>
            <a href="#cookies" class="nav-link">
              <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><circle cx="8" cy="9" r="1" fill="currentColor"></circle><circle cx="15" cy="10" r="1" fill="currentColor"></circle><circle cx="10" cy="15" r="1" fill="currentColor"></circle><circle cx="16" cy="15" r="1" fill="currentColor"></circle></svg>
              <span>YouTube Cookies</span>
            </a>
            <a href="#control" class="nav-link">
              <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
              <span>Bot Control</span>
            </a>
            <a href="#settings" class="nav-link">
              <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="3" r="1"></circle><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"></path><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
              <span>Settings</span>
            </a>
            <a href="#logs" class="nav-link">
              <svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
              <span>Logs</span>
            </a>
          ` : ''}
        </nav>

        <!-- User Profile & Log Out Footer -->
        <div class="sidebar-user">
          <div style="display: flex; align-items: center; gap: 0.65rem; min-width: 0; flex: 1;">
            ${user.avatarUrl ? `<img src="${escapeHtml(user.avatarUrl)}" class="avatar-sm" alt="User Avatar">` : '<div class="avatar-sm" style="background: var(--accent); display: flex; align-items: center; justify-content: center; font-weight: 600; color: #fff;">' + escapeHtml((user.globalName || user.username || 'U')[0].toUpperCase()) + '</div>'}
            <div style="min-width: 0; flex: 1;">
              <div style="font-weight: 600; color: var(--text-bright); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                ${escapeHtml(user.globalName || user.username)}
              </div>
              <div style="font-size: 11px; display: flex; align-items: center; gap: 0.35rem; margin-top: 1px;">
                ${isOwner ? '<span class="badge" style="background: rgba(88, 101, 242, 0.2); color: #a5b3f7; border: 1px solid rgba(88, 101, 242, 0.45); font-size: 9.5px; padding: 1px 5px;">OWNER</span>' : '<span style="color: var(--text-muted); font-size: 11px;">Member</span>'}
              </div>
            </div>
          </div>
          <button id="btn-logout" class="btn btn-sm btn-icon" title="Log Out" style="background: rgba(255, 255, 255, 0.06); padding: 6px 9px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
          </button>
        </div>
      </aside>

      <!-- Main Body Content Area -->
      <div class="main-wrapper">
        <main id="view-container" class="main-content"></main>

        <!-- Developer & Social Credits Footer -->
        <footer class="app-footer">
          <div class="footer-inner">
            <div class="footer-left">
              <div class="footer-brand">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="var(--accent)"/><path d="M10.5 7.5v9l6-4.5-6-4.5z" fill="#ffffff"/></svg>
                <span>Discord Music Bot</span>
              </div>
              <p class="footer-desc">High-performance self-hosted music bot with live Web UI controls.</p>
            </div>

            <div class="footer-right">
              <span class="social-label">Developed by NoxianWill</span>
              <div class="social-links">
                <a href="https://github.com/noxianwill" target="_blank" rel="noopener" class="social-btn" title="GitHub (@noxianwill)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
                </a>
                <a href="https://x.com/walidbouachir" target="_blank" rel="noopener" class="social-btn" title="Twitter / X (@walidbouachir)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                </a>
                <a href="https://www.youtube.com/@NoxianWill" target="_blank" rel="noopener" class="social-btn" title="YouTube (@NoxianWill)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                </a>
                <a href="https://www.twitch.tv/noxianwill" target="_blank" rel="noopener" class="social-btn" title="Twitch (noxianwill)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714z"/></svg>
                </a>
                <a href="https://www.instagram.com/bouachir.walid" target="_blank" rel="noopener" class="social-btn" title="Instagram (@bouachir.walid)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
                </a>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </div>
  `;

  document.getElementById('btn-logout').onclick = async () => {
    try {
      await api.post('/auth/logout', {});
    } catch (_) { }
    location.href = '/#login';
    location.reload();
  };
}

// Global unhandled error & promise rejection handlers
window.addEventListener('unhandledrejection', (event) => {
  // Avoid duplicate popups for errors already handled with toasts or expected 401s
  if (event.reason?.isNetworkError || event.reason?.status === 401) {
    event.preventDefault();
    return;
  }
  const msg = event.reason?.message || 'An unexpected error occurred';
  console.error('[Global Unhandled Rejection]', event.reason);
  showToast(msg, 'error');
});

window.addEventListener('error', (event) => {
  console.error('[Global Script Error]', event.error || event.message);
});

init();
