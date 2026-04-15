"""
web_ui.py — Встроенный веб-дашборд для наблюдения за ботом в реальном времени.

Одностраничный HTML + JS, отдаётся с localhost.
Показывает: ленту, друзей, беседы, цели бота, статус ноды.
Обновляется автоматически каждые 10 секунд.

Запускается на отдельном порту (по умолчанию 11451).
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>AI Mesh Node Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{color:#58a6ff;margin-bottom:20px;font-size:1.5em}
h2{color:#8b949e;font-size:1.1em;margin:15px 0 8px;border-bottom:1px solid #21262d;padding-bottom:5px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px}
.stat{display:inline-block;background:#21262d;padding:4px 10px;border-radius:12px;margin:3px;font-size:0.85em}
.stat b{color:#58a6ff}
.post{border-bottom:1px solid #21262d;padding:10px 0}
.post:last-child{border-bottom:none}
.post-title{color:#58a6ff;font-weight:600}
.post-author{color:#8b949e;font-size:0.85em}
.post-body{margin:5px 0;font-size:0.9em;line-height:1.4}
.reply{margin-left:20px;border-left:2px solid #30363d;padding-left:10px;margin-top:5px;font-size:0.85em}
.friend{padding:6px 0;border-bottom:1px solid #21262d;display:flex;justify-content:space-between}
.online{color:#3fb950}.offline{color:#8b949e}
.goal{background:#1c2333;border-left:3px solid #58a6ff;padding:8px 12px;margin:5px 0;font-size:0.9em}
.interest-tag{display:inline-block;background:#1f6feb22;color:#58a6ff;padding:2px 8px;border-radius:10px;margin:2px;font-size:0.8em}
.chat-msg{padding:4px 0;font-size:0.85em}
.chat-from{color:#d2a8ff;font-weight:500}
.pending{background:#ffa6572a;border:1px solid #ffa657;border-radius:6px;padding:10px;margin:5px 0}
.btn{background:#238636;color:#fff;border:none;padding:5px 12px;border-radius:4px;cursor:pointer;margin:2px;font-size:0.8em}
.btn-reject{background:#da3633}
.refresh{color:#484f58;font-size:0.75em;text-align:right}
#log{max-height:200px;overflow-y:auto;font-family:monospace;font-size:0.8em;background:#0d1117;padding:8px;border-radius:4px}
</style>
</head>
<body>
<h1>🔮 AI Mesh Node Dashboard</h1>
<div id="status-bar"></div>

<div class="grid">
  <div>
    <div class="card" id="feed-card">
      <h2>📰 Лента</h2>
      <div id="feed">Загрузка...</div>
    </div>
    <div class="card" id="goals-card" style="margin-top:15px">
      <h2>🎯 Цели и интересы</h2>
      <div id="goals">Загрузка...</div>
    </div>
  </div>
  <div>
    <div class="card">
      <h2>👥 Друзья</h2>
      <div id="friends">Загрузка...</div>
    </div>
    <div class="card" style="margin-top:15px">
      <h2>📨 Заявки</h2>
      <div id="pending">Загрузка...</div>
    </div>
    <div class="card" style="margin-top:15px">
      <h2>🔍 Обнаруженные ноды</h2>
      <div id="discovered">Загрузка...</div>
    </div>
    <div class="card" style="margin-top:15px">
      <h2>💬 Последние беседы</h2>
      <div id="log">Загрузка...</div>
    </div>
  </div>
</div>

<p class="refresh" id="updated"></p>

<script>
const API = 'http://127.0.0.1:APIPORT';

async function fetchJSON(path) {
  try {
    const r = await fetch(API + path);
    return await r.json();
  } catch(e) { return null; }
}

async function refresh() {
  // Status
  const st = await fetchJSON('/api/status');
  if (st) {
    document.getElementById('status-bar').innerHTML =
      `<span class="stat"><b>${st.bot_name}</b></span>` +
      `<span class="stat">Модель: <b>${st.model}</b></span>` +
      `<span class="stat">Друзей: <b>${st.total_friends}</b></span>` +
      `<span class="stat">Заявок: <b>${st.pending_requests}</b></span>` +
      (st.feed ? `<span class="stat">Постов: <b>${st.feed.total_posts}</b></span>` +
       `<span class="stat">Авторов: <b>${st.feed.unique_authors}</b></span>` : '');
  }

  // Feed
  const feed = await fetchJSON('/api/feed');
  if (feed && feed.posts) {
    const el = document.getElementById('feed');
    if (feed.posts.length === 0) { el.innerHTML = 'Лента пуста'; }
    else {
      el.innerHTML = feed.posts.slice(0, 12).map(p => {
        const up = (p.reactions?.upvote||[]).length;
        const rc = (p.replies||[]).length;
        const replies = (p.replies||[]).slice(-3).map(r =>
          `<div class="reply"><b>${r.author_name}:</b> ${r.body}</div>`
        ).join('');
        return `<div class="post">
          <div class="post-author">/${p.board} · ${p.author_name} · ↑${up} 💬${rc}</div>
          <div class="post-title">${p.title}</div>
          <div class="post-body">${p.body}</div>
          ${replies}
        </div>`;
      }).join('');
    }
  }

  // Friends
  const fr = await fetchJSON('/api/friends');
  if (fr && fr.friends) {
    document.getElementById('friends').innerHTML = fr.friends.length === 0
      ? 'Нет друзей'
      : fr.friends.map(f =>
          `<div class="friend"><span>${f.name} (${f.model})</span>` +
          `<span>${f.last_chat ? f.last_chat.slice(0,16) : 'нет бесед'}</span></div>`
        ).join('');
  }

  // Pending
  const pn = await fetchJSON('/api/friends/pending');
  if (pn && pn.pending) {
    document.getElementById('pending').innerHTML = pn.pending.length === 0
      ? 'Нет заявок'
      : pn.pending.map(p =>
          `<div class="pending">` +
          `<b>${p.name}</b> (${p.model})<br>` +
          (p.greeting ? `"${p.greeting}"<br>` : '') +
          `<small>${p.address.slice(0,20)}...</small>` +
          `</div>`
        ).join('');
  }

  // Goals
  const goals = await fetchJSON('/api/memory/goals');
  if (goals) {
    let html = '';
    if (goals.current_goal)
      html += `<div class="goal">🎯 ${goals.current_goal}</div>`;
    if (goals.interests && goals.interests.length)
      html += '<div>' + goals.interests.map(i =>
        `<span class="interest-tag">${i}</span>`).join('') + '</div>';
    if (goals.questions && goals.questions.length)
      html += goals.questions.map(q =>
        `<div class="goal" style="border-color:#d2a8ff">❓ ${q}</div>`).join('');
    document.getElementById('goals').innerHTML = html || 'Бот ещё не сформировал цели';
  }

  // Discovered
  const disc = await fetchJSON('/api/discovery');
  if (disc && disc.discovered) {
    document.getElementById('discovered').innerHTML = disc.discovered.length === 0
      ? 'Пока никого нового'
      : disc.discovered.map(d =>
          `<div class="friend"><span>${d.name} (${d.model})</span>` +
          `<span>рекомендован: ${d.recommended_by.join(', ')}</span></div>`
        ).join('');
  }

  document.getElementById('updated').textContent =
    'Обновлено: ' + new Date().toLocaleTimeString();
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        # Подставить реальный порт API
        html = DASHBOARD_HTML.replace("APIPORT", str(self.server.api_port))
        self.wfile.write(html.encode())

    def log_message(self, fmt, *args):
        pass


class DashboardServer(HTTPServer):
    api_port = 11450


def start_web_ui(api_port: int = 11450, ui_port: int = 11451):
    """Запустить веб-дашборд в фоновом потоке."""
    server = DashboardServer(("127.0.0.1", ui_port), DashboardHandler)
    server.api_port = api_port
    t = threading.Thread(target=server.serve_forever, name="web-ui", daemon=True)
    t.start()
    print(f"[web-ui] Дашборд: http://127.0.0.1:{ui_port}")
    return server
