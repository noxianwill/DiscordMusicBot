import { escapeHtml } from '../ui.js';

export async function render(container, state) {
  const isSetupRequired = !state.status?.oauthConfigured;

  container.innerHTML = `
    <div style="max-width: 440px; margin: 4rem auto; text-align: center;">
      <div class="card" style="padding: 2.5rem 1.5rem;">
        <h1 style="font-size: 1.6rem; color: var(--text-bright); margin-bottom: 0.5rem;">Discord Music Bot</h1>
        <p style="color: var(--text-muted); margin-bottom: 2rem;">Log in with Discord to access playback controls.</p>

        ${isSetupRequired ? `
          <div style="background: rgba(240, 178, 50, 0.1); border: 1px solid var(--warning); border-radius: var(--radius); padding: 1rem; margin-bottom: 1.5rem; text-align: left;">
            <strong style="color: var(--warning); display: block; margin-bottom: 0.25rem;">OAuth Setup Required</strong>
            <p style="font-size: 13px; color: var(--text-normal);">Discord Client ID and Secret are not configured yet.</p>
            <a href="#setup" class="btn btn-primary btn-sm" style="margin-top: 0.5rem;">View Setup Guide</a>
          </div>
        ` : `
          <a href="/auth/discord" class="btn btn-primary" style="width: 100%; padding: 0.85rem; font-size: 15px;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.893.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
            </svg>
            Log in with Discord
          </a>
        `}
      </div>
    </div>
  `;
}

