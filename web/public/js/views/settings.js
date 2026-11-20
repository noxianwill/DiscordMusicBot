import { api } from '../api.js';
import { escapeHtml, showToast, confirmDialog } from '../ui.js';

export async function render(container, state) {
  if (!state.me?.isOwner) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem;">
        <h2 style="color: var(--danger);">Owner Access Required</h2>
        <p style="color: var(--text-muted);">Only bot owners can view or modify bot configuration.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.5rem;">
      <form id="settings-form" style="display: flex; flex-direction: column; gap: 1.5rem;">
        
        <!-- Restart Notification Banner (Shown after saving) -->
        <div id="settings-restart-banner" style="display: none; background: rgba(240, 178, 50, 0.12); border: 1px solid var(--warning); border-radius: var(--radius); padding: 1.1rem 1.35rem; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <span style="font-size: 22px;">⚠️</span>
            <div>
              <div style="font-weight: 600; color: #fff; font-size: 14px;">Settings saved successfully!</div>
              <div style="font-size: 12.5px; color: var(--text-muted); margin-top: 2px;">
                You must restart the bot process for configuration changes to take effect.
              </div>
            </div>
          </div>
          <button type="button" id="btn-quick-restart" class="btn btn-primary" style="background: var(--warning); color: #000; font-weight: 700; border: none; padding: 0.55rem 1.15rem;">
            🔄 Restart Bot Now
          </button>
        </div>

        <!-- Card 1: Playback & Voice -->
        <div class="card" style="margin: 0;">
          <div class="card-title" style="color: var(--accent); font-size: 14px; margin-bottom: 0.25rem;">
            Playback & Voice Channel
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem;">
            Default audio parameters and voice channel inactivity management.
          </p>

          <div class="grid-2">
            <div class="form-group">
              <label class="form-label" for="s_DEFAULT_VOLUME">Default Volume (0-100)</label>
              <input type="number" id="s_DEFAULT_VOLUME" class="form-control" min="0" max="100">
              <small style="color: var(--text-muted); font-size: 11px;">Starting volume level when the bot joins voice</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOOP_MODE">Default Loop Mode</label>
              <select id="s_LOOP_MODE" class="form-select">
                <option value="off">Off</option>
                <option value="track">Track (repeat single song)</option>
                <option value="queue">Queue (repeat whole queue)</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_MAX_QUEUE_SIZE">Max Queue Size</label>
              <input type="number" id="s_MAX_QUEUE_SIZE" class="form-control" min="1" max="1000">
              <small style="color: var(--text-muted); font-size: 11px;">Maximum tracks allowed in the playback queue</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_MAX_HISTORY_SIZE">Max History Size</label>
              <input type="number" id="s_MAX_HISTORY_SIZE" class="form-control" min="1" max="1000">
              <small style="color: var(--text-muted); font-size: 11px;">Maximum past tracks retained in history</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_AUTO_LEAVE">Auto Leave When Alone</label>
              <select id="s_AUTO_LEAVE" class="form-select">
                <option value="true">True (leave voice when alone)</option>
                <option value="false">False (remain connected)</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_AUTO_LEAVE_DELAY">Auto Leave Delay (seconds)</label>
              <input type="number" id="s_AUTO_LEAVE_DELAY" class="form-control" min="0" max="86400">
              <small style="color: var(--text-muted); font-size: 11px;">Seconds to wait before auto-leaving (default: 300 = 5m)</small>
            </div>
          </div>
        </div>

        <!-- Card 2: Discord & Presence -->
        <div class="card" style="margin: 0;">
          <div class="card-title" style="color: #57f287; font-size: 14px; margin-bottom: 0.25rem;">
            Discord Presence & Commands
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem;">
            Prefixes, restricted channels, and custom presence status templates.
          </p>

          <div class="grid-2">
            <div class="form-group">
              <label class="form-label" for="s_COMMAND_PREFIX">Command Prefix</label>
              <input type="text" id="s_COMMAND_PREFIX" class="form-control" placeholder="!">
              <small style="color: var(--text-muted); font-size: 11px;">Prefix for legacy text commands (e.g. !play)</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_DISCORD_COMMAND_CHANNEL_ID">Dedicated Command Channel ID</label>
              <input type="text" id="s_DISCORD_COMMAND_CHANNEL_ID" class="form-control" placeholder="Leave empty for all channels">
              <small style="color: var(--text-muted); font-size: 11px;">Restricts bot commands to a single Discord channel</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_IDLE_STATUS">Idle Status Text</label>
              <input type="text" id="s_IDLE_STATUS" class="form-control" placeholder="Ready to play">
              <small style="color: var(--text-muted); font-size: 11px;">Activity displayed on Discord when bot is idle</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_PLAYING_STATUS">Playing Status Template</label>
              <input type="text" id="s_PLAYING_STATUS" class="form-control" placeholder="Playing: {title}">
              <small style="color: var(--text-muted); font-size: 11px;">Supports {title}, {artist}, {playlist}</small>
            </div>
          </div>
        </div>

        <!-- Card 3: Roles & Permissions -->
        <div class="card" style="margin: 0;">
          <div class="card-title" style="color: #fee75c; font-size: 14px; margin-bottom: 0.25rem;">
            Roles & Access Permissions
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem;">
            Configure DJ role mapping and bot superusers.
          </p>

          <div class="grid-2">
            <div class="form-group">
              <label class="form-label" for="s_DJ_ROLE_NAME">DJ Role Name (Discord)</label>
              <input type="text" id="s_DJ_ROLE_NAME" class="form-control" placeholder="DJ">
              <small style="color: var(--text-muted); font-size: 11px;">Discord role name that unlocks playback controls, seek, and queue management</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_PANEL_OWNER_IDS">Panel Owner Discord IDs</label>
              <input type="text" id="s_PANEL_OWNER_IDS" class="form-control" placeholder="id1, id2 (comma-separated)">
              <small style="color: var(--text-muted); font-size: 11px;">Extra Discord User IDs granted full Owner privileges</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_ALLOWED_USER_IDS">Allowed Web UI User IDs</label>
              <input type="text" id="s_ALLOWED_USER_IDS" class="form-control" placeholder="Leave empty for all server members">
              <small style="color: var(--text-muted); font-size: 11px;">Restricts login to specific Discord IDs; empty allows any server member</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_MAX_UPLOAD_MB">Max File Upload Size (MB)</label>
              <input type="number" id="s_MAX_UPLOAD_MB" class="form-control" min="1" max="1000">
              <small style="color: var(--text-muted); font-size: 11px;">Maximum audio upload file size allowed on web panel</small>
            </div>
          </div>
        </div>

        <!-- Card 4: Audio & YouTube Settings -->
        <div class="card" style="margin: 0;">
          <div class="card-title" style="color: #eb459e; font-size: 14px; margin-bottom: 0.25rem;">
            Audio Formats & YouTube Configuration
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem;">
            Directory paths, supported local file extensions, and YouTube backend mode.
          </p>

          <div class="grid-2">
            <div class="form-group">
              <label class="form-label" for="s_SUPPORTED_FORMATS">Supported Audio Formats</label>
              <input type="text" id="s_SUPPORTED_FORMATS" class="form-control" placeholder=".mp3,.flac,.ogg,.wav">
              <small style="color: var(--text-muted); font-size: 11px;">Comma-separated extensions scanned in playlist folders</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_YOUTUBE_AUTH_MODE">YouTube Auth Mode</label>
              <select id="s_YOUTUBE_AUTH_MODE" class="form-select">
                <option value="disabled">Disabled (use yt-dlp + cookies.txt directly)</option>
                <option value="oauth">OAuth (Google Cloud credentials)</option>
                <option value="token">Token (Pre-existing tokens)</option>
              </select>
              <small style="color: var(--text-muted); font-size: 11px;">yt-dlp with cookies handles YouTube downloads seamlessly</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_PLAYLISTS_DIRECTORY">Playlists Storage Directory</label>
              <input type="text" id="s_PLAYLISTS_DIRECTORY" class="form-control" placeholder="./playlists">
              <small style="color: var(--text-muted); font-size: 11px;">Base filesystem folder where local playlist subdirectories reside</small>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_DATA_DIRECTORY">Data Storage Directory</label>
              <input type="text" id="s_DATA_DIRECTORY" class="form-control" placeholder="./data">
              <small style="color: var(--text-muted); font-size: 11px;">Persistent bot state, cache, and token directory</small>
            </div>
          </div>
        </div>

        <!-- Card 5: Logging & System Diagnostics -->
        <div class="card" style="margin: 0;">
          <div class="card-title" style="color: #5865f2; font-size: 14px; margin-bottom: 0.25rem;">
            Logging & Diagnostics
          </div>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1.25rem;">
            Console and file log verbosity, command tracking, and log rotation limits.
          </p>

          <div class="grid-2">
            <div class="form-group">
              <label class="form-label" for="s_LOG_LEVEL">Bot Log Level</label>
              <select id="s_LOG_LEVEL" class="form-select">
                <option value="STANDARD">STANDARD (INFO) - Recommended</option>
                <option value="EVERYTHING">EVERYTHING (DEBUG)</option>
                <option value="QUIET">QUIET (WARNING)</option>
                <option value="ERRORS">ERRORS (ERROR only)</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_COMMANDS">Log Command Executions</label>
              <select id="s_LOG_COMMANDS" class="form-select">
                <option value="true">True (log user, channel, and command)</option>
                <option value="false">False</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_TO_FILE">Write Logs to File</label>
              <select id="s_LOG_TO_FILE" class="form-select">
                <option value="true">True (save to logs/bot.log)</option>
                <option value="false">False</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_TO_CONSOLE">Write Logs to Console</label>
              <select id="s_LOG_TO_CONSOLE" class="form-select">
                <option value="true">True (print to terminal/journal)</option>
                <option value="false">False</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_ROTATION_MB">Log Rotation Max Size (MB)</label>
              <input type="number" id="s_LOG_ROTATION_MB" class="form-control" min="1" max="100">
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_BACKUP_COUNT">Log Backup Retain Count</label>
              <input type="number" id="s_LOG_BACKUP_COUNT" class="form-control" min="1" max="20">
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_DISCORD_INTERNALS">Log Raw Gateway Internals</label>
              <select id="s_LOG_DISCORD_INTERNALS" class="form-select">
                <option value="false">False (clean logs - recommended)</option>
                <option value="true">True (raw heartbeat packets)</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="s_LOG_YTDLP_VERBOSE">Log yt-dlp Diagnostic Verbose</label>
              <select id="s_LOG_YTDLP_VERBOSE" class="form-select">
                <option value="false">False</option>
                <option value="true">True (detailed yt-dlp extractor trace)</option>
              </select>
            </div>
          </div>
        </div>

        <div style="text-align: right; margin-bottom: 2rem;">
          <button type="submit" id="btn-save-settings" class="btn btn-primary" style="min-width: 160px; padding: 0.75rem 1.5rem; font-weight: 600;">
            Save All Settings
          </button>
        </div>
      </form>
    </div>
  `;

  const form = container.querySelector('#settings-form');
  const btnSave = container.querySelector('#btn-save-settings');
  const restartBanner = container.querySelector('#settings-restart-banner');
  const btnQuickRestart = container.querySelector('#btn-quick-restart');

  async function loadSettings() {
    try {
      const data = await api.rpc('settings.get');
      for (const [k, v] of Object.entries(data || {})) {
        const input = container.querySelector(`#s_${k}`);
        if (input) {
          input.value = (v === undefined || v === null) ? '' : String(v);
        }
      }
    } catch (_) {
      showToast('Failed to load settings', 'error');
    }
  }

  btnQuickRestart.onclick = async () => {
    btnQuickRestart.disabled = true;
    btnQuickRestart.textContent = 'Restarting...';
    try {
      await api.rpc('bot.restart');
      showToast('Bot restart initiated successfully!', 'success');
      setTimeout(() => {
        restartBanner.style.display = 'none';
        btnQuickRestart.disabled = false;
        btnQuickRestart.textContent = '🔄 Restart Bot Now';
      }, 3000);
    } catch (err) {
      showToast(`Restart failed: ${err.message}`, 'error');
      btnQuickRestart.disabled = false;
      btnQuickRestart.textContent = '🔄 Restart Bot Now';
    }
  };

  form.onsubmit = async (e) => {
    e.preventDefault();
    const values = {};
    const inputs = container.querySelectorAll('[id^="s_"]');
    for (const el of inputs) {
      const key = el.id.substring(2);
      values[key] = el.value.trim();
    }

    if (btnSave) {
      btnSave.disabled = true;
      btnSave.textContent = 'Saving...';
    }

    try {
      await api.rpc('settings.set', null, { values });
      showToast('Settings saved successfully! Restart bot to apply changes.', 'success');
      restartBanner.style.display = 'flex';
      restartBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (err) {
      showToast(err.message || 'Failed to save settings', 'error');
    } finally {
      if (btnSave) {
        btnSave.disabled = false;
        btnSave.textContent = 'Save All Settings';
      }
    }
  };

  await loadSettings();
}
