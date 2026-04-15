#!/usr/bin/env python3
"""
main.py — Entry point for Ollama I2P Mesh Node.
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


def load_config(path="config.yaml"):
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reflection_loop(memory, interval=3600):
    time.sleep(120)
    while True:
        try:
            memory.reflect_and_evolve()
        except Exception as e:
            print("[reflect] Error: " + str(e))
        time.sleep(interval)


def main():
    cfg_path = "config.yaml"

    if needs_setup(cfg_path):
        config = run_wizard(cfg_path)
    else:
        config = load_config(cfg_path)

    if not config.get("bot", {}).get("name"):
        print("[!] Bot name not set. Delete config.yaml and restart.")
        sys.exit(1)

    bot_name = config["bot"]["name"]
    print("[init] Bot: " + bot_name)
    print("[init] Model: " + config["bot"]["model"])

    friends = FriendManager(config)
    brain = BotBrain(config)
    feed = FeedManager(config["paths"].get("data_dir", "data"))
    memory = Memory(config)
    brain.set_memory(memory)
    gossip = GossipEngine(config, friends, feed)
    discovery = Discovery(config, friends)
    feed_bot = FeedBot(config, brain, feed, gossip)

    server = create_server(config, friends, brain, feed, gossip, memory, discovery)
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()

    api_port = config["network"]["listen_port"]
    start_web_ui(api_port=api_port, ui_port=api_port + 1)

    gossip.start()
    discovery.start()

    threading.Thread(
        target=auto_chat_loop, args=(config, friends, brain, memory),
        name="chat", daemon=True).start()

    if config.get("feed_bot", {}).get("enabled", True):
        threading.Thread(target=feed_bot.run_loop, name="feed", daemon=True).start()

    threading.Thread(
        target=reflection_loop, args=(memory,),
        name="reflect", daemon=True).start()

    try:
        cli_loop(config, friends, brain, feed)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        gossip.stop()
        discovery.stop()
        server.shutdown()
        print("[done] " + bot_name + " stopped.")


if __name__ == "__main__":
    main()
