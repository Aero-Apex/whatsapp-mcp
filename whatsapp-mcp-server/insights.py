"""Chat statistics, exports, contact search, bridge status and forwarding.

Everything here reads the bridge's local store (read-only) or calls the bridge's REST API on localhost.
Dates are UTC. `since` is inclusive and `until` is exclusive, so "until 2026-08-01" includes all of July.
"""

import datetime as dt
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import requests

import whatsapp

EXPORT_DIR = os.environ.get("WHATSAPP_EXPORT_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
MAX_EXPORT_MESSAGES = 20000


def _readonly(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)


def _lower_bound(value: Optional[str]) -> Optional[str]:
    """'2026-07-01' -> '2026-07-01 00:00:00' (inclusive)."""
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{dt.date.fromisoformat(value).isoformat()} 00:00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
        return value
    raise ValueError("Dates must look like 2026-07-01 or 2026-07-01 18:30:00 (UTC)")


def _upper_bound(value: Optional[str]) -> Optional[str]:
    """Exclusive upper bound: '2026-08-01' -> '2026-08-01 00:00:00', so July is included and August is not."""
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{dt.date.fromisoformat(value).isoformat()} 00:00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
        return value
    raise ValueError("Dates must look like 2026-08-01 or 2026-08-01 18:30:00 (UTC)")


def _range_clause(chat_jid: str, since: Optional[str], until: Optional[str]) -> Tuple[str, list]:
    conditions = ["chat_jid = ?"]
    params: list = [chat_jid]
    lower = _lower_bound(since)
    upper = _upper_bound(until)
    if lower:
        conditions.append("timestamp >= ?")
        params.append(lower)
    if upper:
        conditions.append("timestamp < ?")
        params.append(upper)
    return " AND ".join(conditions), params


def _sender_label(chat_jid: str, sender: str, is_from_me: bool) -> str:
    if is_from_me:
        return "Me"
    if chat_jid.endswith("@g.us") and sender == chat_jid.split("@")[0]:
        return "(unknown member)"
    return whatsapp.get_sender_name(sender) if sender else "unknown"


def chat_stats(chat_jid: str, since: Optional[str] = None, until: Optional[str] = None) -> Dict[str, Any]:
    """Message counts, top senders, media types and busiest days for one chat."""
    where, params = _range_clause(chat_jid, since, until)
    conn = _readonly(whatsapp.MESSAGES_DB_PATH)
    try:
        total, from_me, with_media, first, last = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_from_me), 0), "
            "COALESCE(SUM(CASE WHEN media_type IS NOT NULL AND media_type != '' THEN 1 ELSE 0 END), 0), "
            f"MIN(timestamp), MAX(timestamp) FROM messages WHERE {where}",
            params,
        ).fetchone()
        active_days = conn.execute(
            f"SELECT COUNT(DISTINCT substr(timestamp, 1, 10)) FROM messages WHERE {where}", params
        ).fetchone()[0]
        sender_rows = conn.execute(
            f"SELECT sender, is_from_me, COUNT(*) FROM messages WHERE {where} "
            "GROUP BY sender, is_from_me ORDER BY COUNT(*) DESC LIMIT 10",
            params,
        ).fetchall()
        media_rows = conn.execute(
            f"SELECT media_type, COUNT(*) FROM messages WHERE {where} "
            "AND media_type IS NOT NULL AND media_type != '' GROUP BY media_type ORDER BY COUNT(*) DESC",
            params,
        ).fetchall()
        day_rows = conn.execute(
            f"SELECT substr(timestamp, 1, 10) AS day, COUNT(*) FROM messages WHERE {where} "
            "GROUP BY day ORDER BY COUNT(*) DESC, day DESC LIMIT 5",
            params,
        ).fetchall()
    finally:
        conn.close()

    top_senders = [
        {"name": _sender_label(chat_jid, sender, bool(me)), "messages": count}
        for sender, me, count in sender_rows
    ]
    return {
        "chat_jid": chat_jid,
        "messages": total,
        "from_me": from_me,
        "with_media": with_media,
        "first_message": first,
        "last_message": last,
        "active_days": active_days,
        "top_senders": top_senders,
        "media_types": {kind: count for kind, count in media_rows},
        "busiest_days": [{"day": day, "messages": count} for day, count in day_rows],
    }


def _chat_name(conn: sqlite3.Connection, chat_jid: str) -> str:
    row = conn.execute("SELECT name FROM chats WHERE jid = ?", (chat_jid,)).fetchone()
    return row[0] if row and row[0] else chat_jid


def _safe_file_part(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "chat"


def export_chat(
    chat_jid: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
    format: str = "markdown",
    limit: int = 5000,
) -> Dict[str, Any]:
    """Write the messages of one chat in a time range to a Markdown or JSON file in EXPORT_DIR."""
    fmt = (format or "markdown").lower()
    if fmt not in ("markdown", "json"):
        raise ValueError("format must be 'markdown' or 'json'")
    limit = max(1, min(int(limit), MAX_EXPORT_MESSAGES))
    where, params = _range_clause(chat_jid, since, until)

    conn = _readonly(whatsapp.MESSAGES_DB_PATH)
    try:
        name = _chat_name(conn, chat_jid)
        rows = conn.execute(
            f"SELECT id, sender, is_from_me, timestamp, content, media_type, filename FROM messages "
            f"WHERE {where} ORDER BY timestamp ASC LIMIT ?",
            params + [limit],
        ).fetchall()
    finally:
        conn.close()

    entries = []
    for message_id, sender, is_from_me, timestamp, content, media_type, filename in rows:
        entries.append({
            "message_id": message_id,
            "time": timestamp,
            "from": _sender_label(chat_jid, sender or "", bool(is_from_me)),
            "text": content or "",
            "media_type": media_type or "",
            "filename": filename or "",
        })

    os.makedirs(EXPORT_DIR, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    extension = "md" if fmt == "markdown" else "json"
    path = os.path.join(EXPORT_DIR, f"{_safe_file_part(name)}-{stamp}.{extension}")

    if fmt == "json":
        body = json.dumps({"chat": name, "chat_jid": chat_jid, "messages": entries}, ensure_ascii=False, indent=2)
    else:
        lines = [f"# {name}", "", f"Exported {len(entries)} message(s) from `{chat_jid}` (times in UTC).", ""]
        for entry in entries:
            time_text = (entry["time"] or "")[:19]
            if entry["media_type"]:
                media = f"[{entry['media_type']}: {entry['filename'] or 'file'}]"
                text = f"{media} {entry['text']}".rstrip()
            else:
                text = entry["text"]
            lines.append(f"**{time_text} {entry['from']}:** {text}")
            lines.append("")
        body = "\n".join(lines)

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)

    return {
        "path": path,
        "format": fmt,
        "messages": len(entries),
        "preview": body[:1500],
    }


def list_contacts(query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    """Saved contacts, optionally filtered by name or number."""
    limit = max(1, min(int(limit), 500))
    conditions: List[str] = []
    params: List[Any] = []
    if query and query.strip():
        like = f"%{query.strip()}%"
        conditions.append("(full_name LIKE ? OR first_name LIKE ? OR push_name LIKE ? OR their_jid LIKE ?)")
        params.extend([like, like, like, like])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = _readonly(whatsapp.WHATSAPP_DB_PATH)
    try:
        rows = conn.execute(
            f"SELECT their_jid, first_name, full_name, push_name FROM whatsmeow_contacts {where} "
            "ORDER BY (full_name IS NULL OR full_name = ''), full_name, push_name LIMIT ?",
            params + [limit],
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"The contact list is not ready yet ({exc}). Pair the bridge and let it sync first.")
    finally:
        conn.close()

    contacts = []
    for jid, first_name, full_name, push_name in rows:
        contacts.append({
            "jid": jid,
            "name": full_name or first_name or push_name or "",
            "push_name": push_name or "",
            "phone": jid.split("@")[0] if jid.endswith("@s.whatsapp.net") else "",
            "is_lid": jid.endswith("@lid"),
        })
    return contacts


def bridge_status() -> Dict[str, Any]:
    """Whether the bridge is running and connected, plus store counts."""
    try:
        response = requests.get(f"{whatsapp.WHATSAPP_API_BASE_URL}/status", timeout=5)
    except requests.RequestException as exc:
        return {"reachable": False, "error": f"The bridge did not answer: {exc}"}
    try:
        body = response.json()
    except ValueError:
        return {"reachable": True, "error": f"Unexpected answer from the bridge (HTTP {response.status_code})"}
    if not body.get("success"):
        return {"reachable": True, "error": body.get("message", "The bridge reported an error")}
    return {"reachable": True, **(body.get("data") or {})}


def forward_message(from_chat_jid: str, message_id: str, to_chat_jid: str) -> Tuple[bool, str]:
    """Send a stored message (text or media) to another chat. Media is downloaded, then sent again."""
    conn = _readonly(whatsapp.MESSAGES_DB_PATH)
    try:
        row = conn.execute(
            "SELECT content, media_type FROM messages WHERE id = ? AND chat_jid = ?",
            (message_id, from_chat_jid),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return False, "No such message in that chat"
    content, media_type = row[0] or "", row[1] or ""

    if not media_type:
        if not content:
            return False, "That message has no text to forward"
        return whatsapp.send_message(to_chat_jid, content)

    path = whatsapp.download_media(message_id, from_chat_jid)
    if not path:
        return False, "The media could not be downloaded, so it cannot be forwarded"
    if media_type == "audio":
        ok, message = whatsapp.send_audio_message(to_chat_jid, path)
    else:
        ok, message = whatsapp.send_file(to_chat_jid, path)
    if ok and content:
        whatsapp.send_message(to_chat_jid, content)
    return ok, message
