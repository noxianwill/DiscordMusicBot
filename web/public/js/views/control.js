import { api } from '../api.js';
import { escapeHtml, formatDuration, showToast, confirmDialog } from '../ui.js';
import { addWsListener, isWsConnected } from '../ws.js';

export async function render(container, state) {
  if (!state.me?.isOwner) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem;">
        <h2 style="color: var(--danger); margin-bottom: 0.5rem;">Owner Access Required</h2>
        <p style="color: var(--text-muted);">Only bot owners can control the bot process lifecycle.</p>
      </div>
    `;
    return;
  }

  let statusData = null;
  let timer = null;

  container.innerHTML = `
    <div style="max-width: 860px; margin: 0 auto;">
      <!-- Bot Lifecycle Card -->
      <div class="card">
        <div class="card-title">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
            <span>Bot Process Supervisor</span>
          </div>
          <a href="#logs" class="btn btn-sm" style="font-size: 12px;">View Logs &rarr;</a>
        </div>
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 1.5rem;">
          Direct supervisor controls to start, stop, and restart the child Python process. Restarts track all manual and supervisor-triggered reloads.
        </p>

        <div id="status-card" style="margin-bottom: 1.5rem;">
          <p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">Loading supervisor status...</p>
        </div>

        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; padding-top: 0.5rem; border-top: 1px solid var(--border);">
          <button id="btn-start-bot" class="btn btn-primary">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            Start Bot
          </button>
          <button id="btn-restart-bot" class="btn">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
            Restart Bot
          </button>
          <button id="btn-stop-bot" class="btn btn-danger">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>
            Stop Bot (Process)
          </button>
        </div>
      </div>
    </div>
  `;

  const statusCard = container.querySelector('#status-card');
  const btnStart = container.querySelector('#btn-start-bot');
  const btnRestart = container.querySelector('#btn-restart-bot');
  const btnStop = container.querySelector('#btn-stop-bot');

  async function loadStatus() {
    try {
      statusData = await api.rpc('bot.status');
      renderStatus();
    } catch (_) {}
  }

  function renderStatus() {
    if (!statusData) return;
    const { state: botState, pid, startedAt, restarts, lastExit, version } = statusData;

    const uptimeStr = startedAt ? formatDuration(Math.floor(Date.now() / 1000 - startedAt)) : 'N/A';

    let badgeClass = 'badge-stopped';
    let statusGlow = '#80848e';
    if (botState === 'running') {
      badgeClass = 'badge-online';
      statusGlow = '#23a55a';
    } else if (botState === 'starting') {
      badgeClass = 'badge-starting';
      statusGlow = '#f0b232';
    } else if (botState === 'crashed') {
      badgeClass = 'badge-crashed';
      statusGlow = '#da373c';
    }

    statusCard.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem;">
        <div style="background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.06); padding: 1.15rem; border-radius: var(--radius);">
          <div style="color: var(--text-muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;">Status</div>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="width: 8px; height: 8px; border-radius: 50%; background: ${statusGlow}; box-shadow: 0 0 8px ${statusGlow};"></span>
            <span class="badge ${badgeClass}" style="font-size: 11px;">${escapeHtml(botState)}</span>
          </div>
        </div>

        <div style="background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.06); padding: 1.15rem; border-radius: var(--radius);">
          <div style="color: var(--text-muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;">Process PID</div>
          <div style="font-size: 18px; font-weight: 700; color: var(--text-bright); font-family: var(--font-mono);">${pid ? `#${pid}` : '<span style="color: var(--text-muted); font-weight: 400; font-size: 14px;">None</span>'}</div>
        </div>

        <div style="background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.06); padding: 1.15rem; border-radius: var(--radius);">
          <div style="color: var(--text-muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;">Uptime</div>
          <div style="font-size: 18px; font-weight: 700; color: var(--text-bright);">${uptimeStr}</div>
        </div>

        <div style="background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.06); padding: 1.15rem; border-radius: var(--radius);">
          <div style="color: var(--text-muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;">Restarts</div>
          <div style="font-size: 18px; font-weight: 700; color: var(--text-bright); display: flex; align-items: baseline; gap: 0.35rem;">
            <span>${restarts || 0}</span>
            <span style="font-size: 11px; font-weight: 400; color: var(--text-muted);">reloads</span>
          </div>
        </div>
      </div>

      ${lastExit ? `
        <div style="margin-top: 1rem; font-size: 12px; color: var(--text-muted); background: rgba(0, 0, 0, 0.15); padding: 0.6rem 0.85rem; border-radius: 6px;">
          Previous exit: return code ${lastExit.code} (${formatDuration(lastExit.uptime)} uptime)
        </div>
      ` : ''}
    `;

    btnStart.disabled = (botState === 'running' || botState === 'starting');
    btnStop.disabled = (botState === 'stopped');
    btnRestart.disabled = (botState === 'starting');
  }

  btnStart.onclick = async () => {
    btnStart.disabled = true;
    try {
      await api.rpc('bot.start');
      showToast('Bot start command issued', 'info');
      await loadStatus();
    } catch (_) {
      btnStart.disabled = false;
    }
  };

  btnStop.onclick = async () => {
    const confirmed = await confirmDialog(
      'Are you sure you want to stop the Discord bot process? The bot will go offline until started again.',
      'Stop Bot Process',
      true
    );
    if (!confirmed) return;

    btnStop.disabled = true;
    try {
      await api.rpc('bot.stop');
      showToast('Bot stopped', 'info');
      await loadStatus();
    } catch (_) {
      btnStop.disabled = false;
    }
  };

  btnRestart.onclick = async () => {
    const confirmed = await confirmDialog(
      'Restart the Discord bot process? Ongoing playback will briefly stop.',
      'Restart Bot'
    );
    if (!confirmed) return;

    btnRestart.disabled = true;
    try {
      await api.rpc('bot.restart');
      showToast('Bot restarting...', 'info');
      await loadStatus();
    } catch (_) {
      btnRestart.disabled = false;
    }
  };

  const unsubscribeWs = addWsListener((evt) => {
    if (evt.kind === 'lifecycle') {
      loadStatus();
    } else if (evt.kind === 'ws_connected') {
      loadStatus();
    }
  });

  const onVisibilityChange = () => {
    if (!document.hidden) loadStatus();
  };
  document.addEventListener('visibilitychange', onVisibilityChange);

  await loadStatus();
  timer = setInterval(() => {
    if (!isWsConnected() && !document.hidden) {
      loadStatus();
    }
  }, 10000);

  return () => {
    if (timer) clearInterval(timer);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    unsubscribeWs();
  };
}

