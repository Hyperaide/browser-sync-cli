"""
Hyperaide Browser Auth Sync CLI

Syncs your local browser authentication state to Hyperaide so the AI agent
can perform browser automation tasks using your logged-in accounts.

Usage:
    python main.py
    # or after installation:
    hyperaide-sync
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
        # Running as compiled binary
        bundle_dir = sys._MEIPASS
        
        # Set Playwright driver path for bundled binary
        playwright_driver = os.path.join(bundle_dir, 'playwright', 'driver')
        if os.path.exists(playwright_driver):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = playwright_driver
            
        # Also check for browsers in the bundle
        browsers_path = os.path.join(bundle_dir, 'playwright', 'driver', 'package', '.local-browsers')
        if os.path.exists(browsers_path):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path

setup_bundled_playwright()

import httpx
import typer
import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.theme import Theme
from rich import box
from playwright.sync_api import sync_playwright

# Modern "Vercel-like" Theme
THEME = Theme({
    "info": "white",
    "warning": "yellow",
    "danger": "red",
    "success": "green",
    "muted": "dim white",
    "accent": "bold cyan",
    "logo": "bold blue",
})

# Initialize Typer app and Rich console
app = typer.Typer(
    name="hyperaide-sync",
    help="Sync your browser authentication to Hyperaide",
    add_completion=False,
    invoke_without_command=True,  # Allow running without subcommand
)
console = Console(theme=THEME)

# Global dev flag (set via callback)
_dev_mode = False


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    dev: bool = typer.Option(
        False,
        "--dev",
        help="Use development API server (localhost:3000)",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token", "-t",
        help="Hyperaide sync token (or set HYPERAIDE_SYNC_TOKEN env var)",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
):
    """
    Hyperaide Browser Auth Sync - sync your browser authentication.
    """
    global _dev_mode
    _dev_mode = dev
    
    if dev:
        os.environ["HYPERAIDE_DEV"] = "1"
    
    # If no subcommand, run the sync (main) command
    if ctx.invoked_subcommand is None:
        sync_browser_auth(token=token)


@app.command(name="sync")
def sync_command(
    token: Optional[str] = typer.Option(
        None,
        "--token", "-t",
        help="Hyperaide sync token (or set HYPERAIDE_SYNC_TOKEN env var)",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
):
    """
    Sync your browser authentication to Hyperaide.
    """
    sync_browser_auth(token=token)

# Configuration
DEFAULT_API_URL = "https://api.hyperaide.com"
DEV_API_URL = "http://localhost:4000"
DEFAULT_WELCOME_URL = "https://app.hyperaide.com/browser-sync/welcome"
DEV_WELCOME_URL = "http://localhost:3000/browser-sync/welcome"

# Auth-related cookie name patterns
AUTH_COOKIE_PATTERNS = [
    "session", "token", "auth", "jwt", "login", "user", "sid", "csrf",
    "_session", "_token", "_auth", "access", "refresh", "id_token"
]


def get_api_url() -> str:
    """Get API URL from environment or use default."""
    env_url = os.environ.get("HYPERAIDE_API_URL")
    if env_url:
        return env_url.rstrip("/")
    
    # Check if running in development mode
    if os.environ.get("HYPERAIDE_DEV") == "1":
        return DEV_API_URL
    
    return DEFAULT_API_URL


def get_welcome_url() -> str:
    """Get the welcome page URL for the browser sync."""
    if os.environ.get("HYPERAIDE_DEV") == "1":
        return DEV_WELCOME_URL
    return DEFAULT_WELCOME_URL


def get_token() -> Optional[str]:
    """Get sync token from environment variable."""
    return os.environ.get("HYPERAIDE_SYNC_TOKEN")


def require_token(token: Optional[str]) -> str:
    """Require sync token from argument or environment, exit if missing."""
    if token:
        return token
    
    env_token = get_token()
    if env_token:
        return env_token
    
    console.print("[danger]✖ Missing sync token[/danger]")
    console.print("[muted]  Usage: HYPERAIDE_SYNC_TOKEN=your_token hyperaide-sync[/muted]")
    sys.exit(1)


# --- UI Helpers ---

from rich.text import Text

def print_logo():
    """Print the ASCII logo with a gradient."""
    f = pyfiglet.Figlet(font='ansi_shadow')
    ascii_art = f.renderText('Hyperaide')
    
    # Create a simple vertical gradient (blue to cyan)
    text = Text(ascii_art)
    
    # Simple logic: Split lines and color them progressively
    # Rich doesn't have a built-in "gradient" for a single block of text easily,
    # so we'll just style it with a nice consistent cyan/blue look for now.
    # To do a true gradient requires iteration character by character which is complex for ASCII art.
    # Instead, we'll use a bold style that looks great on dark terminals.
    
    # White to Gray gradient
    # Top is bright white, fading down to gray
    lines = ascii_art.splitlines()
    # Hex codes: White -> Light Gray -> Darker Gray
    colors = ["#FFFFFF", "#EEEEEE", "#DDDDDD", "#BBBBBB", "#999999", "#777777"]
    
    for i, line in enumerate(lines):
        color = colors[min(i, len(colors)-1)]
        console.print(line, style=f"bold {color}")

    console.print("  Browser Auth Sync CLI\n", style="muted")

def print_step(message: str, emoji: str = "•") -> None:
    """Clean, minimal step output."""
    console.print(f"[accent]{emoji}[/accent]  {message}")

def print_subtle(message: str, padding: int = 4) -> None:
    """Dimmed instructional text."""
    pad = " " * padding
    console.print(f"{pad}[muted]{message}[/muted]")

def print_success(message: str) -> None:
    console.print(f"[success]✔[/success]  {message}")

def print_error(message: str) -> None:
    console.print(f"[danger]✖  {message}[/danger]")

def print_header(title: str) -> None:
    console.print(f"\n[bold white]{title}[/bold white]")

def build_sites_table(
    sites: list[dict],
    title: Optional[str] = None,
    include_status: bool = False,
) -> Table:
    table = Table(
        box=box.SIMPLE, 
        show_header=True, 
        header_style="bold muted",
        pad_edge=False,
        collapse_padding=True
    )
    
    table.add_column("Site")
    table.add_column("Domain", style="muted")
    if include_status:
        table.add_column("Status", style="success")
        
    for site in sites:
        row = [
            site.get("display_name", site.get("domain")),
            site.get("domain"),
        ]
        if include_status:
            row.append(site.get("status", "active"))
        table.add_row(*row)
        
    return table

# --- Logic ---

def validate_token(token: str) -> dict:
    """Validate sync token with the server and start sync session."""
    api_url = get_api_url()
    
    with console.status("[bold]Connecting to Hyperaide...[/bold]", spinner="dots"):
        try:
            response = httpx.post(
                f"{api_url}/api/v1/browser_sync/start",
                headers={"x-api-key": token},  # Server still expects x-api-key header
                timeout=30,
            )
            
            if response.status_code == 401:
                print_error("Invalid sync token")
                sys.exit(1)
            elif response.status_code != 200:
                print_error(f"Server error: {response.status_code}")
                print_subtle(response.text)
                sys.exit(1)
            
            return response.json()
            
        except httpx.RequestError as e:
            print_error(f"Failed to connect: {e}")
            sys.exit(1)


def is_auth_cookie(cookie: dict) -> bool:
    """Check if a cookie appears to be auth-related."""
    name = cookie.get("name", "").lower()
    
    # Check for auth-related patterns in name
    for pattern in AUTH_COOKIE_PATTERNS:
        if pattern in name:
            return True
    
    # httpOnly cookies are typically server-set session cookies
    if cookie.get("httpOnly", False):
        return True
    
    return False


def normalize_domain(domain: str) -> str:
    """Normalize a domain by removing leading dots and www."""
    if not domain:
        return ""
    return domain.lstrip(".").replace("www.", "").lower()


def extract_domain_from_url(url: str) -> str:
    """Extract normalized domain from URL."""
    try:
        parsed = urlparse(url)
        return normalize_domain(parsed.netloc)
    except Exception:
        return ""


def run_browser_session() -> tuple[list[dict], list[str]]:
    """
    Launch browser, let user log in, and capture cookies on close.
    """
    visited_domains: set[str] = set()
    cookies = []

    print_step("Opening secure browser window...", emoji="🔒")
    print_subtle("Log in to your sites. Close the browser when done.")
    
    # Small pause for UX
    time.sleep(1)
    
    with sync_playwright() as p:
        # Launch browser with persistent context for cookie storage
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",  # Use system Chrome instead of bundled Chromium
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
        
        # Track page navigations
        def on_page_created(page):
            def on_navigate(url):
                domain = extract_domain_from_url(url)
                if domain:
                    visited_domains.add(domain)
            
            page.on("framenavigated", lambda frame: on_navigate(frame.url) if frame == page.main_frame else None)
        
        context.on("page", on_page_created)
        
        # Navigate to the welcome page
        page = context.new_page()
        welcome_url = get_welcome_url()
        try:
            page.goto(welcome_url, wait_until="domcontentloaded", timeout=10000)
        except Exception as e:
            # If welcome page fails, show a simple message
            print_subtle("Could not load welcome page, continuing anyway...")
            page.set_content("""
                <html><body style="font-family: system-ui; padding: 40px; background: #1a1a2e; color: white;">
                <h1>Hyperaide Browser Sync</h1>
                <p>Open new tabs and log into the sites you want Hyperaide to access.</p>
                <p><strong>Close the browser when you're done to sync your authentication.</strong></p>
                </body></html>
            """)

        # Wait for browser to be closed by user
        with console.status("[bold]Waiting for browser session...[/bold]", spinner="dots"):
            try:
                while True:
                    try:
                        # User manually closed the window
                        if not context.pages:
                            break

                        # Keep capturing cookies while valid
                        cookies = context.cookies()
                        time.sleep(0.5)
                    except Exception:
                        # Browser process killed/crashed
                        break
            except KeyboardInterrupt:
                console.print()
                print_error("Sync cancelled")
                return [], []
        
        # Explicitly close browser
        try:
            browser.close()
        except Exception:
            pass
        
        # Filter to auth-relevant cookies
        auth_cookies = [c for c in cookies if is_auth_cookie(c)]
        
        return auth_cookies, list(visited_domains)


def complete_sync(token: str, cookies: list[dict], visited_domains: list[str]) -> dict:
    """Send cookies to server to complete sync."""
    api_url = get_api_url()
    
    with console.status("[bold]Encrypting and uploading...[/bold]", spinner="dots"):
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
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error", "No cookies provided")
                print_error(f"Sync skipped: {error_msg}")
                return {"connected_sites": []}
            elif response.status_code != 200:
                print_error(f"Failed to complete sync: {response.status_code}")
                print_subtle(response.text)
                sys.exit(1)
            
            return response.json()
            
        except httpx.RequestError as e:
            print_error(f"Failed to complete sync: {e}")
            sys.exit(1)


def display_results(result: dict):
    """Display sync results to user."""
    connected_sites = result.get("connected_sites", [])
    
    if not connected_sites:
        print_error("No authenticated sites detected")
        print_subtle("Did you log in before closing the browser?")
        return
    
    print_success(f"Successfully synced {len(connected_sites)} site(s)")
    
    console.print()
    console.print(build_sites_table(connected_sites))


def sync_browser_auth(token: Optional[str] = None):
    """
    Main sync function - opens browser, captures cookies, syncs to Hyperaide.
    """
    console.clear()
    print_logo()
    
    # Require sync token
    token = require_token(token)
    
    # Validate token and start sync session
    start_result = validate_token(token)
    
    # Check if user has existing context
    if start_result.get("existing"):
        existing_sites = start_result.get("connected_sites", [])
        
        if existing_sites:
            print_step(f"Found {len(existing_sites)} previously connected site(s)")
            # console.print(build_sites_table(existing_sites))
            console.print()
    
    # Run browser session
    cookies, visited_domains = run_browser_session()
    
    # Display captured sites (debug/feedback)
    if visited_domains:
        print_step(f"Captured session data from {len(visited_domains)} domain(s)")
    else:
        print_step("No domains visited")
    
    # Check if we have any cookies before syncing
    if not cookies:
        print_error("No authentication cookies captured")
        return
    
    # Complete sync
    result = complete_sync(token, cookies, visited_domains)
    
    # Display results
    console.print()
    display_results(result)
    
    console.print()
    print_subtle("Manage connected sites at https://app.hyperaide.com/browser-connections", padding=2)
    console.print()


@app.command()
def reset(
    token: Optional[str] = typer.Option(
        None,
        "--token", "-t",
        help="Hyperaide sync token",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Skip confirmation prompt",
    ),
):
    """
    Reset your browser sync and disconnect all sites.
    """
    print_logo()
    
    # Require sync token
    token = require_token(token)
    
    # Confirm reset
    if not force:
        confirm = typer.confirm(
            "This will disconnect all synced sites. Are you sure?",
            default=False,
        )
        if not confirm:
            print_subtle("Reset cancelled")
            return
    
    api_url = get_api_url()
    
    with console.status("[bold]Resetting browser sync...[/bold]", spinner="dots"):
        try:
            response = httpx.delete(
                f"{api_url}/api/v1/browser_sync",
                headers={"x-api-key": token},
                timeout=30,
            )
            
            if response.status_code == 401:
                print_error("Invalid sync token")
                sys.exit(1)
            elif response.status_code != 200:
                print_error(f"Failed to reset: {response.status_code}")
                sys.exit(1)
            
            print_success("Browser sync has been reset")
            print_subtle("Run hyperaide-sync to start a new session")
            
        except httpx.RequestError as e:
            print_error(f"Failed to reset: {e}")
            sys.exit(1)


@app.command()
def status(
    token: Optional[str] = typer.Option(
        None,
        "--token", "-t",
        help="Hyperaide sync token",
        envvar="HYPERAIDE_SYNC_TOKEN",
    ),
):
    """
    Check your current browser sync status.
    """
    print_logo()
    
    # Require sync token
    token = require_token(token)
    
    api_url = get_api_url()
    
    with console.status("[bold]Fetching status...[/bold]", spinner="dots"):
        try:
            response = httpx.get(
                f"{api_url}/api/v1/browser_sync",
                headers={"x-api-key": token},
                timeout=30,
            )
            
            if response.status_code == 401:
                print_error("Invalid sync token")
                sys.exit(1)
            elif response.status_code != 200:
                print_error(f"Failed to get status: {response.status_code}")
                sys.exit(1)
            
            data = response.json()
            connected_sites = data.get("connected_sites", [])
            status_text = data.get("status", "unknown")
            last_synced = data.get("last_synced_at")
            
            if status_text == "not_synced":
                print_step("No browser sync configured", emoji="○")
                print_subtle("Run hyperaide-sync to sync your browser authentication")
                return
            
            # Show connected sites
            if connected_sites:
                console.print(
                    build_sites_table(
                        connected_sites,
                        include_status=True,
                    )
                )
                
                if last_synced:
                    console.print(f"\n[muted]Last synced: {last_synced}[/muted]")
            else:
                print_step("Browser sync is active but no sites are connected", emoji="⚠")
                
        except httpx.RequestError as e:
            print_error(f"Failed to get status: {e}")
            sys.exit(1)


if __name__ == "__main__":
    app()
