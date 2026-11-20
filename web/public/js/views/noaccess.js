export async function render(container) {
  container.innerHTML = `
    <div style="max-width: 500px; margin: 4rem auto; text-align: center;">
      <div class="card" style="padding: 2.5rem 1.5rem;">
        <h1 style="font-size: 1.5rem; color: var(--danger); margin-bottom: 0.5rem;">Access Restricted</h1>
        <p style="color: var(--text-normal); margin-bottom: 1.5rem;">
          You do not have permission to control this bot. Either your account is not a member of any servers with the bot, or you are not on the authorized user list.
        </p>
        <div style="display: flex; gap: 0.75rem; justify-content: center;">
          <a href="/auth/discord" class="btn">Switch Account</a>
          <button class="btn btn-danger" id="logout-btn">Log Out</button>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#logout-btn').onclick = async () => {
    try {
      const { api } = await import('../api.js');
      await api.post('/auth/logout', {});
    } catch (_) {}
    location.href = '/#login';
    location.reload();
  };
}

