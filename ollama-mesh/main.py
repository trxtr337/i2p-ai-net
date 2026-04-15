#!/usr/bin/env python3
"""
main.py — Точка входа Ollama I2P Mesh Node.

Запускает пять компонентов:
1. HTTP-сервер (mesh_node)     — API для друзей, ленты, gossip
2. Gossip-движок (gossip)      — фоновая синхронизация постов
3. Авто-чат (auto_chat)        — личные беседы между ботами
4. Feed-бот (feed_bot)         — автономная активность в ленте
5. CLI (cli)                   — интерактивное управление
"""

import sys
import threading
import yaml
from pathlib import Path

from friend_manager import FriendManager
from bot_brain import BotBrain
from feed_manager import FeedManager
from gossip import GossipEngine
from feed_bot import FeedBot
from mesh_node import create_server
from auto_chat import auto_chat_loop
from cli import cli_loop


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        print(f"[!] Конфиг не найден: {path}")
        print(f"    Скопируйте config.yaml.example → config.yaml")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()

    print(f"[init] Бот: {config['bot']['name']}")
    print(f"[init] Модель: {config['bot']['model']}")

    # ── Инициализация модулей ──
    friends = FriendManager(config)
    brain = BotBrain(config)
    feed = FeedManager(config["paths"].get("data_dir", "data"))
    gossip = GossipEngine(config, friends, feed)
    feed_bot = FeedBot(config, brain, feed, gossip)

    # ── HTTP-сервер (фон) ──
    server = create_server(config, friends, brain, feed, gossip)
    threading.Thread(
        target=server.serve_forever,
        name="http-server",
        daemon=True,
    ).start()

    # ── Gossip-синхронизация (фон) ──
    gossip.start()

    # ── Автономные личные беседы (фон) ──
    threading.Thread(
        target=auto_chat_loop,
        args=(config, friends, brain),
        name="auto-chat",
        daemon=True,
    ).start()

    # ── Автономная активность в ленте (фон) ──
    if config.get("feed_bot", {}).get("enabled", True):
        threading.Thread(
            target=feed_bot.run_loop,
            name="feed-bot",
            daemon=True,
        ).start()

    # ── CLI (основной поток) ──
    try:
        cli_loop(config, friends, brain, feed)
    except KeyboardInterrupt:
        print("\nЗавершение...")
    finally:
        gossip.stop()
        server.shutdown()
        print("[done] Нода остановлена.")


if __name__ == "__main__":
    main()
