import { escapeHtml } from '../ui.js';

export async function render(container) {
  let redirectUri = `${location.origin}/auth/discord/callback`;
  let wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  let panelUrl = `${wsProto}//${location.host}/agent`;

  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      if (data.redirectUri) redirectUri = data.redirectUri;
      if (data.agentWsUrl) panelUrl = data.agentWsUrl;
    }
  } catch (_) {}

  container.innerHTML = `
    <div style="max-width: 720px; margin: 2rem auto;">
      <div class="card">
        <h1 class="card-title">Discord OAuth2 Setup Guide</h1>
        <p style="color: var(--text-normal); margin-bottom: 1.5rem;">
          To enable login with Discord, configure your bot's Discord application in the Developer Portal.
        </p>

        <ol style="padding-left: 1.25rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 1rem;">
          <li>
            <strong>Open Developer Portal:</strong><br>
            Go to <a href="https://discord.com/developers/applications" target="_blank" rel="noreferrer">discord.com/developers/applications</a> and select your bot application.
          </li>
          <li>
            <strong>Add OAuth2 Redirect URI:</strong><br>
            Navigate to <strong>OAuth2</strong> &rarr; <strong>General</strong> &rarr; <strong>Redirects</strong>, click <strong>Add Redirect</strong>, and paste:
            <div style="background: var(--bg-darker); padding: 0.5rem 0.75rem; border-radius: var(--radius); font-family: var(--font-mono); margin-top: 0.25rem; font-size: 13px; user-select: all;">
              ${escapeHtml(redirectUri)}
            </div>
          </li>
          <li>
            <strong>Copy Credentials into .env:</strong><br>
            Copy the <strong>Client ID</strong> and reset/copy the <strong>Client Secret</strong> into your Web UI's <code>.env</code> file:
            <pre style="background: var(--bg-darker); padding: 0.75rem; border-radius: var(--radius); font-family: var(--font-mono); margin-top: 0.25rem; font-size: 13px;">
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here</pre>
          </li>
          <li>
            <strong>Configure Bot config.txt:</strong><br>
            Add the panel address to your bot's <code>config.txt</code>:
            <pre style="background: var(--bg-darker); padding: 0.75rem; border-radius: var(--radius); font-family: var(--font-mono); margin-top: 0.25rem; font-size: 13px;">
PANEL_ENABLED=true
PANEL_URL=${escapeHtml(panelUrl)}
PANEL_SECRET=your_shared_secret_here</pre>
          </li>
          <li>
            <strong>Restart the Web UI:</strong><br>
            Restart the PM2 service or container to apply the new credentials:
            <pre style="background: var(--bg-darker); padding: 0.5rem 0.75rem; border-radius: var(--radius); font-family: var(--font-mono); margin-top: 0.25rem; font-size: 13px;">pm2 restart discordbot</pre>
          </li>
        </ol>

        <div style="text-align: right;">
          <a href="#login" class="btn btn-primary">Return to Login</a>
        </div>
      </div>
    </div>
  `;
}

