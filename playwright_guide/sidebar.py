"""
Injects and drives the floating chat sidebar on the live FireMapSim page —
used by playwright/guide.py.

Submitting a message in the sidebar sets window.__fsai_pending__;
guide.py's main() polls for it via wait_for_user_message(), calls the API,
then hands the reply to window.__fsai_append_agent__ via append_agent_reply().
"""

from playwright.sync_api import Page

SIDEBAR_JS = """(args) => {
    const [width, welcome] = args;
    if (document.getElementById('__fsai_sidebar__')) return;

    const panel = document.createElement('div');
    panel.id = '__fsai_sidebar__';
    panel.setAttribute('style', [
        'all: initial',
        'position: fixed',
        'top: 0',
        'right: 0',
        'bottom: 0',
        'width: ' + width + 'px',
        'height: 100vh',
        'z-index: 2147483647',
        'display: flex',
        'flex-direction: column',
        'background: #ffffff',
        'border-left: 3px solid #ff6600',
        'box-shadow: -4px 0 24px rgba(0,0,0,0.18)',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
        'font-size: 14px',
        'color: #1a1a1a',
        'overflow: hidden',
        'box-sizing: border-box',
        'transform: translateX(100%)',
        'transition: transform 0.25s ease',
        'visibility: hidden',
    ].join(' !important; ') + ' !important');

    const header = document.createElement('div');
    header.setAttribute('style', [
        'all: initial', 'display: flex', 'align-items: center', 'gap: 8px',
        'padding: 12px 16px', 'background: #f7f7f7', 'border-bottom: 1px solid #e5e5e5',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'flex-shrink: 0',
        'box-sizing: border-box',
    ].join(' !important; ') + ' !important');

    const dot = document.createElement('span');
    dot.setAttribute('style', 'all:initial !important; width:10px !important; height:10px !important; border-radius:50% !important; background:#ff6600 !important; display:inline-block !important;');
    const title = document.createElement('span');
    title.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; font-weight:600 !important; color:#1a1a1a !important;');
    title.textContent = 'FireMapSim AI Co-pilot';
    const collapseBtn = document.createElement('button');
    collapseBtn.setAttribute('style', 'all:initial !important; margin-left:auto !important; background:transparent !important; border:none !important; color:#888 !important; font-size:18px !important; line-height:1 !important; cursor:pointer !important; padding:0 2px !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important;');
    collapseBtn.textContent = String.fromCharCode(10005);
    collapseBtn.title = 'Collapse';
    collapseBtn.onclick = () => window.__fsai_toggle__(false);
    header.appendChild(dot);
    header.appendChild(title);
    header.appendChild(collapseBtn);

    const msgArea = document.createElement('div');
    msgArea.id = '__fsai_msg_area__';
    msgArea.setAttribute('style', [
        'all: initial', 'flex: 1 1 auto', 'overflow-y: auto', 'overflow-x: hidden',
        'padding: 16px', 'display: flex', 'flex-direction: column', 'gap: 10px',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
        'font-size: 14px', 'color: #333', 'line-height: 1.55',
        'min-height: 0', 'box-sizing: border-box',
    ].join(' !important; ') + ' !important');

    const inputRow = document.createElement('div');
    inputRow.id = '__fsai_input_row__';
    inputRow.setAttribute('style', [
        'all: initial', 'display: flex', 'gap: 8px', 'align-items: center',
        'padding: 12px 16px', 'background: #f7f7f7', 'border-top: 1px solid #e5e5e5',
        'flex-shrink: 0', 'box-sizing: border-box',
    ].join(' !important; ') + ' !important');

    const input = document.createElement('input');
    input.id = '__fsai_input__';
    input.type = 'text';
    input.placeholder = 'Ask about your burn setup...';
    input.setAttribute('style', [
        'all: initial', 'flex: 1 1 auto', 'min-width: 0', 'padding: 8px 10px',
        'border: 1px solid #ccc', 'border-radius: 6px',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'font-size: 13px',
        'color: #1a1a1a', 'background: #ffffff', 'box-sizing: border-box',
    ].join(' !important; ') + ' !important');

    const sendBtn = document.createElement('button');
    sendBtn.id = '__fsai_send__';
    sendBtn.textContent = 'Send';
    sendBtn.setAttribute('style', [
        'all: initial', 'background: #ff6600', 'color: #fff', 'border: none',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'font-size: 12px',
        'font-weight: 600', 'padding: 8px 14px', 'border-radius: 6px', 'cursor: pointer',
        'flex-shrink: 0', 'box-sizing: border-box',
    ].join(' !important; ') + ' !important');

    inputRow.appendChild(input);
    inputRow.appendChild(sendBtn);

    panel.appendChild(header);
    panel.appendChild(msgArea);
    panel.appendChild(inputRow);
    (document.body || document.documentElement).appendChild(panel);

    const launcher = document.createElement('button');
    launcher.id = '__fsai_launcher__';
    launcher.setAttribute('style', [
        'all: initial', 'position: fixed', 'bottom: 24px', 'right: 24px',
        'width: 56px', 'height: 56px', 'border-radius: 50%',
        'background: #ff6600', 'box-shadow: 0 4px 16px rgba(0,0,0,0.3)',
        'display: flex', 'align-items: center', 'justify-content: center',
        'cursor: pointer', 'z-index: 2147483647', 'border: none',
        'font-size: 26px', 'box-sizing: border-box',
    ].join(' !important; ') + ' !important');
    launcher.title = 'Open FireMapSim AI Co-pilot';
    launcher.textContent = String.fromCodePoint(128293);

    const badge = document.createElement('span');
    badge.id = '__fsai_badge__';
    badge.setAttribute('style', 'all:initial !important; position:absolute !important; top:-2px !important; right:-2px !important; width:14px !important; height:14px !important; border-radius:50% !important; background:#ff3b30 !important; border:2px solid #fff !important; display:none !important; box-sizing:border-box !important;');
    launcher.appendChild(badge);
    launcher.onclick = () => window.__fsai_toggle__(true);
    (document.body || document.documentElement).appendChild(launcher);

    window.__fsai_expanded__ = false;
    window.__fsai_toggle__ = function(expand) {
        const p = document.getElementById('__fsai_sidebar__');
        const l = document.getElementById('__fsai_launcher__');
        const b = document.getElementById('__fsai_badge__');
        if (!p || !l) return;
        window.__fsai_expanded__ = expand;
        if (expand) {
            document.documentElement.style.setProperty('margin-right', width + 'px', 'important');
            document.body.style.setProperty('margin-right', width + 'px', 'important');
            p.style.setProperty('visibility', 'visible', 'important');
            p.style.setProperty('transform', 'translateX(0)', 'important');
            l.style.setProperty('display', 'none', 'important');
            if (b) b.style.setProperty('display', 'none', 'important');
            const inp = document.getElementById('__fsai_input__');
            if (inp) inp.focus();
        } else {
            document.documentElement.style.setProperty('margin-right', '0px', 'important');
            document.body.style.setProperty('margin-right', '0px', 'important');
            p.style.setProperty('transform', 'translateX(100%)', 'important');
            p.style.setProperty('visibility', 'hidden', 'important');
            l.style.setProperty('display', 'flex', 'important');
        }
        window.dispatchEvent(new Event('resize'));
    };

    // ---- chat transcript + input wiring ----------------------

    window.__fsai_pending__ = null;   // set by trySend(); read+cleared by Python
    window.__fsai_busy__ = false;      // true while waiting on an API reply

    function scrollBottom() {
        const area = document.getElementById('__fsai_msg_area__');
        if (area) area.scrollTop = area.scrollHeight;
    }

    function appendBubble(text, role) {
        const area = document.getElementById('__fsai_msg_area__');
        if (!area) return;
        const wrap = document.createElement('div');
        wrap.setAttribute('style', [
            'all: initial', 'display: flex',
            'justify-content: ' + (role === 'user' ? 'flex-end' : 'flex-start'),
        ].join(' !important; ') + ' !important');
        const bg = role === 'user' ? '#ff6600' : (role === 'error' ? '#fdecea' : '#f1f1f1');
        const color = role === 'user' ? '#ffffff' : (role === 'error' ? '#b3261e' : '#1a1a1a');
        const bubble = document.createElement('div');
        bubble.setAttribute('style', [
            'all: initial', 'max-width: 85%', 'padding: 8px 12px', 'border-radius: 12px',
            'background: ' + bg, 'color: ' + color,
            'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'font-size: 13px',
            'line-height: 1.5', 'white-space: pre-wrap', 'word-wrap: break-word',
            'box-sizing: border-box',
        ].join(' !important; ') + ' !important');
        bubble.textContent = text;
        wrap.appendChild(bubble);
        area.appendChild(wrap);
        scrollBottom();
    }

    function showTyping() {
        removeTyping();
        const area = document.getElementById('__fsai_msg_area__');
        if (!area) return;
        const wrap = document.createElement('div');
        wrap.id = '__fsai_typing__';
        wrap.setAttribute('style', 'all:initial !important; display:flex !important; justify-content:flex-start !important;');
        const bubble = document.createElement('div');
        bubble.setAttribute('style', 'all:initial !important; padding:8px 12px !important; border-radius:12px !important; background:#f1f1f1 !important; color:#999 !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; font-style:italic !important;');
        bubble.textContent = 'Thinking...';
        wrap.appendChild(bubble);
        area.appendChild(wrap);
        scrollBottom();
    }

    function removeTyping() {
        const t = document.getElementById('__fsai_typing__');
        if (t) t.remove();
    }

    function setBusy(busy) {
        window.__fsai_busy__ = busy;
        const inp = document.getElementById('__fsai_input__');
        const btn = document.getElementById('__fsai_send__');
        if (inp) inp.disabled = busy;
        if (btn) btn.disabled = busy;
        if (busy) showTyping(); else removeTyping();
    }

    function flagUnread() {
        if (!window.__fsai_expanded__) {
            const b = document.getElementById('__fsai_badge__');
            if (b) b.style.setProperty('display', 'block', 'important');
        }
    }

    window.__fsai_append_agent__ = function(text) {
        setBusy(false);
        appendBubble(text, 'agent');
        flagUnread();
    };
    window.__fsai_append_error__ = function(text) {
        setBusy(false);
        appendBubble(text, 'error');
        flagUnread();
    };

    function trySend() {
        if (window.__fsai_busy__) return;
        const inp = document.getElementById('__fsai_input__');
        if (!inp) return;
        const val = (inp.value || '').trim();
        if (!val) return;
        inp.value = '';
        appendBubble(val, 'user');
        setBusy(true);
        window.__fsai_pending__ = val;
    }

    sendBtn.onclick = trySend;
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); trySend(); }
    });

    appendBubble(welcome, 'agent');
}"""


def inject_sidebar(page: Page, width: int, welcome: str) -> None:
    """
    Inject a collapsed floating launcher button plus a hidden right sidebar
    chat panel: a scrolling transcript, a text input, and a Send button.
    """
    try:
        page.evaluate(SIDEBAR_JS, [width, welcome])
        print("  -> Sidebar injected (collapsed).")
    except Exception as exc:
        print(f"  !  Sidebar injection failed: {exc}")


def wait_for_user_message(page: Page) -> str:
    """Block until the sidebar's Send button (or Enter) sets a pending message."""
    page.wait_for_function("() => window.__fsai_pending__ !== null", timeout=0)
    msg = page.evaluate("() => window.__fsai_pending__")
    page.evaluate("() => { window.__fsai_pending__ = null; }")
    return msg


def append_agent_reply(page: Page, text: str) -> None:
    page.evaluate("(t) => window.__fsai_append_agent__(t)", text)


def append_agent_error(page: Page, text: str) -> None:
    page.evaluate("(t) => window.__fsai_append_error__(t)", text)
