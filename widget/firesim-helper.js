/*
 * widget/firesim-helper.js
 *
 * FireMapSim Q&A helper for the real frontend: the same floating chat sidebar
 * and control highlighting as playwright/guide.py, but running in the page
 * itself and calling the firesim-ai API directly. Add one line to FireMapSim's
 * index.html (served by the API, which fills in the selector map):
 *
 *   <script src="https://API_HOST/widget/firesim-helper.js" defer></script>
 *
 * The API URL defaults to the script's own origin; override it with
 * data-api="https://..." on the tag. The API's CORS_ORIGINS must include
 * FireMapSim's origin.
 *
 * The helper only explains and points: it never moves the map or edits fields.
 * Replies are rendered as text (textContent), never HTML.
 */
(function () {
    'use strict';

    // Top-level page only, and only once (a dev-server hot reload re-runs it).
    if (window.top !== window || window.__fsaiHelper) return;

    // Replaced with app/ui_selectors.py's STEP_SELECTORS when served by the
    // API. Playwright selector syntax: CSS plus `>> nth=N` and `:has-text('...')`.
    var SELECTORS = /*__FSAI_SELECTORS__*/{};

    var script = document.currentScript;
    var API = ((script && script.dataset.api) ||
               (script && script.src ? new URL(script.src).origin : location.origin)).replace(/\/+$/, '');
    var WIDTH = 360;
    var MAX_CHARS = 2000;  // the API's message limit (api/main.py MAX_MESSAGE_CHARS)
    // Longer than the server can take (60 s LLM timeout x 3 attempts, plus
    // queueing) so the widget doesn't give up on a turn that is still billing.
    var TIMEOUT_MS = 240000;
    var WELCOME = "Ask me anything about FireMapSim - how a control works, where to find " +
                  "it, or what a setting means. I'll point to it on the page while I explain.";
    var STORE_SESSION = 'fsai.session';
    var STORE_LOG = 'fsai.transcript';
    var HIGHLIGHT_CSS =
        'outline: 4px solid #ff6600 !important;' +
        'outline-offset: 3px !important;' +
        'background-color: rgba(255, 102, 0, 0.12) !important;' +
        'transition: all 0.3s ease;';

    // ---- storage (per tab; the page works without it) ---------------------

    function load(key) {
        try { return sessionStorage.getItem(key); } catch (e) { return null; }
    }
    function save(key, value) {
        try {
            if (value === null) sessionStorage.removeItem(key);
            else sessionStorage.setItem(key, value);
        } catch (e) { /* private mode / blocked storage */ }
    }

    // ---- highlighting ------------------------------------------------------

    // Resolves the subset of Playwright selector syntax STEP_SELECTORS uses.
    // Anything else is treated as plain CSS.
    function resolve(selector) {
        var nth = null;
        var m = selector.match(/^(.*?)\s*>>\s*nth=(\d+)\s*$/);
        if (m) { selector = m[1]; nth = parseInt(m[2], 10); }
        var text = null;
        m = selector.match(/^(.*):has-text\((['"])(.*)\2\)$/);
        if (m) { selector = m[1]; text = m[3].toLowerCase(); }
        var found;
        try { found = Array.prototype.slice.call(document.querySelectorAll(selector)); }
        catch (e) { return null; }
        if (text !== null) {
            found = found.filter(function (el) {
                return (el.textContent || '').toLowerCase().indexOf(text) !== -1;
            });
        }
        return found[nth === null ? 0 : nth] || null;
    }

    // Restores every highlighted control by the marker highlightOn leaves,
    // not by re-resolving a selector that may now match a different element.
    function highlightOff() {
        var marked = document.querySelectorAll('[data-fsai-orig-style]');
        for (var i = 0; i < marked.length; i++) {
            marked[i].setAttribute('style', marked[i].dataset.fsaiOrigStyle);
            delete marked[i].dataset.fsaiOrigStyle;
        }
    }

    function highlightOn(key) {
        var el = SELECTORS[key] && resolve(SELECTORS[key]);
        if (!el) return false;
        if (el.dataset.fsaiOrigStyle === undefined) {
            el.dataset.fsaiOrigStyle = el.getAttribute('style') || '';
        }
        el.style.cssText += HIGHLIGHT_CSS;
        el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
        return true;
    }

    // /chat's `highlight` list is the source of truth: outline the first key
    // with a selector; an empty list means outline nothing.
    function applyHighlight(keys) {
        highlightOff();
        for (var i = 0; i < (keys || []).length; i++) {
            if (SELECTORS[keys[i]] && highlightOn(keys[i])) return;
        }
    }

    // ---- API ---------------------------------------------------------------

    function post(path, body, sessionId) {
        var headers = { 'Content-Type': 'application/json' };
        if (sessionId) headers['X-Session-Id'] = sessionId;
        var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
        var timer = ctrl && setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
        return fetch(API + path, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(body || {}),
            signal: ctrl ? ctrl.signal : undefined
        }).finally(function () { if (timer) clearTimeout(timer); });
    }

    function sessionId() {
        var existing = load(STORE_SESSION);
        if (existing) return Promise.resolve(existing);
        return post('/api/session').then(function (r) {
            if (!r.ok) throw httpError(r);
            return r.json();
        }).then(function (data) {
            save(STORE_SESSION, data.session_id);
            return data.session_id;
        });
    }

    function httpError(response) {
        var err = new Error('HTTP ' + response.status);
        err.status = response.status;
        err.response = response;
        return err;
    }

    // Sessions live in API memory, so they vanish on expiry or a server
    // restart. On a 401, mint a fresh one and retry once.
    function chat(message, retried) {
        return sessionId().then(function (sid) {
            return post('/chat', { message: message }, sid);
        }).then(function (r) {
            if (r.status === 401 && !retried) {
                save(STORE_SESSION, null);
                return chat(message, true);
            }
            if (!r.ok) throw httpError(r);
            return r.json();
        });
    }

    function errorText(err) {
        if (err && err.status === 429 && err.response) {
            // The server's 429 detail says which limit was hit and when to retry.
            return err.response.json().then(function (body) {
                return typeof body.detail === 'string' ? body.detail
                    : 'Too many requests. Please wait a moment and try again.';
            }, function () { return 'Too many requests. Please wait a moment and try again.'; });
        }
        return Promise.resolve('Sorry, I ran into a problem reaching the assistant. Please try again.');
    }

    // ---- UI ----------------------------------------------------------------

    // A shadow root keeps FireMapSim's CSS out of the panel and the panel's
    // CSS out of FireMapSim.
    var STYLE = [
        ':host { all: initial; }',
        '* { box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }',
        '.panel { position: fixed; top: 16px; right: 16px; bottom: 16px;',
        '  width: ' + WIDTH + 'px; max-width: calc(100vw - 32px); z-index: 2147483647;',
        '  display: flex; flex-direction: column; overflow: hidden;',
        '  background: #fff; color: #1a1a1a; font-size: 14px;',
        '  border: 1px solid #e5e5e5; border-top: 3px solid #ff6600; border-radius: 12px;',
        '  box-shadow: 0 8px 32px rgba(0,0,0,0.22);',
        '  transform: translateX(calc(100% + 32px)); visibility: hidden;',
        '  transition: transform 0.25s ease, visibility 0s linear 0.25s; }',
        '.panel.open { transform: translateX(0); visibility: visible; transition: transform 0.25s ease; }',
        '.header { display: flex; align-items: center; gap: 8px; padding: 12px 16px;',
        '  background: #f7f7f7; border-bottom: 1px solid #e5e5e5; flex-shrink: 0; }',
        '.dot { width: 10px; height: 10px; border-radius: 50%; background: #ff6600; }',
        '.title { font-size: 13px; font-weight: 600; }',
        '.close { margin-left: auto; background: none; border: none; color: #888;',
        '  font-size: 18px; line-height: 1; cursor: pointer; padding: 0 2px; }',
        '.msgs { flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: 16px;',
        '  display: flex; flex-direction: column; gap: 10px; line-height: 1.55; }',
        '.row { display: flex; justify-content: flex-start; }',
        '.row.user { justify-content: flex-end; }',
        '.bubble { max-width: 85%; padding: 8px 12px; border-radius: 12px; font-size: 13px;',
        '  line-height: 1.5; white-space: pre-wrap; overflow-wrap: break-word;',
        '  background: #f1f1f1; color: #1a1a1a; }',
        '.user .bubble { background: #ff6600; color: #fff; }',
        '.error .bubble { background: #fdecea; color: #b3261e; }',
        '.typing .bubble { color: #999; font-style: italic; }',
        '.input-row { display: flex; gap: 8px; align-items: center; padding: 12px 16px;',
        '  background: #f7f7f7; border-top: 1px solid #e5e5e5; flex-shrink: 0; }',
        'input { flex: 1 1 auto; min-width: 0; padding: 8px 10px; border: 1px solid #ccc;',
        '  border-radius: 6px; font-size: 13px; color: #1a1a1a; background: #fff; }',
        '.send { background: #ff6600; color: #fff; border: none; font-size: 12px; font-weight: 600;',
        '  padding: 8px 14px; border-radius: 6px; cursor: pointer; flex-shrink: 0; }',
        '.send:disabled, input:disabled { opacity: 0.6; cursor: default; }',
        '.launcher { position: fixed; bottom: 24px; right: 24px; width: 56px; height: 56px;',
        '  border-radius: 50%; background: #ff6600; border: none; cursor: pointer;',
        '  box-shadow: 0 4px 16px rgba(0,0,0,0.3); z-index: 2147483647;',
        '  display: flex; align-items: center; justify-content: center; font-size: 26px; }',
        '.launcher.hidden { display: none; }',
        '.badge { position: absolute; top: -2px; right: -2px; width: 14px; height: 14px;',
        '  border-radius: 50%; background: #ff3b30; border: 2px solid #fff; display: none; }',
        '.badge.on { display: block; }'
    ].join('\n');

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function mount() {
        if (document.getElementById('fsai-helper')) return;
        var host = el('div');
        host.id = 'fsai-helper';
        var root = host.attachShadow({ mode: 'open' });
        root.appendChild(el('style', null, STYLE));

        var panel = el('div', 'panel');
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'FireMapSim Q&A Helper');
        var header = el('div', 'header');
        var close = el('button', 'close', String.fromCharCode(10005));
        close.title = 'Collapse';
        close.setAttribute('aria-label', 'Collapse');
        header.appendChild(el('span', 'dot'));
        header.appendChild(el('span', 'title', 'FireMapSim Q&A Helper'));
        header.appendChild(close);

        var msgs = el('div', 'msgs');
        msgs.setAttribute('aria-live', 'polite');
        var inputRow = el('div', 'input-row');
        var input = el('input');
        input.type = 'text';
        input.maxLength = MAX_CHARS;
        input.placeholder = 'Ask about your burn setup...';
        input.setAttribute('aria-label', 'Message');
        var send = el('button', 'send', 'Send');
        inputRow.appendChild(input);
        inputRow.appendChild(send);
        panel.appendChild(header);
        panel.appendChild(msgs);
        panel.appendChild(inputRow);

        var launcher = el('button', 'launcher', String.fromCodePoint(128293));
        launcher.title = 'Open FireMapSim Q&A Helper';
        launcher.setAttribute('aria-label', 'Open FireMapSim Q&A Helper');
        var badge = el('span', 'badge');
        launcher.appendChild(badge);

        root.appendChild(panel);
        root.appendChild(launcher);
        document.body.appendChild(host);

        var expanded = false;
        var busy = false;
        var transcript = [];
        try { transcript = JSON.parse(load(STORE_LOG) || '[]'); } catch (e) { transcript = []; }

        function toggle(expand) {
            expanded = expand;
            panel.classList.toggle('open', expand);
            launcher.classList.toggle('hidden', expand);
            if (expand) {
                badge.classList.remove('on');
                input.focus();
            }
        }

        function bubble(text, role, remember) {
            var row = el('div', 'row ' + role);
            row.appendChild(el('div', 'bubble', text));
            msgs.appendChild(row);
            msgs.scrollTop = msgs.scrollHeight;
            if (remember) {
                transcript.push({ role: role, text: text });
                save(STORE_LOG, JSON.stringify(transcript.slice(-50)));
            }
            return row;
        }

        var typing = null;
        function setBusy(on) {
            busy = on;
            input.disabled = on;
            send.disabled = on;
            if (typing) { typing.remove(); typing = null; }
            if (on) typing = bubble('Thinking...', 'typing', false);
        }

        function reply(text, role) {
            setBusy(false);
            bubble(text, role, true);
            if (!expanded) badge.classList.add('on');
        }

        function trySend() {
            if (busy) return;
            var text = (input.value || '').trim();
            if (!text) return;
            input.value = '';
            bubble(text, 'user', true);
            setBusy(true);
            chat(text).then(function (data) {
                // Show the reply first: highlighting may scroll the page.
                reply(data.reply, 'agent');
                applyHighlight(data.highlight);
            }, function (err) {
                return errorText(err).then(function (msg) { reply(msg, 'error'); });
            });
        }

        bubble(WELCOME, 'agent', false);
        transcript.forEach(function (m) { bubble(m.text, m.role, false); });

        launcher.addEventListener('click', function () { toggle(true); });
        close.addEventListener('click', function () { toggle(false); });
        send.addEventListener('click', trySend);
        // Keep FireMapSim's own keyboard shortcuts from firing while typing.
        ['keyup', 'keypress'].forEach(function (type) {
            input.addEventListener(type, function (e) { e.stopPropagation(); });
        });
        input.addEventListener('keydown', function (e) {
            e.stopPropagation();
            if (e.key === 'Enter') { e.preventDefault(); trySend(); }
        });

        window.__fsaiHelper = { open: function () { toggle(true); }, close: function () { toggle(false); },
                                highlight: applyHighlight, clearHighlight: highlightOff };
    }

    window.__fsaiHelper = {};  // claims the slot so a second copy of the script bails
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount, { once: true });
    } else {
        mount();
    }
})();
