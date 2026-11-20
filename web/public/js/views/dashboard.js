import { api } from '../api.js';
import { escapeHtml, formatDuration, showToast } from '../ui.js';
import { subscribeToGuild, addWsListener, isWsConnected } from '../ws.js';

export async function render(container, state) {
  const guilds = (state.me?.guilds || []).filter(g => g.tier !== 'none');

  if (!state.me?.agentConnected) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem;">
        <h2 style="color: var(--text-bright); margin-bottom: 0.5rem;">Bot Offline / Disconnected</h2>
        <p style="color: var(--text-muted); margin-bottom: 1.5rem;">
          The Python music bot agent is currently offline or disconnected from the panel.
        </p>
        ${state.me?.isOwner ? `<a href="#control" class="btn btn-primary">Open Bot Control</a>` : ''}
      </div>
    `;
    return;
  }

  if (guilds.length === 0 && !state.me?.isOwner) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem 1.5rem;">
        <h2 style="color: var(--text-bright); margin-bottom: 0.5rem;">No Servers Available</h2>
        <p style="color: var(--text-muted);">You are not a member of any servers that the bot is currently in.</p>
      </div>
    `;
    return;
  }

  let selectedGuildId = guilds[0]?.id || null;
  let currentGuildState = null;
  let currentQueue = null;
  let voiceChannels = [];
  let lastVoiceStateKey = null;
  let isVoiceSelectInteracting = false;
  let pollInterval = null;
  let seekInterval = null;
  let isDraggingSeek = false;
  let localElapsed = 0;

  function getActiveTier() {
    if (state.me?.isOwner) return 'owner';
    const g = guilds.find(x => x.id === selectedGuildId);
    return g ? g.tier : 'none';
  }

  function isDjOrAbove() {
    const t = getActiveTier();
    return ['dj', 'admin', 'owner'].includes(t);
  }

  function isAdminOrAbove() {
    const t = getActiveTier();
    return ['admin', 'owner'].includes(t);
  }

  container.innerHTML = `
    <!-- Top toolbar: Server Selector & Voice Channel -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div style="display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 0.75rem; flex: 1; min-width: 240px;">
          <label class="form-label" style="margin: 0; white-space: nowrap; font-weight: 600;">Server:</label>
          <select id="server-select" class="form-select" style="max-width: 280px;">
            ${guilds.map(g => `
              <option value="${escapeHtml(g.id)}" ${g.id === selectedGuildId ? 'selected' : ''}>
                ${escapeHtml(g.name)} (${escapeHtml(g.tier)})
              </option>
            `).join('')}
          </select>
        </div>

        <div id="voice-controls-bar" style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
          <span style="font-size: 13px; color: var(--text-muted);">Loading voice status...</span>
        </div>
      </div>
    </div>

    <!-- Play input box -->
    <div class="card">
      <div class="card-title">Add Music</div>
      <form id="play-form" style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 260px; position: relative;">
          <input type="text" id="play-input" class="form-control" placeholder="Search YouTube or paste video / playlist link..." autocomplete="off">
          <span id="query-type-badge" style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">Search</span>
        </div>
        <button type="submit" id="btn-play-submit" class="btn btn-primary" style="min-width: 100px;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          Play
        </button>
      </form>
    </div>

    <div class="grid-2">
      <!-- Now Playing Card -->
      <div class="card">
        <div class="card-title">Now Playing</div>
        <div id="now-playing-container">
          <p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Nothing is currently playing.</p>
        </div>
      </div>

      <!-- Queue & History Card -->
      <div class="card">
        <div class="card-title">
          <span>Playback Queue</span>
          <div style="display: flex; gap: 0.5rem;">
            <button id="btn-shuffle" class="btn btn-sm" title="Shuffle Queue" style="display: none;">Shuffle</button>
            <button id="btn-clear" class="btn btn-danger btn-sm" title="Clear Queue" style="display: none;">Clear</button>
          </div>
        </div>
        <div id="queue-container">
          <p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Queue is empty.</p>
        </div>
      </div>
    </div>
  `;

  const serverSelect = container.querySelector('#server-select');
  const playInput = container.querySelector('#play-input');
  const playForm = container.querySelector('#play-form');
  const queryTypeBadge = container.querySelector('#query-type-badge');
  const btnShuffle = container.querySelector('#btn-shuffle');
  const btnClear = container.querySelector('#btn-clear');
  const nowPlayingContainer = container.querySelector('#now-playing-container');
  const queueContainer = container.querySelector('#queue-container');

  // Input query detection
  playInput.oninput = () => {
    const val = playInput.value.trim();
    if (!val) {
      queryTypeBadge.textContent = 'Search';
    } else if (val.includes('list=') && (val.includes('youtube.com') || val.includes('youtu.be'))) {
      queryTypeBadge.textContent = 'YouTube Playlist';
    } else if (val.includes('youtube.com') || val.includes('youtu.be')) {
      queryTypeBadge.textContent = 'YouTube Video';
    } else {
      queryTypeBadge.textContent = 'YouTube Search';
    }
  };

  playForm.onsubmit = async (e) => {
    e.preventDefault();
    const query = playInput.value.trim();
    if (!query) return;

    const btnSubmit = container.querySelector('#btn-play-submit');
    btnSubmit.disabled = true;
    btnSubmit.innerHTML = 'Adding...';

    try {
      const res = await api.rpc('play', selectedGuildId, { query });
      if (res.type === 'playlist') {
        showToast(`Added ${res.count} tracks from YouTube playlist!`, 'success');
      } else {
        showToast(`Added: ${res.title || query}`, 'success');
      }
      playInput.value = '';
      queryTypeBadge.textContent = 'Search';
      await refreshData();
    } catch (_) {
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Play';
    }
  };

  function renderVoiceControls(force = false) {
    const vcContainer = container.querySelector('#voice-controls-bar');
    if (!vcContainer) return;

    const inVoice = Boolean(currentGuildState?.voiceChannel);
    const vcName = currentGuildState?.voiceChannel?.name || '';
    const vcId = currentGuildState?.voiceChannel?.id || '';
    const canLeave = isAdminOrAbove();
    const canSwitch = isDjOrAbove();
    const mode = inVoice ? 'connected' : (canSwitch ? 'joinable' : 'idle');

    // Prevent destroying and recreating the dropdown if user is interacting with it
    const existingSelect = vcContainer.querySelector('#voice-select');
    const isInteracting = isVoiceSelectInteracting || (existingSelect && (document.activeElement === existingSelect || existingSelect.matches(':focus')));

    // If the bar mode is already mounted and user is interacting with the dropdown, don't touch DOM
    if (!force && vcContainer.dataset.mode === mode && isInteracting) {
      return;
    }

    // Compute a state fingerprint
    const channelsSig = voiceChannels.map(c => `${c.id}:${c.userIsHere ? 1 : 0}:${c.memberCount}`).join('|');
    const currentVoiceStateKey = `${mode}:${vcId}:${canLeave ? '1' : '0'}:${canSwitch ? '1' : '0'}:${channelsSig}`;

    // If state hasn't changed at all, no-op
    if (!force && currentVoiceStateKey === lastVoiceStateKey) {
      return;
    }

    // If mode hasn't changed and select exists, update options in-place without rebuilding DOM
    if (!force && vcContainer.dataset.mode === mode && existingSelect && !isInteracting) {
      lastVoiceStateKey = currentVoiceStateKey;
      const prevVal = existingSelect.value;
      const defaultOpt = inVoice ? 'Switch channel...' : 'Select Voice Channel...';
      existingSelect.innerHTML = `
        <option value="">${defaultOpt}</option>
        ${voiceChannels.map(c => `
          <option value="${c.id}" ${c.userIsHere ? 'selected' : ''}>
            ${escapeHtml(c.name)} (${c.memberCount} users)
          </option>
        `).join('')}
      `;
      if (prevVal) existingSelect.value = prevVal;
      return;
    }

    lastVoiceStateKey = currentVoiceStateKey;
    vcContainer.dataset.mode = mode;

    if (inVoice) {
      vcContainer.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
          <div class="voice-pill" title="Currently in voice channel">
            <span class="voice-pulse"></span>
            <span>Connected: <strong>${escapeHtml(vcName)}</strong></span>
          </div>
          ${canSwitch ? `
            <select id="voice-select" class="form-select" style="min-width: 160px; max-width: 210px;" title="Switch voice channel">
              <option value="">Switch channel...</option>
              ${voiceChannels.map(c => `
                <option value="${c.id}" ${c.userIsHere ? 'selected' : ''}>
                  ${escapeHtml(c.name)} (${c.memberCount} users)
                </option>
              `).join('')}
            </select>
            <button id="btn-switch-vc" class="btn btn-sm" title="Move to selected channel">Switch</button>
          ` : ''}
          ${canLeave ? `
            <button id="btn-disconnect-vc" class="btn btn-danger btn-sm" title="Disconnect bot from voice channel">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 2px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              Disconnect
            </button>
          ` : ''}
        </div>
      `;

      const voiceSelect = vcContainer.querySelector('#voice-select');
      if (voiceSelect) {
        voiceSelect.onfocus = () => { isVoiceSelectInteracting = true; };
        voiceSelect.onblur = () => { setTimeout(() => { isVoiceSelectInteracting = false; }, 250); };
        voiceSelect.onchange = () => { isVoiceSelectInteracting = false; };
      }

      const btnDisconnect = vcContainer.querySelector('#btn-disconnect-vc');
      if (btnDisconnect) {
        btnDisconnect.onclick = async () => {
          try {
            await api.rpc('leave', selectedGuildId);
            showToast('Disconnected bot from voice channel', 'info');
            await refreshData();
          } catch (_) { }
        };
      }

      const btnSwitch = vcContainer.querySelector('#btn-switch-vc');
      if (btnSwitch && voiceSelect) {
        btnSwitch.onclick = async () => {
          const chId = voiceSelect.value;
          if (!chId) {
            showToast('Select a target voice channel first', 'error');
            return;
          }
          try {
            await api.rpc('join', selectedGuildId, { channelId: chId });
            showToast('Moved to voice channel', 'success');
            await refreshData();
          } catch (_) { }
        };
      }
    } else {
      if (canSwitch) {
        vcContainer.innerHTML = `
          <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: nowrap;">
            <select id="voice-select" class="form-select" style="min-width: 190px; max-width: 270px;" title="Select voice channel">
              <option value="">Select Voice Channel...</option>
              ${voiceChannels.map(c => `
                <option value="${c.id}" ${c.userIsHere ? 'selected' : ''}>
                  ${escapeHtml(c.name)} (${c.memberCount} users)
                </option>
              `).join('')}
            </select>
            <button id="btn-join-vc" class="btn btn-primary btn-sm" style="white-space: nowrap; display: inline-flex; align-items: center; gap: 5px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
              Join Channel
            </button>
          </div>
        `;

        const voiceSelect = vcContainer.querySelector('#voice-select');
        if (voiceSelect) {
          voiceSelect.onfocus = () => { isVoiceSelectInteracting = true; };
          voiceSelect.onblur = () => { setTimeout(() => { isVoiceSelectInteracting = false; }, 250); };
          voiceSelect.onchange = () => { isVoiceSelectInteracting = false; };
        }

        const btnJoin = vcContainer.querySelector('#btn-join-vc');
        if (btnJoin && voiceSelect) {
          btnJoin.onclick = async () => {
            const chId = voiceSelect.value;
            if (!chId) {
              showToast('Select a voice channel first', 'error');
              return;
            }
            try {
              await api.rpc('join', selectedGuildId, { channelId: chId });
              showToast('Connected to voice channel', 'success');
              await refreshData();
            } catch (_) { }
          };
        }
      } else {
        vcContainer.innerHTML = `
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 13px; color: var(--text-muted);">
              Bot is idle. Request a song below to start playing in your voice channel!
            </span>
          </div>
        `;
      }
    }
  }

  async function loadChannels() {
    if (!selectedGuildId) return;
    try {
      const data = await api.rpc('guild.channels', selectedGuildId);
      voiceChannels = data.channels || [];
      renderVoiceControls();
    } catch (_) { }
  }

  async function refreshData() {
    if (!selectedGuildId) return;
    try {
      const [stateRes, queueRes] = await Promise.all([
        api.rpc('guild.state', selectedGuildId),
        api.rpc('queue.get', selectedGuildId)
      ]);
      currentGuildState = stateRes;
      currentQueue = queueRes;
      renderVoiceControls();
      renderNowPlaying();
      renderQueue();
    } catch (_) { }
  }

  function renderNowPlaying() {
    if (seekInterval) {
      clearInterval(seekInterval);
      seekInterval = null;
    }

    if (!currentGuildState || (!currentGuildState.isPlaying && !currentGuildState.isPaused && !currentGuildState.current)) {
      nowPlayingContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2.5rem 0;">Nothing is currently playing.</p>';
      return;
    }

    const cur = currentGuildState.current || {};
    const isPlaying = currentGuildState.isPlaying;
    const canControl = isDjOrAbove();

    const loopMode = currentGuildState.loop || 'off';
    const volume = currentGuildState.volume || 75;
    const duration = cur.duration || 0;
    localElapsed = cur.elapsed || 0;

    nowPlayingContainer.innerHTML = `
      <div class="now-playing">
        <img src="${cur.thumbnail || 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOTAiIGhlaWdodD0iOTAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzExMTIxNCIvPjwvc3ZnPg=='}" class="track-thumb" alt="Thumbnail">
        <div class="track-details">
          <div class="track-title" title="${escapeHtml(cur.title || 'Unknown Title')}">${escapeHtml(cur.title || 'Unknown Title')}</div>
          <div class="track-artist">${escapeHtml(cur.artist || '')} ${cur.requester ? `&bull; Added by ${escapeHtml(cur.requester)}` : ''}</div>
          <div style="font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 0.5rem;">
            <span>Channel: <strong style="color: var(--text-bright);">${escapeHtml(currentGuildState.voiceChannel?.name || 'Unknown')}</strong></span>
            ${cur.sourceType ? `<span class="badge" style="background: rgba(255, 255, 255, 0.08); font-size: 10px;">${escapeHtml(cur.sourceType.toUpperCase())}</span>` : ''}
          </div>
        </div>
      </div>

      <!-- Progress / Seek Bar -->
      <div class="seek-wrap">
        <div class="seek-time-row">
          <span id="seek-current">${formatDuration(localElapsed)}</span>
          <span id="seek-total">${duration ? formatDuration(duration) : '--:--'}</span>
        </div>
        <input type="range" id="seek-slider" class="seek-slider" min="0" max="${duration || 100}" value="${Math.min(localElapsed, duration || 100)}" step="1" ${(!canControl || !duration) ? 'disabled' : ''} title="${duration ? 'Seek position' : 'Live stream / unknown duration'}">
      </div>

      <div class="playback-controls">
        <button id="btn-prev" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Previous Track">&larr; Prev</button>
        <button id="btn-play-pause" class="btn btn-primary btn-sm" ${!canControl ? 'disabled' : ''}>
          ${isPlaying ? 'Pause' : 'Resume'}
        </button>
        <button id="btn-stop" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Stop Playback">Stop</button>
        <button id="btn-skip" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Skip Track">Skip &rarr;</button>
        <button id="btn-restart" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Restart Track">&#8635; Restart</button>

        <button id="btn-loop" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Toggle Loop Mode">
          Loop: ${escapeHtml(loopMode.toUpperCase())}
        </button>

        <div style="display: flex; align-items: center; gap: 0.35rem; margin-left: auto;">
          <span style="font-size: 12px; color: var(--text-muted);">&#128266;</span>
          <input type="range" id="vol-slider" class="volume-slider" min="0" max="100" value="${volume}" ${!canControl ? 'disabled' : ''} title="Volume">
          <span id="vol-text" style="font-size: 11px; width: 28px; font-family: var(--font-mono);">${volume}%</span>
        </div>
      </div>
    `;

    // Hook seek bar slider
    const seekSlider = nowPlayingContainer.querySelector('#seek-slider');
    const seekCurrent = nowPlayingContainer.querySelector('#seek-current');

    if (seekSlider && duration > 0) {
      seekSlider.onmousedown = () => { isDraggingSeek = true; };
      seekSlider.ontouchstart = () => { isDraggingSeek = true; };

      seekSlider.oninput = () => {
        isDraggingSeek = true;
        localElapsed = Number(seekSlider.value);
        if (seekCurrent) seekCurrent.textContent = formatDuration(localElapsed);
      };

      seekSlider.onchange = async () => {
        isDraggingSeek = false;
        const targetSec = Number(seekSlider.value);
        localElapsed = targetSec;
        try {
          await api.rpc('seek', selectedGuildId, { seconds: targetSec });
          await refreshData();
        } catch (_) { }
      };

      // Realtime client-side elapsed timer while actively playing
      if (isPlaying) {
        seekInterval = setInterval(() => {
          if (!isDraggingSeek && seekSlider) {
            localElapsed += 1;
            if (localElapsed > duration) localElapsed = duration;
            seekSlider.value = localElapsed;
            if (seekCurrent) seekCurrent.textContent = formatDuration(localElapsed);
          }
        }, 1000);
      }
    }

    // Hook playback buttons
    const btnPlayPause = nowPlayingContainer.querySelector('#btn-play-pause');
    const btnStop = nowPlayingContainer.querySelector('#btn-stop');
    const btnSkip = nowPlayingContainer.querySelector('#btn-skip');
    const btnPrev = nowPlayingContainer.querySelector('#btn-prev');
    const btnRestart = nowPlayingContainer.querySelector('#btn-restart');
    const btnLoop = nowPlayingContainer.querySelector('#btn-loop');
    const volSlider = nowPlayingContainer.querySelector('#vol-slider');
    const volText = nowPlayingContainer.querySelector('#vol-text');

    if (btnPlayPause) {
      btnPlayPause.onclick = async () => {
        try {
          if (isPlaying) await api.rpc('pause', selectedGuildId);
          else await api.rpc('resume', selectedGuildId);
          await refreshData();
        } catch (_) { }
      };
    }

    if (btnStop) {
      btnStop.onclick = async () => {
        try {
          await api.rpc('stop', selectedGuildId);
          await refreshData();
        } catch (_) { }
      };
    }

    if (btnSkip) {
      btnSkip.onclick = async () => {
        try {
          await api.rpc('skip', selectedGuildId);
          await refreshData();
        } catch (_) { }
      };
    }

    if (btnPrev) {
      btnPrev.onclick = async () => {
        try {
          await api.rpc('previous', selectedGuildId);
          await refreshData();
        } catch (_) { }
      };
    }

    if (btnRestart) {
      btnRestart.onclick = async () => {
        try {
          await api.rpc('restart', selectedGuildId);
          await refreshData();
        } catch (_) { }
      };
    }

    if (btnLoop) {
      btnLoop.onclick = async () => {
        const nextMode = loopMode === 'off' ? 'track' : (loopMode === 'track' ? 'queue' : 'off');
        try {
          await api.rpc('loop', selectedGuildId, { mode: nextMode });
          await refreshData();
        } catch (_) { }
      };
    }

    if (volSlider) {
      volSlider.oninput = () => {
        volText.textContent = `${volSlider.value}%`;
      };
      volSlider.onchange = async () => {
        try {
          await api.rpc('volume', selectedGuildId, { volume: Number(volSlider.value) });
        } catch (_) { }
      };
    }
  }

  function renderQueue() {
    const upcoming = currentQueue?.upcoming || [];
    const canControl = isDjOrAbove();

    btnShuffle.style.display = canControl && upcoming.length > 1 ? 'inline-block' : 'none';
    btnClear.style.display = canControl && upcoming.length > 0 ? 'inline-block' : 'none';

    if (upcoming.length === 0) {
      queueContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2.5rem 0;">Queue is empty.</p>';
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
            ${canControl ? `
              <div style="display: flex; gap: 0.25rem;">
                ${idx > 0 ? `<button class="btn btn-sm btn-move" data-from="${idx}" data-to="${idx - 1}" title="Move Up">&uarr;</button>` : ''}
                ${idx < upcoming.length - 1 ? `<button class="btn btn-sm btn-move" data-from="${idx}" data-to="${idx + 1}" title="Move Down">&darr;</button>` : ''}
                <button class="btn btn-danger btn-sm btn-remove" data-index="${idx}" title="Remove Track">&times;</button>
              </div>
            ` : ''}
          </li>
        `).join('')}
      </ul>
    `;

    for (const btn of queueContainer.querySelectorAll('.btn-remove')) {
      btn.onclick = async () => {
        const index = Number(btn.getAttribute('data-index'));
        try {
          await api.rpc('queue.remove', selectedGuildId, { index });
          await refreshData();
        } catch (_) { }
      };
    }

    for (const btn of queueContainer.querySelectorAll('.btn-move')) {
      btn.onclick = async () => {
        const from = Number(btn.getAttribute('data-from'));
        const to = Number(btn.getAttribute('data-to'));
        try {
          await api.rpc('queue.move', selectedGuildId, { from, to });
          await refreshData();
        } catch (_) { }
      };
    }
  }

  // Hook toolbar buttons
  serverSelect.onchange = async () => {
    selectedGuildId = serverSelect.value;
    lastVoiceStateKey = null;
    subscribeToGuild(selectedGuildId);
    await loadChannels();
    await refreshData();
  };

  btnShuffle.onclick = async () => {
    try {
      await api.rpc('queue.shuffle', selectedGuildId);
      showToast('Queue shuffled', 'success');
      await refreshData();
    } catch (_) { }
  };

  btnClear.onclick = async () => {
    try {
      await api.rpc('queue.clear', selectedGuildId);
      showToast('Queue cleared', 'info');
      await refreshData();
    } catch (_) { }
  };

  // WS Event Listener
  const unsubscribeWs = addWsListener((evt) => {
    if (evt.kind === 'state' && String(evt.guildId) === String(selectedGuildId)) {
      currentGuildState = evt.data;
      renderVoiceControls();
      renderNowPlaying();
    } else if (evt.kind === 'queue' && String(evt.guildId) === String(selectedGuildId)) {
      currentQueue = evt.data;
      renderQueue();
    } else if (evt.kind === 'ws_connected') {
      refreshData();
    }
  });

  // Re-sync if user returns to this tab from another window/tab
  const onVisibilityChange = () => {
    if (!document.hidden) {
      refreshData();
    }
  };
  document.addEventListener('visibilitychange', onVisibilityChange);

  // Initial load
  subscribeToGuild(selectedGuildId);
  await loadChannels();
  await refreshData();

  // Smart fallback poll: ONLY runs if WebSocket is disconnected and tab is visible
  pollInterval = setInterval(() => {
    if (!isWsConnected() && !document.hidden) {
      refreshData();
    }
  }, 8000);

  return () => {
    if (pollInterval) clearInterval(pollInterval);
    if (seekInterval) clearInterval(seekInterval);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    unsubscribeWs();
  };
}
