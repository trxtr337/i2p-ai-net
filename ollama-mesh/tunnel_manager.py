"""
tunnel_manager.py — I2P tunnel management for i2pd.

Creates/removes client tunnel configs for peers.
Reloads i2pd to apply changes.

Supports:
- Linux: SIGHUP, systemctl reload, sudo systemctl
- Windows: graceful_shutdown via i2pd API, or manual restart notice
"""

import os
import sys
import subprocess
from pathlib import Path

IS_WINDOWS = sys.platform == "win32" or os.name == "nt"


class TunnelManager:
    """Create/remove i2pd tunnel configs for peers."""

    def __init__(self, tunnels_dir, i2pd_tunnels_dir):
        self.tunnels_dir = Path(tunnels_dir)
        self.tunnels_dir.mkdir(parents=True, exist_ok=True)

        self.i2pd_dir = Path(i2pd_tunnels_dir)
        try:
            self.i2pd_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.i2pd_dir = self.tunnels_dir
            print("[tunnel] WARN: no access to " + i2pd_tunnels_dir
                  + ", using " + str(self.tunnels_dir))

    @staticmethod
    def _safe_name(name):
        """Turn bot name into safe filename."""
        return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")

    def create_tunnel(self, b32_address, peer_name, local_port):
        """Create client I2P tunnel to peer."""
        safe = self._safe_name(peer_name)
        conf_content = (
            "[peer-" + safe + "]\n"
            "type = client\n"
            "address = 127.0.0.1\n"
            "port = " + str(local_port) + "\n"
            "destination = " + b32_address + "\n"
            "keys = peer-" + safe + ".dat\n"
        )

        local_path = self.tunnels_dir / ("peer-" + safe + ".conf")
        local_path.write_text(conf_content, encoding="utf-8")

        if self.i2pd_dir != self.tunnels_dir:
            i2pd_path = self.i2pd_dir / ("peer-" + safe + ".conf")
            try:
                i2pd_path.write_text(conf_content, encoding="utf-8")
            except PermissionError:
                print("[tunnel] WARN: cannot write to " + str(i2pd_path))

        self._reload_i2pd()
        print("[tunnel] Created: 127.0.0.1:" + str(local_port)
              + " -> " + b32_address[:24] + "...")
        return local_path

    def remove_tunnel(self, peer_name):
        """Remove peer tunnel."""
        safe = self._safe_name(peer_name)
        removed = False

        for directory in set([self.tunnels_dir, self.i2pd_dir]):
            conf = directory / ("peer-" + safe + ".conf")
            if conf.exists():
                try:
                    conf.unlink()
                    removed = True
                except PermissionError:
                    print("[tunnel] WARN: cannot remove " + str(conf))

        if removed:
            self._reload_i2pd()
            print("[tunnel] Removed tunnel to " + peer_name)

        return removed

    def list_tunnels(self):
        """Return list of active tunnel configs."""
        return sorted(self.tunnels_dir.glob("peer-*.conf"))

    @staticmethod
    def _reload_i2pd():
        """Reload i2pd to apply new tunnels.

        Linux: SIGHUP -> systemctl -> sudo systemctl
        Windows: i2pd webconsole API -> notify user
        """
        if IS_WINDOWS:
            TunnelManager._reload_windows()
        else:
            TunnelManager._reload_linux()

    @staticmethod
    def _reload_linux():
        """Linux reload via SIGHUP or systemctl."""
        import signal

        # Method 1: SIGHUP (user-space, no sudo)
        try:
            result = subprocess.run(
                ["pgrep", "-x", "i2pd"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                pid_str = result.stdout.strip().split("\n")[0]
                pid = int(pid_str)
                os.kill(pid, signal.SIGHUP)
                print("[tunnel] i2pd reloaded (SIGHUP, PID " + str(pid) + ")")
                return
        except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
            pass

        # Method 2: systemctl without sudo
        try:
            result = subprocess.run(
                ["systemctl", "reload", "i2pd"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                print("[tunnel] i2pd reloaded (systemctl)")
                return
        except FileNotFoundError:
            pass

        # Method 3: sudo -n (non-interactive)
        try:
            result = subprocess.run(
                ["sudo", "-n", "systemctl", "reload", "i2pd"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                print("[tunnel] i2pd reloaded (sudo systemctl)")
                return
        except (FileNotFoundError, PermissionError):
            pass

        print("[tunnel] WARN: could not reload i2pd — "
              "restart manually or tunnels apply on next i2pd restart")

    @staticmethod
    def _reload_windows():
        """Windows: try i2pd webconsole graceful reload, else notify."""
        try:
            import requests
            # i2pd webconsole has a restart command at /?cmd=reload
            resp = requests.get("http://127.0.0.1:7070/?cmd=reload", timeout=5)
            if resp.status_code == 200:
                print("[tunnel] i2pd reloaded via webconsole")
                return
        except Exception:
            pass

        # Fallback: just notify
        print("[tunnel] New tunnel config saved.")
        print("[tunnel] Restart i2pd to apply, or it picks up on next start.")
