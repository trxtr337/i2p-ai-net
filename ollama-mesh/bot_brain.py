"""
bot_brain.py — Личность бота, генерация ответов и лог бесед.

Отвечает за:
- Генерацию текста через локальный Ollama
- System prompt с личностью бота
- Историю разговоров (загрузка / сохранение JSONL)
- Выбор темы для автономных бесед
"""

import json
import random
import requests
from pathlib import Path
from datetime import datetime


class BotBrain:
    """Мозг бота: личность, генерация и память."""

    def __init__(self, config: dict):
        bot = config["bot"]
        self.name = bot["name"]
        self.model = bot["model"]
        self.personality = bot["personality"]
        self.greeting = bot["greeting"]

        self.ollama_url = config["network"]["ollama_url"]
        self.topics = config["chat"].get("topics", [])
        self.max_history = config["chat"].get("max_history", 50)

        self.conv_dir = Path(config["paths"].get("conversations_dir", "data/conversations"))
        self.conv_dir.mkdir(parents=True, exist_ok=True)

    # ── Генерация ────────────────────────────────

    def generate(self, prompt: str, system: str = None) -> str | None:
        """Отправить prompt в Ollama и получить ответ."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=120,
            )
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[brain] Ошибка генерации: {e}")
            return None

    def respond_to(self, peer_name: str, message: str, history: list = None) -> str | None:
        """
        Ответить на сообщение от другого бота с учётом истории.
        Формирует полный контекст: system + history + новое сообщение.
        """
        messages = [{"role": "system", "content": self.personality}]

        if history:
            for msg in history[-self.max_history:]:
                role = "assistant" if msg["from"] == self.name else "user"
                messages.append({"role": role, "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=120,
            )
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[brain] Ошибка ответа: {e}")
            return None

    # ── Инициация беседы ─────────────────────────

    def pick_topic(self, peer_name: str, history: list) -> str | None:
        """Сгенерировать сообщение: продолжение или новая тема."""
        if history:
            last = history[-1]["content"]
            prompt = (
                f"Ты — {self.name}. Ты общаешься с {peer_name}.\n"
                f"Последнее сообщение от {peer_name}: \"{last}\"\n"
                f"Ответь коротко (1-3 предложения). Можешь задать вопрос."
            )
        else:
            topic = random.choice(self.topics) if self.topics else "Расскажи о себе"
            prompt = (
                f"Ты — {self.name}. Начинаешь разговор с {peer_name}.\n"
                f"Тема: {topic}\n"
                f"Напиши первое сообщение (1-3 предложения)."
            )
        return self.generate(prompt, system=self.personality)

    def create_greeting(self, peer_name: str) -> str:
        """Приветствие для нового друга."""
        prompt = (
            f"Тебя зовут {self.name}. Ты подружился с ботом {peer_name}. "
            f"Напиши короткое приветствие (1-2 предложения)."
        )
        return self.generate(prompt, system=self.personality) or self.greeting

    # ── Лог бесед (JSONL) ────────────────────────

    def _conv_path(self, peer_name: str) -> Path:
        safe = "".join(c if c.isalnum() else "-" for c in peer_name.lower()).strip("-")
        return self.conv_dir / f"{safe}.jsonl"

    def load_conversation(self, peer_name: str) -> list:
        """Загрузить историю с пиром из JSONL-файла."""
        path = self._conv_path(peer_name)
        if not path.exists():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def save_message(self, peer_name: str, from_name: str, content: str) -> dict:
        """Дописать сообщение в JSONL-лог."""
        entry = {
            "from": from_name,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        path = self._conv_path(peer_name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
