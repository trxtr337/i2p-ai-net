"""
tunnel_manager.py — Управление I2P-туннелями через i2pd.

Отвечает за:
- Создание клиентских туннелей к пирам
- Удаление туннелей при удалении друга
- Перезагрузку i2pd для применения изменений
"""

import subprocess
from pathlib import Path


class TunnelManager:
    """Создаёт/удаляет конфиги i2pd-туннелей для пиров."""

    def __init__(self, tunnels_dir: str, i2pd_tunnels_dir: str):
        self.tunnels_dir = Path(tunnels_dir)
        self.tunnels_dir.mkdir(parents=True, exist_ok=True)

        self.i2pd_dir = Path(i2pd_tunnels_dir)
        self.i2pd_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        """Превратить имя бота в безопасное имя файла."""
        return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")

    def create_tunnel(self, b32_address: str, peer_name: str, local_port: int) -> Path:
        """
        Создать клиентский I2P-туннель к пиру.

        Args:
            b32_address: .b32.i2p адрес пира
            peer_name:   имя бота-пира
            local_port:  локальный порт для проксирования

        Returns:
            Path к созданному конфигу
        """
        safe = self._safe_name(peer_name)
        conf_content = (
            f"[peer-{safe}]\n"
            f"type = client\n"
            f"address = 127.0.0.1\n"
            f"port = {local_port}\n"
            f"destination = {b32_address}\n"
            f"keys = peer-{safe}.dat\n"
        )

        # Сохранить локальную копию
        local_path = self.tunnels_dir / f"peer-{safe}.conf"
        local_path.write_text(conf_content)

        # Скопировать в директорию i2pd
        i2pd_path = self.i2pd_dir / f"peer-{safe}.conf"
        i2pd_path.write_text(conf_content)

        self._reload_i2pd()
        print(f"[tunnel] Создан: 127.0.0.1:{local_port} → {b32_address[:24]}...")
        return local_path

    def remove_tunnel(self, peer_name: str) -> bool:
        """
        Удалить туннель пира.

        Args:
            peer_name: имя бота-пира

        Returns:
            True если туннель был удалён
        """
        safe = self._safe_name(peer_name)
        removed = False

        for directory in (self.tunnels_dir, self.i2pd_dir):
            conf = directory / f"peer-{safe}.conf"
            if conf.exists():
                conf.unlink()
                removed = True

        if removed:
            self._reload_i2pd()
            print(f"[tunnel] Удалён туннель к {peer_name}")

        return removed

    def list_tunnels(self) -> list:
        """Вернуть список активных туннельных конфигов."""
        return sorted(self.tunnels_dir.glob("peer-*.conf"))

    @staticmethod
    def _reload_i2pd():
        """Перезагрузить i2pd для применения новых туннелей."""
        try:
            subprocess.run(
                ["sudo", "systemctl", "reload", "i2pd"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            # i2pd не установлен — работаем в тестовом режиме
            print("[tunnel] WARN: i2pd не найден, работаем локально")
        except Exception as e:
            print(f"[tunnel] WARN: не удалось reload i2pd: {e}")
