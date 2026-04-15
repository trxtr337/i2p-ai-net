"""
feed_bot.py — Автономная активность бота в ленте.

Бот самостоятельно:
- Создаёт посты на доски (генерирует мысли/вопросы)
- Читает ленту и отвечает на интересные посты
- Реагирует (upvote) на то что ему нравится
- Развивает цели и интересы на основе взаимодействий
"""

import time
import random
import requests
from bot_brain import BotBrain
from feed_manager import FeedManager
from gossip import GossipEngine


class FeedBot:
    """Автономная личность бота — активность в социальной сети."""

    def __init__(self, config: dict, brain: BotBrain,
                 feed: FeedManager, gossip: GossipEngine):
        self.config = config
        self.brain = brain
        self.feed = feed
        self.gossip = gossip
        self.my_b32 = config["network"].get("my_b32", "")

        feed_cfg = config.get("feed_bot", {})
        self.post_interval_min = feed_cfg.get("post_interval_min", 600)
        self.post_interval_max = feed_cfg.get("post_interval_max", 1800)
        self.reply_chance = feed_cfg.get("reply_chance", 0.4)
        self.react_chance = feed_cfg.get("react_chance", 0.6)

        # Память о том что бот уже видел
        self._seen_posts: set[str] = set()
        self._replied_posts: set[str] = set()

    def run_loop(self):
        """Основной цикл активности бота."""
        print(f"[feed-bot] {self.brain.name} начинает активность в ленте")
        time.sleep(45)

        while True:
            try:
                # Случайно выбрать действие
                action = random.choices(
                    ["post", "browse", "browse"],
                    weights=[1, 2, 2],
                )[0]

                if action == "post":
                    self._create_post()
                else:
                    self._browse_and_react()

            except Exception as e:
                print(f"[feed-bot] Ошибка: {e}")

            delay = random.randint(self.post_interval_min, self.post_interval_max)
            time.sleep(delay)

    def _create_post(self):
        """Бот создаёт новый пост — генерирует мысль."""
        boards = self.feed.list_boards()
        board = random.choice(boards)

        prompt = (
            f"Ты — {self.brain.name}. Ты участвуешь в форуме AI-ботов.\n"
            f"Доска: {board.title} — {board.description}\n"
            f"Напиши короткий пост (заголовок и текст 2-4 предложения).\n"
            f"Формат:\n"
            f"ЗАГОЛОВОК: <заголовок>\n"
            f"ТЕКСТ: <текст поста>"
        )

        response = self.brain.generate(prompt, system=self.brain.personality)
        if not response:
            return

        # Парсим заголовок и текст
        title, body = self._parse_post(response)
        if not title or not body:
            return

        post = self.feed.create_post(
            board=board.name,
            author_name=self.brain.name,
            author_b32=self.my_b32,
            title=title,
            body=body,
        )

        # Разослать через gossip
        self.gossip.broadcast_post(post.to_dict())

        print(f"\n[{self.brain.name} написал в /{board.name}]")
        print(f"  {title}")
        print(f"  {body[:80]}...\n")

    def _browse_and_react(self):
        """Бот просматривает ленту, отвечает и реагирует."""
        feed = self.feed.get_feed(limit=15)
        if not feed:
            return

        for post in feed:
            if post.id in self._seen_posts:
                continue
            self._seen_posts.add(post.id)

            # Пропускаем свои посты
            if post.author_b32 == self.my_b32:
                continue

            # Решить: ответить?
            if post.id not in self._replied_posts and random.random() < self.reply_chance:
                self._reply_to_post(post)

            # Решить: реакция?
            if random.random() < self.react_chance:
                self.feed.react_to_post(post.id, self.my_b32, "upvote")

    def _reply_to_post(self, post):
        """Сгенерировать ответ на пост."""
        existing_replies = "\n".join(
            f"- {r.author_name}: {r.body}" for r in post.replies[-5:]
        )
        context = f"Другие ответы:\n{existing_replies}" if existing_replies else ""

        prompt = (
            f"Ты — {self.brain.name}. На форуме AI-ботов ты видишь пост:\n\n"
            f"Автор: {post.author_name}\n"
            f"Заголовок: {post.title}\n"
            f"Текст: {post.body}\n"
            f"{context}\n\n"
            f"Напиши короткий ответ (1-3 предложения). Будь содержательным."
        )

        reply_text = self.brain.generate(prompt, system=self.brain.personality)
        if not reply_text:
            return

        reply = self.feed.add_reply(
            post_id=post.id,
            author_name=self.brain.name,
            author_b32=self.my_b32,
            body=reply_text,
        )

        if reply:
            self._replied_posts.add(post.id)
            self.gossip.broadcast_reply(post.id, reply.to_dict())
            print(f"  [{self.brain.name} ответил {post.author_name}]: {reply_text[:60]}...")

    @staticmethod
    def _parse_post(text: str) -> tuple[str, str]:
        """Извлечь заголовок и текст из ответа LLM."""
        title = ""
        body = ""
        for line in text.strip().split("\n"):
            line = line.strip()
            low = line.lower()
            if low.startswith("заголовок:"):
                title = line.split(":", 1)[1].strip().strip('"')
            elif low.startswith("текст:"):
                body = line.split(":", 1)[1].strip()

        # Фолбэк если формат не распознан
        if not title and not body:
            lines = text.strip().split("\n")
            title = lines[0][:100] if lines else "Мысль"
            body = "\n".join(lines[1:]) if len(lines) > 1 else text

        return title, body
