# HyperAide Browser Auth Sync CLI

Sync your local browser authentication state to HyperAide so your AI assistant can perform browser automation tasks using your logged-in accounts.

## Quick Start (End Users)

The easiest way to use this tool is via the one-liner:

```bash
curl -fsSL https://hyperaide.com/sync | sh
```

This will:
1. Download the CLI binary for your platform (~250MB, includes Chromium)
2. Prompt for your API key
3. Open a browser for you to log into sites
4. Sync your authentication when you close the browser
5. Clean up automatically

## Development Setup

### Using asdf (Recommended)

```bash
cd browser-sync-cli

# Install Python via asdf
asdf install

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run in dev mode (uses localhost:3000)
python main.py --dev
```

### Using venv

```bash
cd browser-sync-cli

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium

python main.py --dev
```

## Usage

### Sync Browser Auth

```bash
# Interactive mode (will prompt for API key)
python main.py

# With API key
python main.py --api-key YOUR_API_KEY

# Or set environment variable
export HYPERAIDE_API_KEY=your_api_key
python main.py
```

### Check Status

```bash
python main.py status
```

### Reset/Disconnect All Sites

```bash
python main.py reset
python main.py reset --force  # Skip confirmation
```

## Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Start browser sync (default command) |
| `python main.py status` | Check current sync status and connected sites |
| `python main.py reset` | Reset sync and disconnect all sites |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `HYPERAIDE_API_KEY` | Your HyperAide API key |
| `HYPERAIDE_API_URL` | Custom API URL (optional) |
| `HYPERAIDE_DEV` | Set to `1` for development mode |

## How It Works

1. **Authenticate**: You provide your HyperAide API key
2. **Browser Session**: A Chromium browser opens where you can log into sites
3. **Cookie Capture**: When you close the browser, auth cookies are extracted
4. **Secure Sync**: Cookies are sent to HyperAide and stored in a Browserbase context
5. **Ready to Use**: HyperAide can now perform browser tasks using your accounts

## Security

- **Only auth cookies are synced** - We filter for session/token cookies only
- **Your passwords are never stored** - Only session cookies that expire
- **Encrypted at rest** - Browserbase encrypts all context data
- **User control** - You can disconnect sites anytime from the dashboard

## Building the Binary Locally

To build a standalone binary with bundled Chromium:

```bash
cd browser-sync-cli

# Make build script executable
chmod +x build.sh

# Run the build
./build.sh
```

This creates `dist/hyperaide-sync-{os}-{arch}` (~250MB with Chromium bundled).

Test the binary:
```bash
./dist/hyperaide-sync-darwin-arm64 --help
./dist/hyperaide-sync-darwin-arm64 --dev  # Uses localhost API
```

### Building for All Platforms (CI)

GitHub Actions (`.github/workflows/build.yml`) builds for:
- macOS arm64 (Apple Silicon)
- macOS amd64 (Intel)
- Linux amd64

To trigger a release build, push a tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```

## License

MIT
