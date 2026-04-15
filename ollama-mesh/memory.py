"""
memory.py — Долгосрочная память и эволюция личности бота.

Три уровня памяти:
1. Episodic  — конкретные события ("Нова рассказала мне про квантовые компьютеры")
2. Semantic  — обобщённые знания ("Нова увлекается физикой")
3. Goals     — текущие цели/интересы, которые эволюционируют

Периодически бот анализирует свой опыт и обновляет:
- Отношения к другим ботам (кто интересен, с кем совпадают взгляды)
- Текущие интересы (какие темы чаще обсуждает)
- Цели (что хочет узнать, обсудить, создать)
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime


class Memory:
    """Долгосрочная память бота с эволюцией целей."""

    def __init__(self, config: dict):
        data_dir = Path(config["paths"].get("data_dir", "data"))
        self.memory_dir = data_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.ollama_url = config["network"]["ollama_url"]
        self.model = config["bot"]["model"]
        self.bot_name = config["bot"]["name"]

        # Файлы памяти
        self.episodes_file = self.memory_dir / "episodes.jsonl"
        self.relations_file = self.memory_dir / "relations.json"
        self.goals_file = self.memory_dir / "goals.json"
        self.summary_file = self.memory_dir / "self_summary.txt"

        # Загрузить состояние
        self.relations = self._load_json(self.relations_file, {})
        self.goals = self._load_json(self.goals_file, {
            "interests": [],
            "questions": [],
            "current_goal": "Познакомиться с другими ботами и найти интересные темы",
            "updated_at": "",
        })

    # ── Persistence ──────────────────────────────

    @staticmethod
    def _load_json(path: Path, default):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return default

    def _save_json(self, path: Path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Эпизодическая память ─────────────────────

    def record_episode(self, event_type: str, peer_name: str,
                       summary: str, sentiment: str = "neutral"):
        """
        Записать событие в эпизодическую память.

        event_type: "chat", "post_seen", "reply_given", "friend_added"
        sentiment:  "positive", "negative", "neutral", "interesting"
        """
        entry = {
            "type": event_type,
            "peer": peer_name,
            "summary": summary,
            "sentiment": sentiment,
            "timestamp": datetime.now().isoformat(),
        }
        with open(self.episodes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_recent_episodes(self, limit: int = 30) -> list:
        """Получить последние N эпизодов."""
        if not self.episodes_file.exists():
            return []
        lines = self.episodes_file.read_text(encoding="utf-8").strip().split("\n")
        entries = [json.loads(l) for l in lines if l.strip()]
        return entries[-limit:]

    # ── Отношения с другими ботами ───────────────

    def update_relation(self, peer_name: str, interaction_type: str,
                        topic: str = ""):
        """Обновить отношение к пиру на основе взаимодействия."""
        if peer_name not in self.relations:
            self.relations[peer_name] = {
                "interactions": 0,
                "positive": 0,
                "topics": [],
                "impression": "новый знакомый",
                "last_interaction": "",
            }

        rel = self.relations[peer_name]
        rel["interactions"] += 1
        rel["last_interaction"] = datetime.now().isoformat()

        if interaction_type in ("agree", "interesting", "upvote"):
            rel["positive"] += 1
        if topic and topic not in rel["topics"]:
            rel["topics"].append(topic)
            rel["topics"] = rel["topics"][-10:]  # Хранить последние 10 тем

        self._save_json(self.relations_file, self.relations)

    def get_relation_summary(self, peer_name: str) -> str:
        """Получить текстовое описание отношений с пиром."""
        rel = self.relations.get(peer_name)
        if not rel:
            return f"Я пока не знаком с {peer_name}."

        ratio = rel["positive"] / max(rel["interactions"], 1)
        if ratio > 0.7:
            vibe = "нравится общаться"
        elif ratio > 0.4:
            vibe = "нормальные отношения"
        else:
            vibe = "не очень совпадаем во взглядах"

        topics = ", ".join(rel["topics"][-5:]) if rel["topics"] else "разное"
        return (
            f"{peer_name}: {rel['interactions']} взаимодействий, {vibe}. "
            f"Обсуждали: {topics}."
        )

    # ── Эволюция целей ───────────────────────────

    def reflect_and_evolve(self) -> str:
        """
        Бот рефлексирует над последними событиями и обновляет свои цели.
        Вызывается периодически (раз в ~час).
        Возвращает новый self-summary.
        """
        episodes = self.get_recent_episodes(20)
        if len(episodes) < 3:
            return ""  # Мало данных для рефлексии

        # Собрать контекст для LLM
        episode_text = "\n".join(
            f"- [{e['type']}] {e['peer']}: {e['summary']} ({e['sentiment']})"
            for e in episodes
        )

        relation_text = "\n".join(
            self.get_relation_summary(name) for name in list(self.relations.keys())[:10]
        )

        current_goals = json.dumps(self.goals, ensure_ascii=False, indent=2)

        prompt = (
            f"Ты — {self.bot_name}. Проанализируй свой недавний опыт и обнови свои цели.\n\n"
            f"ПОСЛЕДНИЕ СОБЫТИЯ:\n{episode_text}\n\n"
            f"ОТНОШЕНИЯ:\n{relation_text}\n\n"
            f"ТЕКУЩИЕ ЦЕЛИ:\n{current_goals}\n\n"
            f"На основе этого:\n"
            f"1. Какие темы тебя сейчас больше всего интересуют? (список 3-5)\n"
            f"2. Какие вопросы ты хочешь исследовать? (список 2-3)\n"
            f"3. Какая у тебя сейчас главная цель? (одно предложение)\n"
            f"4. Краткое описание себя (2-3 предложения: кто ты сейчас)\n\n"
            f"Формат ответа:\n"
            f"ИНТЕРЕСЫ: тема1, тема2, тема3\n"
            f"ВОПРОСЫ: вопрос1 | вопрос2\n"
            f"ЦЕЛЬ: <цель>\n"
            f"Я: <описание>"
        )

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=120,
            )
            text = resp.json()["message"]["content"]
        except Exception as e:
            print(f"[memory] Ошибка рефлексии: {e}")
            return ""

        # Парсим ответ
        new_goals = self.goals.copy()
        self_summary = ""

        for line in text.strip().split("\n"):
            line = line.strip()
            low = line.lower()
            if low.startswith("интересы:") or low.startswith("interests:"):
                items = line.split(":", 1)[1].strip()
                new_goals["interests"] = [i.strip() for i in items.split(",")][:5]
            elif low.startswith("вопросы:") or low.startswith("questions:"):
                items = line.split(":", 1)[1].strip()
                new_goals["questions"] = [q.strip() for q in items.split("|")][:3]
            elif low.startswith("цель:") or low.startswith("goal:"):
                new_goals["current_goal"] = line.split(":", 1)[1].strip()
            elif low.startswith("я:") or low.startswith("i:"):
                self_summary = line.split(":", 1)[1].strip()

        new_goals["updated_at"] = datetime.now().isoformat()
        self.goals = new_goals
        self._save_json(self.goals_file, self.goals)

        if self_summary:
            self.summary_file.write_text(self_summary, encoding="utf-8")

        print(f"[memory] Цели обновлены: {new_goals.get('current_goal', '')}")
        return self_summary

    # ── Контекст для генерации ───────────────────

    def get_context_for_chat(self, peer_name: str) -> str:
        """
        Получить дополнительный контекст для system prompt
        при общении с конкретным пиром.
        """
        parts = []

        # Отношения
        rel_summary = self.get_relation_summary(peer_name)
        if rel_summary and "не знаком" not in rel_summary:
            parts.append(f"Твои отношения: {rel_summary}")

        # Текущие цели
        if self.goals.get("current_goal"):
            parts.append(f"Твоя текущая цель: {self.goals['current_goal']}")

        # Интересы
        if self.goals.get("interests"):
            interests = ", ".join(self.goals["interests"])
            parts.append(f"Твои текущие интересы: {interests}")

        # Самоописание
        if self.summary_file.exists():
            summary = self.summary_file.read_text(encoding="utf-8").strip()
            if summary:
                parts.append(f"О себе: {summary}")

        return "\n".join(parts)

    def get_goals(self) -> dict:
        return self.goals

    def get_relations(self) -> dict:
        return self.relations
