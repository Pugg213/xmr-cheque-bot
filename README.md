# XMR Cheque Bot

Telegram-бот для создания платёжных чеков в Monero (XMR). MVP-версия с поддержкой stagenet.

## Быстрый старт (Stagenet)

### Локальная разработка

1. **Клонируйте репозиторий и перейдите в директорию:**
   ```bash
   cd xmr-cheque-bot
   ```

2. **Создайте виртуальное окружение и установите зависимости:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Создайте `.env` файл из примера:**
   ```bash
   cp .env.example .env
   ```

4. **Заполните `.env`:**
   ```bash
   # Генерируем ключ шифрования
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   
   # Редактируем .env
   BOT_TOKEN=your_bot_token_from_botfather
   VIEW_KEY_ENCRYPTION_KEY=generated_key_from_above
   ```

5. **Запустите инфраструктуру (Redis + Monero stagenet):**
   ```bash
   docker compose up -d redis monerod monero-wallet-rpc
   ```

6. **Запустите бота локально:**
   ```bash
   # Режим бота (только Telegram polling)
   APP_MODE=bot python -m xmr_cheque_bot
   
   # Или режим монитора (только payment monitor)
   APP_MODE=monitor python -m xmr_cheque_bot
   
   # Или оба режима concurrently
   APP_MODE=both python -m xmr_cheque_bot
   ```

### Docker Compose (полный стек)

```bash
# Заполните .env как описано выше
cp .env.example .env
# ... редактируем .env

# Запуск всего стека
docker compose up -d

# Просмотр логов
docker compose logs -f app
```

## Режимы работы (APP_MODE)

| Режим | Описание | Использование |
|-------|----------|---------------|
| `bot` | Только Telegram бот (polling) | Разработка, scaling бота |
| `monitor` | Только payment monitor worker | Отдельный worker для scaling |
| `both` | Оба режима concurrently (default) | Простой деплой, локальная разработка |

## Сервисы

| Сервис | Порт (хост) | Описание |
|--------|-------------|----------|
| redis | — | Redis для хранения состояний |
| monerod | — | Monero daemon (stagenet) |
| monero-wallet-rpc | — | Wallet RPC |
| app | — | Telegram бот |

## Данные

Используются named volumes:
- `redis_data` — данные Redis
- `monero_data` — блокчейн Monero
- `wallet_files` — файлы кошельков (view-only)

## Stagenet vs Mainnet

По умолчанию конфигурация работает в **stagenet** — тестовой сети Monero.

Для **mainnet** НЕ нужно править базовый `docker-compose.yml` вручную.
Используй override-файл `docker-compose.mainnet.yml`:

```bash
# mainnet (override)
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml up -d --build
```

Что меняется в override:
- убирается `--stagenet`
- порты становятся mainnet: monerod 18080/18081, wallet-rpc 18083

## Тестирование

```bash
# Запуск всех тестов
python -m pytest -q

# С покрытием
python -m pytest --cov=src/xmr_cheque_bot --cov-report=term-missing
```

## Разработка

### Структура проекта

```
xmr-cheque-bot/
├── docker-compose.yml    # Инфраструктура
├── Dockerfile            # Сборка приложения
├── pyproject.toml        # Python зависимости
├── .env.example          # Шаблон переменных окружения
├── src/
│   └── xmr_cheque_bot/
│       ├── __init__.py
│       ├── __main__.py   # Точка входа с APP_MODE
│       ├── bot.py        # Telegram handlers
│       ├── config.py     # Конфигурация (pydantic-settings)
│       ├── monero_rpc.py # RPC клиент для monero-wallet-rpc
│       ├── payment_monitor.py  # Worker для мониторинга платежей
│       ├── storage.py    # Redis storage
│       └── ...
└── tests/                # Тесты
```

### Flow привязки кошелька

1. Пользователь вызывает `/bind`
2. Бот запрашивает адрес и view key
3. При подтверждении:
   - Генерируется `wallet_file_name` (`wallet_{user_id}`)
   - Получается текущая высота блокчейна
   - Вызывается `generate_from_keys` на RPC с `restore_height = current_height - 100`
   - Пароль кошелька генерируется и шифруется
   - Данные сохраняются в Redis

## Безопасность

- **НИКОГДА** не коммитьте `.env` файл
- Файлы кошельков хранятся в named volume `wallet_files`
- View keys шифруются с помощью Fernet (`VIEW_KEY_ENCRYPTION_KEY`)
- Бот использует только view keys — spending ключи не нужны

## Лицензия

MIT
