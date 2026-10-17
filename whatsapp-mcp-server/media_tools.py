"""Tools that let Claude see what is in a chat: images, video frames, documents, media lists and older history.

The bridge downloads media to the server. These tools convert it and return the content to Claude
directly, so Claude does not need access to the server's files. Audio is not transcribed here.
"""
import html
import os
import re
import sqlite3
import subprocess
import tempfile
import zipfile
from typing import Any, Optional

import requests
from mcp.server.fastmcp import Image

from whatsapp import MESSAGES_DB_PATH, WHATSAPP_API_BASE_URL, download_media, get_sender_name

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log", ".py", ".js", ".ts",
    ".sql", ".yaml", ".yml", ".ini", ".cfg", ".srt", ".vtt", ".rtf",
}
MEDIA_TYPES = {"image", "video", "audio", "document", "sticker"}
MAX_TEXT_CHARS = 20000


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{MESSAGES_DB_PATH}?mode=ro", uri=True, timeout=10)


def _media_row(chat_jid: str, message_id: str) -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, sender, is_from_me, timestamp, content, media_type, filename "
            "FROM messages WHERE id = ? AND chat_jid = ?",
            (message_id, chat_jid),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"No message {message_id} in chat {chat_jid}")
    if not row[5]:
        raise ValueError(f"Message {message_id} has no media")
    return {
        "id": row[0],
        "sender": row[1] or "",
        "is_from_me": bool(row[2]),
        "timestamp": row[3],
        "caption": row[4] or "",
        "media_type": row[5],
        "filename": row[6] or "",
    }


def _fetch(chat_jid: str, message_id: str) -> tuple[dict, str]:
    """Return the stored details of a media message and the path of its downloaded file."""
    info = _media_row(chat_jid, message_id)
    path = download_media(message_id, chat_jid)
    if not path or not os.path.isfile(path):
        raise RuntimeError(
            "The media could not be downloaded. Its link may have expired and the phone did not "
            "answer in time (check that the phone is online)."
        )
    return info, path


def _sender_label(chat_jid: str, info: dict) -> str:
    if info["is_from_me"]:
        return "Me"
    sender = info["sender"]
    if chat_jid.endswith("@g.us") and sender == chat_jid.split("@")[0]:
        return "(unknown member)"
    return get_sender_name(sender) if sender else "unknown"


def _describe(chat_jid: str, info: dict, label: str) -> str:
    text = f"{label} from {_sender_label(chat_jid, info)} at {info['timestamp']}"
    if info["filename"]:
        text += f" (file: {info['filename']})"
    if info["caption"]:
        text += f". Caption: {info['caption']}"
    return text


def _run(args: list[str], timeout: int = 120) -> bytes:
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip()[-400:] or "conversion failed")
    return result.stdout


def _duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _frame_to_jpeg(source: str, out_path: str, max_side: int, at_seconds: Optional[float] = None) -> None:
    """Write one frame (or the single image) as a JPEG whose longest edge is at most max_side."""
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    if at_seconds is not None:
        args += ["-ss", f"{at_seconds:.2f}"]
    args += [
        "-i", source, "-frames:v", "1",
        "-vf", f"scale='min({max_side},iw)':'min({max_side},ih)':force_original_aspect_ratio=decrease",
        "-q:v", "4", out_path,
    ]
    _run(args)
    if not os.path.isfile(out_path):
        raise RuntimeError("no picture could be read from this file at this point")


def _image(path: str) -> Image:
    with open(path, "rb") as handle:
        return Image(data=handle.read(), format="jpeg")


def _docx_text(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def view_image(chat_jid: str, message_id: str, max_side: int = 1024) -> Any:
    """Show a photo, picture or sticker from a WhatsApp chat so you can look at it.

    Args:
        chat_jid: The chat containing the image
        message_id: The message ID of the image (get it from list_media)
        max_side: Longest edge of the picture in pixels, 128 to 2048 (default 1024)
    """
    info, source = _fetch(chat_jid, message_id)
    max_side = max(128, min(max_side, 2048))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "view.jpg")
        _frame_to_jpeg(source, out, max_side)
        return [_describe(chat_jid, info, "Image"), _image(out)]


def view_video(chat_jid: str, message_id: str, frames: int = 6, max_side: int = 640) -> Any:
    """Show a video from a WhatsApp chat as evenly spaced still frames. The sound is not included.

    Args:
        chat_jid: The chat containing the video
        message_id: The message ID of the video (get it from list_media)
        frames: How many frames to show, 1 to 12 (default 6)
        max_side: Longest edge of each frame in pixels, 128 to 1280 (default 640)
    """
    info, source = _fetch(chat_jid, message_id)
    frames = max(1, min(frames, 12))
    max_side = max(128, min(max_side, 1280))
    duration = _duration(source)
    if duration > 0:
        times = [duration * (index + 0.5) / frames for index in range(frames)]
    else:
        times = [0.0]

    output: list[Any] = [
        f"{_describe(chat_jid, info, 'Video')}. Length {duration:.1f} s, showing {len(times)} frame(s)."
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for index, at in enumerate(times):
            out = os.path.join(tmp, f"frame_{index:02d}.jpg")
            try:
                _frame_to_jpeg(source, out, max_side, at_seconds=at)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                output.append(f"Frame at {at:.1f} s could not be read: {exc}")
                continue
            output.append(f"Frame {index + 1} at {at:.1f} s")
            output.append(_image(out))
    return output


def read_document(chat_jid: str, message_id: str, max_chars: int = MAX_TEXT_CHARS) -> Any:
    """Read the text of a document from a WhatsApp chat: PDF, Word (.docx) or plain text files.

    Args:
        chat_jid: The chat containing the document
        message_id: The message ID of the document (get it from list_media)
        max_chars: Most characters to return, 1000 to 100000 (default 20000); longer text is cut off
    """
    info, source = _fetch(chat_jid, message_id)
    name = info["filename"] or source
    extension = os.path.splitext(name)[1].lower()
    if extension == ".pdf":
        text = _run(["pdftotext", "-layout", "-enc", "UTF-8", source, "-"]).decode("utf-8", errors="replace").replace("\x0c", "\n").rstrip() + "\n"
    elif extension == ".docx":
        text = _docx_text(source)
    elif extension in TEXT_EXTENSIONS:
        with open(source, "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Cannot read {extension or 'this'} files yet. Supported: PDF, DOCX and plain text.")

    limit = max(1000, min(max_chars, 100000))
    result = {
        "description": _describe(chat_jid, info, "Document"),
        "characters": len(text),
        "truncated": len(text) > limit,
        "text": text[:limit],
    }
    if not text.strip():
        result["note"] = "No text was found. The document may be scanned images."
    return result


def list_media(
    chat_jid: str,
    limit: int = 30,
    media_type: str = "",
    before_timestamp: str = "",
) -> Any:
    """List photos, videos, audio, documents and stickers in a chat, newest first.

    Each item has the message_id that view_image, view_video and read_document need.

    Args:
        chat_jid: The chat to list
        limit: How many items to return, 1 to 200 (default 30)
        media_type: Only this kind: image, video, audio, document or sticker (default all kinds)
        before_timestamp: Only items older than this, e.g. "2026-07-01 00:00:00" (default newest)
    """
    limit = max(1, min(limit, 200))
    if media_type and media_type not in MEDIA_TYPES:
        raise ValueError(f"media_type must be one of: {', '.join(sorted(MEDIA_TYPES))}")

    sql = (
        "SELECT id, sender, is_from_me, timestamp, content, media_type, filename FROM messages "
        "WHERE chat_jid = ? AND media_type IS NOT NULL AND media_type != ''"
    )
    params: list[Any] = [chat_jid]
    if media_type:
        sql += " AND media_type = ?"
        params.append(media_type)
    if before_timestamp:
        sql += " AND timestamp < ?"
        params.append(before_timestamp)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    conn = _connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    items = []
    for message_id, sender, is_from_me, timestamp, content, kind, filename in rows:
        items.append({
            "message_id": message_id,
            "time": timestamp,
            "from": _sender_label(chat_jid, {"sender": sender or "", "is_from_me": bool(is_from_me)}),
            "media_type": kind,
            "filename": filename or "",
            "caption": content or "",
        })
    return items


def load_older_messages(
    chat_jid: str,
    count: int = 50,
    before_message_id: str = "",
    wait_seconds: int = 25,
) -> Any:
    """Ask the phone for older messages in a chat, store them, and report what arrived.

    Use before_message_id="" to start from the oldest message stored so far, or pass a message ID to
    load the messages just before it. Call again with the oldest message ID to keep going back.
    The phone must be online.

    Args:
        chat_jid: The chat to load history for
        count: How many older messages to request, 1 to 100 (default 50)
        before_message_id: Message ID to load before; "" for the oldest stored, "newest" for the latest
        wait_seconds: How long to wait for the phone's answer, 5 to 45 (default 25)
    """
    wait = max(5, min(wait_seconds, 45))
    payload = {
        "chat_jid": chat_jid,
        "count": max(1, min(count, 100)),
        "before_message_id": before_message_id,
        "wait_seconds": wait,
    }
    try:
        response = requests.post(f"{WHATSAPP_API_BASE_URL}/load_history", json=payload, timeout=wait + 30)
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Could not reach the bridge for history: {exc}") from exc
    return {
        "success": bool(body.get("success")),
        "message": body.get("message", ""),
        "data": body.get("data"),
    }


def register(mcp: Any) -> None:
    """Add these tools to the FastMCP server."""
    for tool in (view_image, view_video, read_document, list_media, load_older_messages):
        mcp.tool()(tool)
