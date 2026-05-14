🇷🇺 [Русская версия](README.ru.md)

# Polymarket Account Manager

CLI tool for creating and managing Polymarket trading accounts.

Full registration cycle from scratch: wallet generation → SIWE auth → profile creation → CLOB API keys → USDC approve.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
git clone https://github.com/KirillGordievich/polymarket-account-manager.git
cd polymarket-account-manager
```

### Option 1 — Local project install (recommended for development)

```bash
make install
uv run pam --help  # no venv activation needed
```

Or activate the venv once per terminal session — then `pam` is available directly:

```bash
source .venv/bin/activate
pam --help
```

> `source` cannot be automated via `make` — it modifies the current shell's environment, while make runs each command in a separate subshell.

### Option 2 — Global install (`pam` available everywhere without venv)

```bash
make install-global
pam --help
```

Update after changes:

```bash
make update
```

<details>
<summary>Without make</summary>

```bash
# local
uv sync

# global
uv tool install .
```

</details>

## Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# Referral code (applied to all new accounts)
REFERRAL=SupportMeCode

# Polygon RPC
RPC_URL=https://polygon-rpc.com
```

## Commands

### Create account(s)

```bash
# Single account (using settings from .env)
pam create

# Multiple accounts
pam create --count 5

# With referral code
pam create --referral SupportMeCode

# Skip the approve step
pam create --skip-approve

# Non-interactive mode (use defaults, no prompts)
pam create -y
```

Without any arguments, `pam create` launches an **interactive wizard** that prompts for the number of accounts and referral code. Pass `--yes` / `-y` or any flag to switch to non-interactive mode.

**What happens during `create`:**
1. Ethereum wallet generation
2. Sign-in to Polymarket via direct SIWE auth (EIP-4361)
3. Profile creation — username (faker) + ToS + referral
4. CLOB API key registration
5. USDC approve via relayer (if `--proxy-wallet` is provided)
6. Saved to `accounts/<address>.json` and `accounts/accounts.csv`

### List accounts

```bash
# List all accounts
pam list

# With balances (slower — queries Polygon)
pam list --balances
```

### Check a single account

```bash
pam check 0xYOUR_ADDRESS
```

### Approve USDC (for an existing account)

```bash
pam approve 0xYOUR_ADDRESS --proxy-wallet 0xPROXY_WALLET
```

### Auto-redeem

```bash
# Check auto-redeem status for a single account
pam auto-redeem 0xYOUR_ADDRESS

# Enable / disable
pam auto-redeem 0xYOUR_ADDRESS --enable
pam auto-redeem 0xYOUR_ADDRESS --disable

# All accounts at once
pam auto-redeem-all
pam auto-redeem-all --enable
pam auto-redeem-all --disable
```

### Configuration

```bash
# Show current configuration
pam config

# Version
pam --version
```

## Account structure

Each account is saved to `accounts/<address>.json`:

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

## Project structure

```
src/
  config.py    # All settings (loaded from .env)
  auth.py      # Direct SIWE authentication (EIP-4361)
  profile.py   # POST /profiles (Polymarket profile creation)
  register.py  # CLOB API keys
  approve.py   # Gasless USDC approve via relayer
  balance.py   # On-chain balance queries (USDC, MATIC)
  wallet.py    # Wallet generation and JSON/CSV storage
  cli.py       # CLI commands
  web3/
    abi.py     # Contract ABIs (ERC-20, Gnosis Safe)
accounts/      # JSON accounts + accounts.csv (gitignored)
.env.example   # Configuration template
```

---

## Support

By default, the developer's referral code is used during registration — this is a free way to support the project. To disable it, add to `.env`:

```dotenv
REFERRAL=
```

If this tool was useful to you, any donation in any token is greatly appreciated:

| Network | Address |
|---|---|
| ETH / any L2 | `0x25669AAa8ddE7C6f5aaB35D1170990aC6e0a3fbD` |
| TRON | `TN2worB8odf92grx3JvXYCBR3tzymYpKmF` |
| SOL | `CR5A3zyr5NFkmTbJjbgUY6dWKnrqLWkvLX2jRpwiNqxc` |
| BTC | `bc1qp4knew4wdqpp8446dqeckw4yrkcu0peq3hn7sh` |
