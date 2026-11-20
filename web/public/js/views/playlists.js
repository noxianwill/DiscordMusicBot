import { api } from '../api.js';
import { escapeHtml, formatDuration, showToast, confirmDialog, promptDialog } from '../ui.js';
import { addWsListener } from '../ws.js';

export async function render(container, state) {
  const isOwner = Boolean(state.me?.isOwner);
  let playlists = [];
  let selectedPlaylist = null;
  let playlistTracks = [];

  // YouTube import state
  let fetchedVideos = [];
  let selectedVideoUrls = new Set();

  container.innerHTML = `
    <!-- YouTube Import Panel (Owner only) -->
    ${isOwner ? `
      <div id="yt-import-card" class="card" style="display: none; margin-bottom: 1.5rem; border: 1px solid rgba(255, 60, 60, 0.35); background: linear-gradient(180deg, rgba(45, 20, 20, 0.4) 0%, rgba(25, 25, 28, 0.8) 100%);">
        <div class="card-title" style="font-size: 15px; margin-bottom: 0.75rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem; color: #ff5555;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
            <span>Import Audio from YouTube (Single Video or Full Playlist)</span>
          </div>
          <button id="btn-close-yt-import" class="btn btn-sm" style="padding: 2px 8px;">&times;</button>
        </div>
        <p style="font-size: 12.5px; color: var(--text-muted); margin-bottom: 1.25rem;">
          Inspects any YouTube video or playlist link, allows choosing which songs to import, and converts them to local MP3s using server cookies.
        </p>

        <!-- Step 1: URL input & inspect button -->
        <div style="display: flex; gap: 0.75rem; align-items: flex-end; margin-bottom: 1rem; flex-wrap: wrap;">
          <div style="flex: 1; min-width: 260px;">
            <label class="form-label" style="font-size: 12px;">YouTube Link:</label>
            <input type="text" id="yt-url-input" class="form-control" placeholder="Paste YouTube video or playlist link (e.g. https://www.youtube.com/playlist?list=...)" autocomplete="off">
          </div>
          <button id="btn-fetch-yt" class="btn btn-primary" style="white-space: nowrap; min-width: 140px; padding: 0.65rem 1.15rem;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            Inspect Videos
          </button>
        </div>

        <!-- Step 2: Video checklist (revealed after fetching) -->
        <div id="yt-selection-section" style="display: none; margin-bottom: 1.25rem; background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: var(--radius); padding: 1rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span id="yt-playlist-title" style="font-weight: 600; color: var(--text-bright); font-size: 13.5px;"></span>
              <span id="yt-selected-count-badge" class="badge" style="background: var(--accent); font-size: 11px;">0 selected</span>
            </div>
            <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
              <button id="btn-select-all" class="btn btn-sm">Select All</button>
              <button id="btn-deselect-all" class="btn btn-sm">Deselect All</button>
              <input type="text" id="yt-filter-input" class="form-control" style="width: 170px; padding: 0.25rem 0.5rem; font-size: 12px;" placeholder="Filter songs...">
            </div>
          </div>

          <!-- Video items container -->
          <div id="yt-videos-list" style="max-height: 280px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.35rem; padding-right: 0.25rem;">
          </div>
        </div>

        <!-- Step 3: Target Folder & Download trigger -->
        <div id="yt-target-row" style="display: none; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; align-items: flex-end; margin-bottom: 1rem; padding-top: 1rem; border-top: 1px solid var(--border);">
          <div class="form-group" style="margin: 0;">
            <label class="form-label" style="font-size: 12px;">Save To Playlist Folder:</label>
            <div style="display: flex; gap: 0.5rem;">
              <select id="yt-target-select" class="form-select" style="flex: 1;">
                <option value="__new__">+ Create New Folder...</option>
              </select>
              <input type="text" id="yt-new-name-input" class="form-control" style="flex: 1;" placeholder="Folder name (e.g. gym_mix)">
            </div>
          </div>

          <div style="display: flex; justify-content: flex-end; gap: 0.75rem;">
            <button id="btn-cancel-yt-import" class="btn btn-sm">Cancel</button>
            <button id="btn-submit-yt-import" class="btn btn-primary btn-sm" style="background: linear-gradient(135deg, #da373c 0%, #a1282c 100%); font-weight: 600;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
              Download Selected (<span id="yt-download-btn-count">0</span> tracks)
            </button>
          </div>
        </div>

        <!-- Live Download Progress Output -->
        <div id="yt-progress-box" style="display: none; margin-top: 1rem; padding: 0.75rem 1rem; background: rgba(0, 0, 0, 0.4); border-radius: var(--radius); border-left: 4px solid var(--accent);">
          <div style="display: flex; align-items: center; gap: 0.6rem; font-size: 13px;">
            <span id="yt-prog-icon" style="display: inline-block;">
              <span class="voice-pulse" style="background: var(--accent); box-shadow: 0 0 8px var(--accent);"></span>
            </span>
            <span id="yt-prog-text" style="font-family: var(--font-mono); font-size: 12px; color: var(--text-bright); flex: 1; word-break: break-all;">
              Preparing download...
            </span>
          </div>
        </div>
      </div>
    ` : ''}

    <div class="grid-2">
      <!-- Playlists column -->
      <div class="card">
        <div class="card-title">
          <span>Local Playlists</span>
          <div style="display: flex; gap: 0.4rem;">
            ${isOwner ? `
              <button id="btn-open-yt-import" class="btn btn-sm" style="background: rgba(255, 60, 60, 0.15); border: 1px solid rgba(255, 60, 60, 0.3); color: #ff6666;" title="Import from YouTube">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z"/></svg>
                Import YouTube
              </button>
              <button id="btn-create-pl" class="btn btn-primary btn-sm">+ New Folder</button>
            ` : ''}
          </div>
        </div>
        <div id="playlists-list-container">
          <p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Loading playlists...</p>
        </div>
      </div>

      <!-- Tracks / Details column -->
      <div class="card">
        <div class="card-title">
          <span id="tracks-title">Playlist Tracks</span>
          <div id="playlist-actions" style="display: none; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
            <button id="btn-play-all" class="btn btn-primary btn-sm">&#9654; Play All</button>
            <label style="display: flex; align-items: center; gap: 0.35rem; font-size: 12px; color: var(--text-muted); cursor: pointer;">
              <input type="checkbox" id="chk-shuffle"> Shuffle
            </label>
            ${isOwner ? `
              <button id="btn-add-yt-to-current" class="btn btn-sm" style="color: #ff6666;" title="Add YouTube video to this folder">+ YouTube</button>
              <button id="btn-rename-pl" class="btn btn-sm">Rename</button>
              <button id="btn-delete-pl" class="btn btn-danger btn-sm">Delete</button>
            ` : ''}
          </div>
        </div>

        <div id="tracks-container">
          <p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Select a playlist to view tracks.</p>
        </div>

        ${isOwner ? `
          <!-- Drag-and-drop upload zone -->
          <div id="upload-section" style="margin-top: 1.5rem; display: none;">
            <div class="card-title" style="font-size: 14px;">Upload Local Audio Files</div>
            <div id="drop-zone" class="drop-zone">
              <p style="margin-bottom: 0.5rem; font-weight: 500; color: var(--text-bright);">Drag & drop audio files here</p>
              <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 1rem;">Supports .mp3, .flac, .ogg, .wav (up to 100 MB per file)</p>
              <input type="file" id="file-input" multiple accept=".mp3,.flac,.ogg,.wav" style="display: none;">
              <button type="button" id="btn-browse" class="btn btn-sm">Choose Files</button>
            </div>
            <div id="upload-progress-container" style="margin-top: 1rem;"></div>
          </div>
        ` : ''}
      </div>
    </div>
  `;

  const playlistsListContainer = container.querySelector('#playlists-list-container');
  const tracksTitle = container.querySelector('#tracks-title');
  const playlistActions = container.querySelector('#playlist-actions');
  const tracksContainer = container.querySelector('#tracks-container');
  const uploadSection = container.querySelector('#upload-section');
  const dropZone = container.querySelector('#drop-zone');
  const fileInput = container.querySelector('#file-input');
  const btnBrowse = container.querySelector('#btn-browse');
  const btnCreatePl = container.querySelector('#btn-create-pl');
  const btnPlayAll = container.querySelector('#btn-play-all');
  const chkShuffle = container.querySelector('#chk-shuffle');
  const btnRenamePl = container.querySelector('#btn-rename-pl');
  const btnDeletePl = container.querySelector('#btn-delete-pl');
  const btnAddYtToCurrent = container.querySelector('#btn-add-yt-to-current');
  const uploadProgressContainer = container.querySelector('#upload-progress-container');

  // YouTube import elements
  const ytImportCard = container.querySelector('#yt-import-card');
  const btnOpenYtImport = container.querySelector('#btn-open-yt-import');
  const btnCloseYtImport = container.querySelector('#btn-close-yt-import');
  const btnCancelYtImport = container.querySelector('#btn-cancel-yt-import');
  const btnFetchYt = container.querySelector('#btn-fetch-yt');
  const btnSubmitYtImport = container.querySelector('#btn-submit-yt-import');
  const ytUrlInput = container.querySelector('#yt-url-input');
  const ytSelectionSection = container.querySelector('#yt-selection-section');
  const ytPlaylistTitle = container.querySelector('#yt-playlist-title');
  const ytSelectedCountBadge = container.querySelector('#yt-selected-count-badge');
  const ytVideosList = container.querySelector('#yt-videos-list');
  const btnSelectAll = container.querySelector('#btn-select-all');
  const btnDeselectAll = container.querySelector('#btn-deselect-all');
  const ytFilterInput = container.querySelector('#yt-filter-input');
  const ytTargetRow = container.querySelector('#yt-target-row');
  const ytTargetSelect = container.querySelector('#yt-target-select');
  const ytNewNameInput = container.querySelector('#yt-new-name-input');
  const ytDownloadBtnCount = container.querySelector('#yt-download-btn-count');
  const ytProgressBox = container.querySelector('#yt-progress-box');
  const ytProgText = container.querySelector('#yt-prog-text');

  function updateYtTargetDropdown() {
    if (!ytTargetSelect) return;
    ytTargetSelect.innerHTML = `
      <option value="__new__">+ Create New Folder...</option>
      ${playlists.map(p => `
        <option value="${escapeHtml(p.name)}" ${selectedPlaylist === p.name ? 'selected' : ''}>
          Folder: ${escapeHtml(p.name)}
        </option>
      `).join('')}
    `;
    if (ytNewNameInput) {
      ytNewNameInput.style.display = ytTargetSelect.value === '__new__' ? 'block' : 'none';
    }
  }

  function updateYtSelectionUI() {
    const total = fetchedVideos.length;
    const count = selectedVideoUrls.size;

    if (ytSelectedCountBadge) {
      ytSelectedCountBadge.textContent = `${count} / ${total} selected`;
    }
    if (ytDownloadBtnCount) {
      ytDownloadBtnCount.textContent = count;
    }
    if (btnSubmitYtImport) {
      btnSubmitYtImport.disabled = (count === 0);
    }
  }

  function renderYtVideosList() {
    if (!ytVideosList) return;
    const filterText = (ytFilterInput?.value || '').trim().toLowerCase();

    ytVideosList.innerHTML = fetchedVideos.map((v, idx) => {
      const isSelected = selectedVideoUrls.has(v.url);
      const isMatch = !filterText || (v.title || '').toLowerCase().includes(filterText);

      return `
        <div class="yt-video-row" data-url="${escapeHtml(v.url)}" style="display: ${isMatch ? 'flex' : 'none'}; align-items: center; gap: 0.65rem; padding: 0.45rem 0.65rem; background: ${isSelected ? 'rgba(88, 101, 242, 0.12)' : 'rgba(255, 255, 255, 0.03)'}; border: 1px solid ${isSelected ? 'rgba(88, 101, 242, 0.35)' : 'rgba(255, 255, 255, 0.05)'}; border-radius: 6px; cursor: pointer; transition: background 0.1s ease;">
          <input type="checkbox" class="yt-video-chk" data-url="${escapeHtml(v.url)}" ${isSelected ? 'checked' : ''} style="cursor: pointer; width: 15px; height: 15px; accent-color: var(--accent);">
          <span style="font-size: 11px; color: var(--text-muted); width: 28px; font-family: var(--font-mono);">#${idx + 1}</span>
          <span style="flex: 1; font-size: 13px; color: var(--text-bright); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(v.title)}">
            ${escapeHtml(v.title)}
          </span>
          <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">
            ${v.duration ? formatDuration(v.duration) : '--:--'}
          </span>
        </div>
      `;
    }).join('');

    // Attach row / checkbox click events
    for (const row of ytVideosList.querySelectorAll('.yt-video-row')) {
      const url = row.getAttribute('data-url');
      const chk = row.querySelector('.yt-video-chk');

      row.onclick = (e) => {
        if (e.target !== chk) {
          chk.checked = !chk.checked;
        }
        if (chk.checked) {
          selectedVideoUrls.add(url);
          row.style.background = 'rgba(88, 101, 242, 0.12)';
          row.style.borderColor = 'rgba(88, 101, 242, 0.35)';
        } else {
          selectedVideoUrls.delete(url);
          row.style.background = 'rgba(255, 255, 255, 0.03)';
          row.style.borderColor = 'rgba(255, 255, 255, 0.05)';
        }
        updateYtSelectionUI();
      };
    }
  }

  if (btnFetchYt) {
    btnFetchYt.onclick = async () => {
      const url = ytUrlInput.value.trim();
      if (!url) {
        showToast('Please enter a YouTube link', 'error');
        ytUrlInput.focus();
        return;
      }

      btnFetchYt.disabled = true;
      btnFetchYt.innerHTML = 'Inspecting...';

      try {
        const res = await api.rpc('playlists.inspect_youtube', null, { url });
        fetchedVideos = res.videos || [];

        if (fetchedVideos.length === 0) {
          showToast('No downloadable videos found at that link', 'error');
          return;
        }

        // Default: select all
        selectedVideoUrls = new Set(fetchedVideos.map(v => v.url));

        ytPlaylistTitle.textContent = `${res.title || 'YouTube Playlist'} (${res.count} videos)`;
        ytSelectionSection.style.display = 'block';
        ytTargetRow.style.display = 'grid';

        if (res.isPlaylist && ytNewNameInput && (!ytNewNameInput.value || ytNewNameInput.value === '')) {
          // Pre-populate suggested folder name from YouTube playlist title
          const cleanName = (res.title || 'yt_playlist').toLowerCase().replace(/[^a-z0-9_-]/g, '_').substring(0, 32);
          ytNewNameInput.value = cleanName;
        }

        renderYtVideosList();
        updateYtSelectionUI();
        showToast(`Loaded ${res.count} video(s)! Check or uncheck tracks below.`, 'success');
      } catch (err) {
        showToast(`Failed to inspect link: ${err.message}`, 'error');
      } finally {
        btnFetchYt.disabled = false;
        btnFetchYt.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> Inspect Videos';
      }
    };
  }

  if (btnSelectAll) {
    btnSelectAll.onclick = () => {
      for (const v of fetchedVideos) {
        selectedVideoUrls.add(v.url);
      }
      renderYtVideosList();
      updateYtSelectionUI();
    };
  }

  if (btnDeselectAll) {
    btnDeselectAll.onclick = () => {
      selectedVideoUrls.clear();
      renderYtVideosList();
      updateYtSelectionUI();
    };
  }

  if (ytFilterInput) {
    ytFilterInput.oninput = () => {
      renderYtVideosList();
    };
  }

  if (ytTargetSelect) {
    ytTargetSelect.onchange = () => {
      if (ytNewNameInput) {
        ytNewNameInput.style.display = ytTargetSelect.value === '__new__' ? 'block' : 'none';
      }
    };
  }

  if (btnOpenYtImport) {
    btnOpenYtImport.onclick = () => {
      ytImportCard.style.display = 'block';
      updateYtTargetDropdown();
      ytImportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => ytUrlInput?.focus(), 250);
    };
  }

  if (btnAddYtToCurrent) {
    btnAddYtToCurrent.onclick = () => {
      ytImportCard.style.display = 'block';
      updateYtTargetDropdown();
      if (selectedPlaylist && ytTargetSelect) {
        ytTargetSelect.value = selectedPlaylist;
      }
      if (ytNewNameInput) {
        ytNewNameInput.style.display = 'none';
      }
      ytImportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => {
        if (ytUrlInput) {
          ytUrlInput.focus();
          ytUrlInput.placeholder = `Paste YouTube link to add into '${selectedPlaylist || 'playlist'}'...`;
        }
      }, 250);
      showToast(`YouTube import opened for folder '${selectedPlaylist}'`, 'info');
    };
  }

  if (btnCloseYtImport) {
    btnCloseYtImport.onclick = () => {
      ytImportCard.style.display = 'none';
    };
  }

  if (btnCancelYtImport) {
    btnCancelYtImport.onclick = () => {
      ytImportCard.style.display = 'none';
    };
  }

  if (btnSubmitYtImport) {
    btnSubmitYtImport.onclick = async () => {
      const count = selectedVideoUrls.size;
      if (count === 0) {
        showToast('Please select at least 1 video to import', 'error');
        return;
      }

      let targetPlaylist = ytTargetSelect.value;
      if (targetPlaylist === '__new__') {
        targetPlaylist = ytNewNameInput.value.trim();
        if (!targetPlaylist) {
          showToast('Please enter a name for the new playlist folder', 'error');
          ytNewNameInput.focus();
          return;
        }
      }

      btnSubmitYtImport.disabled = true;
      btnSubmitYtImport.textContent = 'Starting download...';
      ytProgressBox.style.display = 'block';
      ytProgText.textContent = `Starting download of ${count} selected tracks into '${targetPlaylist}'...`;

      try {
        await api.rpc('playlists.import_youtube', null, {
          urls: Array.from(selectedVideoUrls),
          playlist: targetPlaylist
        });
        showToast(`Download started for ${count} track(s)!`, 'success');
      } catch (err) {
        showToast(`Failed to start import: ${err.message}`, 'error');
        btnSubmitYtImport.disabled = false;
        btnSubmitYtImport.textContent = `Download Selected (${count} tracks)`;
      }
    };
  }

  async function loadPlaylists() {
    try {
      playlists = await api.rpc('playlists.list');
      updateYtTargetDropdown();
      renderPlaylistsList();
    } catch (_) {}
  }

  function renderPlaylistsList() {
    if (playlists.length === 0) {
      playlistsListContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">No playlists found.</p>';
      return;
    }

    playlistsListContainer.innerHTML = `
      <ul class="list-group">
        ${playlists.map(p => `
          <li class="list-item pl-item ${selectedPlaylist === p.name ? 'active' : ''}" data-name="${escapeHtml(p.name)}" style="cursor: pointer; transition: background 0.15s ease;">
            <div>
              <strong style="color: var(--text-bright);">${escapeHtml(p.name)}</strong>
              <div style="font-size: 12px; color: var(--text-muted);">${p.trackCount} tracks</div>
            </div>
            <button class="btn btn-sm">&rarr;</button>
          </li>
        `).join('')}
      </ul>
    `;

    for (const item of playlistsListContainer.querySelectorAll('.pl-item')) {
      item.onclick = async () => {
        const name = item.getAttribute('data-name');
        await selectPlaylist(name);
      };
    }
  }

  async function selectPlaylist(name) {
    selectedPlaylist = name;
    tracksTitle.textContent = `Tracks: ${name}`;
    playlistActions.style.display = 'flex';
    if (uploadSection) uploadSection.style.display = 'block';

    renderPlaylistsList();
    tracksContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Loading tracks...</p>';

    try {
      const data = await api.rpc('playlists.get', null, { name });
      playlistTracks = data.tracks || [];
      renderTracks();
    } catch (_) {}
  }

  function renderTracks() {
    if (playlistTracks.length === 0) {
      tracksContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">This playlist folder is currently empty.</p>';
      return;
    }

    tracksContainer.innerHTML = `
      <ul class="list-group" style="max-height: 420px; overflow-y: auto;">
        ${playlistTracks.map(t => `
          <li class="list-item">
            <div style="flex: 1; min-width: 0;">
              <div style="font-weight: 500; color: var(--text-bright); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(t.title)}">
                ${escapeHtml(t.title)}
              </div>
              <div style="font-size: 12px; color: var(--text-muted);">
                ${escapeHtml(t.artist || '')} ${t.duration ? `&bull; ${formatDuration(t.duration)}` : ''}
              </div>
            </div>
            <div style="display: flex; gap: 0.35rem;">
              <button class="btn btn-sm btn-play-track" data-file="${escapeHtml(t.file)}">&#9654; Play</button>
              ${isOwner ? `<button class="btn btn-danger btn-sm btn-del-track" data-file="${escapeHtml(t.file)}">&times;</button>` : ''}
            </div>
          </li>
        `).join('')}
      </ul>
    `;

    for (const btn of tracksContainer.querySelectorAll('.btn-play-track')) {
      btn.onclick = async () => {
        const file = btn.getAttribute('data-file');
        const guildId = state.me?.guilds?.[0]?.id;
        if (!guildId) {
          showToast('No active server found to play track', 'error');
          return;
        }
        try {
          await api.rpc('play.local', guildId, { playlist: selectedPlaylist, file });
          showToast(`Playing track: ${file}`, 'success');
        } catch (_) {}
      };
    }

    for (const btn of tracksContainer.querySelectorAll('.btn-del-track')) {
      btn.onclick = async () => {
        const file = btn.getAttribute('data-file');
        const confirmed = await confirmDialog(`Delete '${file}' from playlist?`, 'Delete Track', true);
        if (!confirmed) return;

        try {
          await api.rpc('tracks.delete', null, { playlist: selectedPlaylist, file });
          showToast(`Deleted ${file}`, 'info');
          await selectPlaylist(selectedPlaylist);
          await loadPlaylists();
        } catch (_) {}
      };
    }
  }

  // Hook action buttons
  if (btnCreatePl) {
    btnCreatePl.onclick = async () => {
      const name = await promptDialog({
        title: 'New Playlist Folder',
        message: 'Enter a folder name for the new local playlist on the server:',
        placeholder: 'e.g. Rock, Lo-Fi, Favorites',
        confirmLabel: 'Create Folder',
        icon: '📁'
      });
      if (!name) return;
      try {
        await api.rpc('playlists.create', null, { name: name.trim() });
        showToast(`Created playlist folder '${name}'`, 'success');
        await loadPlaylists();
        await selectPlaylist(name.trim());
      } catch (_) {}
    };
  }

  if (btnRenamePl) {
    btnRenamePl.onclick = async () => {
      if (!selectedPlaylist) return;
      const newName = await promptDialog({
        title: 'Rename Playlist Folder',
        message: `Enter the new folder name for '${selectedPlaylist}':`,
        defaultValue: selectedPlaylist,
        confirmLabel: 'Rename Folder',
        icon: '✏️'
      });
      if (!newName || newName.trim() === selectedPlaylist) return;
      try {
        await api.rpc('playlists.rename', null, { name: selectedPlaylist, newName: newName.trim() });
        showToast(`Renamed playlist to '${newName}'`, 'success');
        selectedPlaylist = newName.trim();
        await loadPlaylists();
        await selectPlaylist(selectedPlaylist);
      } catch (_) {}
    };
  }

  if (btnDeletePl) {
    btnDeletePl.onclick = async () => {
      if (!selectedPlaylist) return;
      const confirmed = await confirmDialog(`Delete playlist folder '${selectedPlaylist}' and all its songs?`, 'Delete Playlist', true);
      if (!confirmed) return;
      try {
        await api.rpc('playlists.delete', null, { name: selectedPlaylist });
        showToast(`Deleted playlist '${selectedPlaylist}'`, 'info');
        selectedPlaylist = null;
        playlistActions.style.display = 'none';
        if (uploadSection) uploadSection.style.display = 'none';
        tracksTitle.textContent = 'Playlist Tracks';
        tracksContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem 0;">Select a playlist to view tracks.</p>';
        await loadPlaylists();
      } catch (_) {}
    };
  }

  if (btnPlayAll) {
    btnPlayAll.onclick = async () => {
      if (!selectedPlaylist) return;
      const guildId = state.me?.guilds?.[0]?.id;
      if (!guildId) {
        showToast('No active server found', 'error');
        return;
      }
      try {
        const shuffle = chkShuffle ? chkShuffle.checked : false;
        await api.rpc('play.local', guildId, { playlist: selectedPlaylist, shuffle });
        showToast(`Playing playlist '${selectedPlaylist}'!`, 'success');
      } catch (_) {}
    };
  }

  // Upload handlers
  if (dropZone && fileInput && btnBrowse) {
    btnBrowse.onclick = () => fileInput.click();
    dropZone.onclick = (e) => {
      if (e.target !== btnBrowse) fileInput.click();
    };

    dropZone.ondragover = (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    };
    dropZone.ondragleave = () => dropZone.classList.remove('dragover');
    dropZone.ondrop = async (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      const files = Array.from(e.dataTransfer?.files || []);
      if (files.length > 0) await handleFilesUpload(files);
    };

    fileInput.onchange = async () => {
      const files = Array.from(fileInput.files || []);
      if (files.length > 0) await handleFilesUpload(files);
      fileInput.value = '';
    };
  }

  async function handleFilesUpload(files) {
    if (!selectedPlaylist) return;
    const allowed = ['.mp3', '.flac', '.ogg', '.wav'];

    for (const file of files) {
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      if (!allowed.includes(ext)) {
        showToast(`Skipped ${file.name}: unsupported format (${ext})`, 'error');
        continue;
      }

      const itemDiv = document.createElement('div');
      itemDiv.className = 'card';
      itemDiv.style.padding = '0.75rem';
      itemDiv.style.marginBottom = '0.5rem';
      itemDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 0.35rem;">
          <span style="font-weight: 500;">${escapeHtml(file.name)}</span>
          <span class="prog-label">0%</span>
        </div>
        <div class="progress-bar-container" style="height: 6px; margin: 0;">
          <div class="progress-bar" style="width: 0%;"></div>
        </div>
      `;
      uploadProgressContainer.appendChild(itemDiv);

      const progBar = itemDiv.querySelector('.progress-bar');
      const progLabel = itemDiv.querySelector('.prog-label');

      try {
        await api.upload(selectedPlaylist, file, (pct) => {
          progBar.style.width = `${pct}%`;
          progLabel.textContent = `${pct}%`;
        }, true);
        progLabel.textContent = 'Done!';
        progLabel.style.color = 'var(--success)';
      } catch (err) {
        progLabel.textContent = 'Failed';
        progLabel.style.color = 'var(--danger)';
      }
    }

    await selectPlaylist(selectedPlaylist);
    await loadPlaylists();
  }

  // WebSocket listener for live YouTube download progress
  const unsubscribeWs = addWsListener((evt) => {
    if (evt.kind === 'download_progress' && evt.data) {
      const data = evt.data;
      if (ytProgressBox && ytProgText) {
        ytProgressBox.style.display = 'block';
        ytProgText.textContent = data.message || 'Processing...';

        if (data.status === 'completed') {
          showToast(data.message || 'YouTube import completed!', 'success');
          if (btnSubmitYtImport) {
            btnSubmitYtImport.disabled = false;
            btnSubmitYtImport.textContent = `Download Selected (${selectedVideoUrls.size} tracks)`;
          }
          if (ytUrlInput) ytUrlInput.value = '';
          ytSelectionSection.style.display = 'none';
          ytTargetRow.style.display = 'none';
          loadPlaylists();
          if (selectedPlaylist && selectedPlaylist === data.playlist) {
            selectPlaylist(selectedPlaylist);
          }
        } else if (data.status === 'error') {
          showToast(data.message || 'YouTube import error', 'error');
          if (btnSubmitYtImport) {
            btnSubmitYtImport.disabled = false;
            btnSubmitYtImport.textContent = `Download Selected (${selectedVideoUrls.size} tracks)`;
          }
        }
      }
    }
  });

  await loadPlaylists();

  return () => {
    unsubscribeWs();
  };
}
