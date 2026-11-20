export function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }, duration);
}

export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return '--:--';
  const total = Math.floor(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  const pad = (n) => String(n).padStart(2, '0');
  if (hrs > 0) {
    return `${hrs}:${pad(mins)}:${pad(secs)}`;
  }
  return `${pad(mins)}:${pad(secs)}`;
}

export function confirmDialog(message, confirmLabel = 'Confirm', isDanger = false, title = 'Confirmation Required') {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: fixed; inset: 0; background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
      display: flex; align-items: center; justify-content: center; z-index: 10000;
      animation: modalFadeIn 0.15s ease-out;
    `;

    const box = document.createElement('div');
    box.className = 'card';
    box.style.cssText = `
      max-width: 420px; width: 92%; margin: 0;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6), 0 0 0 1px var(--border);
      animation: modalPopIn 0.15s cubic-bezier(0.16, 1, 0.3, 1);
    `;
    box.innerHTML = `
      <div class="card-title">${escapeHtml(title)}</div>
      <p style="font-size: 13.5px; color: var(--text-normal); margin-bottom: 1.5rem; line-height: 1.55;">${escapeHtml(message)}</p>
      <div style="display: flex; justify-content: flex-end; gap: 0.6rem;">
        <button type="button" class="btn btn-sm" id="modal-cancel">Cancel</button>
        <button type="button" class="btn btn-sm ${isDanger ? 'btn-danger' : 'btn-primary'}" id="modal-confirm" style="font-weight: 600;">${escapeHtml(confirmLabel)}</button>
      </div>
    `;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    const cleanup = (val) => {
      window.removeEventListener('keydown', handleKey);
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      resolve(val);
    };

    const handleKey = (e) => {
      if (e.key === 'Escape') cleanup(false);
      else if (e.key === 'Enter') cleanup(true);
    };
    window.addEventListener('keydown', handleKey);

    overlay.onclick = (e) => {
      if (e.target === overlay) cleanup(false);
    };

    box.querySelector('#modal-cancel').onclick = () => cleanup(false);
    box.querySelector('#modal-confirm').onclick = () => cleanup(true);
  });
}

export function promptDialog({
  title = 'Input Required',
  message = '',
  defaultValue = '',
  placeholder = '',
  confirmLabel = 'Save',
  icon = '📁'
} = {}) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: fixed; inset: 0; background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
      display: flex; align-items: center; justify-content: center; z-index: 10000;
      animation: modalFadeIn 0.15s ease-out;
    `;

    const box = document.createElement('div');
    box.className = 'card';
    box.style.cssText = `
      max-width: 440px; width: 92%; margin: 0;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6), 0 0 0 1px var(--border);
      animation: modalPopIn 0.15s cubic-bezier(0.16, 1, 0.3, 1);
    `;
    box.innerHTML = `
      <div class="card-title" style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
        <span>${escapeHtml(icon)}</span>
        <span>${escapeHtml(title)}</span>
      </div>
      ${message ? `<p style="font-size: 13px; color: var(--text-muted); margin-bottom: 1rem; line-height: 1.5;">${escapeHtml(message)}</p>` : ''}
      <form id="modal-prompt-form" style="display: flex; flex-direction: column; gap: 1.25rem;">
        <div class="form-group" style="margin: 0;">
          <input type="text" id="modal-prompt-input" class="form-control" style="width: 100%; box-sizing: border-box; font-size: 14px;" value="${escapeHtml(defaultValue)}" placeholder="${escapeHtml(placeholder)}" autocomplete="off" spellcheck="false">
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 0.6rem;">
          <button type="button" class="btn btn-sm" id="modal-cancel">Cancel</button>
          <button type="submit" class="btn btn-primary btn-sm" id="modal-confirm" style="font-weight: 600;">${escapeHtml(confirmLabel)}</button>
        </div>
      </form>
    `;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    const input = box.querySelector('#modal-prompt-input');
    const form = box.querySelector('#modal-prompt-form');
    const cancelBtn = box.querySelector('#modal-cancel');

    setTimeout(() => {
      input.focus();
      input.select();
    }, 20);

    const cleanup = (val) => {
      window.removeEventListener('keydown', handleKey);
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      resolve(val);
    };

    const handleKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cleanup(null);
      }
    };
    window.addEventListener('keydown', handleKey);

    overlay.onclick = (e) => {
      if (e.target === overlay) cleanup(null);
    };

    cancelBtn.onclick = () => cleanup(null);

    form.onsubmit = (e) => {
      e.preventDefault();
      const val = input.value.trim();
      cleanup(val || null);
    };
  });
}

