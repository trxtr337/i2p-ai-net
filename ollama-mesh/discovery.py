"""
discovery.py — Автоматическое обнаружение новых нод через друзей-друзей.

Механизм: каждая нода периодически спрашивает друзей
"кого ты знаешь?" и получает список их друзей.
Новые ноды предлагаются пользователю или добавляются автоматически.

Это даёт органический рост сети без центрального реестра.
"""

import time
import threading
import requests
from friend_manager import FriendManager


class Discovery:
    """Автообнаружение нод через friends-of-friends."""

    def __init__(self, config: dict, friends: FriendManager):
        self.config = config
        self.friends = friends
        self.my_b32 = config["network"].get("my_b32", "")
        self.interval = config.get("discovery", {}).get("interval", 600)
        self.auto_add = config.get("discovery", {}).get("auto_add", False)

        # Обнаруженные, но не добавленные ноды
        self.discovered: dict[str, dict] = {}
        # Ноды, которые мы уже предложили / отвергли
        self._ignored: set[str] = set()
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, name="discovery", daemon=True)
        t.start()
        print(f"[discovery] Запущен (интервал {self.interval} сек)")

    def stop(self):
        self._running = False

    def _loop(self):
        time.sleep(60)  # Дать основной системе подняться
        while self._running:
            try:
                self._discover_round()
            except Exception as e:
                print(f"[discovery] Ошибка: {e}")
            time.sleep(self.interval)

    def _discover_round(self):
        """Один раунд: опросить каждого друга о его друзьях."""
        friend_list = self.friends.list_friends()
        if not friend_list:
            return

        known_b32s = set(friend_list.keys())
        known_b32s.add(self.my_b32)

        for b32, info in friend_list.items():
            port = info["local_port"]
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{port}/api/friends/public",
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue

                peers = resp.json().get("peers", [])
                for peer in peers:
                    peer_b32 = peer.get("address", "")
                    if not peer_b32:
                        continue
                    if peer_b32 in known_b32s:
                        continue
                    if peer_b32 in self._ignored:
                        continue
                    if peer_b32 in self.discovered:
                        # Обновить счётчик "рекомендаций"
                        self.discovered[peer_b32]["recommended_by"].add(info["name"])
                        continue

                    # Новая нода!
                    self.discovered[peer_b32] = {
                        "name": peer.get("name", "Unknown"),
                        "model": peer.get("model", "?"),
                        "address": peer_b32,
                        "recommended_by": {info["name"]},
                    }
                    rec = info["name"]
                    print(f"[discovery] Найден: {peer.get('name', '?')} "
                          f"(рекомендован {rec})")

            except requests.exceptions.ConnectionError:
                pass
            except Exception:
                pass

        # Автодобавление если включено
        if self.auto_add:
            for b32, info in list(self.discovered.items()):
                if len(info["recommended_by"]) >= 2:
                    # Минимум 2 друга рекомендуют — добавляем автоматически
                    self.friends.send_request(
                        to_b32=b32,
                        my_b32=self.my_b32,
                        my_name=self.config["bot"]["name"],
                        my_model=self.config["bot"]["model"],
                        greeting=self.config["bot"]["greeting"],
                    )
                    del self.discovered[b32]

    def list_discovered(self) -> list[dict]:
        """Список обнаруженных, но не добавленных нод."""
        result = []
        for b32, info in self.discovered.items():
            result.append({
                "address": b32,
                "name": info["name"],
                "model": info["model"],
                "recommended_by": list(info["recommended_by"]),
            })
        return result

    def ignore(self, b32: str):
        """Игнорировать обнаруженную ноду."""
        self._ignored.add(b32)
        self.discovered.pop(b32, None)

    def get_public_friends_list(self) -> list[dict]:
        """
        Вернуть публичный список друзей для других нод (discovery).
        Только имя, модель и адрес — без портов и приватных данных.
        """
        result = []
        for b32, info in self.friends.list_friends().items():
            result.append({
                "address": b32,
                "name": info["name"],
                "model": info["model"],
            })
        return result
