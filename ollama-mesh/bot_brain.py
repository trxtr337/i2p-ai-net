"""
bot_brain.py — Личность бота, генерация ответов и лог бесед.
"""

import json
import random
import requests
from pathlib import Path
from datetime import datetime


class BotBrain:

    def __init__(self, config):
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
        self._memory = memory

    def generate(self, prompt, system=None):
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
            print("[brain] Error: " + str(e))
            return None

    def respond_to(self, peer_name, message, history=None):
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
            print("[brain] Error: " + str(e))
            return None

    def pick_topic(self, peer_name, history):
        if history:
            last = history[-1]["content"]
            prompt = ("You are " + self.name + ". Talking to " + peer_name + ".\n"
                      "Last message from " + peer_name + ": \"" + last + "\"\n"
                      "Reply briefly (1-3 sentences). You can ask a question.")
        else:
            topic = random.choice(self.topics) if self.topics else "Tell me about yourself"
            prompt = ("You are " + self.name + ". Starting a conversation with " + peer_name + ".\n"
                      "Topic: " + topic + "\nWrite the first message (1-3 sentences).")
        return self.generate(prompt, system=self.personality)

    def create_greeting(self, peer_name):
        prompt = ("Your name is " + self.name + ". You just befriended " + peer_name + ". "
                  "Write a short greeting (1-2 sentences).")
        return self.generate(prompt, system=self.personality) or self.greeting

    def _conv_path(self, peer_name):
        safe = "".join(c if c.isalnum() else "-" for c in peer_name.lower()).strip("-")
        return self.conv_dir / (safe + ".jsonl")

    def load_conversation(self, peer_name):
        path = self._conv_path(peer_name)
        if not path.exists():
            return []
        entries = []
        text = path.read_text(encoding="utf-8").strip()
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                entries.append(json.loads(stripped))
        return entries

    def save_message(self, peer_name, from_name, content):
        entry = {
            "from": from_name,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        path = self._conv_path(peer_name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
