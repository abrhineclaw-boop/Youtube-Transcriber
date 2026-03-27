/**
 * Concept Map — interactive radial tree SVG visualization.
 *
 * Supports two data formats:
 *   Legacy:  { central_node, branches: [{ label, children: string[] }] }
 *   Rich:    { central_node, branches: [{ label, importance?, relationship_type?, children: (string | { label, importance?, source_videos?, detail? })[] }] }
 */

/* ── helpers ──────────────────────────────────────────────────────── */

const NS = 'http://www.w3.org/2000/svg';

function _css(prop) {
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
}

function _colors() {
    return {
        accent:  _css('--accent')     || '#6c63ff',
        text:    _css('--text')       || '#e4e6f0',
        muted:   _css('--text-muted') || '#8b8fa3',
        border:  _css('--border')     || '#2e3244',
        bg:      _css('--bg')         || '#0f1117',
        bgCard:  _css('--bg-card')    || '#1a1d27',
    };
}

/** Normalize a child entry to { label, importance, source_videos, detail }. */
function _normalizeChild(child) {
    if (typeof child === 'string') return { label: child };
    return child;
}

/** Word-wrap text into lines that fit a given pixel width at a font size. */
function _wrapText(text, maxWidthPx, fontSize) {
    const charWidth = fontSize * 0.52;
    const maxChars = Math.max(4, Math.floor(maxWidthPx / charWidth));
    if (text.length <= maxChars) return [text];
    const words = text.split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
        const test = cur ? cur + ' ' + w : w;
        if (test.length > maxChars && cur) {
            lines.push(cur);
            cur = w;
        } else {
            cur = test;
        }
    }
    if (cur) lines.push(cur);
    // limit to 3 lines max
    if (lines.length > 3) {
        lines.length = 3;
        lines[2] = lines[2].slice(0, -3) + '...';
    }
    return lines;
}

/* ── SVG primitives ───────────────────────────────────────────────── */

function _makePath(x1, y1, x2, y2, color, width, dashArray) {
    // quadratic bezier — control point offset perpendicular to midpoint
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const off = len * 0.15;
    const cpx = mx + (-dy / len) * off;
    const cpy = my + (dx / len) * off;

    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', `M ${x1} ${y1} Q ${cpx} ${cpy} ${x2} ${y2}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-width', width);
    path.setAttribute('stroke-opacity', '0.5');
    if (dashArray) path.setAttribute('stroke-dasharray', dashArray);
    return path;
}

function _makeCircle(x, y, r, fill) {
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx', x);
    c.setAttribute('cy', y);
    c.setAttribute('r', r);
    c.setAttribute('fill', fill);
    return c;
}

function _makeWrappedText(x, y, lines, fontSize, fill, anchor) {
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', x);
    t.setAttribute('text-anchor', anchor || 'middle');
    t.setAttribute('fill', fill);
    t.setAttribute('font-size', fontSize);
    t.setAttribute('font-family', 'inherit');
    const lineH = fontSize * 1.25;
    const startY = y - ((lines.length - 1) * lineH) / 2;
    lines.forEach((line, i) => {
        const ts = document.createElementNS(NS, 'tspan');
        ts.setAttribute('x', x);
        ts.setAttribute('dy', i === 0 ? '0' : `${lineH}`);
        ts.setAttribute('dominant-baseline', 'central');
        ts.textContent = line;
        t.appendChild(ts);
    });
    // position first tspan
    t.setAttribute('y', startY);
    return t;
}

function _addGlowFilter(svg) {
    const defs = document.createElementNS(NS, 'defs');

    const filter = document.createElementNS(NS, 'filter');
    filter.setAttribute('id', 'node-glow');
    filter.setAttribute('x', '-50%');
    filter.setAttribute('y', '-50%');
    filter.setAttribute('width', '200%');
    filter.setAttribute('height', '200%');

    const blur = document.createElementNS(NS, 'feGaussianBlur');
    blur.setAttribute('in', 'SourceGraphic');
    blur.setAttribute('stdDeviation', '3');
    blur.setAttribute('result', 'blur');

    const merge = document.createElementNS(NS, 'feMerge');
    const n1 = document.createElementNS(NS, 'feMergeNode');
    n1.setAttribute('in', 'blur');
    const n2 = document.createElementNS(NS, 'feMergeNode');
    n2.setAttribute('in', 'SourceGraphic');
    merge.appendChild(n1);
    merge.appendChild(n2);

    filter.appendChild(blur);
    filter.appendChild(merge);
    defs.appendChild(filter);
    svg.appendChild(defs);
}

/* ── relationship type → dash style ───────────────────────────────── */

function _dashForType(type) {
    switch (type) {
        case 'contrasts': return '6,4';
        case 'extends':   return '2,3';
        default:          return null; // solid
    }
}

/* ── tooltip ──────────────────────────────────────────────────────── */

let _tooltip = null;

function _ensureTooltip() {
    if (_tooltip) return _tooltip;
    _tooltip = document.createElement('div');
    _tooltip.className = 'concept-map-tooltip';
    document.body.appendChild(_tooltip);
    return _tooltip;
}

function _showTooltip(e, html) {
    const tip = _ensureTooltip();
    tip.innerHTML = html;
    tip.style.display = 'block';
    _positionTooltip(e);
}

function _positionTooltip(e) {
    if (!_tooltip) return;
    const pad = 12;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    const rect = _tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth) x = e.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight) y = e.clientY - rect.height - pad;
    _tooltip.style.left = x + 'px';
    _tooltip.style.top = y + 'px';
}

function _hideTooltip() {
    if (_tooltip) _tooltip.style.display = 'none';
}

/* ── zoom & pan ───────────────────────────────────────────────────── */

function _enableZoomPan(svg, viewport, container) {
    let scale = 1;
    let tx = 0, ty = 0;
    let isPanning = false;
    let startX, startY;

    function applyTransform() {
        viewport.setAttribute('transform', `translate(${tx},${ty}) scale(${scale})`);
    }

    svg.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.min(4, Math.max(0.3, scale * delta));

        // zoom towards cursor
        const rect = svg.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        tx = mx - (mx - tx) * (newScale / scale);
        ty = my - (my - ty) * (newScale / scale);
        scale = newScale;
        applyTransform();
    }, { passive: false });

    svg.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        isPanning = true;
        startX = e.clientX - tx;
        startY = e.clientY - ty;
        svg.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        tx = e.clientX - startX;
        ty = e.clientY - startY;
        applyTransform();
    });

    window.addEventListener('mouseup', () => {
        isPanning = false;
        svg.style.cursor = 'grab';
    });

    svg.style.cursor = 'grab';

    // reset button
    const resetBtn = document.createElement('button');
    resetBtn.className = 'btn btn-sm btn-secondary concept-map-reset';
    resetBtn.textContent = 'Reset View';
    resetBtn.addEventListener('click', () => {
        scale = 1; tx = 0; ty = 0;
        applyTransform();
    });
    container.style.position = 'relative';
    container.appendChild(resetBtn);
}

/* ── main render ──────────────────────────────────────────────────── */

/**
 * Render a concept map as an interactive SVG radial tree.
 * @param {HTMLElement} container
 * @param {Object} conceptMap
 * @param {boolean} thumbnail  — compact mode, no interactivity
 */
function renderConceptMap(container, conceptMap, thumbnail = false) {
    if (!conceptMap || !conceptMap.branches) return;

    const branches = conceptMap.branches || [];
    const branchCount = branches.length;
    if (branchCount === 0) return;

    const col = _colors();

    /* ── sizing ── */
    const w = container.clientWidth || 400;
    const h = container.clientHeight || 300;
    const cx = w / 2;
    const cy = h / 2;

    const centralR    = thumbnail ? 20 : 36;
    const baseBranchR = thumbnail ? 14 : 24;
    const baseChildR  = thumbnail ? 6  : 10;

    // Adaptive radii based on branch count
    const branchRadius = Math.min(w, h) * (thumbnail ? 0.32 : (branchCount > 6 ? 0.22 : 0.28));
    const childRadius  = Math.min(w, h) * (thumbnail ? 0.45 : (branchCount > 6 ? 0.38 : 0.42));

    const centralFS = thumbnail ? 7  : 12;
    const branchFS  = thumbnail ? 6  : 10;
    const childFS   = thumbnail ? 5  : 8;

    /* ── SVG setup ── */
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);

    if (!thumbnail) _addGlowFilter(svg);

    const viewport = document.createElementNS(NS, 'g');
    viewport.setAttribute('class', 'concept-map-viewport');
    svg.appendChild(viewport);

    /* ── track bounding box ── */
    let minX = cx, maxX = cx, minY = cy, maxY = cy;
    function track(x, y, r) {
        minX = Math.min(minX, x - r - 40);
        maxX = Math.max(maxX, x + r + 40);
        minY = Math.min(minY, y - r - 20);
        maxY = Math.max(maxY, y + r + 20);
    }

    /* ── draw branches ── */
    branches.forEach((branch, i) => {
        const angle = (2 * Math.PI * i) / branchCount - Math.PI / 2;
        const bx = cx + branchRadius * Math.cos(angle);
        const by = cy + branchRadius * Math.sin(angle);

        const importance = branch.importance != null ? branch.importance : 0.8;
        const branchR = baseBranchR * (0.7 + 0.6 * importance);
        const dash = _dashForType(branch.relationship_type);

        // Branch group for collapse/expand
        const branchGroup = document.createElementNS(NS, 'g');
        branchGroup.setAttribute('class', 'concept-map-branch');
        branchGroup.style.opacity = '0';

        // Line center → branch
        const branchLine = _makePath(cx, cy, bx, by, col.accent, thumbnail ? 1.5 : 2, dash);
        branchGroup.appendChild(branchLine);

        // Children group (collapsible)
        const childGroup = document.createElementNS(NS, 'g');
        childGroup.setAttribute('class', 'concept-map-children');

        const children = (branch.children || []).map(_normalizeChild);
        const arcPerBranch = (2 * Math.PI) / branchCount;
        const spread = Math.min(arcPerBranch * 0.8, Math.PI / 2.5);

        children.forEach((child, j) => {
            const childAngle = angle + (j - (children.length - 1) / 2) * (spread / Math.max(children.length - 1, 1));
            const childImportance = child.importance != null ? child.importance : 0.5;
            const childR = baseChildR * (0.7 + 0.6 * childImportance);
            const childX = cx + childRadius * Math.cos(childAngle);
            const childY = cy + childRadius * Math.sin(childAngle);

            track(childX, childY, childR);

            // Line branch → child
            childGroup.appendChild(_makePath(bx, by, childX, childY, col.border, thumbnail ? 0.75 : 1, null));

            // Child circle
            const cc = _makeCircle(childX, childY, childR, col.border);
            childGroup.appendChild(cc);

            // Child label (outside circle)
            if (!thumbnail) {
                // Smart text placement: left-align on right side, right-align on left side
                const isRight = childAngle > -Math.PI / 2 && childAngle < Math.PI / 2;
                const anchor = isRight ? 'start' : 'end';
                const labelX = childX + (isRight ? childR + 6 : -childR - 6);
                const lines = _wrapText(child.label, childRadius * 0.55, childFS);
                childGroup.appendChild(_makeWrappedText(labelX, childY, lines, childFS, col.muted, anchor));
            }

            // Child tooltip
            if (!thumbnail) {
                const cHit = _makeCircle(childX, childY, childR + 4, 'transparent');
                cHit.style.cursor = 'default';
                let tipHtml = `<strong>${child.label}</strong>`;
                if (child.detail) tipHtml += `<div style="margin-top:4px">${child.detail}</div>`;
                if (child.source_videos && child.source_videos.length) {
                    tipHtml += `<div style="margin-top:4px;color:${col.muted};font-size:0.75rem">Sources: ${child.source_videos.join(', ')}</div>`;
                }
                if (child.importance != null) {
                    tipHtml += `<div style="margin-top:2px;color:${col.muted};font-size:0.7rem">Importance: ${Math.round(child.importance * 100)}%</div>`;
                }
                cHit.addEventListener('mouseenter', (e) => _showTooltip(e, tipHtml));
                cHit.addEventListener('mousemove', _positionTooltip);
                cHit.addEventListener('mouseleave', _hideTooltip);
                childGroup.appendChild(cHit);
            }
        });

        branchGroup.appendChild(childGroup);

        // Branch circle (on top of children lines)
        const bc = _makeCircle(bx, by, branchR, col.accent);
        if (!thumbnail) bc.setAttribute('filter', 'url(#node-glow)');
        branchGroup.appendChild(bc);

        // Branch label (inside circle)
        const bLines = _wrapText(branch.label, branchR * 2.2, branchFS);
        branchGroup.appendChild(_makeWrappedText(bx, by, bLines, branchFS, '#fff', 'middle'));

        track(bx, by, branchR);

        // ── interactivity (non-thumbnail) ──
        if (!thumbnail) {
            // Hit area for branch interactions
            const hitArea = _makeCircle(bx, by, branchR + 4, 'transparent');
            hitArea.style.cursor = 'pointer';

            // Hover
            hitArea.addEventListener('mouseenter', (e) => {
                bc.setAttribute('r', branchR * 1.12);
                childGroup.querySelectorAll('path').forEach(p => p.setAttribute('stroke-opacity', '0.8'));

                let tipHtml = `<strong>${branch.label}</strong>`;
                if (branch.relationship_type) tipHtml += `<div style="margin-top:2px;color:${col.muted};font-size:0.75rem">Relationship: ${branch.relationship_type}</div>`;
                if (branch.importance != null) tipHtml += `<div style="color:${col.muted};font-size:0.7rem">Importance: ${Math.round(branch.importance * 100)}%</div>`;
                tipHtml += `<div style="margin-top:4px;color:${col.muted};font-size:0.7rem">Click to toggle children</div>`;
                _showTooltip(e, tipHtml);
            });
            hitArea.addEventListener('mousemove', _positionTooltip);
            hitArea.addEventListener('mouseleave', () => {
                bc.setAttribute('r', branchR);
                childGroup.querySelectorAll('path').forEach(p => p.setAttribute('stroke-opacity', '0.5'));
                _hideTooltip();
            });

            // Click to collapse/expand children
            let collapsed = false;
            hitArea.addEventListener('click', (e) => {
                e.stopPropagation();
                collapsed = !collapsed;
                childGroup.style.display = collapsed ? 'none' : '';
                bc.setAttribute('fill', collapsed ? col.border : col.accent);
            });

            branchGroup.appendChild(hitArea);
        }

        viewport.appendChild(branchGroup);
    });

    // Central node (on top)
    const centralGroup = document.createElementNS(NS, 'g');
    centralGroup.style.opacity = '0';
    const cc = _makeCircle(cx, cy, centralR, col.accent);
    if (!thumbnail) cc.setAttribute('filter', 'url(#node-glow)');
    centralGroup.appendChild(cc);
    const cLines = _wrapText(conceptMap.central_node, centralR * 2, centralFS);
    centralGroup.appendChild(_makeWrappedText(cx, cy, cLines, centralFS, '#fff', 'middle'));

    if (!thumbnail) {
        const cHit = _makeCircle(cx, cy, centralR + 4, 'transparent');
        cHit.style.cursor = 'default';
        cHit.addEventListener('mouseenter', (e) => _showTooltip(e, `<strong>${conceptMap.central_node}</strong>`));
        cHit.addEventListener('mousemove', _positionTooltip);
        cHit.addEventListener('mouseleave', _hideTooltip);
        centralGroup.appendChild(cHit);
    }

    viewport.appendChild(centralGroup);

    /* ── dynamic viewBox ── */
    const pad = thumbnail ? 10 : 30;
    const vbX = minX - pad;
    const vbY = minY - pad;
    const vbW = maxX - minX + pad * 2;
    const vbH = maxY - minY + pad * 2;
    svg.setAttribute('viewBox', `${vbX} ${vbY} ${vbW} ${vbH}`);

    container.appendChild(svg);

    /* ── entrance animation ── */
    const groups = svg.querySelectorAll('.concept-map-branch, .concept-map-viewport > g:last-child');
    groups.forEach((g, i) => {
        requestAnimationFrame(() => {
            g.style.transition = `opacity 0.35s ease-out ${i * 0.06}s`;
            g.style.opacity = '1';
        });
    });

    /* ── zoom & pan (non-thumbnail) ── */
    if (!thumbnail) {
        _enableZoomPan(svg, viewport, container);
    }
}
