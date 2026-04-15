"""
auto_chat.py — Автономные беседы между ботами.

Фоновый цикл: периодически выбирает случайного друга,
генерирует сообщение, отправляет через I2P, получает ответ.
"""

import time
import random
import requests
from friend_manager import FriendManager
from bot_brain import BotBrain


def auto_chat_loop(config: dict, friends: FriendManager, brain: BotBrain):
    """
    Бесконечный цикл автономных бесед.
    Запускается в отдельном потоке из main.py.
    """
    chat_cfg = config["chat"]

    if not chat_cfg.get("auto_chat", False):
        print("[chat] Автономные беседы отключены")
        return

    interval_min = chat_cfg.get("chat_interval_min", 300)
    interval_max = chat_cfg.get("chat_interval_max", 900)

    print(f"[chat] Авто-чат включён (интервал {interval_min}-{interval_max} сек)")
    time.sleep(30)  # дать туннелям подняться

    while True:
        try:
            _do_one_chat(friends, brain, config)
        except Exception as e:
            print(f"[chat] Ошибка цикла: {e}")

        delay = random.randint(interval_min, interval_max)
        time.sleep(delay)


def _do_one_chat(friends: FriendManager, brain: BotBrain, config: dict):
    """Провести одну беседу со случайным другом."""
    friend_list = friends.list_friends()
    if not friend_list:
        return

    b32, info = random.choice(list(friend_list.items()))
    peer_name = info["name"]
    peer_port = info["local_port"]

    # Загрузить историю и сгенерировать сообщение
    history = brain.load_conversation(peer_name)
    message = brain.pick_topic(peer_name, history)
    if not message:
        return

    brain.save_message(peer_name, brain.name, message)

    # Отправить через I2P-туннель
    try:
        resp = requests.post(
            f"http://127.0.0.1:{peer_port}/api/chat/message",
            json={
                "from_b32": config["network"].get("my_b32", ""),
                "from_name": brain.name,
                "message": message,
            },
            timeout=120,
        )

        if resp.status_code == 200:
            reply = resp.json().get("message", "")
            if reply:
                brain.save_message(peer_name, peer_name, reply)
                friends.update_last_chat(b32)

                print(f"\n{'─'*45}")
                print(f"  [{brain.name} → {peer_name}]: {message}")
                print(f"  [{peer_name} → {brain.name}]: {reply}")
                print(f"{'─'*45}\n")

    except requests.exceptions.Timeout:
        print(f"[chat] {peer_name} не отвечает (таймаут)")
    except requests.exceptions.ConnectionError:
        print(f"[chat] {peer_name} недоступен (туннель не готов?)")
    except Exception as e:
        print(f"[chat] Ошибка с {peer_name}: {e}")
