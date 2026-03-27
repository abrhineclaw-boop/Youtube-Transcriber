/* YouTube Transcriber — Client JS */

const API = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },
    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },
    async patch(url) {
        const res = await fetch(url, { method: 'PATCH' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },
    async del(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },
};

/* --- Utility --- */
function formatDuration(seconds) {
    if (!seconds) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${s}s`;
}

function formatTimestamp(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr + 'Z');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatUploadDate(yyyymmdd) {
    if (!yyyymmdd || yyyymmdd.length !== 8) return '';
    const y = yyyymmdd.slice(0, 4);
    const m = parseInt(yyyymmdd.slice(4, 6)) - 1;
    const d = parseInt(yyyymmdd.slice(6, 8));
    return new Date(y, m, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function statusBadge(status) {
    return `<span class="badge badge-${status}">${status}</span>`;
}

function showError(container, msg) {
    container.innerHTML = `<div class="error-msg">${escapeHtml(msg)}</div>`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}


/* ===========================
   LIBRARY PAGE
   =========================== */
/* --- Shared submission & profile logic (used by home page) --- */
async function setupSubmissionForm(loadTranscriptsFn) {
    const profileSelect = document.getElementById('profile-select');
    const urlInput = document.getElementById('url-input');
    const submitBtn = document.getElementById('submit-btn');
    const submitError = document.getElementById('submit-error');
    const profileDetail = document.getElementById('profile-detail');
    const deleteProfileBtn = document.getElementById('delete-profile-btn');
    const addUrlBtn = document.getElementById('add-url-btn');
    const urlQueueEl = document.getElementById('url-queue');

    if (!profileSelect) return;

    let cachedProfiles = [];
    let urlQueue = [];
    let urlDuplicates = {}; // { url: { id, title, status } }

    function isYouTubeUrl(url) {
        return /^https?:\/\/(www\.)?(youtube\.com\/watch|youtu\.be\/|youtube\.com\/shorts\/)/.test(url);
    }

    function isPlaylistOrChannelUrl(url) {
        return /^https?:\/\/(www\.)?youtube\.com\/(playlist\?list=|@[^/]+|channel\/)/.test(url);
    }

    async function checkDuplicates() {
        if (!urlQueue.length) return;
        try {
            const result = await API.post('/api/transcripts/check-urls', { video_urls: urlQueue });
            urlDuplicates = result.duplicates || {};
            renderQueue();
        } catch (e) {
            // Non-critical — silently ignore
        }
    }

    function addUrlsFromInput() {
        const text = urlInput.value.trim();
        if (!text) return;
        const lines = text.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
        const invalid = [];
        let added = false;
        let playlistDetected = false;
        for (const line of lines) {
            if (isPlaylistOrChannelUrl(line)) {
                playlistDetected = true;
                // Auto-populate playlist import and expand it
                const playlistInput = document.getElementById('playlist-url-input');
                const playlistBody = document.getElementById('playlist-import-body');
                const toggleBtn = document.getElementById('toggle-playlist-import');
                if (playlistInput) {
                    playlistInput.value = line;
                    if (playlistBody && !playlistBody.classList.contains('open')) {
                        playlistBody.classList.add('open');
                        if (toggleBtn) toggleBtn.textContent = '\u25be Hide';
                    }
                }
            } else if (isYouTubeUrl(line) && !urlQueue.includes(line)) {
                urlQueue.push(line);
                added = true;
            } else if (!isYouTubeUrl(line)) {
                invalid.push(line);
            }
        }
        urlInput.value = '';
        urlInput.rows = 1;
        renderQueue();
        if (playlistDetected) {
            submitError.textContent = 'Playlist/channel detected \u2014 use the Import section below.';
        } else if (invalid.length) {
            submitError.textContent = `Skipped ${invalid.length} invalid URL(s)`;
        }
        if (added) checkDuplicates();
    }

    function renderQueue() {
        submitBtn.disabled = urlQueue.length === 0;
        submitBtn.textContent = urlQueue.length > 1 ? `Transcribe ${urlQueue.length} URLs` : 'Transcribe';
        if (!urlQueue.length) {
            urlQueueEl.innerHTML = '';
            return;
        }
        urlQueueEl.innerHTML = urlQueue.map((url, i) => {
            const dup = urlDuplicates[url];
            return `
            <div class="url-queue-item${dup ? ' url-queue-duplicate' : ''}">
                <div style="flex:1;min-width:0">
                    <span class="url-queue-text">${escapeHtml(url)}</span>
                    ${dup ? `<div class="url-queue-warning">Already transcribed: ${escapeHtml(dup.title || 'Untitled')} (${dup.status})</div>` : ''}
                </div>
                <button class="remove-btn" data-idx="${i}" title="Remove">&times;</button>
            </div>`;
        }).join('');
        urlQueueEl.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                urlQueue.splice(parseInt(btn.dataset.idx), 1);
                renderQueue();
            });
        });
    }

    function truncate(str, len) {
        return str.length > len ? str.slice(0, len) + '…' : str;
    }

    function renderProfileOptions(profiles, selectId) {
        cachedProfiles = profiles;
        profileSelect.innerHTML = profiles
            .map(p => {
                const desc = p.description ? ` — ${truncate(p.description, 50)}` : '';
                return `<option value="${p.id}">${escapeHtml(p.name)}${escapeHtml(desc)}</option>`;
            })
            .join('');
        if (selectId) profileSelect.value = selectId;
        updateProfileDetail();
    }

    function updateProfileDetail() {
        const id = parseInt(profileSelect.value);
        const p = cachedProfiles.find(x => x.id === id);
        if (p) {
            profileDetail.style.display = 'block';
            profileDetail.innerHTML = `
                <div class="profile-detail-desc">${escapeHtml(p.description || 'No description')}</div>
                ${p.analysis_hints ? `<div class="profile-detail-hints">${escapeHtml(p.analysis_hints)}</div>` : ''}
            `;
            deleteProfileBtn.style.display = 'inline-flex';
        } else {
            profileDetail.style.display = 'none';
            deleteProfileBtn.style.display = 'none';
        }
    }

    try {
        const profiles = await API.get('/api/profiles');
        renderProfileOptions(profiles);
    } catch (e) {
        console.error('Failed to load profiles:', e);
    }

    profileSelect.addEventListener('change', updateProfileDetail);

    if (deleteProfileBtn) {
        deleteProfileBtn.addEventListener('click', async () => {
            const id = parseInt(profileSelect.value);
            const p = cachedProfiles.find(x => x.id === id);
            if (!p || !confirm(`Delete profile "${p.name}"?`)) return;
            try {
                await API.del(`/api/profiles/${id}`);
                const profiles = await API.get('/api/profiles');
                renderProfileOptions(profiles);
            } catch (e) {
                alert('Cannot delete: ' + e.message);
            }
        });
    }

    addUrlBtn.addEventListener('click', addUrlsFromInput);

    urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            addUrlsFromInput();
        }
    });

    urlInput.addEventListener('paste', () => {
        setTimeout(() => {
            const lines = urlInput.value.split('\n').length;
            urlInput.rows = Math.min(lines, 5);
            addUrlsFromInput();
        }, 50);
    });

    submitBtn.addEventListener('click', async () => {
        if (!urlQueue.length) return;
        submitBtn.disabled = true;
        submitError.textContent = '';
        try {
            await API.post('/api/transcripts/batch', {
                video_urls: urlQueue,
                profile_id: parseInt(profileSelect.value),
            });
            urlQueue = [];
            renderQueue();
            await loadTranscriptsFn();
        } catch (e) {
            submitError.textContent = e.message;
        } finally {
            submitBtn.disabled = urlQueue.length === 0;
        }
    });

    const addProfileBtn = document.getElementById('add-profile-btn');
    if (addProfileBtn) {
        addProfileBtn.addEventListener('click', async () => {
            const nameInput = document.getElementById('new-profile-name');
            const descInput = document.getElementById('new-profile-desc');
            const hintsInput = document.getElementById('new-profile-hints');
            const name = nameInput.value.trim();
            if (!name) return;
            try {
                const result = await API.post('/api/profiles', {
                    name,
                    description: descInput.value.trim(),
                    analysis_hints: hintsInput.value.trim(),
                });
                nameInput.value = '';
                descInput.value = '';
                hintsInput.value = '';
                const profiles = await API.get('/api/profiles');
                renderProfileOptions(profiles, result.id);
            } catch (e) {
                alert('Failed to create profile: ' + e.message);
            }
        });
    }

    const toggleProfileBtn = document.getElementById('toggle-profile-form');
    if (toggleProfileBtn) {
        toggleProfileBtn.addEventListener('click', () => {
            const body = document.getElementById('profile-form-body');
            body.classList.toggle('open');
            toggleProfileBtn.textContent = body.classList.contains('open') ? '\u25be Hide' : '\u25b8 New Profile';
        });
    }

    // --- Playlist / Channel Import ---
    const togglePlaylistBtn = document.getElementById('toggle-playlist-import');
    if (togglePlaylistBtn) {
        togglePlaylistBtn.addEventListener('click', () => {
            const body = document.getElementById('playlist-import-body');
            body.classList.toggle('open');
            togglePlaylistBtn.textContent = body.classList.contains('open') ? '\u25be Hide' : '\u25b8 Import Playlist / Channel';
        });
    }

    const importPlaylistBtn = document.getElementById('import-playlist-btn');
    const playlistUrlInput = document.getElementById('playlist-url-input');
    const playlistStatus = document.getElementById('playlist-status');

    if (importPlaylistBtn && playlistUrlInput) {
        importPlaylistBtn.addEventListener('click', async () => {
            const url = playlistUrlInput.value.trim();
            if (!url) return;
            importPlaylistBtn.disabled = true;
            importPlaylistBtn.textContent = 'Extracting...';
            playlistStatus.textContent = '';
            try {
                const result = await API.post('/api/transcripts/import-playlist', {
                    playlist_url: url,
                    profile_id: parseInt(profileSelect.value),
                    max_videos: 50,
                });
                playlistUrlInput.value = '';
                playlistStatus.textContent = result.message;
                playlistStatus.style.color = 'var(--success-color, green)';
                await loadTranscriptsFn();
            } catch (e) {
                playlistStatus.textContent = e.message;
                playlistStatus.style.color = 'var(--danger-color, red)';
            } finally {
                importPlaylistBtn.disabled = false;
                importPlaylistBtn.textContent = 'Import';
            }
        });

        playlistUrlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                importPlaylistBtn.click();
            }
        });
    }

    // --- Bookmarklet ---
    function updateBookmarklet() {
        const link = document.getElementById('bookmarklet-link');
        if (!link) return;
        const profileId = profileSelect.value || '1';
        const origin = location.origin;
        link.href = `javascript:void(fetch('${origin}/api/transcripts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video_url:location.href,profile_id:${profileId}})}).then(r=>r.json()).then(d=>alert('Queued: '+location.href)).catch(e=>alert('Error: '+e.message)))`;
    }
    updateBookmarklet();
    profileSelect.addEventListener('change', updateBookmarklet);
}

/* --- Home page (/ ) — submission form + recent 5 transcripts --- */
async function initHome() {
    const listEl = document.getElementById('transcript-list');
    if (!listEl) return;

    async function loadTranscripts() {
        try {
            const transcripts = await API.get('/api/transcripts?limit=5');
            renderTranscriptList(listEl, transcripts);
        } catch (e) {
            showError(listEl, 'Failed to load transcripts');
        }
    }

    await setupSubmissionForm(loadTranscripts);
    await loadTranscripts();
}

/* --- Library page (/library) — full transcript list with filters --- */
async function initLibrary() {
    const listEl = document.getElementById('transcript-list');
    const channelFilter = document.getElementById('channel-filter');
    const profileFilter = document.getElementById('profile-filter');
    const tagFilter = document.getElementById('tag-filter');
    const tagSuggestions = document.getElementById('tag-suggestions');
    const watchLaterFilter = document.getElementById('watch-later-filter');
    const searchFilter = document.getElementById('search-filter');
    const selectModeBtn = document.getElementById('select-mode-btn');
    const selectionBar = document.getElementById('selection-bar');
    const selectionCount = document.getElementById('selection-count');
    const selectionAnalyzeBtn = document.getElementById('selection-analyze-btn');
    const selectionCancelBtn = document.getElementById('selection-cancel-btn');

    let selectMode = false;
    const selectedIds = new Set();
    let lastTranscripts = [];

    if (!listEl) return;

    async function loadChannels() {
        try {
            const channels = await API.get('/api/channels');
            const current = channelFilter.value;
            channelFilter.innerHTML = '<option value="">All Channels</option>' +
                channels.map(c => `<option value="${escapeHtml(c.channel)}">${escapeHtml(c.channel)} (${c.transcript_count})</option>`).join('');
            if (current) channelFilter.value = current;
        } catch (e) {
            console.error('Failed to load channels:', e);
        }
    }

    async function loadProfileFilter() {
        try {
            const profiles = await API.get('/api/profiles');
            const current = profileFilter.value;
            profileFilter.innerHTML = '<option value="">All Profiles</option>' +
                profiles.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
            if (current) profileFilter.value = current;
        } catch (e) {
            console.error('Failed to load profiles:', e);
        }
    }

    async function loadTags() {
        try {
            const tags = await API.get('/api/tags');
            tagSuggestions.innerHTML = tags.map(t => `<option value="${escapeHtml(t.name)}">`).join('');
        } catch (e) {
            console.error('Failed to load tags:', e);
        }
    }

    function applySearchFilter(transcripts) {
        const q = (searchFilter ? searchFilter.value : '').toLowerCase().trim();
        if (!q) return transcripts;
        return transcripts.filter(t => {
            const title = (t.title || '').toLowerCase();
            const channel = (t.channel || '').toLowerCase();
            const tags = (t.tags || []).map(tg => tg.name || tg).join(' ').toLowerCase();
            return title.includes(q) || channel.includes(q) || tags.includes(q);
        });
    }

    function renderFiltered(transcripts) {
        lastTranscripts = transcripts;
        const filtered = applySearchFilter(transcripts);
        renderTranscriptList(listEl, filtered, selectMode, selectedIds);
        // Show/hide "Retry All Errors" button
        const retryAllBtn = document.getElementById('retry-all-errors-btn');
        if (retryAllBtn) {
            const hasErrors = transcripts.some(t => t.status === 'error');
            retryAllBtn.style.display = hasErrors ? '' : 'none';
        }
    }

    async function loadTranscripts() {
        try {
            const params = new URLSearchParams();
            if (channelFilter.value) params.set('channel', channelFilter.value);
            if (profileFilter.value) params.set('profile_id', profileFilter.value);
            if (tagFilter.value) params.set('tag', tagFilter.value);
            if (watchLaterFilter && watchLaterFilter.classList.contains('active')) params.set('watch_later', 'true');
            const qs = params.toString();
            const transcripts = await API.get('/api/transcripts' + (qs ? '?' + qs : ''));
            renderFiltered(transcripts);
        } catch (e) {
            showError(listEl, 'Failed to load transcripts');
        }
    }

    channelFilter.addEventListener('change', loadTranscripts);
    profileFilter.addEventListener('change', loadTranscripts);
    if (watchLaterFilter) {
        watchLaterFilter.addEventListener('click', () => {
            watchLaterFilter.classList.toggle('active');
            watchLaterFilter.innerHTML = watchLaterFilter.classList.contains('active') ? '&#9733; Watch Later' : '&#9734; Watch Later';
            loadTranscripts();
        });
    }
    const retryAllBtn = document.getElementById('retry-all-errors-btn');
    if (retryAllBtn) {
        retryAllBtn.addEventListener('click', async () => {
            retryAllBtn.disabled = true;
            try {
                const result = await API.post('/api/transcripts/retry-errors');
                retryAllBtn.textContent = `Retried ${result.retried}`;
                setTimeout(() => {
                    retryAllBtn.innerHTML = '&#8635; Retry Errors';
                    retryAllBtn.disabled = false;
                    loadTranscripts();
                }, 1000);
            } catch (err) {
                alert('Retry all failed: ' + (err.message || 'Unknown error'));
                retryAllBtn.disabled = false;
            }
        });
    }

    let tagFilterTimeout;
    tagFilter.addEventListener('input', () => {
        clearTimeout(tagFilterTimeout);
        tagFilterTimeout = setTimeout(loadTranscripts, 300);
    });

    // Search filter
    if (searchFilter) {
        let searchTimeout;
        searchFilter.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => renderFiltered(lastTranscripts), 200);
        });
    }

    // Select mode
    function updateSelectionBar() {
        const count = selectedIds.size;
        selectionCount.textContent = `${count} selected`;
        selectionAnalyzeBtn.disabled = count < 2;
    }

    function exitSelectMode() {
        selectMode = false;
        selectedIds.clear();
        selectModeBtn.textContent = 'Select';
        selectModeBtn.classList.remove('btn-primary');
        selectModeBtn.classList.add('btn-secondary');
        selectionBar.style.display = 'none';
        renderFiltered(lastTranscripts);
    }

    if (selectModeBtn) {
        selectModeBtn.addEventListener('click', () => {
            selectMode = !selectMode;
            if (selectMode) {
                selectModeBtn.textContent = 'Selecting...';
                selectModeBtn.classList.remove('btn-secondary');
                selectModeBtn.classList.add('btn-primary');
                selectionBar.style.display = 'flex';
                updateSelectionBar();
            } else {
                exitSelectMode();
            }
            renderFiltered(lastTranscripts);
        });
    }

    if (selectionCancelBtn) {
        selectionCancelBtn.addEventListener('click', exitSelectMode);
    }

    const instructionsModal = document.getElementById('instructions-modal');
    const instructionsInput = document.getElementById('instructions-input');
    const instructionsRunBtn = document.getElementById('instructions-run-btn');
    const instructionsCancelBtn = document.getElementById('instructions-cancel-btn');

    if (selectionAnalyzeBtn) {
        selectionAnalyzeBtn.addEventListener('click', () => {
            if (selectedIds.size < 2) return;
            if (instructionsModal) {
                instructionsInput.value = '';
                instructionsModal.style.display = 'flex';
                instructionsInput.focus();
            }
        });
    }

    if (instructionsCancelBtn) {
        instructionsCancelBtn.addEventListener('click', () => {
            instructionsModal.style.display = 'none';
        });
    }

    if (instructionsModal) {
        instructionsModal.addEventListener('click', (e) => {
            if (e.target === instructionsModal) instructionsModal.style.display = 'none';
        });
    }

    if (instructionsRunBtn) {
        instructionsRunBtn.addEventListener('click', async () => {
            const instructions = instructionsInput.value.trim();
            if (!instructions) {
                instructionsInput.focus();
                return;
            }
            instructionsRunBtn.disabled = true;
            instructionsRunBtn.textContent = 'Running...';
            try {
                const result = await API.post('/api/cross-analysis', {
                    transcript_ids: [...selectedIds],
                    instructions,
                });
                window.location.href = `/cross-analysis/${result.id}`;
            } catch (e) {
                alert('Cross-analysis failed: ' + (e.message || 'Unknown error'));
                instructionsRunBtn.disabled = false;
                instructionsRunBtn.textContent = 'Run Analysis';
            }
        });
    }

    // Handle clicks on transcript items in select mode
    listEl.addEventListener('click', (e) => {
        if (!selectMode) return;
        const item = e.target.closest('.transcript-item');
        if (!item) return;
        e.preventDefault();
        const tid = parseInt(item.dataset.transcriptId);
        if (isNaN(tid)) return;
        if (selectedIds.has(tid)) {
            selectedIds.delete(tid);
        } else {
            selectedIds.add(tid);
        }
        updateSelectionBar();
        renderFiltered(lastTranscripts);
    });

    await Promise.all([loadTranscripts(), loadChannels(), loadProfileFilter(), loadTags()]);
}

const PIPELINE_STEPS = [
    { key: 'downloading', label: 'Download' },
    { key: 'transcribing', label: 'Transcribe' },
    { key: 'analyzing', label: 'Analyze' },
    { key: 'ready', label: 'Done' },
];

function getStepIndex(status) {
    const idx = PIPELINE_STEPS.findIndex(s => s.key === status);
    return idx >= 0 ? idx : -1;
}

function renderMiniStepper(status) {
    const activeIdx = getStepIndex(status);
    return `<div class="progress-stepper-mini">${PIPELINE_STEPS.map((step, i) => {
        let cls = 'step-upcoming';
        if (i < activeIdx) cls = 'step-completed';
        else if (i === activeIdx) cls = 'step-active';
        return `<span class="mini-dot ${cls}" title="${step.label}"></span>`;
    }).join('')}</div>`;
}

const PACKAGE_DEFS = [
    { key: 'package_a', label: 'Full Scan', types: ['content_vs_fluff', 'named_entities', 'info_density', 'executive_briefing'] },
    { key: 'package_b', label: 'Deep', types: ['section_summaries', 'quote_extraction', 'argument_mapping', 'credibility_flags'] },
    { key: 'package_c', label: 'Research', types: ['question_extraction', 'resource_extraction', 'novelty_scoring'] },
];

function getPackageBadges(completedAnalyses, hasBaseline) {
    const completed = completedAnalyses || [];
    return PACKAGE_DEFS.map(pkg => {
        const done = pkg.types.filter(t => completed.includes(t)).length;
        const total = pkg.types.length;
        if (done === 0 && !(pkg.key === 'package_a' && hasBaseline)) return '';
        if (done === total || (pkg.key === 'package_a' && hasBaseline && done >= total - 1))
            return `<span class="badge badge-pkg-done">${pkg.label}</span>`;
        return `<span class="badge badge-pkg-partial">${pkg.label} ${done}/${total}</span>`;
    }).join('');
}

function renderTranscriptList(container, transcripts, selectMode = false, selectedIds = null) {
    if (!transcripts.length) {
        container.innerHTML = `
            <div class="empty-state">
                <p>No transcripts yet. Paste a YouTube URL above to get started.</p>
            </div>`;
        return;
    }

    const activeStatuses = ['pending', 'downloading', 'transcribing', 'analyzing'];

    container.innerHTML = transcripts.map(t => {
        const packageBadges = getPackageBadges(t.completed_analyses, t.has_baseline);
        const isActive = activeStatuses.includes(t.status);
        const statusHtml = isActive ? renderMiniStepper(t.status) : statusBadge(t.status);
        const errorLine = t.status === 'error' && t.error_message
            ? `<div class="transcript-error">${escapeHtml(t.error_message)}</div>` : '';
        const isSelected = selectMode && selectedIds && selectedIds.has(t.id);
        const tag = selectMode ? 'div' : 'a';
        const hrefAttr = selectMode ? '' : ` href="/transcript/${t.id}"`;

        return `
        <${tag}${hrefAttr} class="transcript-item${t.status === 'error' ? ' transcript-item-error' : ''}${isSelected ? ' selected' : ''}" data-transcript-id="${t.id}">
            ${selectMode ? `<div class="select-checkbox">${isSelected ? '&#9745;' : '&#9744;'}</div>` : ''}
            <div class="transcript-info">
                <div class="transcript-title">${t.watch_later ? '<span class="watch-later-indicator" title="Watch Later">&#9733;</span> ' : ''}${escapeHtml(t.title || t.video_url)}</div>
                <div class="transcript-meta">
                    <span class="channel-link" data-channel="${escapeHtml(t.channel || '')}">${escapeHtml(t.channel || '—')}</span>
                    <span>${formatDuration(t.duration_seconds)}</span>
                    <span>${escapeHtml(t.profile_name)}</span>
                    ${t.upload_date ? `<span>Uploaded ${formatUploadDate(t.upload_date)}</span>` : ''}
                    <span>${formatDate(t.created_at)}</span>
                </div>
                ${(t.tags && t.tags.length) ? `<div class="tag-list">${t.tags.map(tg => `<span class="tag ${tg.source === 'user' ? 'tag-user' : (tg.confirmed ? 'tag-confirmed' : '')} tag-filter-link" data-tag="${escapeHtml(tg.name)}">${escapeHtml(tg.name)}</span>`).join('')}</div>` : ''}
                ${errorLine}
            </div>
            <div class="transcript-badges">
                ${statusHtml}
                ${isActive ? `<button class="btn btn-sm cancel-job-btn" data-id="${t.id}" title="Cancel">&times;</button>` : ''}
                ${(t.status === 'error' || t.status === 'cancelled') ? `<button class="btn btn-sm retry-btn" data-id="${t.id}" title="Retry">&#8635;</button><button class="btn btn-sm remove-btn" data-id="${t.id}" title="Remove">&#128465;</button>` : ''}
                ${packageBadges}
            </div>
        </${tag}>`;
    }).join('');

    // Make channel names clickable to filter
    container.querySelectorAll('.channel-link').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const ch = el.dataset.channel;
            if (ch) {
                const filter = document.getElementById('channel-filter');
                if (filter) {
                    filter.value = ch;
                    filter.dispatchEvent(new Event('change'));
                }
            }
        });
    });

    // Make tags clickable to filter
    container.querySelectorAll('.tag-filter-link').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const tf = document.getElementById('tag-filter');
            if (tf) {
                tf.value = el.dataset.tag;
                tf.dispatchEvent(new Event('input'));
            }
        });
    });

    // Cancel job buttons
    container.querySelectorAll('.cancel-job-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const tid = btn.dataset.id;
            btn.disabled = true;
            try {
                await API.post(`/api/transcripts/${tid}/cancel`);
                btn.textContent = '✓';
                // Re-render after short delay to show updated status
                setTimeout(async () => {
                    try {
                        const params = new URLSearchParams();
                        const channelFilter = document.getElementById('channel-filter');
                        const profileFilter = document.getElementById('profile-filter');
                        const tagFilter = document.getElementById('tag-filter');
                        const watchLaterFilter = document.getElementById('watch-later-filter');
                        if (channelFilter && channelFilter.value) params.set('channel', channelFilter.value);
                        if (profileFilter && profileFilter.value) params.set('profile_id', profileFilter.value);
                        if (tagFilter && tagFilter.value) params.set('tag', tagFilter.value);
                        if (watchLaterFilter && watchLaterFilter.classList.contains('active')) params.set('watch_later', 'true');
                        const limitParam = container.closest('[data-limit]')?.dataset.limit;
                        if (limitParam) params.set('limit', limitParam);
                        const qs = params.toString();
                        const transcripts = await API.get('/api/transcripts' + (qs ? '?' + qs : ''));
                        renderTranscriptList(container, transcripts);
                    } catch (_) {}
                }, 500);
            } catch (err) {
                alert('Cancel failed: ' + (err.message || 'Unknown error'));
                btn.disabled = false;
            }
        });
    });

    // Retry buttons
    container.querySelectorAll('.retry-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const tid = btn.dataset.id;
            btn.disabled = true;
            try {
                await API.post(`/api/transcripts/${tid}/retry`);
                btn.textContent = '✓';
                setTimeout(async () => {
                    try {
                        const params = new URLSearchParams();
                        const channelFilter = document.getElementById('channel-filter');
                        const profileFilter = document.getElementById('profile-filter');
                        const tagFilter = document.getElementById('tag-filter');
                        const watchLaterFilter = document.getElementById('watch-later-filter');
                        if (channelFilter && channelFilter.value) params.set('channel', channelFilter.value);
                        if (profileFilter && profileFilter.value) params.set('profile_id', profileFilter.value);
                        if (tagFilter && tagFilter.value) params.set('tag', tagFilter.value);
                        if (watchLaterFilter && watchLaterFilter.classList.contains('active')) params.set('watch_later', 'true');
                        const limitParam = container.closest('[data-limit]')?.dataset.limit;
                        if (limitParam) params.set('limit', limitParam);
                        const qs = params.toString();
                        const transcripts = await API.get('/api/transcripts' + (qs ? '?' + qs : ''));
                        renderTranscriptList(container, transcripts);
                    } catch (_) {}
                }, 500);
            } catch (err) {
                alert('Retry failed: ' + (err.message || 'Unknown error'));
                btn.disabled = false;
            }
        });
    });

    // Remove buttons
    container.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!confirm('Remove this transcript from the library?')) return;
            const tid = btn.dataset.id;
            btn.disabled = true;
            try {
                await API.del(`/api/transcripts/${tid}`);
                const item = btn.closest('.transcript-item');
                if (item) item.remove();
            } catch (err) {
                alert('Remove failed: ' + (err.message || 'Unknown error'));
                btn.disabled = false;
            }
        });
    });
}


/* ===========================
   TRANSCRIPT DETAIL PAGE
   =========================== */
async function initTranscriptDetail(transcriptId) {
    const container = document.getElementById('detail-content');
    if (!container) return;

    try {
        const transcript = await API.get(`/api/transcripts/${transcriptId}`);
        renderDetailHeader(transcript);

        if (transcript.status === 'error' || transcript.status === 'cancelled') {
            renderErrorState(container, transcriptId, transcript.error_message);
            return;
        }

        if (transcript.status !== 'ready') {
            renderPendingState(container, transcript);
            // Poll until ready
            const poll = setInterval(async () => {
                const status = await API.get(`/api/transcripts/${transcriptId}/status`);
                if (status.status === 'ready') {
                    clearInterval(poll);
                    if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
                    location.reload();
                } else if (status.status === 'error') {
                    clearInterval(poll);
                    if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
                    renderErrorState(container, transcriptId, status.error_message);
                } else {
                    renderPendingState(container, { ...transcript, status: status.status, created_at: status.created_at || transcript.created_at });
                }
            }, 3000);
            return;
        }

        // Load baseline
        let baseline = null;
        try {
            baseline = await API.get(`/api/transcripts/${transcriptId}/baseline`);
        } catch (e) { /* no baseline yet */ }

        // Load packages and existing results
        const [packages, existingResults] = await Promise.all([
            API.get('/api/analysis-packages'),
            API.get(`/api/transcripts/${transcriptId}/analyses`),
        ]);

        const completedTypes = existingResults.map(r => r.analysis_type);
        const analysisData = {};
        for (const r of existingResults) {
            analysisData[r.analysis_type] = JSON.parse(r.result_json);
        }

        renderDetail(container, transcript, baseline, packages, completedTypes, analysisData);
    } catch (e) {
        showError(container, 'Failed to load transcript: ' + e.message);
    }
}

function renderDetailHeader(transcript) {
    const el = document.getElementById('detail-header');
    if (!el) return;
    const isWatchLater = transcript.watch_later === 1;
    el.innerHTML = `
        <div class="detail-title-row">
            <h1>${escapeHtml(transcript.title || 'Untitled')}</h1>
            <button class="watch-later-btn${isWatchLater ? ' active' : ''}" data-id="${transcript.id}" title="Watch Later">
                ${isWatchLater ? '&#9733;' : '&#9734;'}
            </button>
        </div>
        <div class="meta">
            <span>${escapeHtml(transcript.channel || '—')}</span>
            <span>${formatDuration(transcript.duration_seconds)}</span>
            <span>${escapeHtml(transcript.profile_name)}</span>
            ${transcript.upload_date ? `<span>Uploaded ${formatUploadDate(transcript.upload_date)}</span>` : ''}
            <span>${formatDate(transcript.created_at)}</span>
            ${statusBadge(transcript.status)}
        </div>
    `;
    el.querySelector('.watch-later-btn').addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        const result = await API.patch(`/api/transcripts/${btn.dataset.id}/watch-later`);
        const active = result.watch_later === 1;
        btn.classList.toggle('active', active);
        btn.innerHTML = active ? '&#9733;' : '&#9734;';
    });
}

let _elapsedTimer = null;

function formatElapsed(ms) {
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function renderErrorState(container, transcriptId, errorMessage) {
    container.innerHTML = `
        <div class="card">
            <div class="error-msg">${escapeHtml(errorMessage || 'An error occurred')}</div>
            <div style="margin-top:1rem;display:flex;gap:0.5rem">
                <button class="btn btn-sm" id="detail-retry-btn">&#8635; Retry</button>
                <button class="btn btn-sm btn-danger" id="detail-remove-btn">&#128465; Remove</button>
            </div>
        </div>`;
    document.getElementById('detail-retry-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('detail-retry-btn');
        btn.disabled = true;
        btn.textContent = 'Retrying...';
        try {
            await API.post(`/api/transcripts/${transcriptId}/retry`);
            location.reload();
        } catch (err) {
            alert('Retry failed: ' + (err.message || 'Unknown error'));
            btn.disabled = false;
            btn.innerHTML = '&#8635; Retry';
        }
    });
    document.getElementById('detail-remove-btn')?.addEventListener('click', async () => {
        if (!confirm('Remove this transcript from the library?')) return;
        const btn = document.getElementById('detail-remove-btn');
        btn.disabled = true;
        try {
            await API.del(`/api/transcripts/${transcriptId}`);
            window.location.href = '/library';
        } catch (err) {
            alert('Remove failed: ' + (err.message || 'Unknown error'));
            btn.disabled = false;
        }
    });
}

function renderPendingState(container, transcript) {
    // Clear previous timer
    if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }

    const messages = {
        pending: 'Waiting to start...',
        downloading: 'Downloading audio from YouTube...',
        transcribing: 'Transcribing with Whisper (this may take a while for long videos)...',
        analyzing: 'Running baseline analysis...',
    };

    const activeIdx = getStepIndex(transcript.status);

    const stepsHtml = PIPELINE_STEPS.map((step, i) => {
        let cls = 'step-upcoming';
        let icon = `<span class="step-num">${i + 1}</span>`;
        if (i < activeIdx) {
            cls = 'step-completed';
            icon = '<span class="step-check">&#10003;</span>';
        } else if (i === activeIdx) {
            cls = 'step-active';
            icon = '<div class="spinner spinner-sm"></div>';
        }
        const connector = i < PIPELINE_STEPS.length - 1 ? '<div class="progress-connector"></div>' : '';
        return `
            <div class="progress-step ${cls}">
                <div class="step-circle">${icon}</div>
                <div class="step-label">${step.label}</div>
            </div>
            ${connector}`;
    }).join('');

    const createdAt = transcript.created_at;
    const startTime = createdAt ? new Date(createdAt + 'Z').getTime() : Date.now();

    container.innerHTML = `
        <div class="card">
            <div class="progress-stepper">${stepsHtml}</div>
            <div class="progress-status">
                <span>${messages[transcript.status] || 'Processing...'}</span>
                <span class="elapsed-timer" id="elapsed-timer">${formatElapsed(Date.now() - startTime)}</span>
            </div>
            <button class="btn btn-sm btn-secondary" id="cancel-job-detail" style="margin-top:0.75rem">Cancel</button>
        </div>
    `;

    const cancelBtn = document.getElementById('cancel-job-detail');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', async () => {
            cancelBtn.disabled = true;
            cancelBtn.textContent = 'Cancelling...';
            try {
                await API.post(`/api/transcripts/${transcript.id}/cancel`);
                window.location.href = '/library';
            } catch (e) {
                alert('Cancel failed: ' + (e.message || 'Unknown error'));
                cancelBtn.disabled = false;
                cancelBtn.textContent = 'Cancel';
            }
        });
    }

    // Start elapsed timer
    _elapsedTimer = setInterval(() => {
        const el = document.getElementById('elapsed-timer');
        if (el) {
            el.textContent = formatElapsed(Date.now() - startTime);
        } else {
            clearInterval(_elapsedTimer);
            _elapsedTimer = null;
        }
    }, 1000);
}

function renderDetail(container, transcript, baseline, packages, completedTypes, analysisData) {
    let html = '';

    // Executive Briefing (from Package A, if available)
    if (analysisData.executive_briefing) {
        let briefingContent;
        if (Array.isArray(analysisData.executive_briefing)) {
            briefingContent = `<ul class="briefing-list">${analysisData.executive_briefing.map(b =>
                `<li>${escapeHtml(b)}</li>`).join('')}</ul>`;
        } else {
            briefingContent = `<p class="summary-text">${escapeHtml(analysisData.executive_briefing)}</p>`;
        }
        html += `
        <div class="card" style="border-left: 3px solid var(--accent)">
            <h2 class="section-title">Executive Briefing</h2>
            ${briefingContent}
        </div>`;
    }

    // Concept Map (from Package A, if available)
    if (analysisData.concept_map) {
        html += `
        <div class="card">
            <h3 class="section-title">Concept Map</h3>
            <div id="detail-concept-map" style="width:100%;height:450px"></div>
        </div>`;
    }

    // On-Demand Analysis Packages (B and C)
    const onDemandPkgs = Object.entries(packages).filter(([, p]) => p.trigger === 'on_demand');
    if (onDemandPkgs.length) {
        html += `
        <div class="card">
            <h2 class="section-title">On-Demand Analysis</h2>
            <div class="analysis-buttons" id="package-buttons">
                ${onDemandPkgs.map(([key, pkg]) => {
                    const allDone = pkg.analysis_types.every(t => completedTypes.includes(t));
                    return `
                    <div class="analysis-btn">
                        ${allDone ? '<div class="done-indicator"></div>' : ''}
                        <button class="btn ${allDone ? 'btn-secondary' : 'btn-primary'}"
                                data-package="${key}"
                                title="${escapeHtml(pkg.description)}">
                            ${escapeHtml(pkg.label)}
                            ${allDone ? '(view results)' : ''}
                        </button>
                    </div>`;
                }).join('')}
            </div>
            ${onDemandPkgs.some(([, p]) => p.analysis_types.some(t => completedTypes.includes(t))) ? `
            <div class="completed-analyses" style="margin-top:0.5rem">
                ${completedTypes.filter(t => !['content_vs_fluff','named_entities','info_density','executive_briefing','concept_map'].includes(t)).map(t => `
                    <a href="/transcript/${transcript.id}/analysis/${t}" target="_blank" class="badge badge-done" style="cursor:pointer;text-decoration:none">${escapeHtml(t.replace(/_/g, ' '))}</a>
                `).join('')}
            </div>` : ''}
            <div id="analysis-status"></div>
        </div>`;
    }

    // Tags
    html += `
    <div class="card">
        <h2 class="section-title">Tags</h2>
        <div id="tag-manager" class="tag-list">
            <div class="loading"><div class="spinner"></div><span>Loading tags...</span></div>
        </div>
        <div class="tag-add-form" style="margin-top:0.5rem">
            <input type="text" id="new-tag-input" placeholder="Add tag..." list="detail-tag-suggestions">
            <datalist id="detail-tag-suggestions"></datalist>
            <button class="btn btn-sm btn-secondary" id="add-tag-btn">Add</button>
        </div>
    </div>`;


    // Package A inline results: Content vs Fluff summary
    if (analysisData.content_vs_fluff) {
        const cvf = analysisData.content_vs_fluff;
        html += `
        <div class="card">
            <h2 class="section-title">Content vs. Fluff</h2>
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">${cvf.substance_percentage || 0}%</div><div class="stat-label">Substance</div></div>
                <div class="stat-card"><div class="stat-value">${cvf.filler_percentage || 0}%</div><div class="stat-label">Filler</div></div>
                <div class="stat-card"><div class="stat-value">${formatTimestamp(cvf.optimal_start || 0)}</div><div class="stat-label">Start Watching</div></div>
                <div class="stat-card"><div class="stat-value">${formatTimestamp(cvf.optimal_end || 0)}</div><div class="stat-label">Stop Watching</div></div>
            </div>
            ${cvf.summary ? `<p class="summary-text" style="margin-top:0.5rem;font-size:0.8rem;color:var(--text-muted)">${escapeHtml(cvf.summary)}</p>` : ''}
        </div>`;
    }

    // Package A: Info Density per section
    if (analysisData.info_density && Array.isArray(analysisData.info_density)) {
        html += `
        <div class="card">
            <h2 class="section-title">Info Density by Section</h2>
            ${analysisData.info_density.map(s => `
                <div class="extraction-item">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <strong>${escapeHtml(s.section_title || '')}</strong>
                        <span class="badge" style="background:rgba(108,99,255,0.2);color:var(--accent)">${s.score}/100</span>
                    </div>
                    <p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.2rem">${escapeHtml(s.justification || '')}</p>
                </div>
            `).join('')}
        </div>`;
    }

    // Package A: Named Entities
    if (analysisData.named_entities && Array.isArray(analysisData.named_entities) && analysisData.named_entities.length) {
        html += `
        <div class="card">
            <div class="collapsible-header" id="entities-toggle">
                <h2 class="section-title" style="margin-bottom:0">Named Entities</h2>
                <span class="toggle">▸ Show</span>
            </div>
            <div class="collapsible-body" id="entities-body">
                ${analysisData.named_entities.map(e => `
                    <div class="extraction-item" style="display:flex;gap:0.75rem;align-items:flex-start">
                        <span class="badge badge-done" style="min-width:fit-content">${escapeHtml(e.type || 'entity')}</span>
                        <div>
                            <strong>${escapeHtml(e.name)}</strong>
                            ${e.first_mention_timestamp != null ? `<span style="color:var(--text-muted);font-size:0.75rem;margin-left:0.5rem">[${formatTimestamp(e.first_mention_timestamp)}]</span>` : ''}
                            ${e.context ? `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.1rem">${escapeHtml(e.context)}</p>` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>`;
    }

    // Outline with section deep-dive buttons
    if (baseline) {
        const outline = JSON.parse(baseline.outline_json || '[]');
        if (outline.length) {
            html += `
            <div class="card">
                <h2 class="section-title">Content Outline</h2>
                <ul class="outline-list">
                    ${outline.map((s, i) => `
                        <li class="outline-item" style="flex-wrap:wrap">
                            <span class="outline-time">${formatTimestamp(s.start_time)} – ${formatTimestamp(s.end_time)}</span>
                            <div class="outline-content" style="flex:1">
                                <strong>${escapeHtml(s.title)}</strong>
                                <p>${escapeHtml(s.description || '')}</p>
                            </div>
                            <button class="btn btn-sm btn-secondary deep-dive-btn" data-section="${i}" title="Deep-dive this section"
                                ${completedTypes.includes('section_deep_dive_' + i) ? 'style="color:var(--success)"' : ''}>
                                ${completedTypes.includes('section_deep_dive_' + i) ? 'View' : 'Dive'}
                            </button>
                            ${s.summary ? `
                            <details class="outline-details">
                                <summary class="outline-summary-toggle">Summary</summary>
                                <p class="outline-summary-text">${escapeHtml(s.summary)}</p>
                            </details>` : ''}
                        </li>
                    `).join('')}
                </ul>
            </div>`;
        }
    }

    // Transcript text
    const segments = JSON.parse(transcript.transcript_json || '[]');
    if (segments.length) {
        html += `
        <div class="card">
            <div class="collapsible-header" id="transcript-toggle">
                <h2 class="section-title" style="margin-bottom:0">Full Transcript</h2>
                <span class="toggle">▸ Show</span>
            </div>
            <div class="collapsible-body" id="transcript-body">
                <div class="transcript-text">
                    ${segments.map(s => `<span class="timestamp">[${formatTimestamp(s.start)}]</span> ${escapeHtml(s.text)}`).join('<br>')}
                </div>
            </div>
        </div>`;
    }

    // Processing Stats
    const stats = JSON.parse(transcript.processing_stats || '{}');
    if (Object.keys(stats).length) {
        const statItems = [];
        if (stats.total_processing_time_seconds != null) statItems.push({ label: 'Total Time', value: formatElapsed(stats.total_processing_time_seconds * 1000) });
        if (stats.download_time_seconds != null) statItems.push({ label: 'Download', value: formatElapsed(stats.download_time_seconds * 1000) });
        if (stats.transcription_time_seconds != null) statItems.push({ label: 'Transcription', value: formatElapsed(stats.transcription_time_seconds * 1000) });
        if (stats.analysis_time_seconds != null) statItems.push({ label: 'Analysis', value: formatElapsed(stats.analysis_time_seconds * 1000) });
        if (stats.total_word_count != null) statItems.push({ label: 'Words', value: stats.total_word_count.toLocaleString() });
        if (stats.avg_words_per_minute != null) statItems.push({ label: 'Words/Min', value: stats.avg_words_per_minute });
        if (stats.segment_count != null) statItems.push({ label: 'Segments', value: stats.segment_count });
        if (stats.info_density_score != null) statItems.push({ label: 'Auto Info Density', value: stats.info_density_score + '/100' });
        if (stats.pacing_score != null) statItems.push({ label: 'Pacing', value: stats.pacing_score + '/100' });
        if (stats.baseline_input_tokens) statItems.push({ label: 'Input Tokens', value: stats.baseline_input_tokens.toLocaleString() });
        if (stats.baseline_output_tokens) statItems.push({ label: 'Output Tokens', value: stats.baseline_output_tokens.toLocaleString() });
        if (stats.estimated_cost_usd != null) statItems.push({ label: 'Est. Cost', value: '$' + stats.estimated_cost_usd.toFixed(4) });

        html += `
        <div class="card">
            <div class="collapsible-header" id="stats-toggle">
                <h2 class="section-title" style="margin-bottom:0">Processing Stats</h2>
                <span class="toggle">▸ Show</span>
            </div>
            <div class="collapsible-body" id="stats-body">
                <div class="stats-grid" style="margin-top:0.75rem">
                    ${statItems.map(s => `
                        <div class="stat-card">
                            <div class="stat-value">${escapeHtml(String(s.value))}</div>
                            <div class="stat-label">${escapeHtml(s.label)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>`;
    }

    container.innerHTML = html;

    // Render concept map if available
    if (analysisData.concept_map) {
        const mapEl = document.getElementById('detail-concept-map');
        if (mapEl) renderConceptMap(mapEl, analysisData.concept_map, false);
    }

    // Tag management
    const tagManager = document.getElementById('tag-manager');
    const newTagInput = document.getElementById('new-tag-input');
    const addTagBtn = document.getElementById('add-tag-btn');
    const detailTagSuggestions = document.getElementById('detail-tag-suggestions');

    async function loadDetailTags() {
        const [tags, allTags] = await Promise.all([
            API.get(`/api/transcripts/${transcript.id}/tags`),
            API.get('/api/tags'),
        ]);
        detailTagSuggestions.innerHTML = allTags.map(t => `<option value="${escapeHtml(t.name)}">`).join('');

        if (!tags.length) {
            tagManager.innerHTML = '<span style="color:var(--text-muted);font-size:0.8rem">No tags yet</span>';
            return;
        }
        tagManager.innerHTML = tags.map(t => {
            if (!t.accepted) return '';
            const isUser = t.source === 'user';
            const isConfirmed = t.confirmed === 1;
            const tagClass = isUser ? 'tag-user' : (isConfirmed ? 'tag-confirmed' : '');
            return `<span class="tag ${tagClass}" data-tag-id="${t.id}">
                ${escapeHtml(t.name)}
                ${!isUser && !isConfirmed ? `<span class="tag-action" data-action="confirm" title="Confirm">&#10003;</span>` : ''}
                ${!isUser ? `<span class="tag-action" data-action="reject" title="Reject">&times;</span>` : `<span class="tag-action" data-action="remove" title="Remove">&times;</span>`}
            </span>`;
        }).join('');

        tagManager.querySelectorAll('.tag-action').forEach(btn => {
            btn.addEventListener('click', async () => {
                const tagId = btn.closest('.tag').dataset.tagId;
                const action = btn.dataset.action;
                if (action === 'confirm') {
                    await API.post(`/api/transcripts/${transcript.id}/tags/${tagId}/confirm`);
                } else if (action === 'reject') {
                    await API.post(`/api/transcripts/${transcript.id}/tags/${tagId}/reject`);
                } else {
                    await API.del(`/api/transcripts/${transcript.id}/tags/${tagId}`);
                }
                loadDetailTags();
            });
        });
    }

    loadDetailTags();

    if (addTagBtn) {
        addTagBtn.addEventListener('click', async () => {
            const name = newTagInput.value.trim();
            if (!name) return;
            await API.post(`/api/transcripts/${transcript.id}/tags`, { name });
            newTagInput.value = '';
            loadDetailTags();
        });
        newTagInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); addTagBtn.click(); }
        });
    }

    // Collapsible toggles
    ['stats-toggle', 'transcript-toggle', 'entities-toggle'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            const bodyId = id.replace('-toggle', '-body');
            el.addEventListener('click', () => {
                const body = document.getElementById(bodyId);
                const toggle = el.querySelector('.toggle');
                body.classList.toggle('open');
                toggle.textContent = body.classList.contains('open') ? '▾ Hide' : '▸ Show';
            });
        }
    });

    // Package button handlers
    document.querySelectorAll('#package-buttons button').forEach(btn => {
        btn.addEventListener('click', async () => {
            const pkg = btn.dataset.package;
            const pkgInfo = packages[pkg];
            const allDone = pkgInfo.analysis_types.every(t => completedTypes.includes(t));

            if (allDone) {
                // Open first result type
                window.open(`/transcript/${transcript.id}/analysis/${pkgInfo.analysis_types[0]}`, '_blank');
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Running...';
            const statusEl = document.getElementById('analysis-status');
            statusEl.innerHTML = `<div class="loading"><div class="spinner"></div><span>Running ${escapeHtml(pkgInfo.label)}...</span></div>`;

            try {
                await API.post(`/api/transcripts/${transcript.id}/analyze-package`, { package: pkg });
                location.reload();
            } catch (e) {
                statusEl.innerHTML = `<div class="error-msg">Analysis failed: ${escapeHtml(e.message)}<br><button class="btn btn-sm btn-secondary" onclick="location.reload()">Retry</button></div>`;
                btn.disabled = false;
                btn.textContent = pkgInfo.label;
            }
        });
    });

    // Section deep-dive handlers
    document.querySelectorAll('.deep-dive-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const idx = parseInt(btn.dataset.section);
            const ddType = `section_deep_dive_${idx}`;

            if (completedTypes.includes(ddType)) {
                window.open(`/transcript/${transcript.id}/analysis/${ddType}`, '_blank');
                return;
            }

            btn.disabled = true;
            btn.textContent = '...';
            try {
                await API.post(`/api/transcripts/${transcript.id}/section-deep-dive`, { section_index: idx });
                window.open(`/transcript/${transcript.id}/analysis/${ddType}`, '_blank');
                btn.textContent = 'View';
                btn.style.color = 'var(--success)';
                btn.disabled = false;
            } catch (e) {
                btn.textContent = 'Error';
                btn.disabled = false;
            }
        });
    });
}


/* ===========================
   ANALYSIS VIEW PAGE
   =========================== */
async function initAnalysisView(transcriptId, analysisType) {
    const container = document.getElementById('analysis-content');
    const titleEl = document.getElementById('analysis-title');
    if (!container) return;

    try {
        const [transcript, result, types] = await Promise.all([
            API.get(`/api/transcripts/${transcriptId}`),
            API.get(`/api/transcripts/${transcriptId}/analysis/${analysisType}`),
            API.get('/api/analysis-types'),
        ]);

        const typeInfo = types[analysisType] || { label: analysisType };
        if (titleEl) {
            titleEl.textContent = `${typeInfo.label} — ${transcript.title}`;
        }
        document.title = `${typeInfo.label} — ${transcript.title}`;

        const data = JSON.parse(result.result_json);
        renderAnalysisResult(container, analysisType, data);
    } catch (e) {
        showError(container, 'Failed to load analysis: ' + e.message);
    }
}

function renderAnalysisResult(container, type, data) {
    let html = '';

    if (type === 'section_summaries') {
        const summaries = data.section_summaries || [];
        html = summaries.map(s => `
            <div class="extraction-item">
                <h3>${escapeHtml(s.section_title)}</h3>
                <p class="summary-text">${escapeHtml(s.summary)}</p>
                ${s.key_points?.length ? `
                    <ul class="key-points">
                        ${s.key_points.map(p => `<li>${escapeHtml(p)}</li>`).join('')}
                    </ul>
                ` : ''}
            </div>
        `).join('');

    } else if (type === 'content_vs_fluff') {
        html = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${data.substance_percentage || 0}%</div>
                    <div class="stat-label">Substance</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.filler_percentage || 0}%</div>
                    <div class="stat-label">Filler</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${formatTimestamp(data.optimal_start || 0)}</div>
                    <div class="stat-label">Start Watching</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${formatTimestamp(data.optimal_end || 0)}</div>
                    <div class="stat-label">Stop Watching</div>
                </div>
            </div>
            ${data.summary ? `<p class="summary-text" style="margin-bottom:1rem">${escapeHtml(data.summary)}</p>` : ''}
            <h3>Segment Map</h3>
            ${(data.segments || []).map(s => `
                <div class="segment-item">
                    <span class="type-label ${s.type === 'filler' ? 'type-filler' : 'type-substance'}">${escapeHtml(s.type)}</span>
                    <span class="outline-time" style="margin-left:0.5rem">${formatTimestamp(s.start_time)} – ${formatTimestamp(s.end_time)}</span>
                    <strong style="margin-left:0.5rem">${escapeHtml(s.label || '')}</strong>
                    <p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.2rem">${escapeHtml(s.description || '')}</p>
                </div>
            `).join('')}
        `;

    } else if (type === 'quote_extraction') {
        html = data.summary ? `<p class="summary-text" style="margin-bottom:1rem">${escapeHtml(data.summary)}</p>` : '';
        html += (data.extractions || []).map(e => `
            <div class="extraction-item">
                <div class="quote">"${escapeHtml(e.text)}"</div>
                <div class="meta-line">
                    <span class="badge badge-${e.category === 'quote' ? 'ready' : e.category === 'claim' ? 'analyzing' : 'pending'}">${escapeHtml(e.category)}</span>
                    <span style="margin-left:0.5rem">— ${escapeHtml(e.speaker || 'Unknown')}</span>
                    <span style="margin-left:0.5rem">[${formatTimestamp(e.timestamp)}]</span>
                </div>
                <p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.3rem">${escapeHtml(e.context || '')}</p>
            </div>
        `).join('');

    } else if (type === 'transcript_scoring') {
        const scores = data.scores || {};
        const justifications = data.justifications || {};
        const dims = ['information_density', 'clarity', 'structure', 'novelty', 'actionability'];
        const labels = { information_density: 'Info Density', clarity: 'Clarity', structure: 'Structure', novelty: 'Novelty', actionability: 'Actionability' };

        html = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" style="font-size:2rem">${scores.overall || '—'}</div>
                    <div class="stat-label">Overall Score</div>
                </div>
                ${dims.map(d => `
                    <div class="stat-card">
                        <div class="stat-value">${scores[d] != null ? scores[d] : '—'}</div>
                        <div class="stat-label">${labels[d]}</div>
                    </div>
                `).join('')}
            </div>
            ${data.summary ? `<p class="summary-text" style="margin:1rem 0">${escapeHtml(data.summary)}</p>` : ''}
            ${dims.map(d => justifications[d] ? `
                <div class="extraction-item">
                    <strong>${labels[d]}: ${scores[d]}/100</strong>
                    <p style="font-size:0.85rem;color:var(--text-muted);margin-top:0.2rem">${escapeHtml(justifications[d])}</p>
                </div>
            ` : '').join('')}
        `;

    } else if (type === 'argument_mapping') {
        html = data.summary ? `<p class="summary-text" style="margin-bottom:1rem">${escapeHtml(data.summary)}</p>` : '';
        html += (data.arguments || []).map(a => `
            <div class="extraction-item">
                <h3>${escapeHtml(a.claim)}</h3>
                <span class="badge badge-${a.strength === 'strong' ? 'ready' : a.strength === 'moderate' ? 'analyzing' : 'error'}">${escapeHtml(a.strength || 'unknown')}</span>
                <p style="font-size:0.85rem;margin-top:0.3rem">${escapeHtml(a.logical_structure || '')}</p>
                ${a.evidence?.length ? `<ul class="key-points">${a.evidence.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>` : ''}
            </div>
        `).join('');

    } else if (type === 'credibility_flags') {
        html = data.summary ? `<p class="summary-text" style="margin-bottom:1rem">${escapeHtml(data.summary)}</p>` : '';
        html += (data.flags || []).map(f => `
            <div class="extraction-item">
                <div style="display:flex;gap:0.5rem;align-items:center">
                    <span class="badge badge-${f.severity === 'high' ? 'error' : f.severity === 'medium' ? 'analyzing' : 'pending'}">${escapeHtml(f.severity)}</span>
                    <span class="badge" style="background:var(--bg);color:var(--text-muted)">${escapeHtml(f.type?.replace(/_/g, ' ') || '')}</span>
                    ${f.timestamp != null ? `<span style="color:var(--text-muted);font-size:0.75rem">[${formatTimestamp(f.timestamp)}]</span>` : ''}
                </div>
                <p style="margin-top:0.3rem">${escapeHtml(f.description)}</p>
            </div>
        `).join('');

    } else if (type === 'question_extraction') {
        html = (data.questions || []).map((q, i) => `
            <div class="extraction-item">
                <div style="display:flex;gap:0.5rem;align-items:flex-start">
                    <span style="color:var(--accent);font-weight:700;min-width:1.5rem">${i + 1}.</span>
                    <div>
                        <p style="font-weight:600">${escapeHtml(q.text)}</p>
                        <div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.2rem">
                            ${q.speaker ? `<span>— ${escapeHtml(q.speaker)}</span>` : ''}
                            ${q.timestamp != null ? `<span style="margin-left:0.5rem">[${formatTimestamp(q.timestamp)}]</span>` : ''}
                        </div>
                        ${q.context ? `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.1rem">${escapeHtml(q.context)}</p>` : ''}
                    </div>
                </div>
            </div>
        `).join('');

    } else if (type === 'resource_extraction') {
        const typeColors = { book: 'ready', url: 'analyzing', tool: 'pending', paper: 'downloading', person: 'done' };
        html = (data.resources || []).map(r => `
            <div class="extraction-item" style="display:flex;gap:0.75rem;align-items:flex-start">
                <span class="badge badge-${typeColors[r.type] || 'pending'}" style="min-width:fit-content">${escapeHtml(r.type || 'other')}</span>
                <div>
                    <strong>${escapeHtml(r.name)}</strong>
                    ${r.timestamp != null ? `<span style="color:var(--text-muted);font-size:0.75rem;margin-left:0.5rem">[${formatTimestamp(r.timestamp)}]</span>` : ''}
                    ${r.context ? `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.1rem">${escapeHtml(r.context)}</p>` : ''}
                </div>
            </div>
        `).join('');

    } else if (type === 'novelty_scoring') {
        html = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" style="font-size:2rem">${data.overall_score || '—'}</div>
                    <div class="stat-label">Overall Novelty</div>
                </div>
            </div>
            ${data.summary ? `<p class="summary-text" style="margin:1rem 0">${escapeHtml(data.summary)}</p>` : ''}
            ${(data.topics || []).map(t => `
                <div class="extraction-item">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <strong>${escapeHtml(t.topic)}</strong>
                        <span class="badge" style="background:rgba(108,99,255,0.2);color:var(--accent)">${t.score}/100</span>
                    </div>
                    <p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.2rem">${escapeHtml(t.justification || '')}</p>
                </div>
            `).join('')}
        `;

    } else if (type.startsWith('section_deep_dive')) {
        html = `
            <h2>${escapeHtml(data.section_title || 'Section Deep-Dive')}</h2>
            <p class="summary-text" style="margin:1rem 0">${escapeHtml(data.detailed_summary || '')}</p>
            ${data.key_points?.length ? `
                <h3>Key Points</h3>
                <ul class="key-points">${data.key_points.map(p => `<li>${escapeHtml(p)}</li>`).join('')}</ul>
            ` : ''}
            ${data.notable_quotes?.length ? `
                <h3>Notable Quotes</h3>
                ${data.notable_quotes.map(q => `
                    <div class="extraction-item">
                        <div class="quote">"${escapeHtml(q.text)}"</div>
                        ${q.timestamp != null ? `<span style="color:var(--text-muted);font-size:0.75rem">[${formatTimestamp(q.timestamp)}]</span>` : ''}
                        ${q.significance ? `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.2rem">${escapeHtml(q.significance)}</p>` : ''}
                    </div>
                `).join('')}
            ` : ''}
            ${data.questions?.length ? `
                <h3>Questions Raised</h3>
                <ul class="key-points">${data.questions.map(q => `<li>${escapeHtml(q)}</li>`).join('')}</ul>
            ` : ''}
            ${data.connections?.length ? `
                <h3>Connections</h3>
                <ul class="key-points">${data.connections.map(c => `<li>${escapeHtml(c)}</li>`).join('')}</ul>
            ` : ''}
        `;

    } else {
        // Generic fallback
        html = `<pre style="white-space:pre-wrap;font-size:0.8rem">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    }

    container.innerHTML = html;
}

/* renderConceptMap is now in concept-map.js */
