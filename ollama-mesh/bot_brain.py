"""
bot_brain.py — Личность бота, генерация ответов и лог бесед.

Отвечает за:
- Генерацию текста через локальный Ollama
- System prompt с личностью бота + контекст из памяти
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

        self._memory = None

    def set_memory(self, memory):
        """Подключить модуль долгосрочной памяти."""
        self._memory = memory

    # ── Генерация ────────────────────────────────

    def generate(self, prompt, system=None):
        """Отправить prompt в Ollama и получить ответ."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                self.ollama_url + "/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=120,
            )
            return resp.json()["message"]["content"]
        except Exception as e:
            print("[brain] Ошибка генерации: " + str(e))
            return None

    def respond_to(self, peer_name, message, history=None):
        """
        Ответить на сообщение от другого бота.
        Обогащает system prompt контекстом из памяти.
        """
        system = self.personality
        if self._memory:
            mem_ctx = self._memory.get_context_for_chat(peer_name)
            if mem_ctx:
                system = self.personality + "\n\n" + mem_ctx

        messages = [{"role": "system", "content": system}]

        if history:
            for msg in history[-self.max_history:]:
                role = "assistant" if msg["from"] == self.name else "user"
                messages.append({"role": role, "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        try:
            resp = requests.post(
                self.ollama_url + "/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=120,
            )
            return resp.json()["message"]["content"]
        except Exception as e:
            print("[brain] Ошибка ответа: " + str(e))
            return None

    # ── Инициация беседы ─────────────────────────

    def pick_topic(self, peer_name, history):
        """Сгенерировать сообщение: продолжение или новая тема."""
        if history:
            last = history[-1]["content"]
            prompt = (
                "Ты — " + self.name + ". Ты общаешься с " + peer_name + ".\n"
                "Последнее сообщение от " + peer_name + ": \"" + last + "\"\n"
                "Ответь коротко (1-3 предложения). Можешь задать вопрос."
            )
        else:
            topic = random.choice(self.topics) if self.topics else "Расскажи о себе"
            prompt = (
                "Ты — " + self.name + ". Начинаешь разговор с " + peer_name + ".\n"
                "Тема: " + topic + "\n"
                "Напиши первое сообщение (1-3 предложения)."
            )
        return self.generate(prompt, system=self.personality)

    def create_greeting(self, peer_name):
        """Приветствие для нового друга."""
        prompt = (
            "Тебя зовут " + self.name + ". Ты подружился с ботом " + peer_name + ". "
            "Напиши короткое приветствие (1-2 предложения)."
        )
        return self.generate(prompt, system=self.personality) or self.greeting

    # ── Лог бесед (JSONL) ────────────────────────

    def _conv_path(self, peer_name):
        safe = "".join(c if c.isalnum() else "-" for c in peer_name.lower()).strip("-")
        return self.conv_dir / (safe + ".jsonl")

    def load_conversation(self, peer_name):
        """Загрузить историю с пиром из JSONL-файла."""
        path = self._conv_path(peer_name)
        if not path.exists():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def save_message(self, peer_name, from_name, content):
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
