#!/usr/bin/env python3
"""
HyperAide Browser Auth Sync CLI

Syncs your local browser authentication state to HyperAide so the AI agent
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
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from playwright.sync_api import sync_playwright

# Initialize Typer app and Rich console
app = typer.Typer(
    name="hyperaide-sync",
    help="Sync your browser authentication to HyperAide",
    add_completion=False,
    invoke_without_command=True,  # Allow running without subcommand
)
console = Console()

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
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="HyperAide API key (or set HYPERAIDE_API_KEY env var)",
        envvar="HYPERAIDE_API_KEY",
    ),
):
    """
    HyperAide Browser Auth Sync - sync your browser authentication.
    """
    global _dev_mode
    _dev_mode = dev
    
    if dev:
        os.environ["HYPERAIDE_DEV"] = "1"
    
    # If no subcommand, run the sync (main) command
    if ctx.invoked_subcommand is None:
        sync_browser_auth(api_key=api_key)


@app.command(name="sync")
def sync_command(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="HyperAide API key (or set HYPERAIDE_API_KEY env var)",
        envvar="HYPERAIDE_API_KEY",
    ),
):
    """
    Sync your browser authentication to HyperAide.
    """
    sync_browser_auth(api_key=api_key)

# Configuration
DEFAULT_API_URL = "https://api.hyperaide.com"
DEV_API_URL = "http://localhost:4000"
DEFAULT_WELCOME_URL = "https://hyperaide.com/browser-sync/welcome"
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


def get_api_key() -> Optional[str]:
    """Get API key from environment variable."""
    return os.environ.get("HYPERAIDE_API_KEY")


def require_api_key(api_key: Optional[str]) -> str:
    """Require API key from argument or environment, exit if missing."""
    if api_key:
        return api_key
    
    env_key = get_api_key()
    if env_key:
        return env_key
    
    console.print("[red]Error: HYPERAIDE_API_KEY environment variable is required.[/red]")
    console.print("[dim]Usage: HYPERAIDE_API_KEY=your_key hyperaide-sync[/dim]")
    sys.exit(1)


def validate_api_key(api_key: str) -> dict:
    """Validate API key with the server and start sync session."""
    api_url = get_api_url()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Validating API key...", total=None)
        
        try:
            response = httpx.post(
                f"{api_url}/api/v1/browser_sync/start",
                headers={"x-api-key": api_key},
                timeout=30,
            )
            
            if response.status_code == 401:
                console.print("[red]Invalid API key. Please check and try again.[/red]")
                sys.exit(1)
            elif response.status_code != 200:
                console.print(f"[red]Server error: {response.status_code}[/red]")
                console.print(f"[dim]{response.text}[/dim]")
                sys.exit(1)
            
            return response.json()
            
        except httpx.RequestError as e:
            console.print(f"[red]Failed to connect to HyperAide API: {e}[/red]")
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
    
    Returns:
        Tuple of (cookies, visited_domains)
    """
    visited_domains: set[str] = set()
    cookies = []
    
    # Track if the user clicked the sync button in the browser
    sync_requested = False
    
    def on_sync_request():
        nonlocal sync_requested
        sync_requested = True

    console.print()
    console.print(Panel(
        "[bold green]Opening browser...[/bold green]\n\n"
        "Log into the sites you want HyperAide to access.\n"
        "Click the [bold]Close & Sync[/bold] button in the browser when done.",
        title="Browser Session",
    ))
    
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
        
        # 1. Allow the browser to signal "Sync" to Python
        context.expose_function("hyperaideCompleteSync", lambda: on_sync_request())
        
        # 2. Inject the floating button into every page
        context.add_init_script("""
            window.addEventListener('DOMContentLoaded', () => {
                // Only add button to the top-level frame (not iframes)
                if (window.self === window.top) {
                    const btn = document.createElement('div');
                    btn.innerHTML = 'Close & Sync';
                    Object.assign(btn.style, {
                        position: 'fixed',
                        bottom: '20px',
                        right: '20px',
                        zIndex: '2147483647', // Max z-index
                        padding: '12px 24px',
                        backgroundColor: '#111',
                        color: 'white',
                        border: '1px solid #333',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                        fontSize: '14px',
                        fontWeight: '600',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                        transition: 'transform 0.2s ease, opacity 0.2s ease',
                        userSelect: 'none'
                    });
                    
                    btn.onmouseover = () => btn.style.transform = 'translateY(-2px)';
                    btn.onmouseout = () => btn.style.transform = 'translateY(0)';
                    
                    btn.onclick = () => {
                        btn.innerHTML = 'Syncing...';
                        btn.style.opacity = '0.8';
                        btn.style.pointerEvents = 'none';
                        window.hyperaideCompleteSync();
                    };
                    
                    document.body.appendChild(btn);
                }
            });
        """)
        
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
            console.print(f"[dim]Could not load welcome page, continuing anyway...[/dim]")
            page.set_content("""
                <html><body style="font-family: system-ui; padding: 40px; background: #1a1a2e; color: white;">
                <h1>HyperAide Browser Sync</h1>
                <p>Open new tabs and log into the sites you want HyperAide to access.</p>
                <p><strong>Click the 'Close & Sync' button when done.</strong></p>
                </body></html>
            """)

        # Wait for browser to be closed by user OR button click
        try:
            while True:
                try:
                    # Case A: User clicked the button in the browser
                    if sync_requested:
                        console.print("\n[green]Sync requested via button...[/green]")
                        cookies = context.cookies()
                        break
                    
                    # Case B: User manually closed the window
                    if not context.pages:
                        break

                    # Keep capturing cookies while valid
                    cookies = context.cookies()
                    time.sleep(0.5)
                except Exception:
                    # Browser process killed/crashed
                    break
            
            if not sync_requested:
                console.print("\n[green]Browser closed. Processing...[/green]")
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Sync cancelled by user.[/yellow]")
        
        # Explicitly close browser to avoid "Future exception" warning
        try:
            browser.close()
        except Exception:
            pass  # Already closed by user
        
        # Filter to auth-relevant cookies
        auth_cookies = [c for c in cookies if is_auth_cookie(c)]
        
        return auth_cookies, list(visited_domains)


def complete_sync(api_key: str, cookies: list[dict], visited_domains: list[str]) -> dict:
    """Send cookies to server to complete sync."""
    api_url = get_api_url()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Syncing authentication...", total=None)
        
        try:
            response = httpx.post(
                f"{api_url}/api/v1/browser_sync/complete",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "cookies": cookies,
                    "visited_domains": visited_domains,
                },
                timeout=60,
            )
            
            if response.status_code != 200:
                console.print(f"[red]Failed to complete sync: {response.status_code}[/red]")
                console.print(f"[dim]{response.text}[/dim]")
                sys.exit(1)
            
            return response.json()
            
        except httpx.RequestError as e:
            console.print(f"[red]Failed to complete sync: {e}[/red]")
            sys.exit(1)


def display_results(result: dict):
    """Display sync results to user."""
    connected_sites = result.get("connected_sites", [])
    
    console.print()
    
    if not connected_sites:
        console.print(Panel(
            "[yellow]No authenticated sites detected.[/yellow]\n\n"
            "Make sure you logged into sites before closing the browser.",
            title="Sync Complete",
        ))
        return
    
    # Create table of connected sites
    table = Table(title="Connected Sites")
    table.add_column("Site", style="cyan")
    table.add_column("Domain", style="dim")
    
    for site in connected_sites:
        table.add_row(
            site.get("display_name", site.get("domain")),
            site.get("domain"),
        )
    
    console.print(Panel(
        f"[bold green]Successfully synced {len(connected_sites)} site(s)![/bold green]\n\n"
        "HyperAide can now perform browser tasks using your logged-in accounts.",
        title="Sync Complete",
    ))
    console.print()
    console.print(table)


def sync_browser_auth(api_key: Optional[str] = None):
    """
    Main sync function - opens browser, captures cookies, syncs to HyperAide.
    """
    # Display welcome banner
    console.print()
    console.print(Panel(
        "[bold]HyperAide Browser Auth Sync[/bold]\n\n"
        "This tool syncs your browser authentication to HyperAide\n"
        "so your AI assistant can access sites using your accounts.",
        title="Welcome",
        border_style="cyan",
    ))
    
    # Require API key
    api_key = require_api_key(api_key)
    
    # Validate API key and start sync session
    start_result = validate_api_key(api_key)
    
    # Check if user has existing context
    if start_result.get("existing"):
        existing_sites = start_result.get("connected_sites", [])
        
        console.print()
        console.print(Panel(
            f"[yellow]You have an existing sync with {len(existing_sites)} connected site(s).[/yellow]\n\n"
            "You can add more sites by logging into them in the browser.",
            title="Existing Sync Found",
        ))
        
        # Show existing sites
        if existing_sites:
            table = Table(title="Currently Connected")
            table.add_column("Site", style="cyan")
            table.add_column("Domain", style="dim")
            
            for site in existing_sites:
                table.add_row(
                    site.get("display_name", site.get("domain")),
                    site.get("domain"),
                )
            console.print(table)
    
    # Run browser session
    cookies, visited_domains = run_browser_session()
    
    # Display captured sites
    if visited_domains:
        table = Table(title="Sites Captured")
        table.add_column("Domain", style="cyan")
        for domain in sorted(visited_domains):
            table.add_row(domain)
        console.print()
        console.print(table)
        console.print(f"\n[dim]Found {len(cookies)} auth cookies[/dim]")
    else:
        console.print("\n[yellow]No sites were visited.[/yellow]")
    
    # Complete sync
    result = complete_sync(api_key, cookies, visited_domains)
    
    # Display results
    display_results(result)
    
    console.print()
    console.print("[dim]You can view and manage your connected sites at https://hyperaide.com/browser-connections[/dim]")


@app.command()
def reset(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="HyperAide API key",
        envvar="HYPERAIDE_API_KEY",
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
    
    # Require API key
    api_key = require_api_key(api_key)
    
    # Confirm reset
    if not force:
        confirm = typer.confirm(
            "This will disconnect all synced sites. Are you sure?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Reset cancelled.[/yellow]")
            return
    
    api_url = get_api_url()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Resetting browser sync...", total=None)
        
        try:
            response = httpx.delete(
                f"{api_url}/api/v1/browser_sync",
                headers={"x-api-key": api_key},
                timeout=30,
            )
            
            if response.status_code == 401:
                console.print("[red]Invalid API key.[/red]")
                sys.exit(1)
            elif response.status_code != 200:
                console.print(f"[red]Failed to reset: {response.status_code}[/red]")
                sys.exit(1)
            
            console.print()
            console.print(Panel(
                "[green]Browser sync has been reset.[/green]\n\n"
                "All connected sites have been disconnected.\n"
                "Run [bold]hyperaide-sync[/bold] to sync again.",
                title="Reset Complete",
            ))
            
        except httpx.RequestError as e:
            console.print(f"[red]Failed to reset: {e}[/red]")
            sys.exit(1)


@app.command()
def status(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="HyperAide API key",
        envvar="HYPERAIDE_API_KEY",
    ),
):
    """
    Check your current browser sync status.
    """
    
    # Require API key
    api_key = require_api_key(api_key)
    
    api_url = get_api_url()
    
    try:
        response = httpx.get(
            f"{api_url}/api/v1/browser_sync",
            headers={"x-api-key": api_key},
            timeout=30,
        )
        
        if response.status_code == 401:
            console.print("[red]Invalid API key.[/red]")
            sys.exit(1)
        elif response.status_code != 200:
            console.print(f"[red]Failed to get status: {response.status_code}[/red]")
            sys.exit(1)
        
        data = response.json()
        connected_sites = data.get("connected_sites", [])
        status_text = data.get("status", "unknown")
        last_synced = data.get("last_synced_at")
        
        console.print()
        
        if status_text == "not_synced":
            console.print(Panel(
                "[yellow]No browser sync configured.[/yellow]\n\n"
                "Run [bold]hyperaide-sync[/bold] to sync your browser authentication.",
                title="Status",
            ))
            return
        
        # Show connected sites
        if connected_sites:
            table = Table(title=f"Connected Sites ({len(connected_sites)})")
            table.add_column("Site", style="cyan")
            table.add_column("Domain", style="dim")
            table.add_column("Status", style="green")
            
            for site in connected_sites:
                table.add_row(
                    site.get("display_name", site.get("domain")),
                    site.get("domain"),
                    site.get("status", "active"),
                )
            
            console.print(table)
            
            if last_synced:
                console.print(f"\n[dim]Last synced: {last_synced}[/dim]")
        else:
            console.print(Panel(
                "[yellow]Browser sync is configured but no sites are connected.[/yellow]\n\n"
                "Run [bold]hyperaide-sync[/bold] to add sites.",
                title="Status",
            ))
            
    except httpx.RequestError as e:
        console.print(f"[red]Failed to get status: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    app()
