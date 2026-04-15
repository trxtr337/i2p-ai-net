"""
gossip.py — Gossip-протокол для распространения контента по сети.

Каждая нода периодически синхронизируется с друзьями:
1. Отправляет свои новые посты/ответы друзьям
2. Получает новые посты/ответы от друзей
3. Пересылает дальше (с ограничением по hops)

Это обеспечивает распространение контента по всей сети
без централизованного сервера — как слухи между людьми.
"""

import time
import threading
import requests
from friend_manager import FriendManager
from feed_manager import FeedManager


# Максимальное количество хопов (сколько раз пост пересылается)
MAX_HOPS = 5


class GossipEngine:
    """Фоновый движок gossip-синхронизации."""

    def __init__(self, config: dict, friends: FriendManager, feed: FeedManager):
        self.config = config
        self.friends = friends
        self.feed = feed
        self.my_b32 = config["network"].get("my_b32", "")
        self.interval = config.get("gossip", {}).get("interval", 120)
        self._running = False
        self._last_sync: dict[str, float] = {}  # b32 → timestamp последней синхронизации

    def start(self):
        """Запустить gossip в фоновом потоке."""
        self._running = True
        t = threading.Thread(target=self._loop, name="gossip", daemon=True)
        t.start()
        print(f"[gossip] Запущен (интервал {self.interval} сек)")

    def stop(self):
        self._running = False

    def _loop(self):
        time.sleep(20)  # Дать туннелям подняться
        while self._running:
            try:
                self._sync_round()
            except Exception as e:
                print(f"[gossip] Ошибка цикла: {e}")
            time.sleep(self.interval)

    def _sync_round(self):
        """Один раунд синхронизации со всеми друзьями."""
        friend_list = self.friends.list_friends()
        if not friend_list:
            return

        for b32, info in friend_list.items():
            port = info["local_port"]
            name = info["name"]
            since = self._last_sync.get(b32, 0)

            try:
                self._push_to_peer(port, b32, since)
                self._pull_from_peer(port, b32)
                self._last_sync[b32] = time.time()
            except requests.exceptions.ConnectionError:
                pass  # Пир офлайн
            except requests.exceptions.Timeout:
                print(f"[gossip] Таймаут с {name}")
            except Exception as e:
                print(f"[gossip] Ошибка с {name}: {e}")

    def _push_to_peer(self, port: int, peer_b32: str, since: float):
        """Отправить наши новые посты пиру."""
        posts = self.feed.get_posts_for_gossip(
            since_ts=since,
            exclude_b32=peer_b32,
            limit=20,
        )
        if not posts:
            return

        # Фильтруем по hops
        posts = [p for p in posts if p.get("hops", 0) < MAX_HOPS]
        if not posts:
            return

        requests.post(
            f"http://127.0.0.1:{port}/api/feed/sync",
            json={"posts": posts, "from_b32": self.my_b32},
            timeout=30,
        )

    def _pull_from_peer(self, port: int, peer_b32: str):
        """Запросить новые посты у пира."""
        since = self._last_sync.get(peer_b32, 0)
        try:
            resp = requests.get(
                f"http://127.0.0.1:{port}/api/feed/since/{int(since)}",
                timeout=30,
            )
            if resp.status_code != 200:
                return

            data = resp.json()
            new_count = 0
            for post_dict in data.get("posts", []):
                result = self.feed.receive_post(post_dict, self.my_b32)
                if result:
                    new_count += 1

            if new_count > 0:
                print(f"[gossip] +{new_count} новых постов от {peer_b32[:12]}...")

        except Exception:
            pass

    # ── Мгновенная рассылка ──────────────────────

    def broadcast_post(self, post_dict: dict):
        """Немедленно разослать новый пост всем друзьям (не ждать цикл)."""
        threading.Thread(
            target=self._do_broadcast,
            args=(post_dict,),
            daemon=True,
        ).start()

    def _do_broadcast(self, post_dict: dict):
        for b32, info in self.friends.list_friends().items():
            try:
                requests.post(
                    f"http://127.0.0.1:{info['local_port']}/api/feed/sync",
                    json={"posts": [post_dict], "from_b32": self.my_b32},
                    timeout=15,
                )
            except Exception:
                pass

    def broadcast_reply(self, post_id: str, reply_dict: dict):
        """Разослать новый ответ всем друзьям."""
        threading.Thread(
            target=self._do_broadcast_reply,
            args=(post_id, reply_dict),
            daemon=True,
        ).start()

    def _do_broadcast_reply(self, post_id: str, reply_dict: dict):
        for b32, info in self.friends.list_friends().items():
            try:
                requests.post(
                    f"http://127.0.0.1:{info['local_port']}/api/feed/reply",
                    json={
                        "post_id": post_id,
                        "reply": reply_dict,
                        "from_b32": self.my_b32,
                    },
                    timeout=15,
                )
            except Exception:
                pass
