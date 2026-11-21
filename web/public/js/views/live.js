import { api } from '../api.js';
import { escapeHtml, formatDuration, showToast } from '../ui.js';
import { connectWebSocket, subscribeToGuild, addWsListener, isWsConnected } from '../ws.js';

export async function render(container, state) {
  // Extract guildId from location.hash (e.g. #live?guild=123456789)
  const hashParts = location.hash.split('?');
  const params = new URLSearchParams(hashParts[1] || '');
  const guildId = params.get('guild');

  if (!guildId || !/^\d{17,20}$/.test(guildId)) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem; max-width: 600px; margin: 2rem auto;">
        <h2 style="color: var(--danger); margin-bottom: 0.5rem;">Invalid Listener Link</h2>
        <p style="color: var(--text-muted); margin-bottom: 1.5rem;">
          This link is missing a valid Discord Server ID. Ask someone in the voice channel to re-copy their listener link.
        </p>
        <a href="#login" class="btn btn-primary">Go to Login</a>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="max-width: 900px; margin: 0 auto; padding-bottom: 2rem;">
      <!-- Listener Mode Header Banner -->
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; padding: 0.85rem 1.25rem; background: rgba(88, 101, 242, 0.1); border: 1px solid rgba(88, 101, 242, 0.25); border-radius: var(--radius-md); flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 0.65rem;">
          <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px var(--success);"></span>
          <span style="font-weight: 600; font-size: 14px; color: var(--text-bright);">Live Music Stream &bull; Listener Mode</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.5rem;">
          <span style="font-size: 12px; color: var(--text-muted);">Want DJ controls?</span>
          <a href="#login" class="btn btn-sm btn-primary">Login with Discord</a>
        </div>
      </div>

      <!-- Now Playing Card -->
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-title">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
            <span>Now Playing</span>
          </div>
          <div id="live-audio-badge" class="badge badge-online">STREAMING</div>
        </div>

        <div id="live-now-playing">
          <p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Connecting to live stream...</p>
        </div>

        <!-- Canvas Visualizer -->
        <canvas id="live-visualizer" height="40" style="width: 100%; border-radius: var(--radius-sm); margin-top: 0.75rem; background: rgba(0, 0, 0, 0.2); display: block;"></canvas>

        <!-- Lyrics Container -->
        <div id="live-lyrics-drawer" style="display: none; margin-top: 1rem; padding: 1rem; background: rgba(0, 0, 0, 0.25); border: 1px solid var(--border); border-radius: var(--radius-md); max-height: 280px; overflow-y: auto;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">
            <span style="font-weight: 600; font-size: 13px; color: var(--text-bright);">🎤 Synchronized Lyrics</span>
            <button id="btn-close-live-lyrics" class="btn btn-sm" style="padding: 2px 8px; font-size: 11px;">Close</button>
          </div>
          <div id="live-lyrics-content"></div>
        </div>
      </div>

      <!-- Queue Card -->
      <div class="card">
        <div class="card-title">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
            <span>Upcoming Queue</span>
          </div>
          <span id="live-queue-stats" style="font-size: 12px; color: var(--text-muted);"></span>
        </div>
        <div id="live-queue-container">
          <p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">Loading queue...</p>
        </div>
      </div>
    </div>
  `;

  let currentGuildState = null;
  let currentQueue = null;
  let seekInterval = null;
  let animFrameId = null;
  let localElapsed = 0;
  let lyricsData = null;
  let isLyricsOpen = false;

  const nowPlayingContainer = container.querySelector('#live-now-playing');
  const queueContainer = container.querySelector('#live-queue-container');
  const queueStats = container.querySelector('#live-queue-stats');
  const lyricsDrawer = container.querySelector('#live-lyrics-drawer');
  const lyricsContent = container.querySelector('#live-lyrics-content');
  const canvas = container.querySelector('#live-visualizer');

  // Initialize visualizer animation
  function startVisualizer() {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let phase = 0;

    function draw() {
      if (!canvas.parentElement) return;
      const w = canvas.width = canvas.offsetWidth;
      const h = canvas.height = canvas.offsetHeight;
      ctx.clearRect(0, 0, w, h);

      const isPlaying = currentGuildState?.isPlaying;
      const bars = 48;
      const barWidth = w / bars;

      phase += 0.05;

      for (let i = 0; i < bars; i++) {
        let barHeight = 4;
        if (isPlaying) {
          const sin1 = Math.sin(phase + i * 0.35);
          const sin2 = Math.cos(phase * 0.7 + i * 0.2);
          const val = (sin1 + sin2 + 2) / 4;
          barHeight = Math.max(4, val * (h - 6));
        }

        const gradient = ctx.createLinearGradient(0, h, 0, h - barHeight);
        gradient.addColorStop(0, '#5865F2');
        gradient.addColorStop(1, '#9ba8ff');

        ctx.fillStyle = gradient;
        ctx.fillRect(i * barWidth + 1, h - barHeight, barWidth - 2, barHeight);
      }

      animFrameId = requestAnimationFrame(draw);
    }

    draw();
  }

  function renderNowPlaying() {
    if (seekInterval) {
      clearInterval(seekInterval);
      seekInterval = null;
    }

    if (!currentGuildState || (!currentGuildState.isPlaying && !currentGuildState.isPaused && !currentGuildState.current)) {
      nowPlayingContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2.5rem 0;">Nothing is currently playing in this server.</p>';
      return;
    }

    const cur = currentGuildState.current || {};
    const isPlaying = currentGuildState.isPlaying;
    const duration = cur.duration || 0;
    localElapsed = cur.elapsed || 0;

    nowPlayingContainer.innerHTML = `
      <div class="now-playing">
        <img src="${cur.thumbnail || 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOTAiIGhlaWdodD0iOTAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzExMTIxNCIvPjwvc3ZnPg=='}" class="track-thumb" alt="Thumbnail">
        <div class="track-details">
          <div class="track-title" title="${escapeHtml(cur.title || 'Unknown Title')}">${escapeHtml(cur.title || 'Unknown Title')}</div>
          <div class="track-artist">${escapeHtml(cur.artist || '')} ${cur.requester ? `&bull; Added by ${escapeHtml(cur.requester)}` : ''}</div>
          <div style="font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 0.5rem; margin-top: 4px;">
            <span>Voice Channel: <strong style="color: var(--text-bright);">${escapeHtml(currentGuildState.voiceChannel?.name || 'Connected')}</strong></span>
            ${cur.sourceType ? `<span class="badge" style="background: rgba(255, 255, 255, 0.08); font-size: 10px;">${escapeHtml(cur.sourceType.toUpperCase())}</span>` : ''}
          </div>
        </div>
      </div>

      <!-- Seek Bar -->
      <div class="seek-wrap" style="margin-top: 1rem;">
        <div class="seek-time-row">
          <span id="live-seek-current">${formatDuration(localElapsed)}</span>
          <span id="live-seek-total">${duration ? formatDuration(duration) : '--:--'}</span>
        </div>
        <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.1); border-radius: 3px; overflow: hidden; margin-top: 4px;">
          <div id="live-progress-bar" style="height: 100%; background: var(--accent); width: ${duration ? Math.min(100, (localElapsed / duration) * 100) : 0}%; transition: width 0.3s ease;"></div>
        </div>
      </div>

      <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 0.75rem;">
        <span style="font-size: 12px; color: var(--text-muted);">
          Status: <strong style="color: ${isPlaying ? 'var(--success)' : 'var(--warning)'};">${isPlaying ? 'Playing' : 'Paused'}</strong>
        </span>
        <button id="btn-live-lyrics-toggle" class="btn btn-sm" style="display: inline-flex; align-items: center; gap: 4px; font-size: 11px;">
          🎤 ${isLyricsOpen ? 'Hide Lyrics' : 'Live Lyrics'}
        </button>
      </div>
    `;

    const btnLyrics = nowPlayingContainer.querySelector('#btn-live-lyrics-toggle');
    if (btnLyrics) {
      btnLyrics.onclick = () => toggleLyrics(cur);
    }

    if (isPlaying) {
      const seekCurrent = nowPlayingContainer.querySelector('#live-seek-current');
      const progressBar = nowPlayingContainer.querySelector('#live-progress-bar');
      seekInterval = setInterval(() => {
        localElapsed += 1;
        if (duration && localElapsed > duration) localElapsed = duration;
        if (seekCurrent) seekCurrent.textContent = formatDuration(localElapsed);
        if (progressBar && duration) progressBar.style.width = `${Math.min(100, (localElapsed / duration) * 100)}%`;
        updateActiveLyricsLine(localElapsed);
      }, 1000);
    }
  }

  function renderQueue() {
    const upcoming = currentQueue?.upcoming || [];
    if (queueStats) {
      const totalSec = upcoming.reduce((acc, t) => acc + (t.duration || 0), 0);
      queueStats.textContent = `${upcoming.length} tracks &bull; ${formatDuration(totalSec)} total`;
    }

    if (upcoming.length === 0) {
      queueContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">No upcoming songs in the queue.</p>';
      return;
    }

    queueContainer.innerHTML = `
      <ul class="list-group" style="max-height: 400px; overflow-y: auto;">
        ${upcoming.map((t, idx) => `
          <li class="list-item">
            <span style="font-size: 12px; color: var(--text-muted); width: 28px; font-family: var(--font-mono);">#${idx + 1}</span>
            <div style="flex: 1; min-width: 0;">
              <div style="font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-bright);" title="${escapeHtml(t.title)}">
                ${escapeHtml(t.title)}
              </div>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                ${escapeHtml(t.artist || '')} &bull; ${formatDuration(t.duration)} ${t.requester ? `&bull; ${escapeHtml(t.requester)}` : ''}
              </div>
            </div>
          </li>
        `).join('')}
      </ul>
    `;
  }

  async function toggleLyrics(currentTrack) {
    isLyricsOpen = !isLyricsOpen;
    if (!isLyricsOpen) {
      lyricsDrawer.style.display = 'none';
      return;
    }

    lyricsDrawer.style.display = 'block';
    if (!lyricsData || lyricsData.trackTitle !== currentTrack.title) {
      lyricsContent.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">Searching for lyrics...</p>';
      try {
        let cleanTitle = (currentTrack.title || '')
          .replace(/[\(\[][^\)\]]*(?:official|video|audio|lyrics?|remaster|hd|4k|visualizer|clip|version)[^\)\]]*[\)\]]/gi, '')
          .replace(/\|.*$/, '')
          .trim();
        let artist = currentTrack.artist || '';
        if (cleanTitle.includes(' - ')) {
          const parts = cleanTitle.split(' - ');
          if (artist && (artist.toLowerCase().includes(parts[0].toLowerCase()) || parts[0].toLowerCase().includes(artist.toLowerCase()))) {
            cleanTitle = parts[1].trim();
          } else if (!artist) {
            artist = parts[0].trim();
            cleanTitle = parts[1].trim();
          } else {
            cleanTitle = parts[1].trim();
          }
        }

        let data = null;
        if (artist) {
          try {
            const queryParams = new URLSearchParams({ track_name: cleanTitle, artist_name: artist });
            const res = await fetch(`https://lrclib.net/api/get?${queryParams}`);
            if (res.ok) data = await res.json();
          } catch (_) { }
        }

        if (!data) {
          try {
            const searchRes = await fetch(`https://lrclib.net/api/search?q=${encodeURIComponent((cleanTitle + ' ' + artist).trim())}`);
            if (searchRes.ok) {
              const list = await searchRes.json();
              if (Array.isArray(list) && list.length > 0) {
                data = list.find(x => x.syncedLyrics) || list[0];
              }
            }
          } catch (_) { }
        }

        if (data) {
          lyricsData = {
            trackTitle: currentTrack.title,
            synced: parseLrcLines(data.syncedLyrics),
            plain: data.plainLyrics
          };
        } else {
          lyricsData = { trackTitle: currentTrack.title, synced: [], plain: null };
        }
      } catch (_) {
        lyricsData = { trackTitle: currentTrack.title, synced: [], plain: null };
      }
    }

    renderLyricsContent();
  }

  function parseLrcLines(lrcText) {
    if (!lrcText) return [];
    const lines = [];
    const re = /\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\](.*)/;
    for (const raw of lrcText.split('\n')) {
      const match = re.exec(raw.trim());
      if (match) {
        const total = parseFloat(match[1]) * 60 + parseFloat(match[2]);
        const text = match[3].replace(/<\d{1,2}:\d{2}(?:\.\d{1,3})?>/g, '').trim();
        if (text) lines.push({ time: total, text });
      }
    }
    return lines.sort((a, b) => a.time - b.time);
  }

  function renderLyricsContent() {
    if (!lyricsData || (!lyricsData.plain && (!lyricsData.synced || lyricsData.synced.length === 0))) {
      lyricsContent.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">No synchronized lyrics found for this track.</p>';
      return;
    }

    if (lyricsData.synced && lyricsData.synced.length > 0) {
      lyricsContent.innerHTML = `
        <div id="live-lyrics-lines" style="display: flex; flex-direction: column; gap: 0.65rem; text-align: center;">
          ${lyricsData.synced.map((l, idx) => `
            <div class="live-lyric-line" data-time="${l.time}" style="font-size: 14px; font-weight: 500; color: var(--text-muted); transition: all 0.25s ease; padding: 2px 0;">
              ${escapeHtml(l.text)}
            </div>
          `).join('')}
        </div>
      `;
      updateActiveLyricsLine(localElapsed);
    } else {
      lyricsContent.innerHTML = `
        <div style="white-space: pre-wrap; font-size: 13px; line-height: 1.6; color: var(--text-bright); text-align: center;">
          ${escapeHtml(lyricsData.plain)}
        </div>
      `;
    }
  }

  function updateActiveLyricsLine(timeSec) {
    if (!isLyricsOpen || !lyricsData?.synced?.length) return;
    const lines = lyricsContent.querySelectorAll('.live-lyric-line');
    let activeIdx = -1;

    for (let i = 0; i < lyricsData.synced.length; i++) {
      if (lyricsData.synced[i].time <= timeSec) {
        activeIdx = i;
      } else {
        break;
      }
    }

    lines.forEach((el, idx) => {
      if (idx === activeIdx) {
        el.style.color = '#ffffff';
        el.style.fontWeight = '700';
        el.style.fontSize = '16px';
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else {
        el.style.color = 'var(--text-muted)';
        el.style.fontWeight = '500';
        el.style.fontSize = '14px';
      }
    });
  }

  const btnCloseLyrics = container.querySelector('#btn-close-live-lyrics');
  if (btnCloseLyrics) {
    btnCloseLyrics.onclick = () => {
      isLyricsOpen = false;
      lyricsDrawer.style.display = 'none';
      const btn = nowPlayingContainer?.querySelector('#btn-live-lyrics-toggle');
      if (btn) btn.textContent = '🎤 Live Lyrics';
    };
  }

  // Load initial public state
  async function loadData() {
    try {
      const res = await api.get(`/api/public/live?guildId=${guildId}`);
      if (res?.ok && res.data) {
        currentGuildState = res.data.state;
        currentQueue = res.data.queue;
        renderNowPlaying();
        renderQueue();
      }
    } catch (err) {
      nowPlayingContainer.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 2rem 0;">${escapeHtml(err.message || 'Failed to load stream')}</p>`;
    }
  }

  // Connect WebSocket & Subscribe
  connectWebSocket();
  subscribeToGuild(guildId);

  const unsubscribeWs = addWsListener((evt) => {
    if (evt.kind === 'state' && String(evt.guildId) === String(guildId)) {
      currentGuildState = evt.data;
      renderNowPlaying();
    } else if (evt.kind === 'queue' && String(evt.guildId) === String(guildId)) {
      currentQueue = evt.data;
      renderQueue();
    } else if (evt.kind === 'ws_connected') {
      subscribeToGuild(guildId);
      loadData();
    }
  });

  await loadData();
  startVisualizer();

  return () => {
    if (seekInterval) clearInterval(seekInterval);
    if (animFrameId) cancelAnimationFrame(animFrameId);
    unsubscribeWs();
  };
}

