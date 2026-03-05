# M5 QA Fixes — Артефакты

## Что сделано

### 1. Wallet bind flow с RPC `generate_from_keys`

**Изменения:** `src/xmr_cheque_bot/bot.py`

- Добавлен импорт `MoneroWalletRPC`
- Функция `process_view_key` теперь:
  1. Генерирует `wallet_file_name = f"wallet_{user_id}"`
  2. Получает текущую высоту блокчейна через `rpc.get_current_height()`
  3. Вызывает `generate_from_keys` с `restore_height = max(0, current_height - 100)`
  4. Сохраняет `wallet_file_name` в Redis через `storage.bind_wallet()`
  5. Использует случайный пароль (генерируется в `bind_wallet`)

### 2. Entrypoint с `APP_MODE`

**Изменения:** `src/xmr_cheque_bot/__main__.py` (полная перезапись)

- Поддерживаемые режимы: `bot`, `monitor`, `both`
- `bot` mode: запускает aiogram polling через `run_bot()`
- `monitor` mode: запускает `PaymentMonitor.run_forever()` с реальным RedisStorage и RPC
- `both` mode: запускает оба режима concurrently, корректно обрабатывает cancellation
- Использует `asynccontextmanager` для правильного cleanup

### 3. Конфигурация

**Изменения:** `src/xmr_cheque_bot/config.py`

- Добавлен `app_mode: str = "both"` с валидацией
- Добавлен `monitor_interval_sec: int = 30` для настройки интервала монитора

### 4. Документация

**Обновлены:** `.env.example`, `README.md`

- `.env.example` теперь включает `APP_MODE`, `REDIS_URL`, `MONERO_RPC_URL`
- `README.md` содержит точные шаги для запуска в stagenet
- Добавлена таблица режимов работы

## Как проверить

```bash
# 1. Активировать окружение
cd /root/.openclaw/workspace/xmr-cheque-bot
. .venv/bin/activate

# 2. Запустить тесты
python -m pytest -q

# 3. Проверить импорт и конфиг
python -c "from xmr_cheque_bot.config import get_settings; s = get_settings(); print(f'APP_MODE={s.app_mode}')"

# 4. Проверить структуру модулей
python -c "from xmr_cheque_bot.__main__ import run_bot, run_monitor, run_both; print('Entrypoint functions OK')"
```

## Что не сделано / известные ограничения

1. **Daemon height**: используется `get_height` из wallet RPC, а не из monerod. Для stagenet это приемлемо.
2. **Wallet file cleanup**: при удалении данных пользователя (`/settings` → delete) файлы кошельков на диске не удаляются (только записи в Redis).
3. **RPC auth**: в текущей конфигурации `docker-compose.yml` RPC доступен без auth внутри сети Docker.

## Риски / что смотреть в логах

```bash
# При привязке кошелька смотреть:
- "wallet_generated_via_rpc" — успешное создание
- "wallet_rpc_generation_failed" — ошибка RPC
- "wallet_bind_failed" — ошибка сохранения в Redis

# При запуске:
- "xmr_cheque_bot.starting" с mode=bot|monitor|both
- "bot_starting" или "monitor_starting" в зависимости от режима
```

## Артефакты

- Спека: `./shared-dev/specs/M5/` (если применимо)
- Изменения: `git diff HEAD` в репозитории
- Тесты: `pytest -q` (должно быть 106 passed)
