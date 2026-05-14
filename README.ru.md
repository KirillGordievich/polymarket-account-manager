🇬🇧 [English version](README.md)

# Polymarket Account Manager

CLI для создания и управления торговыми аккаунтами Polymarket.

Полный цикл регистрации с нуля: генерация кошелька → SIWE авторизация → создание профиля → CLOB API ключи → approve USDC.

## Требования

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Установка

```bash
git clone <repo>
cd polymarket-account-manager
```

### Вариант 1 — локально в проекте (рекомендуется для разработки)

```bash
make install
uv run pam --help  # без активации venv
```

Или активируй venv один раз в сессии терминала — тогда `pam` доступен напрямую:

```bash
source .venv/bin/activate
pam --help
```

> `source` нельзя автоматизировать через `make` — он меняет окружение текущего шелла, а make запускает каждую команду в отдельном subshell.

### Вариант 2 — глобальная установка (`pam` доступен везде без venv)

```bash
make install-global
pam --help
```

Обновить после изменений:

```bash
make update
```

<details>
<summary>Без make</summary>

```bash
# локально
uv sync

# глобально
uv tool install .
```

</details>

## Настройка

```bash
cp .env.example .env
```

Отредактируй `.env`:

```dotenv
# Реферальный код (применяется ко всем новым аккаунтам)
REFERRAL=SupportMeCode

# Polygon RPC
RPC_URL=https://polygon-rpc.com
```

## Команды

### Создать аккаунт(ы)

```bash
# Один аккаунт (с настройками из .env)
pam create

# Несколько аккаунтов
pam create --count 5

# С реферальным кодом
pam create --referral SupportMeCode

# Пропустить шаг approve
pam create --skip-approve
```

**Что происходит при `create`:**
1. Генерация Ethereum-кошелька
2. Авторизация на Polymarket через SIWE (EIP-4361)
3. Создание профиля — username (faker) + ToS + реферал
4. Регистрация CLOB API ключей
5. Approve USDC через relayer (если указан `--proxy-wallet`)
6. Сохранение в `accounts/<address>.json` и `accounts/accounts.csv`

### Просмотр аккаунтов

```bash
# Список всех аккаунтов
pam list

# С балансами (медленнее — запросы к Polygon)
pam list --balances
```

### Проверка одного аккаунта

```bash
pam check 0xYOUR_ADDRESS
```

### Approve USDC (для существующего аккаунта)

```bash
pam approve 0xYOUR_ADDRESS --proxy-wallet 0xPROXY_WALLET
```

### Auto-redeem

```bash
# Статус auto-redeem для одного аккаунта
pam auto-redeem 0xYOUR_ADDRESS

# Включить / выключить
pam auto-redeem 0xYOUR_ADDRESS --enable
pam auto-redeem 0xYOUR_ADDRESS --disable

# Все аккаунты сразу
pam auto-redeem-all
pam auto-redeem-all --enable
pam auto-redeem-all --disable
```

### Конфигурация

```bash
# Показать текущие настройки
pam config

# Версия
pam --version
```

## Структура аккаунта

Каждый аккаунт сохраняется в `accounts/<address>.json`:

```json
{
  "address": "0x...",
  "private_key": "0x...",
  "username": "john_doe89",
  "polymarket_session": "eyJ...",
  "profile_created": true,
  "api_key": "...",
  "api_secret": "...",
  "api_passphrase": "...",
  "proxy_wallet": "",
  "created_at": "2026-05-14T12:00:00+00:00",
  "usdc_approved": false
}
```

## Файлы

```
src/
  config.py    # Все настройки (читаются из .env)
  auth.py      # SIWE авторизация (EIP-4361)
  profile.py   # POST /profiles (создание профиля Polymarket)
  register.py  # CLOB API ключи
  approve.py   # Gasless USDC approve через relayer
  balance.py   # Запрос балансов (USDC, MATIC)
  wallet.py    # Генерация кошельков и хранение JSON/CSV
  cli.py       # CLI команды
  web3/
    abi.py     # ABI контрактов (ERC-20, Gnosis Safe)
accounts/      # JSON аккаунты + accounts.csv (gitignored)
.env.example   # Шаблон конфигурации
```

---

## Поддержка

По умолчанию при регистрации используется реферальный код разработчика — это бесплатный способ поддержать проект. Если хочешь отключить — добавь в `.env`:

```dotenv
REFERRAL=
```

Если инструмент оказался полезным, буду рад любому донату в любых токенах:

| Сеть | Адрес |
|---|---|
| ETH / любой L2 | `0x25669AAa8ddE7C6f5aaB35D1170990aC6e0a3fbD` |
| TRON | `TN2worB8odf92grx3JvXYCBR3tzymYpKmF` |
| SOL | `CR5A3zyr5NFkmTbJjbgUY6dWKnrqLWkvLX2jRpwiNqxc` |
| BTC | `bc1qp4knew4wdqpp8446dqeckw4yrkcu0peq3hn7sh` |
