#!/bin/bash
# ══════════════════════════════════════════════════
#  Ollama I2P Mesh Node — Установка БЕЗ sudo
#  Всё ставится в user-space (~/.local/, ~/.i2pd/)
# ══════════════════════════════════════════════════
set -e

MESH_DIR="$(cd "$(dirname "$0")" && pwd)"
I2PD_DIR="$HOME/.i2pd"
I2PD_TUNNELS_DIR="$I2PD_DIR/tunnels.d"
I2PD_BIN="$HOME/.local/bin/i2pd"

echo "══════════════════════════════════════════"
echo "  Ollama I2P Mesh — User-Space Setup"
echo "══════════════════════════════════════════"
echo ""

# === 1. Ollama ===
echo "=== 1. Проверка Ollama ==="
if command -v ollama &> /dev/null; then
    echo "[ok] Ollama найдена: $(which ollama)"
else
    echo "[!] Ollama не найдена."
    echo "    Установите вручную: https://ollama.com/download"
    echo "    Или: curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
    read -p "Продолжить без Ollama? [y/N]: " CONT
    if [[ "$CONT" != "y" && "$CONT" != "Y" ]]; then
        exit 1
    fi
fi

# === 2. i2pd (user-space) ===
echo ""
echo "=== 2. Установка i2pd (user-space) ==="
mkdir -p "$HOME/.local/bin"
mkdir -p "$I2PD_DIR"
mkdir -p "$I2PD_TUNNELS_DIR"

if [ -f "$I2PD_BIN" ]; then
    echo "[ok] i2pd уже установлен: $I2PD_BIN"
elif command -v i2pd &> /dev/null; then
    echo "[ok] i2pd найден в системе: $(which i2pd)"
    I2PD_BIN="$(which i2pd)"
else
    echo "[*] Скачиваю i2pd..."
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) ARCH_LABEL="amd64" ;;
        aarch64) ARCH_LABEL="arm64" ;;
        *) echo "[!] Неподдерживаемая архитектура: $ARCH"; exit 1 ;;
    esac

    # Попытка скачать бинарник из releases
    I2PD_VERSION="2.53.1"
    DOWNLOAD_URL="https://github.com/PurpleI2P/i2pd/releases/download/${I2PD_VERSION}/i2pd_${I2PD_VERSION}_linux_${ARCH_LABEL}.tar.gz"
    
    echo "    URL: $DOWNLOAD_URL"
    if curl -fSL "$DOWNLOAD_URL" -o /tmp/i2pd.tar.gz 2>/dev/null; then
        tar xzf /tmp/i2pd.tar.gz -C "$HOME/.local/bin/" i2pd 2>/dev/null || \
        tar xzf /tmp/i2pd.tar.gz -C /tmp/ && find /tmp -name 'i2pd' -type f -exec cp {} "$I2PD_BIN" \;
        chmod +x "$I2PD_BIN"
        rm -f /tmp/i2pd.tar.gz
        echo "[+] i2pd установлен: $I2PD_BIN"
    else
        echo "[!] Не удалось скачать i2pd автоматически."
        echo "    Скачайте вручную:"
        echo "    https://github.com/PurpleI2P/i2pd/releases"
        echo "    Положите бинарник в: $I2PD_BIN"
        echo ""
        read -p "Продолжить без i2pd? [y/N]: " CONT
        if [[ "$CONT" != "y" && "$CONT" != "Y" ]]; then
            exit 1
        fi
    fi
fi

# === 3. Конфиг i2pd ===
echo ""
echo "=== 3. Конфигурация i2pd ==="

I2PD_CONF="$I2PD_DIR/i2pd.conf"
if [ ! -f "$I2PD_CONF" ]; then
    cat > "$I2PD_CONF" << I2PDCONF
## i2pd user-space config for Ollama Mesh

## Top-level options (MUST be before any [section])
log = file
logfile = /dev/null
loglevel = warn
tunnelsdir = $I2PD_TUNNELS_DIR

[http]
enabled = true
address = 127.0.0.1
port = 7070

[httpproxy]
enabled = true
address = 127.0.0.1
port = 4444

[socksproxy]
enabled = true
address = 127.0.0.1
port = 4447

[sam]
enabled = true
address = 127.0.0.1
port = 7656
I2PDCONF
    echo "[+] Создан $I2PD_CONF"
else
    echo "[ok] $I2PD_CONF уже существует"
fi

# Проверить что tunnelsdir на месте (уже включён в шаблон)
if grep -q "tunnelsdir" "$I2PD_CONF" 2>/dev/null; then
    echo "[ok] tunnelsdir настроен"
else
    # Вставить в начало (до секций!), не в конец
    sed -i "1a tunnelsdir = $I2PD_TUNNELS_DIR" "$I2PD_CONF"
    echo "[+] tunnelsdir добавлен в начало конфига"
fi

# === 4. Серверный туннель для mesh-ноды ===
echo ""
echo "=== 4. Серверный туннель ==="
TUNNEL_CONF="$I2PD_TUNNELS_DIR/ollama-mesh.conf"
if [ ! -f "$TUNNEL_CONF" ]; then
    cat > "$TUNNEL_CONF" << 'TUNNELCONF'
[ollama-mesh]
type = server
host = 127.0.0.1
port = 11450
keys = ollama-mesh.dat
inbound.length = 2
outbound.length = 2
inbound.quantity = 3
outbound.quantity = 3
TUNNELCONF
    echo "[+] Создан серверный туннель: $TUNNEL_CONF"
else
    echo "[ok] Серверный туннель уже существует"
fi

# === 5. Python-зависимости ===
echo ""
echo "=== 5. Python-зависимости ==="
cd "$MESH_DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate 2>/dev/null
fi
pip install -r requirements.txt 2>/dev/null || pip install requests pyyaml 2>/dev/null || \
pip install --user requests pyyaml
echo "[ok] Зависимости установлены"

# === 6. Модель Ollama ===
echo ""
echo "=== 6. Скачивание модели Ollama ==="
if command -v ollama &> /dev/null; then
    echo "Доступные модели: llama3, mistral, gemma2, phi3"
    read -p "Какую модель скачать? [llama3]: " MODEL
    MODEL=${MODEL:-llama3}
    ollama pull "$MODEL"
    echo "[ok] Модель $MODEL готова"
else
    MODEL="llama3"
    echo "[!] Ollama не найдена, пропускаю скачивание модели"
fi

# === 7. Обновить config.yaml ===
echo ""
echo "=== 7. Настройка config.yaml ==="
if [ -f "$MESH_DIR/config.yaml" ]; then
    # Обновить пути i2pd на user-space
    sed -i "s|i2pd_tunnels_dir:.*|i2pd_tunnels_dir: \"$I2PD_TUNNELS_DIR/\"|" "$MESH_DIR/config.yaml"
    echo "[ok] Обновлён i2pd_tunnels_dir в config.yaml"
fi

# === 8. Запуск i2pd ===
echo ""
echo "=== 8. Запуск i2pd ==="
if pgrep -x i2pd > /dev/null 2>&1; then
    echo "[ok] i2pd уже запущен (PID: $(pgrep -x i2pd))"
else
    if [ -x "$I2PD_BIN" ]; then
        echo "[*] Запускаю i2pd в фоне..."
        "$I2PD_BIN" --datadir="$I2PD_DIR" --conf="$I2PD_CONF" --tunconf="$I2PD_TUNNELS_DIR/ollama-mesh.conf" --daemon
        sleep 2
        if pgrep -x i2pd > /dev/null 2>&1; then
            echo "[+] i2pd запущен (PID: $(pgrep -x i2pd))"
        else
            echo "[!] i2pd не удалось запустить. Попробуйте вручную:"
            echo "    $I2PD_BIN --datadir=$I2PD_DIR --daemon"
        fi
    else
        echo "[!] i2pd бинарник не найден. Запустите i2pd вручную."
    fi
fi

# === 9. Получение .b32.i2p адреса ===
echo ""
echo "=== 9. Получение .b32.i2p адреса ==="
echo "Подождите 15 секунд пока i2pd создаст ключи..."
sleep 15

# Проверить webconsole
B32=""
if curl -s "http://127.0.0.1:7070/?page=i2p_tunnels" 2>/dev/null | grep -oP '[a-z0-9]{52}\.b32\.i2p' | head -1 > /tmp/b32.txt 2>/dev/null; then
    B32=$(cat /tmp/b32.txt)
fi

if [ -z "$B32" ]; then
    # Попробовать найти в keys
    for keyfile in "$I2PD_DIR"/*.dat "$I2PD_DIR"/destinations/*.dat; do
        if [ -f "$keyfile" ]; then
            B32=$(python3 -c "
import hashlib, base64
with open('$keyfile', 'rb') as f:
    data = f.read()
print('Found key file: $keyfile')
" 2>/dev/null)
        fi
    done
fi

if [ -n "$B32" ]; then
    echo "[+] Ваш адрес: $B32"
    sed -i "s|my_b32: \"\"|my_b32: \"$B32\"|" "$MESH_DIR/config.yaml"
    echo "[ok] Адрес добавлен в config.yaml"
else
    echo "[!] .b32.i2p адрес пока не появился."
    echo "    Проверьте: http://127.0.0.1:7070/?page=i2p_tunnels"
    echo "    Вставьте адрес вручную в config.yaml → network.my_b32"
fi

echo ""
echo "══════════════════════════════════════════"
echo "  Установка завершена!"
echo ""
echo "  Пути:"
echo "    i2pd конфиг:    $I2PD_DIR/"
echo "    i2pd туннели:   $I2PD_TUNNELS_DIR/"
echo "    Mesh нода:      $MESH_DIR/"
echo ""
echo "  Если i2pd не запущен:"
echo "    $I2PD_BIN --datadir=$I2PD_DIR --daemon"
echo ""
echo "  Запуск ноды:  python3 main.py"
echo "══════════════════════════════════════════"
