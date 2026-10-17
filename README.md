# WhatsApp MCP (self-hosted)

Give Claude access to **your own** WhatsApp account through the [Model Context Protocol](https://modelcontextprotocol.io).

Everything runs on a machine you control:

- a **Go bridge** that stays logged in as your WhatsApp account and stores your messages in a local SQLite database,
- a **Python MCP server** that gives Claude tools to read and send through that bridge.

There is no hosted service, no shared account and no server run by the author. Anyone who wants to use it runs their own copy with their own WhatsApp login.

Based on [lharries/whatsapp-mcp](https://github.com/lharries/whatsapp-mcp) (MIT). This version adds group admin tools, reply/react/edit/delete, on-demand history loading, sender-name repair, media viewing (images, video frames, PDF/Word/text documents) and an HTTP mode with bearer-token authentication.

> **Warning:** this uses an unofficial WhatsApp client ([whatsmeow](https://github.com/tulir/whatsmeow)). WhatsApp can restrict or ban accounts that automate them. Use it for your own chats, not for bulk or spam messaging.

## What you can do

- Search and read chats, contacts and groups; list media and load older history from your phone.
- Send text, files, voice notes, locations, contacts and polls; reply, react, edit and delete.
- Manage groups: create, rename, change description, participants, invite links, admin-only settings.
- Let Claude look at photos and video frames, and read PDF, Word (.docx) and plain-text documents.

Audio is not transcribed.

## Privacy and security

- Your messages and pairing data stay in `whatsapp-bridge/store/` on your machine. Nothing is sent to the author.
- The bridge's REST API listens only on `127.0.0.1`.
- The HTTP mode (`whatsapp-mcp-server/http_server.py`) requires `Authorization: Bearer <MCP_TOKEN>` on every request and answers `401` without it. Choose a long random token and keep it secret. Never commit `http.env`.
- If you publish the HTTP mode through a tunnel or a reverse proxy, the token is the only thing protecting your WhatsApp account. Prefer the local stdio mode when you can.

## Requirements

- Go 1.26 or newer, with a C compiler (the SQLite driver uses cgo)
- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- `ffmpeg` and `ffprobe` (video frames, image conversion)
- `poppler-utils` (`pdftotext`, for PDF reading)

## Setup

### 1. Build and pair the bridge

```bash
cd whatsapp-bridge
mkdir -p store
go build -o whatsapp-bridge .
./whatsapp-bridge
```

The first run shows a QR code in the terminal and also writes it to `store/qr.txt`. On your phone open **WhatsApp → Settings → Linked devices → Link a device** and scan it. Once linked, the bridge keeps running and reconnects by itself.

### 2. Start the bridge and the MCP server

Keep the bridge running (see `deploy/whatsapp-bridge.service` for running it as a service).

#### Option A: local, for Claude Desktop (recommended)

```bash
cd whatsapp-mcp-server
uv sync
```

Add the server to Claude Desktop's config. See `deploy/claude_desktop_config.example.json` and replace the path:

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/whatsapp-mcp/whatsapp-mcp-server", "run", "main.py"]
    }
  }
}
```

Restart Claude Desktop afterwards.

#### Option B: HTTP, reachable from other machines

```bash
cp deploy/http.env.example http.env      # then edit it
# put a long random value in MCP_TOKEN, for example: openssl rand -hex 32
set -a; . ./http.env; set +a
cd whatsapp-mcp-server
uv run http_server.py
```

Clients must send `Authorization: Bearer <MCP_TOKEN>`. Only use this behind a tunnel or proxy you control (see `deploy/whatsapp-mcp-http.service`).

## Repairing senders in old group messages

Some older group messages were stored without their real sender and show as `(unknown member)`. With the bridge running, this asks your phone for older history and fixes those senders:

```bash
python3 tools/backfill_senders.py <group-jid>@g.us 60
```

It only works on group chats and stops when no more senders can be fixed.

## Known limits

- **Older expired media:** WhatsApp removes media from its servers after a while. The bridge asks your phone to upload it again, but the phone's new copy can't be checked against the original media key, so media that has expired this way may not download. Recent media downloads normally.
- **History:** messages from before you linked the device are only available through the phone's on-demand history, and only as far back as the phone still has them.
- **Audio** is not transcribed.

## Project layout

```
whatsapp-bridge/        Go bridge: WhatsApp connection, SQLite store, REST API on 127.0.0.1:8786
whatsapp-mcp-server/    Python MCP server (stdio, or HTTP with a bearer token)
tools/                  Optional repair scripts
deploy/                 Example service files and configs (placeholders only)
```

## Credits and license

MIT. See [LICENSE](LICENSE). The original project is by Luke Harries; the Go client library is [whatsmeow](https://github.com/tulir/whatsmeow).
