import { api } from '../api.js';
import { escapeHtml, showToast } from '../ui.js';

export async function render(container, state) {
  if (!state.me?.isOwner) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem;">
        <h2 style="color: var(--danger);">Owner Access Required</h2>
        <p style="color: var(--text-muted);">Only bot owners can view or manage YouTube cookies.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="width: 100%; display: flex; flex-direction: column; gap: 1.5rem;">
      <!-- Current Cookies Viewer & Editor -->
      <div class="card" style="margin: 0;">
        <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span>Current YouTube Cookies</span>
            <span id="cookie-loaded-badge" class="badge" style="background: rgba(255, 255, 255, 0.08); font-size: 11px;">Loading...</span>
          </div>
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <button type="button" id="btn-toggle-mask" class="btn btn-sm" title="Toggle visibility">
              👁️ Show Cookies
            </button>
            <button type="button" id="btn-toggle-wrap" class="btn btn-sm" title="Toggle horizontal wrap">
              Wrap: ON
            </button>
            <button type="button" id="btn-copy-cookies" class="btn btn-sm" title="Copy cookies text">
              📋 Copy
            </button>
            <button type="button" id="btn-browse-cookie" class="btn btn-sm">
              📁 Load File (.txt)
            </button>
            <input type="file" id="cookie-file-input" accept=".txt" style="display: none;">
          </div>
        </div>

        <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 1rem;">
          Below are the active cookies stored on the server. You can view, edit, or paste new Netscape format cookies and click <strong>Save Cookies</strong>.
        </p>

        <form id="cookie-form">
          <div class="form-group" style="position: relative; margin-bottom: 1rem;">
            <textarea id="cookie-text" class="form-control" style="width: 100%; box-sizing: border-box; font-family: var(--font-mono); font-size: 12.5px; line-height: 1.6; tab-size: 2; -moz-tab-size: 2; white-space: pre-wrap; word-break: break-all; overflow: hidden; resize: none; min-height: 220px; filter: blur(8px); user-select: none; background: #141517; border: 1px solid var(--border);" placeholder="# Netscape HTTP Cookie File&#10;.youtube.com&#9;TRUE&#9;/&#9;TRUE&#9;1799999999&#9;SID&#9;..."></textarea>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
            <div style="font-size: 12px; color: var(--text-muted);">
              Editing requires at least one <code>.youtube.com</code> cookie entry.
            </div>
            <button type="submit" id="btn-save-cookies" class="btn btn-primary" style="min-width: 130px; font-weight: 600;">Save Cookies</button>
          </div>
        </form>
      </div>

      <!-- Status Card -->
      <div class="card" style="margin: 0;">
        <div class="card-title">YouTube Cookies Status</div>
        <div id="cookie-status-container">
          <p style="color: var(--text-muted);">Loading cookie status...</p>
        </div>
      </div>

      <!-- Export Guide Card -->
      <div class="card" style="margin: 0;">
        <div class="card-title" style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
          <span>Exporting cookies.txt (How to Prevent Cookies from Expiring)</span>
        </div>

        <p style="font-size: 13.5px; color: var(--text-normal); margin-bottom: 1rem; line-height: 1.6;">
          Supplying your browser session cookies authenticates your bot as a regular user and allows it to access high-quality audio formats and age-restricted tracks without bot-detection flags.
        </p>

        <!-- Caution Callout Banner -->
        <div style="background: rgba(218, 55, 60, 0.12); border-left: 4px solid var(--danger); border-radius: 4px; padding: 0.9rem 1.1rem; margin-bottom: 1.5rem; color: var(--text-normal); font-size: 13px; line-height: 1.55;">
          <div style="color: var(--danger); font-weight: 700; margin-bottom: 0.35rem; display: flex; align-items: center; gap: 0.4rem;">
            <span>⚠️ CRITICAL: Always Use a Disposable / Burner Google Account!</span>
          </div>
          <div>
            <strong>NEVER</strong> use your primary personal Google or YouTube account when exporting <code>cookies.txt</code>.
            If YouTube's automated abuse detection flags high-frequency automated audio requests from a cloud datacenter IP (AWS, DigitalOcean, Hetzner, etc.), the account linked to those session cookies may face restrictions or termination. Always create a free secondary/burner Google account solely for your bot.
          </div>
        </div>

        <div style="margin-bottom: 1.25rem;">
          <h4 style="font-size: 14px; font-weight: 600; color: var(--text-bright); margin-bottom: 0.5rem;">
            Why Normal Exports Expire Quickly
          </h4>
          <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
            YouTube's desktop website runs continuous client-side single-page-app (SPA) JavaScript that rotates and invalidates session tokens (such as <code>SAPISID</code>, <code>__Secure-3PSID</code>, and <code>LOGIN_INFO</code>) as you navigate between pages or when tabs close. If you export cookies from an active browsing session, the tokens may already be invalidated by the time your bot uses them.
          </p>
        </div>

        <div>
          <h4 style="font-size: 14px; font-weight: 600; color: var(--text-bright); margin-bottom: 0.75rem;">
            The robots.txt Clean-Export Method (Recommended by yt-dlp)
          </h4>
          <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 0.75rem;">
            To obtain clean, stable session cookies that do not immediately invalidate:
          </p>
          <ol style="padding-left: 1.35rem; font-size: 13px; display: flex; flex-direction: column; gap: 0.75rem; color: var(--text-normal); line-height: 1.55;">
            <li>
              <strong>Open a New Incognito / Private Window:</strong>
              <div style="color: var(--text-muted);">Open a fresh Private / Incognito browser window in Chrome, Firefox, or Brave.</div>
            </li>
            <li>
              <strong>Sign into Your Burner Account:</strong>
              <div style="color: var(--text-muted);">Navigate to <a href="https://www.youtube.com" target="_blank" rel="noopener" style="color: var(--accent); text-decoration: underline;">YouTube</a> and sign into your <strong>secondary burner account</strong>.</div>
            </li>
            <li>
              <strong>Navigate to robots.txt in the Same Tab:</strong>
              <div style="color: var(--text-muted); margin-top: 0.2rem;">
                In that <strong>exact same browser tab</strong>, navigate directly to:
                <code style="background: rgba(0, 0, 0, 0.35); padding: 2px 7px; border-radius: 4px; font-family: var(--font-mono); color: var(--accent); font-size: 12.5px; display: inline-block; margin: 0.25rem 0;">https://www.youtube.com/robots.txt</code>
              </div>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 0.25rem;">
                <em>Why this works:</em> <code>robots.txt</code> is a static plain text file. Because YouTube's background JavaScript engines and telemetry trackers do not load on this page, YouTube cannot rotate or invalidate your session tokens.
              </div>
            </li>
            <li>
              <strong>Export in Netscape Format:</strong>
              <div style="color: var(--text-muted);">
                Open your cookie exporter extension (recommended: <strong>Get cookies.txt LOCALLY</strong> for <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" rel="noopener" style="color: var(--accent); text-decoration: underline;">Chrome / Brave</a> or <a href="https://addons.mozilla.org/firefox/addon/get-cookies-txt-locally/" target="_blank" rel="noopener" style="color: var(--accent); text-decoration: underline;">Firefox</a>) and click <strong>Export</strong> to save the file as <code>cookies.txt</code> in <strong>Netscape</strong> format.
              </div>
            </li>
            <li>
              <strong>Close the Incognito Window Immediately:</strong>
              <div style="color: var(--text-muted);">Close the entire private browsing session right away without browsing any other YouTube pages. Do not click "Log Out" (logging out invalidates session keys on Google's servers).</div>
            </li>
            <li>
              <strong>Save in Web UI or Bot Directory:</strong>
              <div style="color: var(--text-muted);">
                Click <strong>📁 Load File (.txt)</strong> above or paste the contents into the editor and click <strong>Save Cookies</strong>. Alternatively, place the file directly at <code>DiscordMusicBot/cookies.txt</code>.
              </div>
            </li>
          </ol>
        </div>
      </div>
    </div>
  `;

  const cookieStatusContainer = container.querySelector('#cookie-status-container');
  const cookieLoadedBadge = container.querySelector('#cookie-loaded-badge');
  const cookieFileInput = container.querySelector('#cookie-file-input');
  const btnBrowseCookie = container.querySelector('#btn-browse-cookie');
  const btnCopyCookies = container.querySelector('#btn-copy-cookies');
  const btnToggleMask = container.querySelector('#btn-toggle-mask');
  const btnToggleWrap = container.querySelector('#btn-toggle-wrap');
  const cookieForm = container.querySelector('#cookie-form');
  const cookieText = container.querySelector('#cookie-text');
  const btnSave = container.querySelector('#btn-save-cookies');

  let isMasked = true;
  let isWrapped = true;
  let rawCookies = '';

  function adjustHeight() {
    if (!cookieText) return;
    cookieText.style.height = 'auto';
    const computedHeight = Math.max(220, cookieText.scrollHeight + 16);
    cookieText.style.height = `${computedHeight}px`;
    cookieText.style.overflowY = 'hidden';
    if (isWrapped) {
      cookieText.style.overflowX = 'hidden';
    }
  }

  cookieText.addEventListener('input', adjustHeight);
  window.addEventListener('resize', adjustHeight);

  let resizeObserver = null;
  if (typeof ResizeObserver !== 'undefined' && cookieText) {
    resizeObserver = new ResizeObserver(() => {
      adjustHeight();
    });
    resizeObserver.observe(cookieText);
  }

  async function loadStatusAndCookies() {
    try {
      const [statusData, cookiesData] = await Promise.all([
        api.rpc('cookies.status'),
        api.rpc('cookies.get').catch(() => null)
      ]);

      renderStatus(statusData);

      if (cookiesData && cookiesData.exists && cookiesData.content) {
        rawCookies = cookiesData.content;
        cookieText.value = rawCookies;
        const lineCount = rawCookies.trim().split('\n').length;
        const kbSize = (rawCookies.length / 1024).toFixed(1);
        cookieLoadedBadge.textContent = `${lineCount} lines (${kbSize} KB)`;
        cookieLoadedBadge.style.background = 'rgba(87, 242, 135, 0.2)';
        cookieLoadedBadge.style.color = 'var(--success)';
      } else {
        rawCookies = '';
        cookieText.value = '';
        cookieLoadedBadge.textContent = 'No file found';
        cookieLoadedBadge.style.background = 'rgba(218, 55, 60, 0.2)';
        cookieLoadedBadge.style.color = 'var(--danger)';
      }
    } catch (_) {
      cookieStatusContainer.innerHTML = '<p style="color: var(--danger);">Failed to load cookie status.</p>';
      cookieLoadedBadge.textContent = 'Error loading';
    } finally {
      adjustHeight();
      requestAnimationFrame(adjustHeight);
      setTimeout(adjustHeight, 50);
      setTimeout(adjustHeight, 200);
    }
  }

  function renderStatus(data) {
    const exists = Boolean(data.exists);
    const count = data.youtubeCookieCount || 0;
    const daysLeft = data.daysLeft;

    let warningBanner = '';
    if (!exists) {
      warningBanner = `
        <div style="background: rgba(218, 55, 60, 0.15); border: 1px solid var(--danger); padding: 0.75rem 1rem; border-radius: var(--radius); margin-bottom: 1rem; color: var(--danger);">
          <strong>Warning:</strong> No cookies.txt found! YouTube playback on cloud server IPs may fail with bot detection or 403 Forbidden.
        </div>
      `;
    } else if (daysLeft !== null && daysLeft < 14) {
      warningBanner = `
        <div style="background: rgba(240, 178, 50, 0.15); border: 1px solid var(--warning); padding: 0.75rem 1rem; border-radius: var(--radius); margin-bottom: 1rem; color: var(--warning);">
          <strong>Notice:</strong> Your YouTube session cookies expire in ${daysLeft} days. Export fresh cookies soon to avoid interruptions.
        </div>
      `;
    }

    cookieStatusContainer.innerHTML = `
      ${warningBanner}
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem;">
        <div>
          <div style="color: var(--text-muted); font-size: 12px;">File Status</div>
          <div style="font-size: 16px; font-weight: 600; color: ${exists ? 'var(--success)' : 'var(--danger)'};">
            ${exists ? 'Present' : 'Missing'}
          </div>
        </div>
        <div>
          <div style="color: var(--text-muted); font-size: 12px;">YouTube Cookies Count</div>
          <div style="font-size: 16px; font-weight: 600; color: var(--text-bright);">${count} entries</div>
        </div>
        <div>
          <div style="color: var(--text-muted); font-size: 12px;">Estimated Validity</div>
          <div style="font-size: 16px; font-weight: 600; color: ${daysLeft === null ? 'var(--text-muted)' : (daysLeft < 14 ? 'var(--warning)' : 'var(--success)')};">
            ${daysLeft !== null ? `${daysLeft} days remaining` : 'Unknown'}
          </div>
        </div>
      </div>
    `;
  }

  btnBrowseCookie.onclick = () => cookieFileInput.click();

  cookieFileInput.onchange = () => {
    const file = cookieFileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      rawCookies = e.target.result;
      cookieText.value = rawCookies;
      showToast('Loaded cookies file into editor', 'info');
      adjustHeight();
      requestAnimationFrame(adjustHeight);
    };
    reader.readAsText(file);
  };

  btnCopyCookies.onclick = async () => {
    const val = cookieText.value;
    if (!val) {
      showToast('No cookie content to copy', 'error');
      return;
    }
    try {
      await navigator.clipboard.writeText(val);
      showToast('Cookies copied to clipboard!', 'success');
    } catch (_) {
      showToast('Failed to copy to clipboard', 'error');
    }
  };

  btnToggleMask.onclick = () => {
    isMasked = !isMasked;
    if (isMasked) {
      cookieText.style.filter = 'blur(8px)';
      cookieText.style.userSelect = 'none';
      btnToggleMask.textContent = '👁️ Show Cookies';
    } else {
      cookieText.style.filter = 'none';
      cookieText.style.userSelect = 'auto';
      btnToggleMask.textContent = '👁️ Hide Cookies';
    }
    adjustHeight();
  };

  if (btnToggleWrap) {
    btnToggleWrap.onclick = () => {
      isWrapped = !isWrapped;
      if (isWrapped) {
        cookieText.style.whiteSpace = 'pre-wrap';
        cookieText.style.wordBreak = 'break-all';
        cookieText.style.overflowX = 'hidden';
        btnToggleWrap.textContent = 'Wrap: ON';
      } else {
        cookieText.style.whiteSpace = 'pre';
        cookieText.style.wordBreak = 'normal';
        cookieText.style.overflowX = 'auto';
        btnToggleWrap.textContent = 'Wrap: OFF';
      }
      adjustHeight();
      requestAnimationFrame(adjustHeight);
    };
  }

  cookieForm.onsubmit = async (e) => {
    e.preventDefault();
    const text = cookieText.value.trim();
    if (!text) {
      showToast('Cookie text cannot be empty', 'error');
      return;
    }

    btnSave.disabled = true;
    btnSave.textContent = 'Saving...';

    try {
      await api.rpc('cookies.set', null, { text });
      showToast('Cookies updated successfully!', 'success');
      await loadStatusAndCookies();
    } catch (_) {
    } finally {
      btnSave.disabled = false;
      btnSave.textContent = 'Save Cookies';
    }
  };

  await loadStatusAndCookies();

  return () => {
    window.removeEventListener('resize', adjustHeight);
    if (resizeObserver) resizeObserver.disconnect();
  };
}
