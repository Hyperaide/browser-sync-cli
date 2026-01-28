#!/usr/bin/env python3
"""
Hyperaide Browser Sync CLI

Syncs your browser authentication to Hyperaide so your AI assistant
can access sites using your logged-in accounts.
"""

import os
import sys
import time
from typing import Optional
from urllib.parse import urlparse

# Handle PyInstaller bundled paths for Playwright
def setup_bundled_playwright():
    """Configure Playwright to work when bundled with PyInstaller."""
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        playwright_driver = os.path.join(bundle_dir, 'playwright', 'driver')
        if os.path.exists(playwright_driver):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = playwright_driver
        browsers_path = os.path.join(bundle_dir, 'playwright', 'driver', 'package', '.local-browsers')
        if os.path.exists(browsers_path):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path

setup_bundled_playwright()

import httpx
import typer
from rich.console import Console
from rich.text import Text
from playwright.sync_api import sync_playwright

app = typer.Typer(
    name="hyperaide-sync",
    help="Sync your browser authentication to Hyperaide",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()

# Configuration
DEFAULT_API_URL = "https://api.hyperaide.com"
DEV_API_URL = "http://localhost:4000"
DEFAULT_WELCOME_URL = "https://app.hyperaide.com/browser-sync/welcome"
DEV_WELCOME_URL = "http://localhost:3000/browser-sync/welcome"

AUTH_COOKIE_PATTERNS = [
    "session", "token", "auth", "jwt", "login", "user", "sid", "csrf",
    "_session", "_token", "_auth", "access", "refresh", "id_token"
]


def dim(text: str) -> str:
    return f"[dim]{text}[/dim]"


def success(text: str) -> str:
    return f"[green]+[/green] {text}"


def error(text: str) -> str:
    return f"[red]x[/red] {text}"


def info(text: str) -> str:
    return f"[blue]>[/blue] {text}"


def warn(text: str) -> str:
    return f"[yellow]![/yellow] {text}"


def spinner(text: str):
    """Simple spinner context manager."""
    from rich.status import Status
    return Status(text, console=console, spinner="dots")


def get_api_url() -> str:
    env_url = os.environ.get("HYPERAIDE_API_URL")
    if env_url:
        return env_url.rstrip("/")
    if os.environ.get("HYPERAIDE_DEV") == "1":
        return DEV_API_URL
    return DEFAULT_API_URL


def get_welcome_url() -> str:
    if os.environ.get("HYPERAIDE_DEV") == "1":
        return DEV_WELCOME_URL
    return DEFAULT_WELCOME_URL


def get_sync_token() -> Optional[str]:
    return os.environ.get("HYPERAIDE_SYNC_TOKEN")


def require_sync_token(token: Optional[str]) -> str:
    if token:
        return token
    env_token = get_sync_token()
    if env_token:
        return env_token
    console.print()
    console.print(error("Missing sync token"))
    console.print(dim("Set HYPERAIDE_SYNC_TOKEN or use --token"))
    console.print()
    sys.exit(1)


def validate_token(token: str) -> dict:
    """Validate sync token and start session."""
    api_url = get_api_url()

    with spinner("Authenticating..."):
        try:
            response = httpx.post(
                f"{api_url}/api/v1/browser_sync/start",
                headers={"x-api-key": token},
                timeout=30,
            )

            if response.status_code == 401:
                console.print()
                console.print(error("Invalid sync token"))
                console.print(dim("Check your token at app.hyperaide.com/browser"))
                console.print()
                sys.exit(1)
            elif response.status_code != 200:
                console.print()
                console.print(error(f"Server error ({response.status_code})"))
                console.print()
                sys.exit(1)

            return response.json()

        except httpx.RequestError as e:
            console.print()
            console.print(error(f"Connection failed: {e}"))
            console.print()
            sys.exit(1)


def is_auth_cookie(cookie: dict) -> bool:
    name = cookie.get("name", "").lower()
    for pattern in AUTH_COOKIE_PATTERNS:
        if pattern in name:
            return True
    if cookie.get("httpOnly", False):
        return True
    return False


def normalize_domain(domain: str) -> str:
    if not domain:
        return ""
    return domain.lstrip(".").replace("www.", "").lower()


def extract_domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return normalize_domain(parsed.netloc)
    except Exception:
        return ""


def run_browser_session() -> tuple[list[dict], list[str]]:
    """Launch browser, let user log in, capture cookies on close."""
    visited_domains: set[str] = set()
    cookies = []

    console.print()
    console.print("  Opening browser...")
    console.print(dim("  Log into sites, then close browser to sync"))
    console.print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        def on_page_created(page):
            def on_navigate(url):
                domain = extract_domain_from_url(url)
                if domain:
                    visited_domains.add(domain)
            page.on("framenavigated", lambda frame: on_navigate(frame.url) if frame == page.main_frame else None)

        context.on("page", on_page_created)

        page = context.new_page()
        welcome_url = get_welcome_url()
        try:
            page.goto(welcome_url, wait_until="domcontentloaded", timeout=10000)
        except Exception:
            page.set_content("""
                <html><body style="font-family: system-ui; padding: 40px; background: #0a0a0a; color: #fafafa;">
                <h1 style="font-weight: 500;">Hyperaide Browser Sync</h1>
                <p style="color: #a1a1aa;">Open new tabs and log into the sites you want to sync.</p>
                <p style="color: #a1a1aa;"><strong>Close the browser when done.</strong></p>
                </body></html>
            """)

        try:
            while True:
                try:
                    if not context.pages:
                        break
                    cookies = context.cookies()
                    time.sleep(0.5)
                except Exception:
                    break
        except KeyboardInterrupt:
            console.print(warn("Cancelled"))

        try:
            browser.close()
        except Exception:
            pass

        auth_cookies = [c for c in cookies if is_auth_cookie(c)]
        return auth_cookies, list(visited_domains)


def complete_sync(token: str, cookies: list[dict], visited_domains: list[str]) -> dict:
    """Send cookies to server."""
    api_url = get_api_url()

    with spinner("Syncing..."):
        try:
            response = httpx.post(
                f"{api_url}/api/v1/browser_sync/complete",
                headers={
                    "x-api-key": token,
                    "Content-Type": "application/json",
                },
                json={
                    "cookies": cookies,
                    "visited_domains": visited_domains,
                },
                timeout=60,
            )

            if response.status_code == 400:
                return {"connected_sites": []}
            elif response.status_code != 200:
                console.print()
                console.print(error(f"Sync failed ({response.status_code})"))
                console.print()
                sys.exit(1)

            return response.json()

        except httpx.RequestError as e:
            console.print()
            console.print(error(f"Sync failed: {e}"))
            console.print()
            sys.exit(1)


def print_header():
    console.print()
    console.print("  [bold]Hyperaide[/bold] Browser Sync")
    console.print()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dev: bool = typer.Option(False, "--dev", help="Use local dev server"),
    token: Optional[str] = typer.Option(
        None, "--token", "-t",
        help="Sync token",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
):
    """Sync your browser authentication to Hyperaide."""
    if dev:
        os.environ["HYPERAIDE_DEV"] = "1"

    if ctx.invoked_subcommand is None:
        sync(token=token)


def sync(token: Optional[str] = None):
    """Main sync flow."""
    print_header()

    token = require_sync_token(token)
    start_result = validate_token(token)

    existing_sites = start_result.get("connected_sites", [])
    if existing_sites:
        console.print(f"  {len(existing_sites)} site(s) already connected")
        for site in existing_sites[:3]:
            console.print(dim(f"    {site.get('display_name', site.get('domain'))}"))
        if len(existing_sites) > 3:
            console.print(dim(f"    ...and {len(existing_sites) - 3} more"))
        console.print()

    cookies, visited_domains = run_browser_session()

    if not cookies:
        console.print(warn("No auth cookies captured"))
        console.print(dim("  Make sure you logged into sites before closing"))
        console.print()
        return

    result = complete_sync(token, cookies, visited_domains)
    connected_sites = result.get("connected_sites", [])

    console.print()
    if connected_sites:
        console.print(success(f"Synced {len(connected_sites)} site(s)"))
        console.print()
        for site in connected_sites:
            console.print(f"    {site.get('display_name', site.get('domain'))}")
    else:
        console.print(warn("No new sites connected"))

    console.print()
    console.print(dim("  Manage at app.hyperaide.com/browser"))
    console.print()


@app.command()
def status(
    token: Optional[str] = typer.Option(
        None, "--token", "-t",
        help="Sync token",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
):
    """Check sync status."""
    print_header()

    token = require_sync_token(token)
    api_url = get_api_url()

    with spinner("Checking..."):
        try:
            response = httpx.get(
                f"{api_url}/api/v1/browser_sync",
                headers={"x-api-key": token},
                timeout=30,
            )

            if response.status_code == 401:
                console.print(error("Invalid sync token"))
                sys.exit(1)
            elif response.status_code != 200:
                console.print(error(f"Failed ({response.status_code})"))
                sys.exit(1)

            data = response.json()

        except httpx.RequestError as e:
            console.print(error(f"Failed: {e}"))
            sys.exit(1)

    connected_sites = data.get("connected_sites", [])
    status_text = data.get("status", "unknown")

    console.print()
    if status_text == "not_synced" or not connected_sites:
        console.print(dim("  No sites connected"))
        console.print(dim("  Run `hyperaide-sync` to sync"))
    else:
        console.print(f"  {len(connected_sites)} connected site(s)")
        console.print()
        for site in connected_sites:
            name = site.get("display_name", site.get("domain"))
            console.print(f"    [green]*[/green] {name}")

    console.print()


@app.command()
def reset(
    token: Optional[str] = typer.Option(
        None, "--token", "-t",
        help="Sync token",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Reset browser sync and disconnect all sites."""
    print_header()

    token = require_sync_token(token)

    if not force:
        confirm = typer.confirm("Disconnect all sites?", default=False)
        if not confirm:
            console.print(dim("  Cancelled"))
            console.print()
            return

    api_url = get_api_url()

    with spinner("Resetting..."):
        try:
            response = httpx.delete(
                f"{api_url}/api/v1/browser_sync",
                headers={"x-api-key": token},
                timeout=30,
            )

            if response.status_code == 401:
                console.print(error("Invalid sync token"))
                sys.exit(1)
            elif response.status_code != 200:
                console.print(error(f"Failed ({response.status_code})"))
                sys.exit(1)

        except httpx.RequestError as e:
            console.print(error(f"Failed: {e}"))
            sys.exit(1)

    console.print()
    console.print(success("Reset complete"))
    console.print(dim("  Run `hyperaide-sync` to sync again"))
    console.print()


if __name__ == "__main__":
    app()
