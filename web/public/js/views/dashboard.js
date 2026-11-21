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
  let animFrameId = null;
  let isDraggingSeek = false;
  let localElapsed = 0;
  let isLyricsOpen = false;
  let lyricsCache = null;

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
    <div class="card" style="margin-bottom: 1.25rem; padding: 1rem 1.35rem;">
      <div class="topbar-container">
        <div class="topbar-server-group">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--accent);"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
            <label class="form-label" style="margin: 0; white-space: nowrap; font-weight: 600; font-size: 13px;">Server:</label>
            <select id="server-select" class="form-select" style="min-width: 170px; max-width: 250px; font-weight: 600;">
              ${guilds.map(g => `
                <option value="${escapeHtml(g.id)}" ${g.id === selectedGuildId ? 'selected' : ''}>
                  ${escapeHtml(g.name)} (${escapeHtml(g.tier)})
                </option>
              `).join('')}
            </select>
          </div>
          <button id="btn-share-listener" class="btn btn-sm" style="display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;" title="Copy public link so friends can listen & watch in real-time without logging in">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
            Share Live Link
          </button>
        </div>

        <div id="voice-controls-bar" class="topbar-voice-group">
          <span style="font-size: 13px; color: var(--text-muted);">Loading voice status...</span>
        </div>
      </div>
    </div>

    <!-- Play input box -->
    <div class="card" style="margin-bottom: 1.25rem;">
      <div class="card-title" style="margin-bottom: 0.75rem;">
        <span style="display: inline-flex; align-items: center; gap: 6px;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="color: var(--accent);"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          Add Music
        </span>
        <div style="display: flex; gap: 0.85rem; align-items: center; font-size: 11px; font-weight: 500;">
          <span class="source-pill-yt"><span style="width: 6px; height: 6px; border-radius: 50%; background: currentColor;"></span> YouTube</span>
          <span class="source-pill-sp"><span style="width: 6px; height: 6px; border-radius: 50%; background: currentColor;"></span> Spotify</span>
          <span class="source-pill-sc"><span style="width: 6px; height: 6px; border-radius: 50%; background: currentColor;"></span> SoundCloud</span>
        </div>
      </div>
      <form id="play-form" style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 260px; position: relative;">
          <input type="text" id="play-input" class="form-control" placeholder="Search track name, or paste YouTube, Spotify, or SoundCloud link..." autocomplete="off">
          <span id="query-type-badge" style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">Search</span>
        </div>
        <button type="submit" id="btn-play-submit" class="btn btn-primary" style="min-width: 105px; gap: 6px;">
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
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span>Playback Queue</span>
            <span id="queue-header-summary" style="font-size: 12px; color: var(--text-muted); font-weight: normal;"></span>
          </div>
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
  const btnShareListener = container.querySelector('#btn-share-listener');
  const playInput = container.querySelector('#play-input');
  const playForm = container.querySelector('#play-form');
  const queryTypeBadge = container.querySelector('#query-type-badge');
  const btnShuffle = container.querySelector('#btn-shuffle');
  const btnClear = container.querySelector('#btn-clear');
  const nowPlayingContainer = container.querySelector('#now-playing-container');
  const queueContainer = container.querySelector('#queue-container');

  if (btnShareListener) {
    btnShareListener.onclick = () => {
      if (!selectedGuildId) return;
      const shareUrl = `${location.origin}/#live?guild=${selectedGuildId}`;
      navigator.clipboard.writeText(shareUrl).then(() => {
        showToast('Public live listener link copied to clipboard!', 'success');
      }).catch(() => {
        window.prompt('Copy and share this live link:', shareUrl);
      });
    };
  }

  // Input query detection
  playInput.oninput = () => {
    const val = playInput.value.trim();
    if (!val) {
      queryTypeBadge.textContent = 'Search';
    } else if (val.includes('spotify.com')) {
      if (val.includes('/playlist/')) queryTypeBadge.textContent = 'Spotify Playlist';
      else if (val.includes('/album/')) queryTypeBadge.textContent = 'Spotify Album';
      else queryTypeBadge.textContent = 'Spotify Track';
    } else if (val.includes('soundcloud.com')) {
      queryTypeBadge.textContent = 'SoundCloud';
    } else if (val.includes('list=') && (val.includes('youtube.com') || val.includes('youtu.be'))) {
      queryTypeBadge.textContent = 'YouTube Playlist';
    } else if (val.includes('youtube.com') || val.includes('youtu.be')) {
      queryTypeBadge.textContent = 'YouTube Video';
    } else {
      queryTypeBadge.textContent = 'Search';
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
      if (res?.type === 'playlist') {
        if (!res.count) {
          showToast('No tracks could be loaded from playlist', 'error');
        } else {
          showToast(`Added ${res.count} tracks from YouTube playlist!`, 'success');
        }
      } else {
        showToast(`Added: ${res?.title || query}`, 'success');
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
    const voiceStats = currentGuildState?.voiceStats;
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
    const vsSig = voiceStats ? `${voiceStats.region}:${voiceStats.latencyMs}:${voiceStats.isOptimal}` : '';
    const currentVoiceStateKey = `${mode}:${vcId}:${canLeave ? '1' : '0'}:${canSwitch ? '1' : '0'}:${vsSig}:${channelsSig}`;

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
        <div class="voice-status-subgroup">
          <div class="voice-pill" title="Currently in voice channel">
            <span class="voice-pulse"></span>
            <span>Connected: <strong>${escapeHtml(vcName)}</strong></span>
          </div>
          ${voiceStats?.region ? `
            <div class="badge" style="font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; background: rgba(87, 242, 135, 0.15); color: var(--success); cursor: help;" title="Connected to Discord voice server: ${escapeHtml(voiceStats.endpoint || voiceStats.region)} (Audio Ping: ${voiceStats.latencyMs ? voiceStats.latencyMs + 'ms' : 'low'})">
              <span>📍 ${escapeHtml(voiceStats.region)}</span>
              ${voiceStats.latencyMs ? `<span>• <strong>${Math.round(voiceStats.latencyMs)}ms</strong></span>` : ''}
            </div>
          ` : ''}
          ${voiceStats?.canOptimize && !voiceStats?.isOptimal ? `
            <button id="btn-optimize-vc" class="btn btn-sm btn-outline" style="font-size: 11px; padding: 2.5px 8px; border-color: rgba(88, 101, 242, 0.4); color: #a5b3f7; display: inline-flex; align-items: center; gap: 4px;" title="Set voice channel region to Frankfurt (0-5ms ping to bot)">
              ⚡ Optimize to Frankfurt
            </button>
          ` : ''}
        </div>

        <div class="voice-actions-subgroup">
          ${canSwitch ? `
            <select id="voice-select" class="form-select form-select-sm" style="min-width: 145px; max-width: 195px;" title="Switch voice channel">
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
            <button id="btn-disconnect-vc" class="btn btn-danger btn-sm" style="white-space: nowrap;" title="Disconnect bot from voice channel">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 2px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              Disconnect
            </button>
          ` : ''}
        </div>
      `;

      const btnOptimize = vcContainer.querySelector('#btn-optimize-vc');
      if (btnOptimize) {
        btnOptimize.onclick = async () => {
          btnOptimize.disabled = true;
          btnOptimize.textContent = 'Optimizing...';
          try {
            await api.rpc('voice.optimize', { region: 'frankfurt' });
            showToast('Voice channel region optimized to Frankfurt!', 'success');
          } catch (err) {
            showToast(`Optimization failed: ${err.message}`, 'error');
            btnOptimize.disabled = false;
            btnOptimize.textContent = '⚡ Optimize to Frankfurt';
          }
        };
      }

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
    const serverElapsed = Number(cur.elapsed || 0);
    if (!isDraggingSeek) {
      if (Math.abs(localElapsed - serverElapsed) > 1.2 || !isPlaying) {
        localElapsed = serverElapsed;
      }
    }

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

      <!-- Canvas Audio Spectrum Visualizer -->
      <canvas id="dashboard-visualizer" class="audio-spectrum" height="32" style="width: 100%; border-radius: var(--radius-sm); margin: 0.75rem 0 0.5rem 0; background: rgba(0, 0, 0, 0.2); display: block;"></canvas>

      <!-- Progress / Seek Bar -->
      <div class="seek-wrap">
        <div class="seek-time-row">
          <span id="seek-current">${formatDuration(localElapsed)}</span>
          <span id="seek-total">${duration ? formatDuration(duration) : '--:--'}</span>
        </div>
        <input type="range" id="seek-slider" class="seek-slider" min="0" max="${duration || 100}" value="${Math.min(localElapsed, duration || 100)}" step="1" ${(!canControl || !duration) ? 'disabled' : ''} title="${duration ? 'Seek position' : 'Live stream / unknown duration'}">
      </div>

      <div class="playback-controls-row">
        <div class="playback-transport-group">
          <button id="btn-prev" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Previous Track" style="padding: 0.45rem 0.75rem;">
            &larr; Prev
          </button>
          <button id="btn-play-pause" class="btn btn-primary btn-sm" ${!canControl ? 'disabled' : ''} style="min-width: 82px; padding: 0.45rem 0.95rem; font-weight: 600;">
            ${isPlaying ? 'Pause' : 'Resume'}
          </button>
          <button id="btn-stop" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Stop Playback" style="padding: 0.45rem 0.75rem;">
            Stop
          </button>
          <button id="btn-skip" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Skip Track" style="padding: 0.45rem 0.75rem;">
            Skip &rarr;
          </button>
          <button id="btn-restart" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Restart Track" style="padding: 0.45rem 0.75rem;">
            &#8635; Restart
          </button>
        </div>

        <div class="playback-utility-group">
          <button id="btn-loop" class="btn btn-sm" ${!canControl ? 'disabled' : ''} title="Toggle Loop Mode" style="padding: 0.45rem 0.75rem;">
            Loop: ${escapeHtml(loopMode.toUpperCase())}
          </button>

          <button id="btn-toggle-lyrics" class="btn btn-sm ${isLyricsOpen ? 'btn-primary' : ''}" style="padding: 0.45rem 0.75rem;" title="Synchronized Karaoke Lyrics">
            🎤 Lyrics
          </button>

          <div style="display: flex; align-items: center; gap: 0.4rem; padding-left: 0.65rem; border-left: 1px solid var(--border);">
            <span style="font-size: 13px; color: var(--text-muted);">&#128266;</span>
            <input type="range" id="vol-slider" class="volume-slider" min="0" max="100" value="${volume}" ${!canControl ? 'disabled' : ''} title="Volume">
            <span id="vol-text" style="font-size: 11px; width: 28px; font-family: var(--font-mono); color: var(--text-muted);">${volume}%</span>
          </div>
        </div>
      </div>

      <!-- Karaoke / Synchronized Lyrics Drawer -->
      <div id="lyrics-drawer" class="lyrics-drawer" style="display: ${isLyricsOpen ? 'block' : 'none'}; margin-top: 1rem; padding: 0.85rem; background: rgba(0, 0, 0, 0.25); border: 1px solid var(--border); border-radius: var(--radius-md); max-height: 250px; overflow-y: auto;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.35rem;">
          <span style="font-weight: 600; font-size: 13px; color: var(--text-bright);">🎤 Synchronized Lyrics (Karaoke)</span>
          <button id="btn-close-lyrics" class="btn btn-sm" style="padding: 2px 8px; font-size: 11px;">Close</button>
        </div>
        <div id="lyrics-content">
          <p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">Click Lyrics to load</p>
        </div>
      </div>
    `;

    // Start Visualizer Canvas
    const canvas = nowPlayingContainer.querySelector('#dashboard-visualizer');
    if (canvas) {
      if (animFrameId) cancelAnimationFrame(animFrameId);
      const ctx = canvas.getContext('2d');
      let phase = 0;

      function draw() {
        if (!canvas.parentElement) return;
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = canvas.offsetHeight;
        ctx.clearRect(0, 0, w, h);

        const bars = 48;
        const barWidth = w / bars;
        phase += 0.05;

        for (let i = 0; i < bars; i++) {
          let barHeight = 3;
          if (isPlaying) {
            const sin1 = Math.sin(phase + i * 0.35);
            const sin2 = Math.cos(phase * 0.7 + i * 0.2);
            const val = (sin1 + sin2 + 2) / 4;
            barHeight = Math.max(3, val * (h - 4));
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

    // Lyrics helper functions
    function updateActiveLyrics(timeSec) {
      if (!isLyricsOpen || !lyricsCache?.syncedLyrics?.length) return;
      const lyricsBody = nowPlayingContainer.querySelector('#lyrics-content');
      if (!lyricsBody) return;
      const lines = lyricsBody.querySelectorAll('.lyric-line');
      let activeIdx = -1;

      for (let i = 0; i < lyricsCache.syncedLyrics.length; i++) {
        if (lyricsCache.syncedLyrics[i].time <= timeSec) {
          activeIdx = i;
        } else {
          break;
        }
      }

      lines.forEach((el, idx) => {
        if (idx === activeIdx) {
          if (!el.classList.contains('active')) {
            el.classList.add('active');
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        } else {
          el.classList.remove('active');
        }
      });
    }

    function renderLyricsDrawer(content) {
      if (!content) return;
      if (!lyricsCache || (!lyricsCache.plainLyrics && (!lyricsCache.syncedLyrics || lyricsCache.syncedLyrics.length === 0))) {
        content.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">No lyrics available for this track.</p>';
        return;
      }

      if (lyricsCache.syncedLyrics && lyricsCache.syncedLyrics.length > 0) {
        content.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 0.35rem;">
            ${lyricsCache.syncedLyrics.map((l) => `
              <div class="lyric-line" data-time="${l.time}">
                ${escapeHtml(l.text)}
              </div>
            `).join('')}
          </div>
        `;

        for (const lineEl of content.querySelectorAll('.lyric-line')) {
          lineEl.onclick = async () => {
            const targetSec = parseFloat(lineEl.getAttribute('data-time'));
            if (!isNaN(targetSec) && canControl) {
              try {
                await api.rpc('seek', selectedGuildId, { seconds: targetSec });
                localElapsed = targetSec;
                updateActiveLyrics(localElapsed);
              } catch (_) { }
            }
          };
        }
        updateActiveLyrics(localElapsed);
      } else {
        content.innerHTML = `
          <div style="white-space: pre-wrap; font-size: 13px; line-height: 1.6; color: var(--text-bright); text-align: center;">
            ${escapeHtml(lyricsCache.plainLyrics)}
          </div>
        `;
      }
    }

    async function toggleLyrics(currentTrack) {
      const drawer = nowPlayingContainer.querySelector('#lyrics-drawer');
      const content = nowPlayingContainer.querySelector('#lyrics-content');
      if (!drawer || !content) return;

      isLyricsOpen = !isLyricsOpen;
      drawer.style.display = isLyricsOpen ? 'block' : 'none';
      if (!isLyricsOpen) return;

      if (!lyricsCache || lyricsCache.trackTitle !== currentTrack.title) {
        content.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 1.5rem 0;">Fetching synchronized lyrics...</p>';
        try {
          const raw = await api.rpc('lyrics.get', selectedGuildId, {
            title: currentTrack.title,
            artist: currentTrack.artist
          });
          const lyricsData = raw?.data || raw;
          if (lyricsData && (lyricsData.syncedLyrics?.length || lyricsData.plainLyrics)) {
            lyricsCache = {
              trackTitle: currentTrack.title,
              syncedLyrics: lyricsData.syncedLyrics || [],
              plainLyrics: lyricsData.plainLyrics || ''
            };
          } else {
            lyricsCache = { trackTitle: currentTrack.title, syncedLyrics: [], plainLyrics: null };
          }
        } catch (_) {
          lyricsCache = { trackTitle: currentTrack.title, syncedLyrics: [], plainLyrics: null };
        }
      }

      renderLyricsDrawer(content);
    }

    // Hook Lyrics Button
    const btnToggleLyrics = nowPlayingContainer.querySelector('#btn-toggle-lyrics');
    if (btnToggleLyrics) {
      btnToggleLyrics.onclick = () => toggleLyrics(cur);
    }

    const btnCloseLyrics = nowPlayingContainer.querySelector('#btn-close-lyrics');
    if (btnCloseLyrics) {
      btnCloseLyrics.onclick = () => {
        isLyricsOpen = false;
        const drawer = nowPlayingContainer.querySelector('#lyrics-drawer');
        if (drawer) drawer.style.display = 'none';
      };
    }

    // Restore open lyrics view if already open on re-render
    if (isLyricsOpen) {
      const lyricsContent = nowPlayingContainer.querySelector('#lyrics-content');
      if (lyricsCache && lyricsCache.trackTitle === cur.title) {
        renderLyricsDrawer(lyricsContent);
      } else {
        toggleLyrics(cur);
      }
    }

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

      // Realtime high-precision client timer (250ms interval) for ultra-tight lyrics and progress sync
      if (isPlaying) {
        seekInterval = setInterval(() => {
          if (!isDraggingSeek && seekSlider) {
            localElapsed += 0.25;
            if (localElapsed > duration) localElapsed = duration;
            seekSlider.value = Math.round(localElapsed);
            if (seekCurrent) seekCurrent.textContent = formatDuration(Math.round(localElapsed));
          }
          updateActiveLyrics(localElapsed);
        }, 250);
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

    const queueSummary = container.querySelector('#queue-header-summary');
    if (queueSummary) {
      if (upcoming.length > 0) {
        const totalSec = upcoming.reduce((acc, t) => acc + (t.duration || 0), 0);
        queueSummary.textContent = `• ${upcoming.length} tracks (${formatDuration(totalSec)})`;
      } else {
        queueSummary.textContent = '';
      }
    }

    btnShuffle.style.display = canControl && upcoming.length > 1 ? 'inline-block' : 'none';
    btnClear.style.display = canControl && upcoming.length > 0 ? 'inline-block' : 'none';

    if (upcoming.length === 0) {
      queueContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2.5rem 0;">Queue is empty.</p>';
      return;
    }

    queueContainer.innerHTML = `
      <ul class="list-group" id="queue-list" style="max-height: 400px; overflow-y: auto;">
        ${upcoming.map((t, idx) => `
          <li class="list-item queue-item" draggable="${canControl ? 'true' : 'false'}" data-index="${idx}">
            ${canControl ? `<span class="drag-handle" title="Drag to reorder">&#8942;&#8942;</span>` : ''}
            <span style="font-size: 12px; color: var(--text-muted); width: 26px; font-family: var(--font-mono); text-align: center;">#${idx + 1}</span>
            <div style="flex: 1; min-width: 0; padding-right: 0.5rem;">
              <div style="font-weight: 500; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-bright);" title="${escapeHtml(t.title)}">
                ${escapeHtml(t.title)}
              </div>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                ${escapeHtml(t.artist || '')} &bull; ${formatDuration(t.duration)} ${t.requester ? `&bull; Added by ${escapeHtml(t.requester)}` : ''}
              </div>
            </div>
            ${canControl ? `
              <div class="queue-btn-group">
                <button class="btn btn-primary btn-sm queue-action-btn btn-queue-play" data-index="${idx}" title="Play Track Now">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                </button>
                <button class="btn btn-sm queue-action-btn btn-move" data-from="${idx}" data-to="${idx - 1}" title="Move Up" ${idx === 0 ? 'disabled style="opacity: 0.15; cursor: default;"' : ''}>&uarr;</button>
                <button class="btn btn-sm queue-action-btn btn-move" data-from="${idx}" data-to="${idx + 1}" title="Move Down" ${idx === upcoming.length - 1 ? 'disabled style="opacity: 0.15; cursor: default;"' : ''}>&darr;</button>
                <button class="btn btn-danger btn-sm queue-action-btn btn-remove" data-index="${idx}" title="Remove Track">&times;</button>
              </div>
            ` : ''}
          </li>
        `).join('')}
      </ul>
    `;

    // Drag-and-drop queue reordering
    if (canControl) {
      let draggedIdx = null;
      const items = queueContainer.querySelectorAll('.queue-item');

      items.forEach(item => {
        item.addEventListener('dragstart', (e) => {
          draggedIdx = Number(item.getAttribute('data-index'));
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', String(draggedIdx));
          item.classList.add('is-dragging');
        });

        item.addEventListener('dragover', (e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          const targetIdx = Number(item.getAttribute('data-index'));
          if (targetIdx === draggedIdx) return;

          const rect = item.getBoundingClientRect();
          const relY = e.clientY - rect.top;
          if (relY < rect.height / 2) {
            item.classList.add('drag-over-top');
            item.classList.remove('drag-over-bottom');
          } else {
            item.classList.add('drag-over-bottom');
            item.classList.remove('drag-over-top');
          }
        });

        item.addEventListener('dragleave', () => {
          item.classList.remove('drag-over-top', 'drag-over-bottom');
        });

        item.addEventListener('dragend', () => {
          items.forEach(el => el.classList.remove('is-dragging', 'drag-over-top', 'drag-over-bottom'));
          draggedIdx = null;
        });

        item.addEventListener('drop', async (e) => {
          e.preventDefault();
          item.classList.remove('drag-over-top', 'drag-over-bottom');
          const targetIdx = Number(item.getAttribute('data-index'));
          if (draggedIdx === null || draggedIdx === targetIdx) return;

          const from = draggedIdx;
          const to = targetIdx;
          draggedIdx = null;

          // Optimistic local update
          const moved = upcoming.splice(from, 1)[0];
          upcoming.splice(to, 0, moved);
          renderQueue();

          try {
            await api.rpc('queue.move', selectedGuildId, { from, to });
            await refreshData();
          } catch (_) {
            await refreshData();
          }
        });
      });
    }

    for (const btn of queueContainer.querySelectorAll('.btn-remove')) {
      btn.onclick = async () => {
        const index = Number(btn.getAttribute('data-index'));
        try {
          await api.rpc('queue.remove', selectedGuildId, { index });
          await refreshData();
        } catch (_) { }
      };
    }

    for (const btn of queueContainer.querySelectorAll('.btn-queue-play')) {
      btn.onclick = async () => {
        const index = Number(btn.getAttribute('data-index'));
        btn.disabled = true;
        btn.innerHTML = '&#8987;';
        try {
          await api.rpc('queue.play', selectedGuildId, { index });
          await refreshData();
        } catch (_) {
          await refreshData();
        }
      };
    }

    for (const btn of queueContainer.querySelectorAll('.btn-move:not([disabled])')) {
      btn.onclick = async () => {
        const from = Number(btn.getAttribute('data-from'));
        const to = Number(btn.getAttribute('data-to'));
        if (isNaN(from) || isNaN(to) || from === to) return;
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
    if (animFrameId) cancelAnimationFrame(animFrameId);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    unsubscribeWs();
  };
}
