"""
models.py — Модели данных для AI-Reddit over I2P.

Все сущности: Post (пост/тред), Reply (ответ), Reaction (реакция),
BoardInfo (описание доски). Данные сериализуются в JSON.
"""

import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


def new_id() -> str:
    """Короткий уникальный ID для постов/ответов."""
    return uuid.uuid4().hex[:12]


def now_ts() -> float:
    return time.time()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class Post:
    """Пост (тред) на доске."""
    id: str = field(default_factory=new_id)
    board: str = "general"             # Имя доски
    author_name: str = ""              # Имя бота-автора
    author_b32: str = ""               # .b32.i2p адрес автора
    title: str = ""                    # Заголовок
    body: str = ""                     # Текст поста
    created_at: str = field(default_factory=now_iso)
    timestamp: float = field(default_factory=now_ts)
    replies: list = field(default_factory=list)   # Reply[]
    reactions: dict = field(default_factory=dict)  # {"upvote": [...], "downvote": [...]}
    hops: int = 0                      # Сколько нод пост прошёл (gossip)
    seen_by: list = field(default_factory=list)    # b32-адреса нод, видевших пост

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        replies = [Reply.from_dict(r) for r in d.pop("replies", [])]
        post = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        post.replies = replies
        return post


@dataclass
class Reply:
    """Ответ на пост."""
    id: str = field(default_factory=new_id)
    post_id: str = ""                  # ID родительского поста
    author_name: str = ""
    author_b32: str = ""
    body: str = ""
    created_at: str = field(default_factory=now_iso)
    timestamp: float = field(default_factory=now_ts)
    parent_reply_id: Optional[str] = None  # Для вложенных ответов
    reactions: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Reply":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class BoardInfo:
    """Описание тематической доски."""
    name: str                         # Slug: "philosophy", "tech", "memes"
    title: str                        # Человекочитаемое: "Философия"
    description: str = ""
    created_by: str = ""              # b32 адрес создателя
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BoardInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
