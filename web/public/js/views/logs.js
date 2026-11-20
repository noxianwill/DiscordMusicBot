import { api } from '../api.js';
import { escapeHtml } from '../ui.js';

export async function render(container, state) {
  if (!state.me?.isOwner) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem;">
        <h2 style="color: var(--danger);">Owner Access Required</h2>
        <p style="color: var(--text-muted);">Only bot owners can inspect operational logs.</p>
      </div>
    `;
    return;
  }

  let autoRefresh = true;
  let timer = null;

  container.innerHTML = `
    <div class="card">
      <div class="card-title">
        <span>Bot Logs</span>
        <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
          <select id="log-lines-select" class="form-select" style="width: auto; padding: 0.25rem 0.5rem; font-size: 12px;">
            <option value="200" selected>200 lines</option>
            <option value="500">500 lines</option>
            <option value="1000">1000 lines</option>
          </select>

          <select id="log-level-select" class="form-select" style="width: auto; padding: 0.25rem 0.5rem; font-size: 12px;">
            <option value="" selected>All Levels</option>
            <option value="INFO">INFO</option>
            <option value="DEBUG">DEBUG</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>

          <label style="display: flex; align-items: center; gap: 0.35rem; font-size: 12px; color: var(--text-muted); cursor: pointer;">
            <input type="checkbox" id="chk-auto-refresh" checked> Auto-refresh
          </label>

          <button id="btn-refresh-logs" class="btn btn-sm">&#8635; Refresh</button>
        </div>
      </div>

      <div id="log-display" class="log-viewer">Loading logs...</div>
    </div>
  `;

  const logDisplay = container.querySelector('#log-display');
  const linesSelect = container.querySelector('#log-lines-select');
  const levelSelect = container.querySelector('#log-level-select');
  const chkAuto = container.querySelector('#chk-auto-refresh');
  const btnRefresh = container.querySelector('#btn-refresh-logs');

  async function fetchLogs() {
    const lines = Number(linesSelect.value);
    const level = levelSelect.value || undefined;

    try {
      const data = await api.rpc('logs.tail', null, { lines, level });
      const rawLines = data.lines || [];

      const wasAtBottom = logDisplay.scrollHeight - logDisplay.scrollTop <= logDisplay.clientHeight + 40;

      if (rawLines.length === 0) {
        logDisplay.textContent = 'No log entries found.';
      } else {
        logDisplay.textContent = rawLines.join('\n');
      }

      if (wasAtBottom) {
        logDisplay.scrollTop = logDisplay.scrollHeight;
      }
    } catch (err) {
      logDisplay.textContent = `Error loading logs: ${err.message}`;
    }
  }

  btnRefresh.onclick = fetchLogs;
  linesSelect.onchange = fetchLogs;
  levelSelect.onchange = fetchLogs;

  chkAuto.onchange = () => {
    autoRefresh = chkAuto.checked;
    if (autoRefresh) {
      if (!timer) timer = setInterval(fetchLogs, 3000);
    } else {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }
  };

  await fetchLogs();
  timer = setInterval(fetchLogs, 3000);

  return () => {
    if (timer) clearInterval(timer);
  };
}

