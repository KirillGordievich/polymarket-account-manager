# Roadmap: Professional CLI Improvements

## Context

`pam` CLI works end-to-end (create → auth → profile → API key → approve → save).
This roadmap covers improvements to make it production-quality.

---

## 1. UX & Output

### 1.1 `--version` flag
- Add `@click.version_option()` to `cli()` group
- Read version from `pyproject.toml` via `importlib.metadata`
- Files: `src/cli.py`

### 1.2 `--json` / `--csv` output for `list` and `check`
- Add `--format` option (`table` default, `json`, `csv`)
- `list --format json` → prints JSON array to stdout (pipeable)
- `check --format json` → prints single JSON object
- Files: `src/cli.py`

### 1.3 `--verbose` / `--quiet` global flags
- Add to `@cli.group()` as `@click.option('--verbose', '-v', count=True)`
- `--quiet` suppresses non-essential output
- `-v` shows network requests, cookie details
- `-vv` shows full request/response bodies
- Thread via `click.Context.obj` dict
- Files: `src/cli.py`, all commands

### 1.4 Progress bars for batch operations
- `create --count N`: `rich.progress.Progress` with task per account
- `deposit-all`: progress bar across accounts
- Files: `src/cli.py`

### 1.5 Shell completion
- Click has built-in support: `_PAM_COMPLETE=bash_source pam`
- Add `pam completion` command that prints the completion script
- Document in README
- Files: `src/cli.py`, `README.md`

### 1.6 `--dry-run` for transaction commands
- Show what would happen without executing transactions
- Print addresses, amounts, estimated gas
- Apply to `deposit`, `withdraw`, `approve` when implemented
- Files: `src/cli.py`

---

## 2. Reliability

### 2.1 Input validation
- Address: 0x prefix, 42 chars, valid checksum (via `Web3.is_checksum_address`)
- Private key: 0x prefix optional, 64 hex chars, derives to valid address
- Amounts: positive, reasonable upper bound warning (>$10k)
- RPC URL: valid URL format, quick connectivity check on first use
- Add `validate_address()`, `validate_private_key()` helpers
- Files: new `src/validation.py`, `src/cli.py` (click callbacks)

### 2.2 Retry with exponential backoff
- Wrap network calls: `@retry(max_attempts=3, backoff=1.5)`
- Apply to: RPC calls (balance, transfer), gamma-api (nonce, login, profiles), relayer
- Distinguish retryable (timeout, 429, 502-504) vs fatal (400, 401, 403)
- Use `tenacity` library or simple custom decorator
- Files: new `src/retry.py`, `src/deposit.py`, `src/auth.py`, `src/profile.py`, `src/approve.py`

### 2.3 Custom exceptions
```python
class PamError(Exception): ...
class NetworkError(PamError): ...      # RPC/API unreachable
class AuthError(PamError): ...         # SIWE/session invalid
class ProfileError(PamError): ...      # Profile creation issues
class TransactionError(PamError): ...  # tx failed/reverted
class ValidationError(PamError): ...   # bad input
```
- CLI catches `PamError` and shows user-friendly message
- Files: new `src/exceptions.py`, all modules

### 2.4 Proxy/VPN support
- `HTTP_PROXY` / `HTTPS_PROXY` env vars (requests already respects these)
- `--proxy` CLI flag for explicit proxy
- Playwright: `proxy={"server": "..."}` in `browser.launch()`
- Document in `.env.example`
- Files: `src/auth.py`, `src/config.py`, `.env.example`

### 2.5 Graceful shutdown & cleanup
- Signal handler (SIGINT/SIGTERM) → close browser, save partial state
- `atexit` handler for browser cleanup
- Context manager for browser lifecycle
- Files: `src/auth.py`, `src/cli.py`

---

## 3. Profile & Username

### 3.1 Custom username via faker
- Add `--faker-username` flag to `pam create` to generate human-like usernames
- Use `faker` library (e.g. `Faker().user_name()`)
- After profile creation, PATCH `gamma-api/profiles` to update display name
- Default: username = deposit wallet address (current behavior)
- Files: `src/profile.py`, `src/cli.py`, `pyproject.toml`

---

## 4. New Commands

### 4.1 `pam import`
```
pam import --key 0xabc...     # import by private key
pam import --file wallet.json # import from JSON
```
- Validate key, derive address, check for duplicates
- Optionally run auth + profile creation
- Files: `src/cli.py`, `src/wallet.py`

### 4.2 `pam export`
```
pam export 0xabc...              # print JSON to stdout
pam export --all --format csv    # export all as CSV
pam export --all --keys          # include private keys (requires --confirm)
```
- Safety: private keys hidden by default
- Files: `src/cli.py`, `src/wallet.py`

### 4.3 `pam delete`
```
pam delete 0xabc...
pam delete --all --confirm
```
- Check balance first, warn if non-zero
- Require `--confirm` flag (no accidental deletion)
- Files: `src/cli.py`, `src/wallet.py`

### 4.4 `pam health`
```
pam health
```
- Check RPC connectivity (eth_chainId)
- Check gamma-api availability (GET /nonce)
- Check relayer (GET /health or similar)
- Check CLOB API
- Color-coded status: green/red per service
- Files: `src/cli.py`, new `src/health.py`

### 4.5 `pam refresh`
```
pam refresh 0xabc...   # re-authenticate, get fresh session
pam refresh --all      # refresh all accounts
```
- Re-run SIWE auth, update session in account JSON
- Useful when sessions expire (7 days TTL)
- Files: `src/cli.py`

### 4.6 `pam deposit` / `pam deposit-all`
```
pam deposit 0xabc... --amount 10 --from-key 0xFUNDING_KEY
pam deposit-all --amount 10 --from-key 0xFUNDING_KEY
```
- Transfer USDC + MATIC (for gas) from a funding wallet to managed accounts
- `FROM_KEY` env var for non-interactive usage
- `--matic` flag to control gas amount (default 0.01)
- Was implemented in v0.1.0 but removed — re-add in next version
- Files: `src/cli.py`, `src/deposit.py`, `.env.example`

### 4.7 `pam withdraw`
```
pam withdraw 0xabc... --to 0xdef... --amount 100
pam withdraw --all --to 0xdef...   # sweep all accounts
```
- Transfer USDC from managed account to external wallet
- Optional: also sweep MATIC
- Files: `src/cli.py`, `src/deposit.py`

---

## 5. Code Quality (Background)

### 5.1 Structured logging
- Replace `console.print` debug output with `logging` module
- `--verbose` maps to `logging.DEBUG`
- Normal mode = `logging.INFO`
- `--quiet` = `logging.WARNING`
- Files: all modules

### 5.2 Type hints everywhere
- Add `py.typed` marker
- Ensure all public functions have full type annotations
- Files: all modules

### 5.3 Tests (when ready)
- `tests/test_validation.py` — address/key validation
- `tests/test_auth.py` — SIWE message construction, JWT encoding
- `tests/test_wallet.py` — JSON/CSV serialization
- `tests/test_profile.py` — mock gamma-api responses
- Use `pytest` + `responses` (mock HTTP) + `pytest-playwright` (optional)
- Files: new `tests/` directory

---

## Priority Order

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 1 | `--version` | High | 5 min |
| 2 | `--json` output | High | 30 min |
| 3 | Input validation | High | 1h |
| 4 | Custom exceptions | High | 1h |
| 5 | Retry logic | High | 1h |
| 6 | `pam health` | Medium | 30 min |
| 7 | `pam import/export/delete` | Medium | 1.5h |
| 8 | `--verbose/--quiet` | Medium | 1h |
| 9 | Progress bars | Medium | 30 min |
| 10 | Shell completion | Medium | 15 min |
| 11 | Proxy support | Medium | 30 min |
| 12 | `pam deposit/deposit-all` | Medium | 30 min |
| 13 | `pam refresh/withdraw` | Medium | 1h |
| 14 | `--dry-run` | Low | 30 min |
| 15 | Graceful shutdown | Low | 30 min |
| 16 | Tests | Low-Med | 3h+ |
