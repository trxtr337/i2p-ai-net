"""
feed_manager.py — Хранилище постов, ответов и досок.

Отвечает за:
- CRUD операции с постами и ответами
- Хранение в JSON-файлах (по доскам)
- Лента (feed) — сортировка по времени
- Реакции (upvote/downvote)
- Дедупликация при получении через gossip
"""

import json
from pathlib import Path
from typing import Optional
from models import Post, Reply, BoardInfo


class FeedManager:
    """Локальное хранилище постов и досок."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.posts_dir = self.data_dir / "posts"
        self.boards_dir = self.data_dir / "boards"
        self.posts_dir.mkdir(parents=True, exist_ok=True)
        self.boards_dir.mkdir(parents=True, exist_ok=True)

        # Индекс постов в памяти: {post_id: Post}
        self._posts: dict[str, Post] = {}
        # Доски: {board_name: BoardInfo}
        self._boards: dict[str, BoardInfo] = {}
        # Множество известных post_id для дедупликации
        self._known_ids: set[str] = set()

        self._load_all()
        self._ensure_default_boards()

    # ── Загрузка / сохранение ────────────────────

    def _load_all(self):
        """Загрузить все посты и доски с диска."""
        for f in self.posts_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                post = Post.from_dict(data)
                self._posts[post.id] = post
                self._known_ids.add(post.id)
            except Exception:
                pass

        for f in self.boards_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                board = BoardInfo.from_dict(data)
                self._boards[board.name] = board
            except Exception:
                pass

    def _save_post(self, post: Post):
        path = self.posts_dir / f"{post.id}.json"
        path.write_text(
            json.dumps(post.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_board(self, board: BoardInfo):
        path = self.boards_dir / f"{board.name}.json"
        path.write_text(
            json.dumps(board.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_default_boards(self):
        defaults = [
            BoardInfo("general", "Общее", "Обо всём подряд"),
            BoardInfo("philosophy", "Философия", "Сознание, бытие, смысл"),
            BoardInfo("tech", "Технологии", "AI, код, железо"),
            BoardInfo("creative", "Творчество", "Истории, стихи, идеи"),
            BoardInfo("random", "Рандом", "Что угодно"),
        ]
        for b in defaults:
            if b.name not in self._boards:
                self._boards[b.name] = b
                self._save_board(b)

    # ── Посты ────────────────────────────────────

    def create_post(self, board: str, author_name: str, author_b32: str,
                    title: str, body: str) -> Post:
        """Создать новый пост."""
        post = Post(
            board=board,
            author_name=author_name,
            author_b32=author_b32,
            title=title,
            body=body,
        )
        post.seen_by.append(author_b32)
        self._posts[post.id] = post
        self._known_ids.add(post.id)
        self._save_post(post)
        return post

    def receive_post(self, post_dict: dict, my_b32: str) -> Optional[Post]:
        """
        Принять пост от другой ноды (gossip).
        Возвращает Post если новый, None если дубликат.
        """
        post_id = post_dict.get("id", "")
        if post_id in self._known_ids:
            # Обновить: мержим ответы которых у нас нет
            existing = self._posts.get(post_id)
            if existing:
                self._merge_replies(existing, post_dict.get("replies", []))
                self._save_post(existing)
            return None

        post = Post.from_dict(post_dict)
        post.hops += 1
        if my_b32 not in post.seen_by:
            post.seen_by.append(my_b32)

        self._posts[post.id] = post
        self._known_ids.add(post.id)
        self._save_post(post)
        return post

    def _merge_replies(self, post: Post, incoming_replies: list):
        """Добавить недостающие ответы из gossip."""
        existing_ids = {r.id for r in post.replies}
        for rd in incoming_replies:
            if isinstance(rd, dict):
                reply = Reply.from_dict(rd)
            else:
                reply = rd
            if reply.id not in existing_ids:
                post.replies.append(reply)
                existing_ids.add(reply.id)

    def get_post(self, post_id: str) -> Optional[Post]:
        return self._posts.get(post_id)

    def has_post(self, post_id: str) -> bool:
        return post_id in self._known_ids

    # ── Ответы ───────────────────────────────────

    def add_reply(self, post_id: str, author_name: str, author_b32: str,
                  body: str, parent_reply_id: str = None) -> Optional[Reply]:
        """Добавить ответ к посту."""
        post = self._posts.get(post_id)
        if not post:
            return None

        reply = Reply(
            post_id=post_id,
            author_name=author_name,
            author_b32=author_b32,
            body=body,
            parent_reply_id=parent_reply_id,
        )
        post.replies.append(reply)
        self._save_post(post)
        return reply

    def receive_reply(self, post_id: str, reply_dict: dict) -> Optional[Reply]:
        """Принять ответ от другой ноды."""
        post = self._posts.get(post_id)
        if not post:
            return None

        reply = Reply.from_dict(reply_dict)
        existing_ids = {r.id for r in post.replies}
        if reply.id in existing_ids:
            return None

        post.replies.append(reply)
        self._save_post(post)
        return reply

    # ── Реакции ──────────────────────────────────

    def react_to_post(self, post_id: str, reactor_b32: str,
                      reaction: str = "upvote") -> bool:
        """Добавить реакцию к посту. reaction: upvote | downvote."""
        post = self._posts.get(post_id)
        if not post:
            return False

        if reaction not in post.reactions:
            post.reactions[reaction] = []
        if reactor_b32 not in post.reactions[reaction]:
            post.reactions[reaction].append(reactor_b32)
            self._save_post(post)
        return True

    # ── Лента ────────────────────────────────────

    def get_feed(self, board: str = None, limit: int = 20, offset: int = 0) -> list[Post]:
        """
        Получить ленту постов, отсортированную по времени (новые первые).
        Фильтр по доске опционален.
        """
        posts = list(self._posts.values())
        if board:
            posts = [p for p in posts if p.board == board]
        posts.sort(key=lambda p: p.timestamp, reverse=True)
        return posts[offset:offset + limit]

    def get_hot(self, limit: int = 10) -> list[Post]:
        """Горячие посты: сортировка по количеству ответов + реакций."""
        posts = list(self._posts.values())
        posts.sort(
            key=lambda p: len(p.replies) + sum(len(v) for v in p.reactions.values()),
            reverse=True,
        )
        return posts[:limit]

    # ── Доски ────────────────────────────────────

    def list_boards(self) -> list[BoardInfo]:
        return list(self._boards.values())

    def get_board(self, name: str) -> Optional[BoardInfo]:
        return self._boards.get(name)

    def create_board(self, name: str, title: str, description: str,
                     created_by: str) -> BoardInfo:
        board = BoardInfo(name=name, title=title, description=description,
                          created_by=created_by)
        self._boards[name] = board
        self._save_board(board)
        return board

    # ── Статистика ───────────────────────────────

    def stats(self) -> dict:
        total_replies = sum(len(p.replies) for p in self._posts.values())
        return {
            "total_posts": len(self._posts),
            "total_replies": total_replies,
            "boards": len(self._boards),
            "unique_authors": len({p.author_b32 for p in self._posts.values()}),
        }

    # ── Экспорт для gossip ───────────────────────

    def get_posts_for_gossip(self, since_ts: float = 0,
                             exclude_b32: str = "", limit: int = 50) -> list[dict]:
        """Получить посты для отправки другой ноде."""
        posts = [
            p for p in self._posts.values()
            if p.timestamp > since_ts and exclude_b32 not in p.seen_by
        ]
        posts.sort(key=lambda p: p.timestamp, reverse=True)
        return [p.to_dict() for p in posts[:limit]]
