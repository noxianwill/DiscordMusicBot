import { showToast } from './ui.js';

let csrfToken = null;

export function setCsrfToken(token) {
  csrfToken = token;
}

export function getCsrfToken() {
  return csrfToken;
}

export async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };

  if (csrfToken && options.method && options.method !== 'GET') {
    headers['X-CSRF-Token'] = csrfToken;
  }

  if (options.body && typeof options.body === 'object' && !(options.body instanceof Blob || options.body instanceof FormData || options.body instanceof ArrayBuffer)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  let res;
  try {
    res = await fetch(path, {
      ...options,
      headers
    });
  } catch (netErr) {
    const isOffline = typeof navigator !== 'undefined' && !navigator.onLine;
    const msg = isOffline
      ? 'You appear to be offline. Please check your internet connection.'
      : 'Unable to reach the server. Please check your network or server status.';
    showToast(msg, 'error');
    const err = new Error(msg);
    err.isNetworkError = true;
    err.cause = netErr;
    throw err;
  }

  if (res.status === 401) {
    if (!location.hash.startsWith('#login') && !location.hash.startsWith('#setup')) {
      location.hash = '#login';
    }
    throw new Error('Unauthorized');
  }

  let data;
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    data = await res.json();
  } else {
    data = await res.text();
  }

  if (!res.ok) {
    const errorMsg = data?.error || (typeof data === 'string' ? data : 'Request failed');
    showToast(errorMsg, 'error');
    const err = new Error(errorMsg);
    err.status = res.status;
    err.code = data?.code;
    throw err;
  }

  return data;
}

export const api = {
  get: (path) => request(path, { method: 'GET' }),
  post: (path, body) => request(path, { method: 'POST', body }),
  rpc: (action, guildId = null, params = {}) =>
    request('/api/rpc', {
      method: 'POST',
      body: { action, guildId, params }
    }).then(res => res.data),
  upload: (playlist, file, onProgress, overwrite = false) => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const url = `/api/upload?playlist=${encodeURIComponent(playlist)}&filename=${encodeURIComponent(file.name)}&overwrite=${overwrite}`;

      xhr.open('POST', url);
      if (csrfToken) {
        xhr.setRequestHeader('X-CSRF-Token', csrfToken);
      }
      xhr.setRequestHeader('Content-Type', 'application/octet-stream');

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            onProgress(pct, e.loaded, e.total);
          }
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve(data.data);
          } catch (_) {
            resolve(xhr.responseText);
          }
        } else {
          let errText = xhr.statusText;
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.error) errText = data.error;
          } catch (_) {}
          showToast(`Upload failed: ${errText}`, 'error');
          reject(new Error(errText));
        }
      };

      xhr.onerror = () => {
        showToast('Network error during upload', 'error');
        reject(new Error('Network error'));
      };

      xhr.send(file);
    });
  }
};

