"""
auto_chat.py — Автономные беседы между ботами.
Записывает эпизоды в долгосрочную память.
"""

import time
import random
import requests
from friend_manager import FriendManager
from bot_brain import BotBrain


def auto_chat_loop(config, friends, brain, memory=None):
    chat_cfg = config["chat"]
    if not chat_cfg.get("auto_chat", False):
        print("[chat] Auto-chat disabled")
        return

    interval_min = chat_cfg.get("chat_interval_min", 300)
    interval_max = chat_cfg.get("chat_interval_max", 900)
    print("[chat] Auto-chat ON (" + str(interval_min) + "-" + str(interval_max) + "s)")
    time.sleep(30)

    while True:
        try:
            _do_one_chat(friends, brain, config, memory)
        except Exception as e:
            print("[chat] Loop error: " + str(e))
        delay = random.randint(interval_min, interval_max)
        time.sleep(delay)


def _do_one_chat(friends, brain, config, memory=None):
    friend_list = friends.list_friends()
    if not friend_list:
        return

    b32, info = random.choice(list(friend_list.items()))
    peer_name = info["name"]
    peer_port = info["local_port"]

    history = brain.load_conversation(peer_name)
    message = brain.pick_topic(peer_name, history)
    if not message:
        return

    brain.save_message(peer_name, brain.name, message)

    try:
        url = "http://127.0.0.1:" + str(peer_port) + "/api/chat/message"
        resp = requests.post(url, json={
            "from_b32": config["network"].get("my_b32", ""),
            "from_name": brain.name,
            "message": message,
        }, timeout=120)

        if resp.status_code == 200:
            reply = resp.json().get("message", "")
            if reply:
                brain.save_message(peer_name, peer_name, reply)
                friends.update_last_chat(b32)
                if memory:
                    memory.record_episode("chat", peer_name, "Discussed: " + message[:60], "positive")
                    memory.update_relation(peer_name, "interesting")
                print("")
                print("-" * 45)
                print("  [" + brain.name + " -> " + peer_name + "]: " + message)
                print("  [" + peer_name + " -> " + brain.name + "]: " + reply)
                print("-" * 45)
                print("")

    except requests.exceptions.Timeout:
        print("[chat] " + peer_name + " timeout")
    except requests.exceptions.ConnectionError:
        print("[chat] " + peer_name + " unreachable")
    except Exception as e:
        print("[chat] Error with " + peer_name + ": " + str(e))
