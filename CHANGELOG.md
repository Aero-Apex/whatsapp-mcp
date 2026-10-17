# Changelog

## 1.0.0

First stable release of the self-hosted WhatsApp MCP.

### Added
- MCP tools: `bridge_status`, `list_contacts`, `chat_stats`, `export_chat` (Markdown or JSON, with date range) and `forward_message` (text and media).
- Bridge endpoint `GET /api/status`: connection state, linked number, store counts and version. It answers even when WhatsApp is disconnected.
- Database indexes for per-chat queries, so large chats stay fast.
- Tests: a Python suite (`uv run pytest`) and Go tests for the bridge store (`go test ./...`), run in CI.
- Optional repair script `tools/backfill_senders.py` for group messages with unknown senders.

### Fixed
- A later copy of a message (live, history sync or an edit) could erase its media link, media key and file details. Now only the fields the copy actually has are updated.
- Chat names were overwritten by empty names on updates. An empty name no longer erases a known one.
- A missing LID mapping table silently disabled contact-name lookup, so contacts showed as numbers. The contact lookup now continues without it.
- `send_file` and `send_audio_message` could read any file on the machine, including hidden folders such as `~/.ssh`. Files are now limited to allowed folders and hidden files are refused.
- Sending a file had no timeout and could hang the MCP server.
- The HTTP server read duplicate `Authorization` headers ambiguously. It now requires exactly one.

### Changed
- Sender names are cached for five minutes, so listing a busy chat no longer reopens the databases for every message.
- Table and index creation moved into one schema function shared by the bridge and its tests.
- Removed the unused transcription dependency and the unused `httpx`. `uvicorn` is now declared explicitly.
- Project metadata: version 1.0.0, MIT license, and a README that documents self-hosting and configuration.
