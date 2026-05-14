"""CLI for managing Polymarket accounts."""
from __future__ import annotations

import importlib.metadata
import json
import sys

import click
from py_clob_client_v2.clob_types import ApiCreds
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from src import config
from src.approve import _poll_transaction as poll_transaction
from src.approve import create_deposit_wallet, derive_deposit_wallet, relay_wallet_approve
from src.auth import get_polymarket_session
from src.balance import get_matic_balance, get_usdc_balance
from src.config import RPC_URL
from src.fingerprint import generate_headers
from src.profile import accept_terms, create_profile, get_deposit_addresses, get_profile
from src.proxy import ProxyRotator, load_proxies, proxy_display
from src.register import drop_notifications, get_notifications, register_api_key, verify_account
from src.wallet import generate_wallet, get_account_path, init_batch_csv, list_accounts, save_account

console = Console()


def _save_acc(acc: dict) -> None:
    """Persist updated account dict to its JSON file."""
    path = get_account_path(acc["address"])
    path.write_text(json.dumps(acc, indent=2))


def _fix_account(acc: dict, referral: str) -> dict[str, str]:
    """Attempt to complete all missing steps for a single account.

    Returns a dict mapping step names to results: "fixed" or "failed: <reason>".
    Updates the account JSON file on disk after each successful step.
    """
    addr = acc["address"]
    private_key = acc["private_key"]
    proxy = acc.get("http_proxy", "")
    results: dict[str, str] = {}

    # Reuse stored user_agent if available
    account_headers = generate_headers()
    if acc.get("user_agent"):
        account_headers["user-agent"] = acc["user_agent"]

    # Determine what needs fixing
    needs_wallet = not acc.get("proxy_wallet")
    needs_profile = not acc.get("profile_created")
    needs_username = acc.get("profile_created") and not acc.get("username")
    needs_trading = not acc.get("trading_enabled")
    needs_terms = not acc.get("terms_accepted")
    needs_api = not acc.get("api_key")
    needs_approve = not acc.get("usdc_approved")
    needs_deposit = not acc.get("deposit_address")

    all_needs = [
        needs_wallet, needs_profile, needs_username, needs_trading,
        needs_terms, needs_api, needs_approve, needs_deposit,
    ]
    if not any(all_needs):
        return {}

    # Save referral code if not already stored
    if referral and not acc.get("referral_code"):
        acc["referral_code"] = referral
        _save_acc(acc)

    # Re-authenticate (always fresh session)
    session = ""
    server_profile: dict = {}
    try:
        console.print("  [dim]re-authenticating...[/dim]")
        session = get_polymarket_session(private_key, proxy=proxy, headers=account_headers)
        acc["polymarket_session"] = session
    except Exception as e:
        results["auth"] = f"failed: {e}"
        console.print(f"  [red]Auth failed: {e}[/red]")
        # Without auth, only deposit_address might work (fun.xyz doesn't need session)
        if needs_deposit and acc.get("proxy_wallet"):
            try:
                dep = get_deposit_addresses(addr, acc["proxy_wallet"], proxy=proxy, headers=account_headers)
                deposit_address = dep.get("depositAddr", "")
                if deposit_address:
                    acc["deposit_address"] = deposit_address
                    _save_acc(acc)
                    results["deposit"] = "fixed"
                    console.print(f"  Deposit:  [green]{deposit_address}[/green]")
            except Exception as e2:
                results["deposit"] = f"failed: {e2}"
        return results

    # 1. Deploy wallet
    wallet = acc.get("proxy_wallet", "") or derive_deposit_wallet(addr)
    if needs_wallet:
        try:
            console.print("  [dim]deploying deposit wallet...[/dim]")
            create_resp = create_deposit_wallet(addr, proxy=proxy, session=session, headers=account_headers)
            tx_id = create_resp.get("transactionID", "")
            if tx_id and create_resp.get("state") != "STATE_FAILED":
                state = poll_transaction(tx_id, proxy=proxy, session=session, headers=account_headers)
                if state == "STATE_CONFIRMED":
                    console.print("  Wallet:   [green]deployed[/green]")
                else:
                    console.print(f"  Wallet:   [yellow]{state}[/yellow]")
            else:
                console.print("  Wallet:   [dim]already deployed[/dim]")
            acc["proxy_wallet"] = wallet
            _save_acc(acc)
            results["wallet"] = "fixed"
        except Exception as e:
            results["wallet"] = f"failed: {e}"
            console.print(f"  Wallet:   [red]{e}[/red]")
            acc["proxy_wallet"] = wallet  # still set derived address

    # 2. Create profile
    profile_id = ""
    if needs_profile:
        try:
            console.print("  [dim]creating profile...[/dim]")
            resp = create_profile(session, addr, wallet, referral=referral, proxy=proxy, headers=account_headers)
            acc["profile_created"] = True
            username = resp.get("pseudonym", "") or resp.get("name", "")
            profile_id = resp.get("id", "")
            if not profile_id or not username:
                fetched = get_profile(session, proxy=proxy, headers=account_headers)
                profile_id = profile_id or str(fetched.get("id", ""))
                username = username or fetched.get("pseudonym", "") or fetched.get("name", "")
            acc["username"] = username
            _save_acc(acc)
            results["profile"] = "fixed"
            needs_username = False
            console.print(f"  Profile:  [green]{username}[/green]")
        except Exception as e:
            results["profile"] = f"failed: {e}"
            console.print(f"  Profile:  [red]{e}[/red]")

    # 2b. Fetch username (profile exists but username empty)
    if needs_username:
        try:
            console.print("  [dim]fetching username...[/dim]")
            fetched = get_profile(session, proxy=proxy, headers=account_headers)
            if not fetched:
                # Profile doesn't exist on server — re-create it
                console.print("  [dim]profile not found on server, re-creating...[/dim]")
                resp = create_profile(session, addr, wallet, referral=referral, proxy=proxy, headers=account_headers)
                fetched = resp if resp.get("id") else get_profile(session, proxy=proxy, headers=account_headers)
            username = fetched.get("pseudonym", "") or fetched.get("name", "")
            profile_id = str(fetched.get("id", ""))
            if username:
                acc["username"] = username
                _save_acc(acc)
                results["username"] = "fixed"
                console.print(f"  Username: [green]{username}[/green]")
            else:
                results["username"] = "failed: no pseudonym in profile"
                console.print("  Username: [yellow]no pseudonym in profile[/yellow]")
        except Exception as e:
            results["username"] = f"failed: {e}"
            console.print(f"  Username: [red]{e}[/red]")

    # 3. Register API key (= "Enable Trading" on frontend) — must happen before accept_terms
    if needs_api or needs_trading:
        try:
            console.print("  [dim]registering API key (enable trading)...[/dim]")
            creds = register_api_key(private_key, proxy=proxy, headers=account_headers)
            acc["api_key"] = creds.api_key
            acc["api_secret"] = creds.api_secret
            acc["api_passphrase"] = creds.api_passphrase
            acc["trading_enabled"] = True
            _save_acc(acc)
            results["api_key"] = "fixed"
            if needs_trading:
                results["trading"] = "fixed"
            console.print(f"  API key:  [green]{creds.api_key}[/green]")
            console.print("  Trading:  [green]enabled[/green]")
        except Exception as e:
            results["api_key"] = f"failed: {e}"
            if needs_trading:
                results["trading"] = f"failed: {e}"
            console.print(f"  API key:  [red]{e}[/red]")

    # 4. Approve USDC
    if needs_approve:
        try:
            console.print("  [dim]approving USDC...[/dim]")
            result = relay_wallet_approve(private_key, wallet, proxy=proxy, session=session, headers=account_headers)
            acc["usdc_approved"] = True
            _save_acc(acc)
            results["approve"] = "fixed"
            console.print(f"  Approved: [green]{result.get('transactionID', '?')}[/green]")
        except Exception as e:
            results["approve"] = f"failed: {e}"
            console.print(f"  Approved: [red]{e}[/red]")

    # 5. Accept terms
    if needs_terms:
        try:
            # Fetch profile to get profile_id and check termsAcceptedAt
            if not profile_id:
                server_profile = get_profile(session, proxy=proxy, headers=account_headers)
                if not server_profile:
                    console.print("  [dim]profile not found, re-creating for terms...[/dim]")
                    resp = create_profile(
                        session, addr, wallet, referral=referral,
                        proxy=proxy, headers=account_headers,
                    )
                    server_profile = resp if resp.get("id") else get_profile(
                        session, proxy=proxy, headers=account_headers,
                    )
                if server_profile:
                    profile_id = str(server_profile.get("id", ""))

            if not profile_id:
                results["terms"] = "failed: no profile_id"
                console.print("  Terms:    [yellow]no profile_id[/yellow]")
            else:
                if not server_profile:
                    server_profile = get_profile(session, proxy=proxy, headers=account_headers)
                if server_profile and server_profile.get("termsAcceptedAt"):
                    acc["terms_accepted"] = True
                    _save_acc(acc)
                    results["terms"] = "fixed"
                    console.print("  Terms:    [green]already accepted on server[/green]")
                else:
                    console.print("  [dim]accepting terms...[/dim]")
                    accept_terms(session, profile_id, proxy=proxy, headers=account_headers)
                    acc["terms_accepted"] = True
                    _save_acc(acc)
                    results["terms"] = "fixed"
                    console.print("  Terms:    [green]accepted[/green]")
        except Exception as e:
            results["terms"] = f"failed: {e}"
            console.print(f"  Terms:    [red]{e}[/red]")

    # 6. Deposit address
    if needs_deposit:
        try:
            console.print("  [dim]fetching deposit address...[/dim]")
            dep = get_deposit_addresses(addr, wallet, proxy=proxy, headers=account_headers)
            deposit_address = dep.get("depositAddr", "")
            if deposit_address:
                acc["deposit_address"] = deposit_address
                _save_acc(acc)
                results["deposit"] = "fixed"
                console.print(f"  Deposit:  [green]{deposit_address}[/green]")
            else:
                results["deposit"] = "failed: empty address from fun.xyz"
        except Exception as e:
            results["deposit"] = f"failed: {e}"
            console.print(f"  Deposit:  [red]{e}[/red]")

    return results


@click.group()
@click.version_option(version=importlib.metadata.version("polymarket-account-manager"), prog_name="pam")
def cli() -> None:
    """Polymarket Account Manager."""


@cli.command()
@click.option("--count", default=None, type=int, help="Number of accounts to create")
@click.option("--referral", default=None, envvar="REFERRAL", help="Referral code for profile creation")
@click.option("--skip-approve", is_flag=True, help="Skip USDC approve step")
@click.option("--disable-auto-redeem", is_flag=True, help="Disable auto-redeem for new accounts")
@click.option("--proxy-wallet", default="", help="Deposit wallet address for relayer approve")
@click.option("--proxy-file", default=None, type=click.Path(exists=True), help="File with proxy list (one per line)")
@click.option("-o", "--output", default=None, help="Batch CSV filename (default: timestamp-based)")
@click.option("-y", "--yes", is_flag=True, help="Skip interactive prompts (use defaults)")
def create(
    count: int | None,
    referral: str | None,
    skip_approve: bool,
    disable_auto_redeem: bool,
    proxy_wallet: str,
    proxy_file: str | None,
    output: str | None,
    yes: bool,
) -> None:
    """Create new Polymarket account(s): wallet + profile + API key + optional USDC approve.

    Without arguments: interactive wizard. With --yes or flags: non-interactive.
    """
    interactive = not yes and sys.stdin.isatty() and count is None

    if interactive:
        console.print()
        console.rule("[bold]Polymarket Account Manager[/bold]")
        console.print()

        count = IntPrompt.ask("How many accounts to create?", default=1)

        if referral is None:
            referral = Prompt.ask(
                "Referral code [dim](supports the developer \u2764\ufe0f, press Enter to keep)[/dim]",
                default=config.REFERRAL,
            )

        disable_auto_redeem = not Confirm.ask(
            "Enable auto-redeem for new accounts?",
            default=True,
        )

        proxy_file_input = Prompt.ask(
            "Proxy file path [dim](leave empty for direct connection)[/dim]",
            default="",
        )
        if proxy_file_input:
            proxy_file = proxy_file_input

        # skip_approve stays as-is from CLI default (False)
        console.print()
    else:
        if count is None:
            count = 1

    if referral is None:
        referral = config.REFERRAL

    # ── Batch CSV ──
    batch_csv = init_batch_csv(output or "")
    console.print(f"Batch CSV: [dim]{batch_csv}[/dim]")

    # ── Proxy setup ──
    proxy_rotator = None
    if proxy_file:
        proxies_list = load_proxies(proxy_file)
        proxy_rotator = ProxyRotator(proxies_list)
        console.print(f"Loaded [bold]{len(proxies_list)}[/bold] proxies from {proxy_file}")
        console.print()

    # ── Main loop ──
    for i in range(count):
        prefix = f"[{i + 1}/{count}] " if count > 1 else ""
        account_proxy = proxy_rotator.next() if proxy_rotator else ""
        account_headers = generate_headers()
        account_ua = account_headers.get("user-agent", "")

        # Step 1: Generate wallet
        address, private_key = generate_wallet()
        console.print(f"{prefix}Wallet:   [bold]{address}[/bold]")
        if account_proxy:
            console.print(f"{prefix}Proxy:    [dim]{proxy_display(account_proxy)}[/dim]")
        # Show short fingerprint identifier
        ua_short = account_ua.split("(")[1].split(")")[0] if "(" in account_ua else account_ua[:40]
        console.print(f"{prefix}Browser:  [dim]{ua_short}[/dim]")

        # Step 2: Sign in via SIWE → get polymarketsession cookie
        session = ""
        try:
            console.print(f"{prefix}Session:  signing in...")
            session = get_polymarket_session(
                private_key, log=console.print, proxy=account_proxy, headers=account_headers,
            )
            console.print(f"{prefix}Session:  [green]ok[/green] ({session[:20]}...)")
        except Exception as e:
            console.print(f"{prefix}[red]Sign-in failed: {e}[/red]")
            save_account(address, private_key)
            continue

        # Step 3: Deploy deposit wallet (must happen BEFORE profile creation)
        wallet = proxy_wallet or derive_deposit_wallet(address)
        if not skip_approve:
            try:
                console.print(f"{prefix}Wallet:   deploying deposit wallet...")
                create_resp = create_deposit_wallet(
                    address, proxy=account_proxy, session=session, headers=account_headers,
                )
                tx_id = create_resp.get("transactionID", "")
                if tx_id and create_resp.get("state") != "STATE_FAILED":
                    state = poll_transaction(tx_id, proxy=account_proxy, session=session, headers=account_headers)
                    if state == "STATE_CONFIRMED":
                        console.print(f"{prefix}Wallet:   [green]deposit wallet deployed[/green]")
                    else:
                        console.print(f"{prefix}Wallet:   [yellow]deploy state: {state}[/yellow]")
                else:
                    console.print(f"{prefix}Wallet:   [dim]already deployed[/dim]")
            except Exception as e:
                console.print(f"{prefix}Wallet:   [dim]deploy: {e}[/dim]")

        # Step 4: Create profile
        username = ""
        profile_created = False
        terms_accepted = False
        try:
            resp = create_profile(
                session, address, wallet, referral=referral,
                proxy=account_proxy, headers=account_headers,
            )
            profile_created = True
            username = resp.get("pseudonym", "") or resp.get("name", "")
            profile_id = resp.get("id", "")

            # 422 = profile exists; response may lack id/pseudonym — fetch via GET
            if not profile_id or not username:
                fetched = get_profile(session, proxy=account_proxy, headers=account_headers)
                profile_id = profile_id or str(fetched.get("id", ""))
                username = username or fetched.get("pseudonym", "") or fetched.get("name", "")

            console.print(f"{prefix}Profile:  [green]{username}[/green]")
        except Exception as e:
            console.print(f"{prefix}[yellow]Profile failed: {e}[/yellow]")

        # Step 5: Register on CLOB API (= "Enable Trading" on frontend)
        trading_enabled = False
        try:
            creds = register_api_key(private_key, proxy=account_proxy, headers=account_headers)
            trading_enabled = True
            console.print(f"{prefix}API key:  [green]{creds.api_key}[/green]")
        except Exception as e:
            console.print(f"{prefix}[red]API registration failed: {e}[/red]")
            save_account(
                address, private_key, username=username,
                polymarket_session=session, profile_created=profile_created,
                referral_code=referral,
            )
            continue

        # Step 6: Approve via deposit wallet relayer
        usdc_approved = False
        if not skip_approve:
            try:
                result = relay_wallet_approve(
                    private_key, wallet, proxy=account_proxy,
                    session=session, headers=account_headers,
                )
                usdc_approved = True
                tx_id = result.get("transactionID", "?")
                console.print(f"{prefix}Approved: [green]{tx_id}[/green]")
            except Exception as e:
                console.print(f"{prefix}[yellow]Approve failed: {e}[/yellow]")
                console.print(f"{prefix}[dim]Run 'pam approve-all' to retry later[/dim]")

        # Step 7: Accept Terms of Service
        if profile_created:
            try:
                if profile_id:
                    accept_terms(session, profile_id, proxy=account_proxy, headers=account_headers)
                    terms_accepted = True
                    console.print(f"{prefix}Terms:    [green]accepted[/green]")
                else:
                    console.print(f"{prefix}[yellow]Terms: no profile_id in response[/yellow]")
            except Exception as e:
                console.print(f"{prefix}[yellow]Terms failed: {e}[/yellow]")

        # Step 8: Fetch deposit addresses from fun.xyz
        deposit_address = ""
        try:
            dep = get_deposit_addresses(address, wallet, proxy=account_proxy, headers=account_headers)
            deposit_address = dep.get("depositAddr", "")
            console.print(f"{prefix}Deposit:  [green]{deposit_address}[/green]")
        except Exception as e:
            console.print(f"{prefix}Deposit:  [dim]fun.xyz failed: {e}[/dim]")

        # Step 8: Disable auto-redeem (optional)
        auto_redeem_enabled = True
        if disable_auto_redeem:
            try:
                drop_notifications(private_key, creds)
                auto_redeem_enabled = False
                console.print(f"{prefix}Redeem:   [yellow]auto-redeem disabled[/yellow]")
            except Exception as e:
                console.print(f"{prefix}[yellow]Auto-redeem disable failed: {e}[/yellow]")

        # Save account
        path = save_account(
            address=address,
            private_key=private_key,
            username=username,
            polymarket_session=session,
            profile_created=profile_created,
            trading_enabled=trading_enabled,
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            api_passphrase=creds.api_passphrase,
            proxy_wallet=wallet,
            deposit_address=deposit_address,
            terms_accepted=terms_accepted,
            usdc_approved=usdc_approved,
            auto_redeem_enabled=auto_redeem_enabled,
            referral_code=referral,
            http_proxy=account_proxy,
            user_agent=account_ua,
        )
        console.print(f"{prefix}Saved:    {path}")
        console.print()


@cli.command()
@click.argument("address")
@click.option("--proxy-wallet", default="", help="Deposit wallet address (auto-detected from account)")
def approve(address: str, proxy_wallet: str) -> None:
    """Approve USDC for an existing account via deposit wallet relayer (gasless)."""
    path = get_account_path(address)
    if not path.exists():
        console.print(f"[red]Account not found: {path}[/red]")
        return

    acc = json.loads(path.read_text())
    wallet = proxy_wallet or acc.get("proxy_wallet", "")
    if not wallet or wallet.lower() == address.lower():
        wallet = derive_deposit_wallet(address)
        console.print(f"  Derived proxy wallet: [dim]{wallet}[/dim]")

    account_headers = generate_headers()
    result = relay_wallet_approve(
        acc["private_key"], wallet,
        session=acc.get("polymarket_session", ""), headers=account_headers,
    )
    console.print(f"  tx: [green]{result.get('transactionHash', result.get('transactionID'))}[/green]")

    # Update account file
    acc["proxy_wallet"] = wallet
    acc["usdc_approved"] = True
    path.write_text(json.dumps(acc, indent=2))
    console.print("[green]Account updated[/green]")


@cli.command("approve-all")
def approve_all_cmd() -> None:
    """Retry USDC approve for all accounts that don't have it yet."""
    accounts = list_accounts()
    if not accounts:
        console.print("[yellow]No accounts found[/yellow]")
        return

    pending = [(i, acc) for i, acc in enumerate(accounts, 1) if not acc.get("usdc_approved")]
    if not pending:
        console.print("[green]All accounts are already approved[/green]")
        return

    console.print(f"Found [bold]{len(pending)}[/bold] accounts to approve")
    console.print()

    for i, acc in pending:
        addr = acc["address"]
        short = f"{addr[:10]}...{addr[-4:]}"
        prefix = f"[{i}/{len(accounts)}] {short}"
        session = acc.get("polymarket_session", "")
        wallet = acc.get("proxy_wallet", "")

        # Auto-compute proxy wallet if missing or wrong (= EOA)
        if not wallet or wallet.lower() == addr.lower():
            wallet = derive_deposit_wallet(addr)
            console.print(f"{prefix}: [dim]derived proxy wallet: {wallet[:10]}...[/dim]")

        # Generate unique fingerprint per account
        account_headers = generate_headers()

        # Re-authenticate for fresh session
        try:
            console.print(f"{prefix}: [dim]re-authenticating...[/dim]")
            session = get_polymarket_session(acc["private_key"], headers=account_headers)
        except Exception as e:
            console.print(f"{prefix}: [red]auth failed: {e}[/red]")
            continue

        try:
            result = relay_wallet_approve(acc["private_key"], wallet, session=session, headers=account_headers)
            tx_id = result.get("transactionID", "?")
            console.print(f"{prefix}: [green]{tx_id}[/green]")

            # Update account file
            path = get_account_path(addr)
            acc["proxy_wallet"] = wallet
            acc["usdc_approved"] = True
            path.write_text(json.dumps(acc, indent=2))
        except Exception as e:
            console.print(f"{prefix}: [red]{e}[/red]")


@cli.command()
@click.argument("address")
@click.option("--referral", default=None, envvar="REFERRAL", help="Referral code for profile creation")
def fix(address: str, referral: str | None) -> None:
    """Fix an incomplete account by retrying failed steps."""
    if referral is None:
        referral = config.REFERRAL

    path = get_account_path(address)
    if not path.exists():
        console.print(f"[red]Account not found: {path}[/red]")
        return

    acc = json.loads(path.read_text())
    console.print(f"Fixing [bold]{address}[/bold]")

    results = _fix_account(acc, referral)

    if not results:
        console.print("[green]Account is already complete — nothing to fix[/green]")
        return

    fixed = sum(1 for v in results.values() if v == "fixed")
    failed = sum(1 for v in results.values() if v.startswith("failed"))
    console.print()
    if fixed and not failed:
        console.print(f"[green]All {fixed} step(s) fixed[/green]")
    elif fixed and failed:
        console.print(f"[yellow]{fixed} fixed, {failed} failed[/yellow]")
    else:
        console.print(f"[red]All {failed} step(s) failed[/red]")


@cli.command("fix-all")
@click.option("--referral", default=None, envvar="REFERRAL", help="Referral code for profile creation")
def fix_all(referral: str | None) -> None:
    """Fix all incomplete accounts by retrying their failed steps."""
    if referral is None:
        referral = config.REFERRAL

    accounts = list_accounts()
    if not accounts:
        console.print("[yellow]No accounts found[/yellow]")
        return

    # Find incomplete accounts
    incomplete = []
    for acc in accounts:
        issues = []
        if not acc.get("proxy_wallet"):
            issues.append("wallet")
        if not acc.get("profile_created"):
            issues.append("profile")
        elif not acc.get("username"):
            issues.append("username")
        if not acc.get("trading_enabled"):
            issues.append("trading")
        if not acc.get("terms_accepted"):
            issues.append("terms")
        if not acc.get("api_key"):
            issues.append("api_key")
        if not acc.get("usdc_approved"):
            issues.append("approve")
        if not acc.get("deposit_address"):
            issues.append("deposit")
        if issues:
            incomplete.append((acc, issues))

    if not incomplete:
        console.print("[green]All accounts are complete — nothing to fix[/green]")
        return

    console.print(f"Found [bold]{len(incomplete)}[/bold] incomplete account(s) out of {len(accounts)} total")
    console.print()

    total_fixed = 0
    total_failed = 0

    for i, (acc, issues) in enumerate(incomplete, 1):
        addr = acc["address"]
        console.print(f"[{i}/{len(incomplete)}] [bold]{addr}[/bold] — missing: {', '.join(issues)}")

        results = _fix_account(acc, referral)

        fixed = sum(1 for v in results.values() if v == "fixed")
        failed = sum(1 for v in results.values() if v.startswith("failed"))
        total_fixed += fixed
        total_failed += failed
        console.print()

    console.rule("[bold]Summary[/bold]")
    console.print(f"  Accounts processed: {len(incomplete)}")
    console.print(f"  Steps fixed:        [green]{total_fixed}[/green]")
    if total_failed:
        console.print(f"  Steps failed:       [red]{total_failed}[/red]")
    else:
        console.print("  Steps failed:       [green]0[/green]")


@cli.command("list")
@click.option("--rpc-url", default=RPC_URL, help="Polygon RPC URL")
@click.option("--balances", is_flag=True, help="Fetch on-chain balances (slower)")
def list_cmd(rpc_url: str, balances: bool) -> None:
    """List all saved accounts."""
    accounts = list_accounts()
    if not accounts:
        console.print("[yellow]No accounts found in accounts/[/yellow]")
        return

    table = Table(title=f"Polymarket Accounts ({len(accounts)})")
    table.add_column("#", style="dim")
    table.add_column("Address", style="cyan")
    table.add_column("API Key", style="green")
    table.add_column("Proxy", style="blue")
    table.add_column("Approved", style="yellow")
    table.add_column("Created", style="dim")
    if balances:
        table.add_column("USDC", style="green")
        table.add_column("MATIC", style="blue")

    for i, acc in enumerate(accounts, 1):
        proxy = acc.get("proxy_wallet", "")
        proxy_short = proxy[:8] + "..." + proxy[-4:] if proxy else "-"
        row = [
            str(i),
            acc["address"][:10] + "..." + acc["address"][-4:],
            acc.get("api_key", "")[:12] + "..." if acc.get("api_key") else "-",
            proxy_short,
            "yes" if acc.get("usdc_approved") else "no",
            acc.get("created_at", "")[:10],
        ]
        if balances:
            try:
                usdc = get_usdc_balance(acc["address"], rpc_url)
                matic = get_matic_balance(acc["address"], rpc_url)
                row.extend([f"${usdc:.2f}", f"{matic:.4f}"])
            except Exception:
                row.extend(["err", "err"])
        table.add_row(*row)

    console.print(table)


@cli.command()
@click.argument("address")
@click.option("--rpc-url", default=RPC_URL, help="Polygon RPC URL")
def check(address: str, rpc_url: str) -> None:
    """Check account status and balance."""
    path = get_account_path(address)
    if not path.exists():
        console.print(f"[red]Account file not found: {path}[/red]")
        return

    acc = json.loads(path.read_text())
    usdc = get_usdc_balance(address, rpc_url)
    matic = get_matic_balance(address, rpc_url)

    console.print(f"Address:      [cyan]{address}[/cyan]")
    console.print(f"Username:     [magenta]{acc.get('username') or '-'}[/magenta]")
    console.print(f"Profile:      {'[green]yes[/green]' if acc.get('profile_created') else '[yellow]no[/yellow]'}")
    trading = "[green]enabled[/green]" if acc.get("trading_enabled") else "[yellow]not enabled[/yellow]"
    console.print(f"Trading:      {trading}")
    console.print(f"Proxy Wallet: [blue]{acc.get('proxy_wallet') or '-'}[/blue]")
    console.print(f"Deposit:      [blue]{acc.get('deposit_address') or '-'}[/blue]")
    console.print(f"API Key:      [green]{acc.get('api_key', '-')}[/green]")
    terms = "[green]accepted[/green]" if acc.get("terms_accepted") else "[yellow]not accepted[/yellow]"
    console.print(f"Terms:        {terms}")
    console.print(f"Approved:     {'[green]yes[/green]' if acc.get('usdc_approved') else '[yellow]no[/yellow]'}")
    console.print(f"USDC:         [green]${usdc:.2f}[/green]")
    console.print(f"MATIC:        [blue]{matic:.6f}[/blue]")

    # Verify on Polymarket
    if acc.get("api_key"):
        try:
            creds = ApiCreds(
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                api_passphrase=acc["api_passphrase"],
            )
            result = verify_account(acc["private_key"], creds)
            console.print(f"CLOB:         [green]{result}[/green]")
        except Exception as e:
            console.print(f"CLOB:         [red]{e}[/red]")


def _load_account_creds(address: str) -> tuple[dict, ApiCreds]:
    """Load account JSON and return (acc_dict, ApiCreds). Exits on error."""
    path = get_account_path(address)
    if not path.exists():
        console.print(f"[red]Account not found: {path}[/red]")
        raise SystemExit(1)

    acc = json.loads(path.read_text())
    if not acc.get("api_key"):
        console.print("[red]Account has no API credentials. Run 'pam create' first.[/red]")
        raise SystemExit(1)

    creds = ApiCreds(
        api_key=acc["api_key"],
        api_secret=acc["api_secret"],
        api_passphrase=acc["api_passphrase"],
    )
    return acc, creds


@cli.command("auto-redeem")
@click.argument("address")
@click.option("--enable", "action", flag_value="enable", help="Enable auto-redeem")
@click.option("--disable", "action", flag_value="disable", help="Disable auto-redeem")
@click.option("--status", "action", flag_value="status", default=True, help="Check auto-redeem status (default)")
def auto_redeem(address: str, action: str) -> None:
    """Check, enable, or disable auto-redeem for an account."""
    acc, creds = _load_account_creds(address)

    if action == "status":
        notifications = get_notifications(acc["private_key"], creds)
        if notifications:
            console.print(f"Auto-redeem: [green]enabled[/green] ({len(notifications)} subscription(s))")
            for n in notifications:
                console.print(f"  {json.dumps(n)}")
        else:
            console.print("Auto-redeem: [yellow]disabled[/yellow] (no subscriptions)")

    elif action == "disable":
        result = drop_notifications(acc["private_key"], creds)
        console.print("Auto-redeem: [yellow]disabled[/yellow]")
        if result:
            console.print(f"  Response: {result}")

    elif action == "enable":
        # Check current status first
        notifications = get_notifications(acc["private_key"], creds)
        if notifications:
            console.print("Auto-redeem: [green]already enabled[/green]")
            return
        msg = "Auto-redeem enable requires on-chain approval (setApprovalForAll on CTF contract)."
        console.print(f"[yellow]{msg}[/yellow]")
        console.print("[yellow]This is done automatically when you use 'pam approve' with a proxy wallet.[/yellow]")
        console.print("[dim]Support for direct enable via CLI is coming soon.[/dim]")


@cli.command("auto-redeem-all")
@click.option("--enable", "action", flag_value="enable", help="Enable auto-redeem for all accounts")
@click.option("--disable", "action", flag_value="disable", help="Disable auto-redeem for all accounts")
@click.option("--status", "action", flag_value="status", default=True, help="Check status for all accounts (default)")
def auto_redeem_all(action: str) -> None:
    """Check, enable, or disable auto-redeem for all accounts."""
    accounts = list_accounts()
    if not accounts:
        console.print("[yellow]No accounts found[/yellow]")
        return

    for i, acc in enumerate(accounts, 1):
        addr = acc["address"]
        short = f"{addr[:10]}...{addr[-4:]}"
        prefix = f"[{i}/{len(accounts)}] {short}"

        if not acc.get("api_key"):
            console.print(f"{prefix}: [dim]no API key, skipping[/dim]")
            continue

        creds = ApiCreds(
            api_key=acc["api_key"],
            api_secret=acc["api_secret"],
            api_passphrase=acc["api_passphrase"],
        )

        try:
            if action == "status":
                notifications = get_notifications(acc["private_key"], creds)
                status = "[green]enabled[/green]" if notifications else "[yellow]disabled[/yellow]"
                console.print(f"{prefix}: {status}")
            elif action == "disable":
                drop_notifications(acc["private_key"], creds)
                console.print(f"{prefix}: [yellow]disabled[/yellow]")
            elif action == "enable":
                notifications = get_notifications(acc["private_key"], creds)
                if notifications:
                    console.print(f"{prefix}: [green]already enabled[/green]")
                else:
                    console.print(f"{prefix}: [yellow]requires on-chain approval[/yellow]")
        except Exception as e:
            console.print(f"{prefix}: [red]{e}[/red]")


@cli.command("config")
def show_config() -> None:
    """Show current configuration (loaded from .env and environment)."""
    table = Table(title="Current Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Env var", style="dim")

    rows = [
        # Network
        ("RPC URL",               config.RPC_URL,               "RPC_URL"),
        ("Chain ID",              str(config.CHAIN_ID),          "CHAIN_ID"),
        # Contracts
        ("USDC.e",                config.USDC_E_POLYGON,         "USDC_E_POLYGON"),
        ("CTF Exchange",          config.CTF_EXCHANGE,           "CTF_EXCHANGE"),
        ("Neg Risk CTF Exchange", config.NEG_RISK_CTF_EXCHANGE,  "NEG_RISK_CTF_EXCHANGE"),
        ("Neg Risk Adapter",      config.NEG_RISK_ADAPTER,       "NEG_RISK_ADAPTER"),
        # API endpoints
        ("Polymarket URL",        config.POLYMARKET_URL,         "POLYMARKET_URL"),
        ("Gamma API",             config.GAMMA_API,              "GAMMA_API"),
        ("CLOB host",             config.CLOB_HOST,              "CLOB_HOST"),
        ("Relayer URL",           config.RELAYER_URL,            "RELAYER_URL"),
        # Registration
        ("Referral code",         config.REFERRAL or "[dim](none)[/dim]", "REFERRAL"),
    ]

    for label, value, env_var in rows:
        table.add_row(label, value, env_var)

    console.print(table)


if __name__ == "__main__":
    cli()
