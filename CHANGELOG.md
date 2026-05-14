# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-05-15

### Added

- **Account creation** (`pam create`): full automated flow — wallet generation,
  SIWE authentication, profile creation (ToS + referral), CLOB API key
  registration, gasless USDC approve via relayer.
- **Interactive wizard**: `pam create` without arguments prompts for account
  count and referral code; `--yes` / `-y` flag for non-interactive (scripting).
- **Direct SIWE auth** (`src/auth.py`): headless Python sign-in to Polymarket
  — builds EIP-4361 message, signs with EIP-191, sends JWT to gamma-api.
  No browser or Playwright needed.
- **Dynamic browser fingerprinting** (`src/fingerprint.py`): each account gets
  a unique set of browser headers via `browserforge` (desktop Chrome only).
  Fingerprint is reused across all API calls within a single account lifecycle.
- **Gasless USDC approve** (`src/approve.py`): EIP-712 signed batch of 12
  approval calls submitted to Polymarket relayer — CTF Exchange,
  Neg Risk CTF Exchange, Neg Risk Adapter, and USDC spender.
- **Account listing** (`pam list`): table view with optional on-chain balance
  fetching (`--balances`).
- **Account check** (`pam check <address>`): detailed status with USDC/MATIC
  balances and CLOB API verification.
- **Auto-redeem** (`pam auto-redeem`, `pam auto-redeem-all`): check, enable,
  or disable auto-redeem via CLOB API.
- **Configuration** (`pam config`): display current settings from `.env`.
- **Centralized config** (`src/config.py`): all settings and contract addresses
  in one place with sensible Polygon mainnet defaults, overridable via `.env`.
- **Account storage**: JSON files per account + CSV export in `accounts/`.
