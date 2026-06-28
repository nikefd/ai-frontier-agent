/*!
 * sparrow-chat.js — the official floating chat dock for sparrow agents.
 *
 * Zero dependencies, self-injecting CSS, framework-free. Drop it on any page
 * that talks to a sparrow Harness over SSE and you get a consistent chat UI:
 * a floating action button, a slide-out dock, a conversation drawer, streaming
 * replies, tool-step chips, and citations.
 *
 *   <script src="/sparrow-chat.js"></script>
 *   <script>
 *     SparrowChat.mount({
 *       endpoint: '/api/agent/chat',
 *       conversationsApi: '/api/agent/conversations',
 *       title: 'AI Assistant',
 *       hint: 'Ask me anything…',
 *       accent: '#7c3aed',
 *     });
 *   </script>
 *
 * Markdown rendering is used if a global `marked` is present, else plain text.
 */
(function (global) {
  'use strict';

  var DEFAULTS = {
    endpoint: '/api/agent/chat',            // POST {message, conversation_id} -> SSE
    conversationsApi: '/api/agent/conversations', // GET list / GET :id / DELETE :id
    title: 'AI Assistant',
    hint: '',
    accent: '#7c3aed',
    placeholder: 'Type a message…',
    storageKey: 'sparrow_conv_id',
    fabIcon: '💬',
  };

  function h(html) {
    var t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstChild;
  }

  function esc(s) {
    return (s || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function md(text) {
    if (global.marked && typeof global.marked.parse === 'function') {
      try { return global.marked.parse(text || ''); } catch (e) { /* fall through */ }
    }
    return esc(text || '').replace(/\n/g, '<br>');
  }

  function relTime(ts) {
    if (!ts) return '';
    var t = new Date(ts).getTime();
    if (isNaN(t)) return '';
    var min = Math.floor(Math.max(0, Date.now() - t) / 60000);
    if (min < 1) return 'just now';
    if (min < 60) return min + 'm ago';
    var hr = Math.floor(min / 60);
    if (hr < 24) return hr + 'h ago';
    var day = Math.floor(hr / 24);
    if (day < 7) return day + 'd ago';
    return new Date(t).toISOString().slice(0, 10);
  }

  function injectStyle(accent) {
    if (document.getElementById('sparrow-chat-style')) return;
    var css = [
      ':root{--sp-accent:' + accent + '}',
      '.sp-fab{position:fixed;right:24px;bottom:24px;z-index:9000;width:56px;height:56px;',
      'border:none;border-radius:50%;cursor:pointer;background:var(--sp-accent);color:#fff;',
      'font-size:24px;box-shadow:0 6px 20px rgba(0,0,0,.25);transition:transform .15s}',
      '.sp-fab:hover{transform:scale(1.06)}',
      '.sp-dock{position:fixed;right:24px;bottom:92px;z-index:9000;width:420px;',
      'max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 120px);',
      'display:flex;flex-direction:column;background:#fff;border:1px solid #e3e7ef;',
      'border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.3);overflow:hidden;',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;',
      'font-size:14px;color:#0f172a}',
      '.sp-dock.sp-hidden{display:none}',
      '.sp-head{display:flex;align-items:center;justify-content:space-between;',
      'padding:12px 14px;border-bottom:1px solid #e3e7ef;background:#f1f3f8}',
      '.sp-title{font-weight:600;font-size:14px}',
      '.sp-head-actions{display:flex;gap:6px;align-items:center}',
      '.sp-btn{background:none;border:1px solid #e3e7ef;border-radius:6px;cursor:pointer;',
      'color:#64748b;font-size:13px;padding:3px 8px;line-height:1.2}',
      '.sp-btn:hover{background:#e7ebf2;color:#0f172a}',
      '.sp-hint{margin:10px 14px 0;padding:8px 12px;background:#f1f3f8;border:1px solid #e3e7ef;',
      'border-radius:8px;font-size:12px;color:#64748b}',
      '.sp-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:12px}',
      '.sp-msg{padding:10px 14px;border-radius:10px;max-width:88%;font-size:14px;line-height:1.55;',
      'word-wrap:break-word;overflow-wrap:anywhere}',
      '.sp-msg.user{background:var(--sp-accent);color:#fff;align-self:flex-end;border-bottom-right-radius:2px}',
      '.sp-msg.bot{background:#f1f3f8;color:#0f172a;border:1px solid #e3e7ef;align-self:flex-start;',
      'border-bottom-left-radius:2px}',
      '.sp-msg.bot p:first-child{margin-top:0}.sp-msg.bot p:last-child{margin-bottom:0}',
      '.sp-msg.bot pre{background:#0f172a;color:#e2e8f0;padding:10px;border-radius:8px;overflow:auto}',
      '.sp-steps{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}.sp-steps:empty{display:none}',
      '.sp-chip{font-size:12px;padding:3px 9px;border-radius:999px;background:#fff;',
      'border:1px solid #e3e7ef;color:#94a3b8;white-space:nowrap}',
      '.sp-chip.running{border-color:var(--sp-accent);color:var(--sp-accent)}',
      '.sp-chip em{font-style:normal;opacity:.7}',
      '.sp-cites{margin-top:8px;font-size:12px;color:#94a3b8;border-top:1px dashed #e3e7ef;padding-top:6px}',
      '.sp-thinking{color:#94a3b8;font-style:italic}',
      '.sp-input{display:flex;gap:8px;padding:12px 14px;border-top:1px solid #e3e7ef;background:#f1f3f8}',
      '.sp-input textarea{flex:1;resize:none;border:1px solid #e3e7ef;border-radius:8px;padding:8px 10px;',
      'font-family:inherit;font-size:14px;max-height:120px;color:#0f172a}',
      '.sp-input textarea:focus{outline:none;border-color:var(--sp-accent)}',
      '.sp-send{border:none;border-radius:8px;background:var(--sp-accent);color:#fff;cursor:pointer;',
      'padding:0 16px;font-size:14px}',
      '.sp-send:disabled{opacity:.5;cursor:default}',
      // conversation drawer
      '.sp-drawer{position:absolute;inset:0;background:#fff;z-index:5;display:flex;flex-direction:column}',
      '.sp-drawer.sp-hidden{display:none}',
      '.sp-conv{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid #e3e7ef;cursor:pointer}',
      '.sp-conv:hover{background:#f1f3f8}',
      '.sp-conv-main{flex:1;min-width:0}',
      '.sp-conv-title{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      '.sp-conv-meta{font-size:11px;color:#94a3b8}',
      '.sp-conv-del{background:none;border:none;color:#94a3b8;cursor:pointer;font-size:15px;',
      'padding:2px 6px;border-radius:6px;opacity:0;transition:opacity .15s}',
      '.sp-conv:hover .sp-conv-del{opacity:1}.sp-conv-del:hover{background:#e7ebf2;color:#0f172a}',
      '.sp-empty{padding:24px 8px;text-align:center;color:#94a3b8;font-size:12px}',
      '@media(max-width:520px){.sp-dock{right:8px;left:8px;width:auto;bottom:84px}.sp-fab{right:16px;bottom:16px}}',
    ].join('');
    var style = document.createElement('style');
    style.id = 'sparrow-chat-style';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function SparrowChat(opts) {
    this.cfg = Object.assign({}, DEFAULTS, opts || {});
    this.convId = localStorage.getItem(this.cfg.storageKey) || '';
    this.busy = false;
    this.opened = false;
    this._build();
  }

  SparrowChat.prototype._build = function () {
    injectStyle(this.cfg.accent);
    var c = this.cfg;
    this.fab = h('<button class="sp-fab" title="' + esc(c.title) + '">' + c.fabIcon + '</button>');
    this.dock = h(
      '<div class="sp-dock sp-hidden">' +
      '<div class="sp-head"><span class="sp-title">' + esc(c.title) + '</span>' +
      '<div class="sp-head-actions">' +
      '<button class="sp-btn" data-act="convs" title="History">🕘</button>' +
      '<button class="sp-btn" data-act="new" title="New chat">＋</button>' +
      '<button class="sp-btn" data-act="close" title="Close">✕</button>' +
      '</div></div>' +
      (c.hint ? '<div class="sp-hint">' + esc(c.hint) + '</div>' : '') +
      '<div class="sp-msgs"></div>' +
      '<div class="sp-input"><textarea rows="1" placeholder="' + esc(c.placeholder) + '"></textarea>' +
      '<button class="sp-send">Send</button></div>' +
      '<div class="sp-drawer sp-hidden"></div>' +
      '</div>'
    );
    document.body.appendChild(this.fab);
    document.body.appendChild(this.dock);

    this.msgs = this.dock.querySelector('.sp-msgs');
    this.input = this.dock.querySelector('textarea');
    this.sendBtn = this.dock.querySelector('.sp-send');
    this.drawer = this.dock.querySelector('.sp-drawer');

    var self = this;
    this.fab.addEventListener('click', function () { self.toggle(); });
    this.dock.querySelector('[data-act="close"]').addEventListener('click', function () { self.toggle(false); });
    this.dock.querySelector('[data-act="new"]').addEventListener('click', function () { self.newConversation(); });
    this.dock.querySelector('[data-act="convs"]').addEventListener('click', function () { self.toggleDrawer(); });
    this.sendBtn.addEventListener('click', function () { self.send(); });
    this.input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); self.send(); }
    });
    this.input.addEventListener('input', function () {
      self.input.style.height = 'auto';
      self.input.style.height = Math.min(self.input.scrollHeight, 120) + 'px';
    });
  };

  SparrowChat.prototype.toggle = function (force) {
    var open = force !== undefined ? force : this.dock.classList.contains('sp-hidden');
    this.dock.classList.toggle('sp-hidden', !open);
    if (open && !this.opened) { this.init(); this.opened = true; }
    if (open) this.input.focus();
  };

  SparrowChat.prototype.init = function () {
    if (this.convId) this.loadMessages(this.convId);
    else this.msgs.innerHTML = '<div class="sp-empty">Start a new chat, or open history above.</div>';
  };

  SparrowChat.prototype.newConversation = function () {
    this.convId = 'c_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    localStorage.setItem(this.cfg.storageKey, this.convId);
    this.msgs.innerHTML = '<div class="sp-empty">New chat started ✨</div>';
    this.drawer.classList.add('sp-hidden');
  };

  SparrowChat.prototype.toggleDrawer = function () {
    var hidden = this.drawer.classList.contains('sp-hidden');
    if (hidden) this.loadConversations();
    this.drawer.classList.toggle('sp-hidden', !hidden);
  };

  SparrowChat.prototype.loadConversations = function () {
    var self = this;
    this.drawer.innerHTML = '<div class="sp-empty">Loading…</div>';
    fetch(this.cfg.conversationsApi).then(function (r) { return r.json(); }).then(function (data) {
      var convs = Array.isArray(data) ? data : (data.conversations || []);
      if (!convs.length) { self.drawer.innerHTML = '<div class="sp-empty">No conversations yet.</div>'; return; }
      self.drawer.innerHTML = '';
      convs.forEach(function (cv) {
        var row = h(
          '<div class="sp-conv" data-id="' + esc(cv.id) + '">' +
          '<div class="sp-conv-main"><div class="sp-conv-title">' + esc(cv.title || 'New chat') + '</div>' +
          '<div class="sp-conv-meta">' + (cv.msg_count || 0) + ' msgs · ' + relTime(cv.updated_at) + '</div></div>' +
          '<button class="sp-conv-del" title="Delete">🗑</button></div>'
        );
        row.querySelector('.sp-conv-main').addEventListener('click', function () {
          self.convId = cv.id;
          localStorage.setItem(self.cfg.storageKey, cv.id);
          self.drawer.classList.add('sp-hidden');
          self.loadMessages(cv.id);
        });
        row.querySelector('.sp-conv-del').addEventListener('click', function (e) {
          e.stopPropagation();
          fetch(self.cfg.conversationsApi + '/' + encodeURIComponent(cv.id), { method: 'DELETE' })
            .then(function () { self.loadConversations(); });
        });
        self.drawer.appendChild(row);
      });
    }).catch(function () { self.drawer.innerHTML = '<div class="sp-empty">Failed to load.</div>'; });
  };

  SparrowChat.prototype.loadMessages = function (convId) {
    var self = this;
    fetch(this.cfg.conversationsApi + '/' + encodeURIComponent(convId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var list = data.messages || [];
        self.msgs.innerHTML = '';
        list.forEach(function (m) {
          if (m.role === 'user') self.addUser(m.content);
          else self.addBotFull(m);
        });
        self.scrollDown();
      }).catch(function () { /* ignore */ });
  };

  SparrowChat.prototype.addUser = function (text) {
    this.msgs.appendChild(h('<div class="sp-msg user">' + esc(text) + '</div>'));
  };

  SparrowChat.prototype.addBotFull = function (m) {
    var steps = (m.tool_steps || []).map(function (s) {
      return '<span class="sp-chip">' + esc(s.label) + ': ' + esc(s.summary) + '</span>';
    }).join('');
    var cites = (m.citations || []).length
      ? '<div class="sp-cites">Sources: ' + m.citations.map(esc).join(' · ') + '</div>' : '';
    this.msgs.appendChild(h('<div class="sp-msg bot">' +
      (steps ? '<div class="sp-steps">' + steps + '</div>' : '') + md(m.content) + cites + '</div>'));
  };

  SparrowChat.prototype.scrollDown = function () { this.msgs.scrollTop = this.msgs.scrollHeight; };

  SparrowChat.prototype.send = function () {
    if (this.busy) return;
    var text = this.input.value.trim();
    if (!text) return;
    this.input.value = '';
    this.input.style.height = 'auto';
    if (!this.convId) this.newConversation();
    var empty = this.msgs.querySelector('.sp-empty');
    if (empty) this.msgs.innerHTML = '';

    this.addUser(text);
    var bot = h('<div class="sp-msg bot"><div class="sp-steps"></div>' +
      '<div class="sp-body"><span class="sp-thinking">Thinking…</span></div></div>');
    this.msgs.appendChild(bot);
    var ui = { steps: bot.querySelector('.sp-steps'), body: bot.querySelector('.sp-body') };
    this.scrollDown();

    this.busy = true;
    this.sendBtn.disabled = true;
    var self = this;
    fetch(this.cfg.endpoint, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ message: text, conversation_id: this.convId }),
    }).then(function (resp) {
      if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);
      return self._consume(resp.body, ui);
    }).catch(function (e) {
      ui.body.innerHTML = '❌ ' + esc(e.message);
    }).then(function () {
      self.busy = false;
      self.sendBtn.disabled = false;
    });
  };

  SparrowChat.prototype._consume = function (body, ui) {
    var self = this;
    var reader = body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    function pump() {
      return reader.read().then(function (res) {
        if (res.done) return;
        buf += decoder.decode(res.value, { stream: true });
        var parts = buf.split('\n\n');
        buf = parts.pop();
        parts.forEach(function (part) {
          var line = part.split('\n').filter(function (l) { return l.indexOf('data:') === 0; })[0];
          if (!line) return;
          var ev;
          try { ev = JSON.parse(line.slice(5).trim()); } catch (e) { return; }
          self._event(ev, ui);
        });
        self.scrollDown();
        return pump();
      });
    }
    return pump();
  };

  SparrowChat.prototype._event = function (ev, ui) {
    if (ev.type === 'tool_call') {
      var args = Object.keys(ev.arguments || {}).map(function (k) { return k + '=' + ev.arguments[k]; }).join(' ');
      ui.steps.appendChild(h('<span class="sp-chip running" data-tool="' + esc(ev.name) + '">⚙️ ' +
        esc(ev.label || ev.name) + (args ? ' <em>' + esc(args) + '</em>' : '') + '</span>'));
    } else if (ev.type === 'tool_result') {
      var chips = ui.steps.querySelectorAll('.sp-chip.running[data-tool="' + ev.name + '"]');
      var chip = chips[chips.length - 1];
      if (chip) {
        chip.classList.remove('running');
        chip.innerHTML = '✅ ' + esc(ev.label || ev.name) + ': ' + esc(ev.summary || '');
      }
    } else if (ev.type === 'final') {
      var cites = (ev.citations || []).length
        ? '<div class="sp-cites">Sources: ' + ev.citations.map(esc).join(' · ') + '</div>' : '';
      ui.body.innerHTML = md(ev.content) + cites;
    } else if (ev.type === 'error') {
      ui.body.innerHTML = '❌ ' + esc(ev.message || 'error');
    }
  };

  // Public API
  global.SparrowChat = {
    mount: function (opts) { return new SparrowChat(opts); },
  };
})(typeof window !== 'undefined' ? window : this);
