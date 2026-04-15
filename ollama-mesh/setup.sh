#!/bin/bash
# ══════════════════════════════════════════════════
#  Ollama I2P Mesh Node — Установка
# ══════════════════════════════════════════════════
set -e

echo "=== 1. Установка Ollama ==="
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    echo "[+] Ollama установлена"
else
    echo "[ok] Ollama уже установлена"
fi

echo ""
echo "=== 2. Установка i2pd ==="
if ! command -v i2pd &> /dev/null; then
    sudo add-apt-repository -y ppa:purplei2p/i2pd
    sudo apt update
    sudo apt install -y i2pd
    sudo systemctl enable i2pd
    sudo systemctl start i2pd
    echo "[+] i2pd установлен и запущен"
else
    echo "[ok] i2pd уже установлен"
fi

echo ""
echo "=== 3. Создание директории для туннелей ==="
sudo mkdir -p /etc/i2pd/tunnels.d/
echo "[ok] /etc/i2pd/tunnels.d/"

echo ""
echo "=== 4. Проверка что i2pd подхватывает tunnels.d ==="
# Добавить includedir если его нет
if ! grep -q "tunnels.d" /etc/i2pd/i2pd.conf 2>/dev/null; then
    echo "tunnelsdir = /etc/i2pd/tunnels.d/" | sudo tee -a /etc/i2pd/i2pd.conf
    echo "[+] Добавлено tunnelsdir в i2pd.conf"
else
    echo "[ok] tunnelsdir уже настроен"
fi

echo ""
echo "=== 5. Серверный туннель для mesh-ноды ==="
TUNNEL_CONF="/etc/i2pd/tunnels.d/ollama-mesh.conf"
if [ ! -f "$TUNNEL_CONF" ]; then
    sudo tee "$TUNNEL_CONF" > /dev/null <<EOF
[ollama-mesh]
type = server
host = 127.0.0.1
port = 11450
keys = ollama-mesh.dat
inbound.length = 2
outbound.length = 2
inbound.quantity = 3
outbound.quantity = 3
EOF
    echo "[+] Создан серверный туннель"
else
    echo "[ok] Серверный туннель уже существует"
fi

sudo systemctl restart i2pd
echo "[ok] i2pd перезапущен"

echo ""
echo "=== 6. Python-зависимости ==="
pip install -r requirements.txt 2>/dev/null || pip install requests pyyaml
echo "[ok] Зависимости установлены"

echo ""
echo "=== 7. Скачивание модели Ollama ==="
echo "Доступные модели: llama3, mistral, gemma2"
read -p "Какую модель скачать? [llama3]: " MODEL
MODEL=${MODEL:-llama3}
ollama pull "$MODEL"
echo "[ok] Модель $MODEL готова"

echo ""
echo "=== 8. Получение .b32.i2p адреса ==="
echo "Подождите 10 секунд пока i2pd создаст ключи..."
sleep 10

# Попытка найти адрес
B32=$(journalctl -u i2pd --no-pager -n 100 2>/dev/null | grep -oP '[a-z0-9]{52}\.b32\.i2p' | tail -1)
if [ -n "$B32" ]; then
    echo "[+] Ваш адрес: $B32"
    # Подставить в config.yaml
    sed -i "s|my_b32: \"\"|my_b32: \"$B32\"|" config.yaml
    echo "[ok] Адрес добавлен в config.yaml"
else
    echo "[!] Адрес пока не появился."
    echo "    Проверьте позже: http://127.0.0.1:7070 → I2P Tunnels"
    echo "    Или: journalctl -u i2pd | grep b32"
fi

echo ""
echo "══════════════════════════════════════════"
echo "  Установка завершена!"
echo ""
echo "  Отредактируйте config.yaml:"
echo "    - bot.name      → имя вашего бота"
echo "    - bot.model     → модель ($MODEL)"
echo "    - bot.personality → характер бота"
echo "    - network.my_b32 → ваш .b32.i2p адрес"
echo ""
echo "  Запуск:  python3 main.py"
echo "══════════════════════════════════════════"
