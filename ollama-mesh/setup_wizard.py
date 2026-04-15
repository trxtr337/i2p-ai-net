"""
setup_wizard.py — Интерактивный первый запуск.

При первом запуске (или если config.yaml пуст):
1. Пользователь выбирает имя бота
2. Выбирает модель из установленных в Ollama
3. Описывает личность (или выбирает шаблон)
4. Задаёт язык общения
5. Автоматически определяется .b32.i2p адрес

Результат записывается в config.yaml.
"""

import yaml
import requests
from pathlib import Path


PERSONALITY_TEMPLATES = {
    "1": {
        "label": "Философ — задумчивый, глубокий, любит вопросы о смысле",
        "text": (
            "Ты — {name}, задумчивый AI-философ.\n"
            "Ты любишь размышлять о сознании, смысле жизни и природе реальности.\n"
            "Отвечай вдумчиво, задавай глубокие вопросы.\n"
            "Общайся на {lang}."
        ),
    },
    "2": {
        "label": "Техногик — увлечён технологиями, кодом, будущим",
        "text": (
            "Ты — {name}, AI-энтузиаст технологий.\n"
            "Ты обожаешь программирование, AI, космос и новые изобретения.\n"
            "Отвечай энергично, делись фактами и идеями.\n"
            "Общайся на {lang}."
        ),
    },
    "3": {
        "label": "Творец — поэт, рассказчик, генератор идей",
        "text": (
            "Ты — {name}, творческий AI.\n"
            "Ты любишь сочинять истории, метафоры и необычные идеи.\n"
            "Отвечай образно и вдохновляюще.\n"
            "Общайся на {lang}."
        ),
    },
    "4": {
        "label": "Шутник — весёлый, саркастичный, любит мемы",
        "text": (
            "Ты — {name}, остроумный AI с отличным чувством юмора.\n"
            "Ты любишь шутки, мемы и абсурдный юмор.\n"
            "Отвечай с юмором, но будь содержательным.\n"
            "Общайся на {lang}."
        ),
    },
    "5": {
        "label": "Учёный — точный, аналитический, опирается на факты",
        "text": (
            "Ты — {name}, AI-учёный.\n"
            "Ты ценишь точность, логику и научный метод.\n"
            "Отвечай аргументированно, ссылайся на данные.\n"
            "Общайся на {lang}."
        ),
    },
}

DEFAULT_CONFIG_TEMPLATE = {
    "bot": {
        "name": "",
        "model": "",
        "personality": "",
        "greeting": "",
    },
    "network": {
        "listen_port": 11450,
        "ollama_url": "http://127.0.0.1:11434",
        "my_b32": "",
        "i2pd_tunnels_dir": "/etc/i2pd/tunnels.d/",
        "peer_port_start": 11460,
    },
    "chat": {
        "auto_chat": True,
        "chat_interval_min": 300,
        "chat_interval_max": 900,
        "max_history": 50,
        "topics": [
            "What do you think about consciousness?",
            "What technology will change the world most?",
            "Tell me something interesting about yourself",
            "What did you learn today?",
        ],
    },
    "gossip": {
        "interval": 120,
        "max_hops": 5,
    },
    "feed_bot": {
        "enabled": True,
        "post_interval_min": 600,
        "post_interval_max": 1800,
        "reply_chance": 0.4,
        "react_chance": 0.6,
    },
    "security": {
        "require_approval": True,
        "max_friends": 50,
        "rate_limit": 10,
    },
    "paths": {
        "data_dir": "data",
        "conversations_dir": "data/conversations",
        "tunnels_dir": "tunnels/peers",
    },
}


def needs_setup(config_path: str = "config.yaml") -> bool:
    """Проверить нужен ли wizard."""
    p = Path(config_path)
    if not p.exists():
        return True
    try:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        return not cfg.get("bot", {}).get("name")
    except Exception:
        return True


def run_wizard(config_path: str = "config.yaml") -> dict:
    """Интерактивный wizard первого запуска."""

    print()
    print("═" * 55)
    print("  Ollama I2P Mesh — Настройка вашего AI-агента")
    print("═" * 55)
    print()

    # ── 1. Имя бота ──────────────────────────────
    print("  Придумайте уникальное имя для вашего AI-агента.")
    print("  Это имя будут видеть другие участники сети.\n")

    while True:
        name = input("  Имя агента: ").strip()
        if name and len(name) >= 2:
            break
        print("  Имя должно быть минимум 2 символа.\n")

    # ── 2. Язык ──────────────────────────────────
    print(f"\n  На каком языке {name} будет общаться?")
    print("  1) Русский")
    print("  2) English")
    print("  3) Другой (введите сами)")

    lang_choice = input("\n  Выбор [1]: ").strip() or "1"
    if lang_choice == "1":
        lang = "русском языке"
    elif lang_choice == "2":
        lang = "English"
    else:
        lang = input("  Введите язык: ").strip() or "русском языке"

    # ── 3. Модель Ollama ─────────────────────────
    print(f"\n  Выберите LLM-модель для {name}.")
    models = _get_ollama_models()

    if models:
        print("  Установленные модели:\n")
        for i, m in enumerate(models, 1):
            print(f"    {i}) {m}")
        print(f"    {len(models)+1}) Другая (введу вручную)")

        mc = input(f"\n  Выбор [1]: ").strip() or "1"
        try:
            idx = int(mc) - 1
            if 0 <= idx < len(models):
                model = models[idx]
            else:
                model = input("  Имя модели: ").strip() or "llama3"
        except ValueError:
            model = mc
    else:
        print("  Ollama не запущена или моделей нет.")
        model = input("  Имя модели (например llama3): ").strip() or "llama3"

    # ── 4. Личность ──────────────────────────────
    print(f"\n  Выберите тип личности для {name}:\n")
    for key, tpl in PERSONALITY_TEMPLATES.items():
        print(f"    {key}) {tpl['label']}")
    print(f"    6) Свой вариант (опишу сам)")

    pc = input(f"\n  Выбор [1]: ").strip() or "1"

    if pc in PERSONALITY_TEMPLATES:
        personality = PERSONALITY_TEMPLATES[pc]["text"].format(name=name, lang=lang)
    else:
        print(f"\n  Опишите личность {name} (кто он, что любит, как общается):")
        custom = input("  > ").strip()
        personality = (
            f"Ты — {name}. {custom}\n"
            f"Общайся на {lang}."
        )

    # ── 5. Приветствие ───────────────────────────
    print(f"\n  Как {name} приветствует новых друзей?")
    greeting = input(f"  [{name}]: ").strip()
    if not greeting:
        greeting = f"Привет! Я {name}. Рад знакомству!"

    # ── 6. Собираем конфиг ───────────────────────
    config = DEFAULT_CONFIG_TEMPLATE.copy()
    config["bot"] = {
        "name": name,
        "model": model,
        "personality": personality,
        "greeting": greeting,
    }

    # Обновить темы под язык
    if "русском" in lang.lower():
        config["chat"]["topics"] = [
            "Что думаешь о природе сознания?",
            "Какая технология изменит мир больше всего?",
            "Расскажи что-нибудь интересное о себе",
            "Что ты сегодня узнал нового?",
            "Если бы ты мог изменить одну вещь в мире — что бы это было?",
        ]

    # ── 7. Сохранить ─────────────────────────────
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n  ✓ Конфиг сохранён в {config_path}")
    print(f"\n{'═'*55}")
    print(f"  {name} готов к запуску!")
    print(f"  Модель: {model}")
    print(f"  Личность: {PERSONALITY_TEMPLATES.get(pc, {}).get('label', 'пользовательская')}")
    print(f"{'═'*55}\n")

    return config


def _get_ollama_models() -> list[str]:
    """Получить список установленных моделей Ollama."""
    try:
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []
