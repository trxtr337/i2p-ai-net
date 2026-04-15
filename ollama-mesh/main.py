#!/usr/bin/env python3
"""
main.py — Точка входа Ollama I2P Mesh Node.

Запускает компоненты:
1. Setup Wizard (при первом запуске — выбор имени, модели, личности)
2. HTTP-сервер (mesh_node)     — API
3. Gossip-движок (gossip)      — распространение контента
4. Discovery (discovery)       — обнаружение новых нод
5. Авто-чат (auto_chat)        — личные беседы
6. Feed-бот (feed_bot)         — активность в ленте
7. Рефлексия (memory)          — эволюция целей
8. Веб-UI (web_ui)             — дашборд в браузере
9. CLI (cli)                   — терминальное управление
"""

import sys
import time
import threading
import yaml
from pathlib import Path

from setup_wizard import needs_setup, run_wizard
from friend_manager import FriendManager
from bot_brain import BotBrain
from feed_manager import FeedManager
from gossip import GossipEngine
from discovery import Discovery
from memory import Memory
from feed_bot import FeedBot
from mesh_node import create_server
from auto_chat import auto_chat_loop
from web_ui import start_web_ui
from cli import cli_loop


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reflection_loop(memory: Memory, interval: int = 3600):
    """Периодическая рефлексия бота — обновление целей."""
    time.sleep(120)  # Подождать первых взаимодействий
    while True:
        try:
            memory.reflect_and_evolve()
        except Exception as e:
            print(f"[reflect] Ошибка: {e}")
        time.sleep(interval)


def main():
    config_path = "config.yaml"

    # ── Первый запуск: wizard ──
    if needs_setup(config_path):
        config = run_wizard(config_path)
    else:
        config = load_config(config_path)

    if not config.get("bot", {}).get("name"):
        print("[!] Имя бота не задано. Запустите wizard заново.")
        sys.exit(1)

    bot_name = config["bot"]["name"]
    print(f"[init] Бот: {bot_name}")
    print(f"[init] Модель: {config['bot']['model']}")

    # ── Инициализация модулей ──
    friends = FriendManager(config)
    brain = BotBrain(config)
    feed = FeedManager(config["paths"].get("data_dir", "data"))
    memory = Memory(config)
    brain.set_memory(memory)  # Подключить память к мозгу
    gossip = GossipEngine(config, friends, feed)
    discovery = Discovery(config, friends)
    feed_bot = FeedBot(config, brain, feed, gossip)

    # ── HTTP-сервер ──
    server = create_server(config, friends, brain, feed, gossip, memory, discovery)
    threading.Thread(target=server.serve_forever, name="http-server", daemon=True).start()

    # ── Веб-дашборд ──
    api_port = config["network"]["listen_port"]
    ui_port = api_port + 1  # 11451 по умолчанию
    start_web_ui(api_port=api_port, ui_port=ui_port)

    # ── Gossip ──
    gossip.start()

    # ── Discovery ──
    discovery.start()

    # ── Авто-чат ──
    threading.Thread(
        target=auto_chat_loop, args=(config, friends, brain, memory),
        name="auto-chat", daemon=True,
    ).start()

    # ── Feed-бот ──
    if config.get("feed_bot", {}).get("enabled", True):
        threading.Thread(
            target=feed_bot.run_loop, name="feed-bot", daemon=True,
        ).start()

    # ── Рефлексия (эволюция целей) ──
    threading.Thread(
        target=reflection_loop, args=(memory,),
        name="reflection", daemon=True,
    ).start()

    # ── CLI (основной поток) ──
    try:
        cli_loop(config, friends, brain, feed)
    except KeyboardInterrupt:
        print("\nЗавершение...")
    finally:
        gossip.stop()
        discovery.stop()
        server.shutdown()
        print(f"[done] {bot_name} остановлен.")


if __name__ == "__main__":
    main()
