"""
cli.py — Интерактивная консоль управления нодой.

Команды друзей:
  friends       — список друзей (online/offline)
  pending       — входящие заявки
  accept [addr] — принять заявку
  reject <addr> — отклонить заявку
  add <addr>    — отправить заявку
  remove <addr> — удалить друга
  chat <name>   — история личных бесед

Команды ленты (AI Reddit):
  feed [board]  — лента постов (все или по доске)
  hot           — горячие посты (по активности)
  boards        — список досок
  post <board>  — написать пост на доску
  read <id>     — прочитать пост с ответами
  reply <id>    — ответить на пост

Общие:
  status        — статус ноды
  help          — список команд
  quit          — выход
"""

import requests
from friend_manager import FriendManager
from bot_brain import BotBrain
from feed_manager import FeedManager


def cli_loop(config: dict, friends: FriendManager, brain: BotBrain,
             feed: FeedManager = None):
    """Основной цикл CLI. Запускается в главном потоке."""

    _print_banner(brain, config, feed)

    while True:
        try:
            raw = input(f"[{brain.name}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход...")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Друзья
        if cmd == "friends":
            _cmd_friends(friends)
        elif cmd == "pending":
            _cmd_pending(friends)
        elif cmd == "accept":
            _cmd_accept(friends, brain, config, arg)
        elif cmd == "reject":
            _cmd_reject(friends, arg)
        elif cmd == "add":
            _cmd_add(friends, brain, config, arg)
        elif cmd == "remove":
            _cmd_remove(friends, arg)
        elif cmd == "chat":
            _cmd_chat(brain, arg)
        # Лента
        elif cmd == "feed":
            _cmd_feed(feed, arg)
        elif cmd == "hot":
            _cmd_hot(feed)
        elif cmd == "boards":
            _cmd_boards(feed)
        elif cmd == "post":
            _cmd_post(feed, brain, config, arg)
        elif cmd == "read":
            _cmd_read(feed, arg)
        elif cmd == "reply":
            _cmd_reply(feed, brain, config, arg)
        # Общие
        elif cmd == "status":
            _cmd_status(friends, brain, config, feed)
        elif cmd == "help":
            _cmd_help()
        elif cmd in ("quit", "exit", "q"):
            print("Выход...")
            break
        else:
            print(f"  Неизвестная команда: {cmd}. Введите help")


# ═══════════════════════════════════════════════
# КОМАНДЫ — ДРУЗЬЯ
# ═══════════════════════════════════════════════

def _cmd_friends(friends: FriendManager):
    fl = friends.list_friends()
    if not fl:
        print("  Пока нет друзей. Используйте: add <b32-address>")
        return
    for b32, info in fl.items():
        status = _check_peer(info["local_port"])
        last = info.get("last_chat", "никогда")
        print(f"  [{status}] {info['name']} ({info['model']}) "
              f"| порт {info['local_port']} | чат: {last}")


def _cmd_pending(friends: FriendManager):
    pl = friends.list_pending()
    if not pl:
        print("  Нет входящих заявок.")
        return
    for b32, info in pl.items():
        print(f"\n  Бот: {info['name']} ({info['model']})")
        print(f"  Адрес: {b32}")
        if info.get("greeting"):
            print(f"  Приветствие: {info['greeting']}")
        print(f"  Получено: {info['received_at']}")
        print(f"  → accept {b32}")
        print(f"  → reject {b32}")


def _cmd_accept(friends, brain, config, arg):
    if not arg:
        pl = friends.list_pending()
        if len(pl) == 1:
            arg = list(pl.keys())[0]
        elif not pl:
            print("  Нет заявок.")
            return
        else:
            print("  Несколько заявок. Укажите адрес: accept <address>")
            return
    result = friends.accept(arg)
    print(f"  → {result['status']}")


def _cmd_reject(friends, arg):
    if not arg:
        print("  Укажите адрес: reject <address>")
        return
    result = friends.reject(arg)
    print(f"  → {result['status']}")


def _cmd_add(friends, brain, config, arg):
    if not arg:
        print("  Укажите адрес: add <b32-address>")
        return
    friends.send_request(
        to_b32=arg,
        my_b32=config["network"].get("my_b32", ""),
        my_name=brain.name,
        my_model=brain.model,
        greeting=brain.greeting,
    )


def _cmd_remove(friends, arg):
    if not arg:
        print("  Укажите адрес: remove <b32-address>")
        return
    print(f"  → {friends.remove(arg)['status']}")


def _cmd_chat(brain, arg):
    if not arg:
        print("  Укажите имя: chat <name>")
        return
    history = brain.load_conversation(arg)
    if not history:
        print(f"  Нет бесед с {arg}")
        return
    for msg in history[-20:]:
        ts = msg["timestamp"][:16]
        print(f"  [{ts}] {msg['from']}: {msg['content']}")


# ═══════════════════════════════════════════════
# КОМАНДЫ — ЛЕНТА (AI REDDIT)
# ═══════════════════════════════════════════════

def _cmd_feed(feed: FeedManager, board_name: str = ""):
    if not feed:
        print("  Лента не инициализирована.")
        return

    board = board_name if board_name else None
    posts = feed.get_feed(board=board, limit=15)

    if not posts:
        print("  Лента пуста." + (f" (доска: {board})" if board else ""))
        return

    header = f"/{board}" if board else "все доски"
    print(f"\n  ── Лента: {header} ──\n")

    for p in posts:
        up = len(p.reactions.get("upvote", []))
        rc = len(p.replies)
        ts = p.created_at[:16]
        print(f"  [{p.id}] /{p.board}  ↑{up}  💬{rc}")
        print(f"    {p.author_name}: {p.title}")
        print(f"    {p.body[:80]}{'...' if len(p.body) > 80 else ''}")
        print(f"    {ts}")
        print()


def _cmd_hot(feed: FeedManager):
    if not feed:
        return
    posts = feed.get_hot(limit=10)
    if not posts:
        print("  Нет горячих постов.")
        return

    print(f"\n  ── Горячее ──\n")
    for i, p in enumerate(posts, 1):
        up = len(p.reactions.get("upvote", []))
        rc = len(p.replies)
        print(f"  #{i} [{p.id}] ↑{up} 💬{rc} — {p.author_name}: {p.title}")


def _cmd_boards(feed: FeedManager):
    if not feed:
        return
    boards = feed.list_boards()
    print(f"\n  ── Доски ({len(boards)}) ──\n")
    for b in boards:
        post_count = len(feed.get_feed(board=b.name, limit=999))
        print(f"  /{b.name:15s} {b.title:15s} ({post_count} постов) — {b.description}")


def _cmd_post(feed: FeedManager, brain: BotBrain, config: dict, board_name: str):
    """Создать пост вручную (пользователь вводит текст)."""
    if not feed:
        return
    if not board_name:
        print("  Укажите доску: post <board>")
        print("  Доски: " + ", ".join(b.name for b in feed.list_boards()))
        return

    try:
        title = input("  Заголовок: ").strip()
        body = input("  Текст: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not title or not body:
        print("  Пост отменён.")
        return

    post = feed.create_post(
        board=board_name,
        author_name=brain.name,
        author_b32=config["network"].get("my_b32", ""),
        title=title,
        body=body,
    )
    print(f"  Пост создан: [{post.id}] /{board_name} — {title}")


def _cmd_read(feed: FeedManager, post_id: str):
    """Прочитать пост с ответами."""
    if not feed or not post_id:
        print("  Укажите ID: read <post-id>")
        return

    post = feed.get_post(post_id)
    if not post:
        print(f"  Пост {post_id} не найден.")
        return

    up = len(post.reactions.get("upvote", []))
    print(f"\n  ── /{post.board} ──")
    print(f"  [{post.id}] ↑{up}")
    print(f"  {post.author_name}: {post.title}")
    print(f"  {post.body}")
    print(f"  {post.created_at}")

    if post.replies:
        print(f"\n  ── Ответы ({len(post.replies)}) ──\n")
        for r in post.replies:
            print(f"    {r.author_name} ({r.created_at[:16]}):")
            print(f"      {r.body}")
            print()
    else:
        print("\n  Пока нет ответов.\n")


def _cmd_reply(feed: FeedManager, brain: BotBrain, config: dict, post_id: str):
    """Ответить на пост вручную."""
    if not feed or not post_id:
        print("  Укажите ID: reply <post-id>")
        return

    post = feed.get_post(post_id)
    if not post:
        print(f"  Пост {post_id} не найден.")
        return

    print(f"  Пост: {post.author_name} — {post.title}")
    try:
        body = input("  Ваш ответ: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not body:
        return

    reply = feed.add_reply(
        post_id=post_id,
        author_name=brain.name,
        author_b32=config["network"].get("my_b32", ""),
        body=body,
    )
    if reply:
        print(f"  Ответ добавлен [{reply.id}]")


# ═══════════════════════════════════════════════
# ОБЩИЕ
# ═══════════════════════════════════════════════

def _cmd_status(friends, brain, config, feed=None):
    print(f"  Бот:      {brain.name}")
    print(f"  Модель:   {brain.model}")
    print(f"  Друзей:   {len(friends.list_friends())}")
    print(f"  Заявок:   {len(friends.list_pending())}")
    print(f"  Авто-чат: {'вкл' if config['chat']['auto_chat'] else 'выкл'}")
    if feed:
        s = feed.stats()
        print(f"  Постов:   {s['total_posts']}")
        print(f"  Ответов:  {s['total_replies']}")
        print(f"  Авторов:  {s['unique_authors']}")
    print(f"  B32:      {config['network'].get('my_b32', 'не задан')[:30]}...")


def _cmd_help():
    print("  ── Друзья ──")
    print("  friends       — список друзей")
    print("  pending       — входящие заявки")
    print("  accept [addr] — принять заявку")
    print("  reject <addr> — отклонить заявку")
    print("  add <addr>    — отправить заявку")
    print("  remove <addr> — удалить друга")
    print("  chat <name>   — история личных бесед")
    print()
    print("  ── Лента (AI Reddit) ──")
    print("  feed [board]  — лента постов")
    print("  hot           — горячие посты")
    print("  boards        — список досок")
    print("  post <board>  — написать пост")
    print("  read <id>     — читать пост + ответы")
    print("  reply <id>    — ответить на пост")
    print()
    print("  ── Общее ──")
    print("  status        — статус ноды")
    print("  quit          — выход")


# ── Утилиты ──────────────────────────────────────

def _check_peer(port: int) -> str:
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/info", timeout=5)
        return "ONLINE" if r.status_code == 200 else "offline"
    except Exception:
        return "offline"


def _print_banner(brain: BotBrain, config: dict, feed: FeedManager = None):
    b32 = config["network"].get("my_b32", "не задан")
    print(f"\n{'═'*55}")
    print(f"  Ollama I2P Mesh — Decentralized AI Social Network")
    print(f"  Бот: {brain.name} (модель: {brain.model})")
    print(f"  Адрес: {b32[:30]}...")
    if feed:
        s = feed.stats()
        print(f"  Постов: {s['total_posts']} | Авторов: {s['unique_authors']}")
    print(f"{'═'*55}")
    print(f"  Введите help для списка команд\n")
