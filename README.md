# WhatsApp MCP (self-hosted)

Give Claude access to **your own** WhatsApp account through the [Model Context Protocol](https://modelcontextprotocol.io).

Everything runs on a machine you control:

- a **Go bridge** that stays logged in as your WhatsApp account and stores your messages in a local SQLite database,
- a **Python MCP server** that gives Claude tools to read and send through that bridge.

There is no hosted service, no shared account and no server run by the author. Anyone who wants to use it runs their own copy with their own WhatsApp login.

Based on [lharries/whatsapp-mcp](https://github.com/lharries/whatsapp-mcp) (MIT). See [CHANGELOG.md](CHANGELOG.md) for what changed in 1.0.0.

> **Warning:** this uses an unofficial WhatsApp client ([whatsmeow](https://github.com/tulir/whatsmeow)). WhatsApp can restrict or ban accounts that automate them. Use it for your own chats, not for bulk or spam messaging.

## What you can do

- **Read:** search and list chats and messages, see the context around a message, list media, load older history from your phone, and look up contacts.
- **Send:** text, files, voice notes, locations, contacts and polls; reply, react, edit, delete and forward.
- **Groups:** create, rename, change the description, manage participants, invite links, admin-only settings.
- **Insights:** statistics for a chat (who writes most, media types, busiest days), exports to Markdown or JSON, bridge status.
- **Media:** Claude can look at photos and video frames, and read PDF, Word (.docx) and plain-text documents.

Audio is not transcribed.

## Privacy and security

- Your messages and pairing data stay in `whatsapp-bridge/store/` on your machine. Nothing is sent to the author.
- The bridge's REST API listens only on `127.0.0.1`.
- The HTTP mode (`whatsapp-mcp-server/http_server.py`) requires `Authorization: Bearer <MCP_TOKEN>` on every request and answers `401` without it. Choose a long random token and keep it secret. Never commit `http.env`.
- If you publish the HTTP mode through a tunnel or a reverse proxy, the token is the only thing protecting your WhatsApp account. Prefer the local stdio mode when you can.
- Files can only be sent from allowed folders (your home folder, the temp folder and the bridge's store by default), and hidden files and folders such as `.ssh` or `.env` are never sent. Change this with `WHATSAPP_ALLOWED_MEDIA_DIRS`.
- Exports can contain private chat text. They are written to `whatsapp-mcp-server/exports/` by default, which is git-ignored.

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

Check that it is running with `curl http://127.0.0.1:8786/api/status`, or ask Claude to call `bridge_status`.

### 2. Run the MCP server

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

## Configuration

| Variable | Used by | Default | Purpose |
| --- | --- | --- | --- |
| `MCP_TOKEN` | HTTP server | (required) | Bearer token every HTTP request must send |
| `PUBLIC_HOST` | HTTP server | `localhost` | Host name clients connect to (DNS-rebinding check) |
| `HOST` / `PORT` | HTTP server | `127.0.0.1` / `8795` | Listen address |
| `WHATSAPP_ALLOWED_MEDIA_DIRS` | MCP server | home folder and temp folder | Folders files may be sent from, separated by the OS path separator. The bridge store is always included. |
| `WHATSAPP_EXPORT_DIR` | MCP server | `whatsapp-mcp-server/exports` | Where `export_chat` writes files |

## Tools added in 1.0.0

| Tool | What it does |
| --- | --- |
| `bridge_status` | Is the bridge running, connected and logged in? Store counts and version. |
| `list_contacts` | Saved contacts, filtered by name or number. |
| `chat_stats` | Message counts, top senders, media types and busiest days for one chat, optionally between two dates. |
| `export_chat` | Write one chat (or a date range) to a Markdown or JSON file and return a preview. |
| `forward_message` | Forward a text or media message to another chat. |

Dates are UTC. `since` is inclusive and `until` is exclusive, so `until = 2026-08-01` includes all of July.

## Repairing senders in old group messages

Some older group messages were stored without their real sender and show as `(unknown member)`. With the bridge running, this asks your phone for older history and fixes those senders:

```bash
python3 tools/backfill_senders.py <group-jid>@g.us 60
```

It only works on group chats and stops when no more senders can be fixed.

## Testing

```bash
cd whatsapp-mcp-server
uv sync --all-groups
uv run pytest

cd ../whatsapp-bridge
go vet ./...
go test -count=1 ./...
```

The Python tests use a temporary database and never contact WhatsApp. The Go tests use an in-memory SQLite database and need a C compiler.

## Known limits

- **Older expired media:** WhatsApp removes media from its servers after a while. The bridge asks your phone to upload it again, but the phone's new copy can't be checked against the original media key, so media that has expired this way may not download. Recent media downloads normally.
- **History:** messages from before you linked the device are only available through the phone's on-demand history, and only as far back as the phone still has them.
- **Audio** is not transcribed.

## Project layout

```
whatsapp-bridge/        Go bridge: WhatsApp connection, SQLite store, REST API on 127.0.0.1:8786
whatsapp-mcp-server/    Python MCP server (stdio, or HTTP with a bearer token) and its tests
tools/                  Optional repair scripts
deploy/                 Example service files and configs (placeholders only)
```

## Credits and license

MIT. See [LICENSE](LICENSE). The original project is by Luke Harries; the Go client library is [whatsmeow](https://github.com/tulir/whatsmeow).
