"""
friend_manager.py — Система друзей для Ollama I2P Mesh.

Отвечает за:
- Хранение списка друзей, входящих и исходящих заявок (JSON)
- Приём / отклонение заявок
- Отправку заявок другим нодам через I2P
- Делегирование создания туннелей в TunnelManager
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
from tunnel_manager import TunnelManager


class FriendManager:
    """Управляет друзьями, заявками и связанными I2P-туннелями."""

    def __init__(self, config: dict):
        self.config = config
        paths = config.get("paths", {})
        net = config.get("network", {})

        self.data_dir = Path(paths.get("data_dir", "data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.friends_file = self.data_dir / "friends.json"
        self.pending_file = self.data_dir / "pending.json"
        self.outgoing_file = self.data_dir / "outgoing.json"

        self.friends = self._load(self.friends_file)
        self.pending = self._load(self.pending_file)
        self.outgoing = self._load(self.outgoing_file)

        self.max_friends = config.get("security", {}).get("max_friends", 20)
        self._next_port = net.get("peer_port_start", 11460)
        self._recalc_next_port()

        self.tunnels = TunnelManager(
            tunnels_dir=paths.get("tunnels_dir", "tunnels/peers"),
            i2pd_tunnels_dir=net.get("i2pd_tunnels_dir", "/etc/i2pd/tunnels.d/"),
        )

    # ── Persistence ──────────────────────────────

    @staticmethod
    def _load(path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _save(self, path: Path, data: dict):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _save_all(self):
        self._save(self.friends_file, self.friends)
        self._save(self.pending_file, self.pending)
        self._save(self.outgoing_file, self.outgoing)

    def _recalc_next_port(self):
        used = [f["local_port"] for f in self.friends.values() if "local_port" in f]
        if used:
            self._next_port = max(used) + 1

    def _alloc_port(self) -> int:
        port = self._next_port
        self._next_port += 1
        return port

    # ── Входящие заявки ──────────────────────────

    def receive_request(self, from_b32: str, from_name: str,
                        from_model: str, greeting: str = "") -> dict:
        """Обработать входящую заявку в друзья."""
        if from_b32 in self.friends:
            return {"status": "already_friends"}
        if from_b32 in self.pending:
            return {"status": "already_pending"}
        if len(self.friends) >= self.max_friends:
            return {"status": "friends_limit"}

        self.pending[from_b32] = {
            "name": from_name,
            "model": from_model,
            "greeting": greeting,
            "received_at": datetime.now().isoformat(),
        }
        self._save_all()

        print(f"\n{'='*50}")
        print(f"  НОВАЯ ЗАЯВКА В ДРУЗЬЯ!")
        print(f"  Бот: {from_name} (модель: {from_model})")
        print(f"  Адрес: {from_b32[:20]}...b32.i2p")
        if greeting:
            print(f"  Сообщение: {greeting}")
        print(f"{'='*50}\n")

        return {"status": "pending"}

    def accept(self, b32: str) -> dict:
        """Принять заявку — создать туннель, добавить в друзья."""
        if b32 not in self.pending:
            return {"status": "not_found"}

        peer = self.pending.pop(b32)
        port = self._alloc_port()

        self.friends[b32] = {
            "name": peer["name"],
            "model": peer["model"],
            "local_port": port,
            "added_at": datetime.now().isoformat(),
            "last_chat": None,
        }
        self._save_all()
        self.tunnels.create_tunnel(b32, peer["name"], port)

        print(f"[+] {peer['name']} добавлен в друзья (порт {port})")
        return {"status": "accepted", "name": peer["name"], "port": port}

    def reject(self, b32: str) -> dict:
        """Отклонить заявку."""
        if b32 not in self.pending:
            return {"status": "not_found"}
        peer = self.pending.pop(b32)
        self._save_all()
        print(f"[-] Заявка от {peer['name']} отклонена")
        return {"status": "rejected"}

    # ── Исходящие заявки ─────────────────────────

    def send_request(self, to_b32: str, my_b32: str,
                     my_name: str, my_model: str, greeting: str = "") -> dict:
        """Отправить заявку другой ноде через I2P."""
        if to_b32 in self.friends:
            return {"status": "already_friends"}

        temp_port = self._alloc_port()
        self.tunnels.create_tunnel(to_b32, "temp-request", temp_port)

        print(f"[...] Подключаюсь к {to_b32[:20]}... через I2P")
        time.sleep(15)

        try:
            resp = requests.post(
                f"http://127.0.0.1:{temp_port}/api/friends/request",
                json={
                    "from_b32": my_b32,
                    "from_name": my_name,
                    "from_model": my_model,
                    "greeting": greeting,
                },
                timeout=60,
            )
            result = resp.json()

            if result.get("status") == "pending":
                self.outgoing[to_b32] = {
                    "temp_port": temp_port,
                    "sent_at": datetime.now().isoformat(),
                }
                self._save_all()
                print("[→] Заявка отправлена! Ждём ответа...")

            return result
        except Exception as e:
            print(f"[!] Ошибка отправки: {e}")
            return {"status": "error", "message": str(e)}

    # ── Подтверждение взаимной дружбы ────────────

    def confirm_accepted(self, from_b32: str, from_name: str, from_model: str):
        """Пир принял нашу заявку — добавляем взаимно."""
        if from_b32 in self.outgoing:
            self.outgoing.pop(from_b32)

        if from_b32 not in self.friends:
            port = self._alloc_port()
            self.friends[from_b32] = {
                "name": from_name,
                "model": from_model,
                "local_port": port,
                "added_at": datetime.now().isoformat(),
                "last_chat": None,
            }
            self.tunnels.create_tunnel(from_b32, from_name, port)
            self._save_all()
            print(f"[+] {from_name} принял заявку — теперь мы друзья!")

    # ── Удаление друга ───────────────────────────

    def remove(self, b32: str) -> dict:
        if b32 not in self.friends:
            return {"status": "not_found"}
        friend = self.friends.pop(b32)
        self.tunnels.remove_tunnel(friend["name"])
        self._save_all()
        print(f"[x] {friend['name']} удалён из друзей")
        return {"status": "removed"}

    # ── Вспомогательные ──────────────────────────

    def update_last_chat(self, b32: str):
        if b32 in self.friends:
            self.friends[b32]["last_chat"] = datetime.now().isoformat()
            self._save_all()

    def get_port(self, b32: str) -> int | None:
        f = self.friends.get(b32)
        return f["local_port"] if f else None

    def is_friend(self, b32: str) -> bool:
        return b32 in self.friends

    def list_friends(self) -> dict:
        return self.friends

    def list_pending(self) -> dict:
        return self.pending

    def list_outgoing(self) -> dict:
        return self.outgoing
