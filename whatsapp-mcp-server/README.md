# WhatsApp MCP server

The Python MCP server for WhatsApp MCP. See the [project README](../README.md) for setup, privacy notes and the list of limits.

- `main.py`: MCP tools, served over stdio by default
- `http_server.py`: the same tools over HTTP with a bearer token (`MCP_TOKEN`)
- `whatsapp.py`: talks to the bridge's REST API on `127.0.0.1:8786` and reads its SQLite store
- `media_tools.py`: image, video-frame and document tools
