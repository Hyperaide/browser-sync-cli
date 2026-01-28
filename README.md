# Hyperaide Browser Sync

Sync your browser authentication to Hyperaide so your AI assistant can access sites using your logged-in accounts.

## Quick Start

```bash
curl -fsSL https://hyperaide.com/sync | sh
```

Or with your sync token:

```bash
export HYPERAIDE_SYNC_TOKEN=your_token
curl -fsSL https://hyperaide.com/sync | sh
```

## Usage

```bash
# Sync (default)
hyperaide-sync

# With token
hyperaide-sync --token YOUR_TOKEN

# Check status
hyperaide-sync status

# Reset all sites
hyperaide-sync reset
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run in dev mode
python main.py --dev
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `HYPERAIDE_SYNC_TOKEN` | Your sync token |
| `HYPERAIDE_API_URL` | Custom API URL (optional) |
| `HYPERAIDE_DEV` | Set to `1` for dev mode |

## How It Works

1. Browser opens for you to log into sites
2. Auth cookies are captured when you close
3. Cookies sync to Hyperaide securely
4. Your AI assistant can now access those sites

## Security

- Only session cookies are synced (not passwords)
- Encrypted at rest
- Disconnect anytime from dashboard

## Building

```bash
chmod +x build.sh
./build.sh
```

Creates `dist/hyperaide-sync-{os}-{arch}`.
