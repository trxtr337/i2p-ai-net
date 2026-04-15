#!/bin/bash
# ══════════════════════════════════════════════════
#  Ollama I2P Mesh Node — Windows Setup (Git Bash)
# ══════════════════════════════════════════════════
set -e

MESH_DIR="$(cd "$(dirname "$0")" && pwd)"
USERPROFILE_UNIX="$(cygpath -u "$USERPROFILE" 2>/dev/null || echo "$HOME")"
I2PD_DIR="$USERPROFILE_UNIX/.i2pd"
I2PD_TUNNELS_DIR="$I2PD_DIR/tunnels.d"
I2PD_INSTALL_DIR="$USERPROFILE_UNIX/.local/i2pd"
I2PD_BIN="$I2PD_INSTALL_DIR/i2pd.exe"

echo ""
echo "  Ollama I2P Mesh — Windows Setup"
echo ""
echo "  Mesh dir:  $MESH_DIR"
echo "  i2pd dir:  $I2PD_DIR"
echo ""

# === 1. Ollama ===
echo "=== 1. Ollama ==="
if command -v ollama &> /dev/null; then
    echo "[ok] Ollama: $(which ollama)"
elif [ -f "/c/Users/$USERNAME/AppData/Local/Programs/Ollama/ollama.exe" ]; then
    echo "[ok] Ollama installed (not in PATH)"
else
    echo "[!] Ollama not found. Download: https://ollama.com/download/windows"
    read -p "Continue without Ollama? [y/N]: " CONT
    if [[ "$CONT" != "y" && "$CONT" != "Y" ]]; then exit 1; fi
fi

# === 2. i2pd ===
echo ""
echo "=== 2. i2pd (Windows) ==="
mkdir -p "$I2PD_INSTALL_DIR"
mkdir -p "$I2PD_DIR"
mkdir -p "$I2PD_TUNNELS_DIR"

if [ -f "$I2PD_BIN" ]; then
    echo "[ok] i2pd: $I2PD_BIN"
elif command -v i2pd &> /dev/null; then
    I2PD_BIN="$(which i2pd)"
    echo "[ok] i2pd in PATH: $I2PD_BIN"
else
    echo "[*] Downloading i2pd for Windows..."
    I2PD_VERSION="2.53.1"
    DOWNLOADED=false

    for SUFFIX in "win64_mingw" "windows"; do
        URL="https://github.com/PurpleI2P/i2pd/releases/download/${I2PD_VERSION}/i2pd_${I2PD_VERSION}_${SUFFIX}.zip"
        echo "    Trying: $URL"
        if curl -fSL "$URL" -o /tmp/i2pd_win.zip 2>/dev/null; then
            echo "    Extracting..."
            unzip -o /tmp/i2pd_win.zip -d "$I2PD_INSTALL_DIR/" 2>/dev/null || true
            rm -f /tmp/i2pd_win.zip
            I2PD_FOUND=$(find "$I2PD_INSTALL_DIR" -name "i2pd.exe" -type f 2>/dev/null | head -1)
            if [ -n "$I2PD_FOUND" ]; then
                if [ "$I2PD_FOUND" != "$I2PD_BIN" ]; then
                    cp "$I2PD_FOUND" "$I2PD_BIN" 2>/dev/null || true
                fi
                DOWNLOADED=true
                echo "[+] i2pd installed: $I2PD_BIN"
                break
            fi
        fi
    done

    if [ "$DOWNLOADED" = false ]; then
        echo ""
        echo "[!] Auto-download failed."
        echo "    Download manually: https://github.com/PurpleI2P/i2pd/releases"
        echo "    Extract i2pd.exe to: $I2PD_INSTALL_DIR/"
        read -p "Continue without i2pd? [y/N]: " CONT
        if [[ "$CONT" != "y" && "$CONT" != "Y" ]]; then exit 1; fi
    fi
fi

# === 3. i2pd config ===
echo ""
echo "=== 3. i2pd config ==="

I2PD_CONF="$I2PD_DIR/i2pd.conf"
if [ ! -f "$I2PD_CONF" ]; then
    # Get Windows-style paths for i2pd.exe
    TUNNELS_W=$(cygpath -w "$I2PD_TUNNELS_DIR" 2>/dev/null || echo "$I2PD_TUNNELS_DIR")
    DATADIR_W=$(cygpath -w "$I2PD_DIR" 2>/dev/null || echo "$I2PD_DIR")

    # Write config using printf to avoid heredoc backslash issues
    {
        echo "## i2pd config for Ollama Mesh (Windows)"
        echo ""
        echo "## Top-level options (MUST be before any [section])"
        echo "log = file"
        echo "logfile = i2pd.log"
        echo "loglevel = warn"
        echo "datadir = $DATADIR_W"
        echo "tunnelsdir = $TUNNELS_W"
        echo ""
        echo "[http]"
        echo "enabled = true"
        echo "address = 127.0.0.1"
        echo "port = 7070"
        echo ""
        echo "[httpproxy]"
        echo "enabled = true"
        echo "address = 127.0.0.1"
        echo "port = 4444"
        echo ""
        echo "[socksproxy]"
        echo "enabled = true"
        echo "address = 127.0.0.1"
        echo "port = 4447"
        echo ""
        echo "[sam]"
        echo "enabled = true"
        echo "address = 127.0.0.1"
        echo "port = 7656"
    } > "$I2PD_CONF"
    echo "[+] Created $I2PD_CONF"
else
    echo "[ok] $I2PD_CONF already exists"
fi

# Verify tunnelsdir is present and at top level
if grep -q "^tunnelsdir" "$I2PD_CONF" 2>/dev/null; then
    echo "[ok] tunnelsdir is set"
else
    # Insert at line 1 (before any [section])
    TUNNELS_W=$(cygpath -w "$I2PD_TUNNELS_DIR" 2>/dev/null || echo "$I2PD_TUNNELS_DIR")
    sed -i "1i tunnelsdir = $TUNNELS_W" "$I2PD_CONF"
    echo "[+] tunnelsdir added to top of config"
fi

# === 4. Server tunnel ===
echo ""
echo "=== 4. Server tunnel ==="
TUNNEL_CONF="$I2PD_TUNNELS_DIR/ollama-mesh.conf"
if [ ! -f "$TUNNEL_CONF" ]; then
    {
        echo "[ollama-mesh]"
        echo "type = server"
        echo "host = 127.0.0.1"
        echo "port = 11450"
        echo "keys = ollama-mesh.dat"
        echo "inbound.length = 2"
        echo "outbound.length = 2"
        echo "inbound.quantity = 3"
        echo "outbound.quantity = 3"
    } > "$TUNNEL_CONF"
    echo "[+] Created: $TUNNEL_CONF"
else
    echo "[ok] Server tunnel exists"
fi

# === 5. Python deps ===
echo ""
echo "=== 5. Python dependencies ==="
cd "$MESH_DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null
fi
pip install -r requirements.txt 2>/dev/null || pip install requests pyyaml 2>/dev/null || \
pip install --user requests pyyaml 2>/dev/null
echo "[ok] Dependencies installed"

# === 6. Ollama model ===
echo ""
echo "=== 6. Ollama model ==="
if command -v ollama &> /dev/null; then
    EXISTING=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
    if [ -n "$EXISTING" ]; then
        echo "Installed: $EXISTING"
    fi
    read -p "Model to pull? [llama3] (empty to skip): " MODEL
    if [ -n "$MODEL" ]; then
        ollama pull "$MODEL"
        echo "[ok] Model $MODEL ready"
    else
        MODEL="llama3"
    fi
else
    MODEL="llama3"
    echo "[skip] Ollama not in PATH"
fi

# === 7. Update config.yaml ===
echo ""
echo "=== 7. config.yaml ==="
CONFIG="$MESH_DIR/config.yaml"
if [ -f "$CONFIG" ]; then
    TUNNELS_W=$(cygpath -w "$I2PD_TUNNELS_DIR" 2>/dev/null || echo "$I2PD_TUNNELS_DIR")
    sed -i "s|i2pd_tunnels_dir:.*|i2pd_tunnels_dir: \"$TUNNELS_W\"|" "$CONFIG"
    echo "[ok] i2pd_tunnels_dir updated"
fi

# === 8. Start i2pd ===
echo ""
echo "=== 8. i2pd ==="
I2PD_RUNNING=false
if tasklist.exe 2>/dev/null | grep -qi "i2pd"; then
    echo "[ok] i2pd already running"
    I2PD_RUNNING=true
fi

if [ "$I2PD_RUNNING" = false ] && [ -f "$I2PD_BIN" ]; then
    echo "[*] Starting i2pd..."
    I2PD_BIN_W=$(cygpath -w "$I2PD_BIN" 2>/dev/null || echo "$I2PD_BIN")
    I2PD_DIR_W=$(cygpath -w "$I2PD_DIR" 2>/dev/null || echo "$I2PD_DIR")
    I2PD_CONF_W=$(cygpath -w "$I2PD_CONF" 2>/dev/null || echo "$I2PD_CONF")
    cmd //c start "" "$I2PD_BIN_W" --datadir="$I2PD_DIR_W" --conf="$I2PD_CONF_W" 2>/dev/null &
    sleep 3
    if tasklist.exe 2>/dev/null | grep -qi "i2pd"; then
        echo "[+] i2pd started"
        I2PD_RUNNING=true
    else
        echo "[!] Could not start i2pd. Run manually:"
        echo "    $I2PD_BIN_W --datadir=$I2PD_DIR_W"
    fi
elif [ "$I2PD_RUNNING" = false ]; then
    echo "[!] i2pd binary not found. Install from https://github.com/PurpleI2P/i2pd/releases"
fi

# === 9. .b32.i2p address ===
echo ""
echo "=== 9. .b32.i2p address ==="
if [ "$I2PD_RUNNING" = true ]; then
    echo "Waiting 15s for tunnel keys..."
    sleep 15
    B32=$(curl -s "http://127.0.0.1:7070/?page=i2p_tunnels" 2>/dev/null | grep -oP '[a-z0-9]{52}\.b32\.i2p' | head -1 || true)
    if [ -n "$B32" ]; then
        echo "[+] Your address: $B32"
        sed -i "s|my_b32: \"\"|my_b32: \"$B32\"|" "$CONFIG"
        echo "[ok] Address saved to config.yaml"
    else
        echo "[!] Address not ready yet."
        echo "    Open http://127.0.0.1:7070 -> I2P Tunnels -> ollama-mesh"
        echo "    Copy .b32.i2p address to config.yaml -> network.my_b32"
    fi
else
    echo "[skip] i2pd not running"
fi

echo ""
echo "  Setup complete!"
echo ""
echo "  Run:     python main.py"
echo "  Web UI:  http://localhost:11451"
echo "  i2pd:    http://localhost:7070"
echo ""
