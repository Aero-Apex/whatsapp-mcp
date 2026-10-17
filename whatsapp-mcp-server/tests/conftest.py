"""Shared fixtures: a small bridge store (messages, chats, names and contacts) built in a temporary folder.

The tests never talk to WhatsApp or to the bridge. They only read the local databases.
"""

import os
import sqlite3
import sys

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

import insights  # noqa: E402
import whatsapp  # noqa: E402

GROUP = "120000000000000001@g.us"
ANNA = "5511111111@s.whatsapp.net"

MESSAGES_SCHEMA = """
CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP);
CREATE TABLE messages (
    id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP, is_from_me BOOLEAN,
    media_type TEXT, filename TEXT, url TEXT, media_key BLOB, file_sha256 BLOB,
    file_enc_sha256 BLOB, file_length INTEGER, PRIMARY KEY (id, chat_jid));
CREATE TABLE sender_names (user TEXT PRIMARY KEY, name TEXT, updated TIMESTAMP);
"""

CONTACTS_SCHEMA = """
CREATE TABLE whatsmeow_contacts (
    our_jid TEXT, their_jid TEXT, first_name TEXT, full_name TEXT, push_name TEXT, business_name TEXT,
    PRIMARY KEY (our_jid, their_jid));
"""

# id, chat, sender, content, timestamp, is_from_me, media_type, filename, url
MESSAGES = [
    ("M1", GROUP, "5511111111", "hello", "2026-07-01 10:00:00+00:00", 0, "", "", ""),
    ("M2", GROUP, "5522222222", "hi", "2026-07-01 10:05:00+00:00", 0, "", "", ""),
    ("M3", GROUP, "5511111111", "look", "2026-07-02 09:00:00+00:00", 0, "image", "a.jpg", "https://example.test/a"),
    ("M4", GROUP, "120000000000000001", "lost", "2026-07-02 09:30:00+00:00", 0, "", "", ""),
    ("M5", GROUP, "me", "sent", "2026-07-03 12:00:00+00:00", 1, "", "", ""),
]


@pytest.fixture
def store(tmp_path, monkeypatch):
    messages_path = tmp_path / "messages.db"
    contacts_path = tmp_path / "whatsapp.db"

    conn = sqlite3.connect(messages_path)
    conn.executescript(MESSAGES_SCHEMA)
    conn.execute("INSERT INTO chats VALUES (?, ?, ?)", (GROUP, "Test group", "2026-07-03 12:00:00+00:00"))
    conn.executemany(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename, url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        MESSAGES,
    )
    conn.execute("INSERT INTO sender_names VALUES (?, ?, ?)", ("5522222222", "Ben Test", "2026-07-01"))
    conn.commit()
    conn.close()

    conn = sqlite3.connect(contacts_path)
    conn.executescript(CONTACTS_SCHEMA)
    conn.execute(
        "INSERT INTO whatsmeow_contacts VALUES (?, ?, ?, ?, ?, ?)",
        ("999@s.whatsapp.net", ANNA, "Anna", "Anna Test", "anna push", ""),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(whatsapp, "MESSAGES_DB_PATH", str(messages_path))
    monkeypatch.setattr(whatsapp, "WHATSAPP_DB_PATH", str(contacts_path))
    monkeypatch.setattr(insights, "EXPORT_DIR", str(tmp_path / "exports"))
    whatsapp._name_cache.clear()
    return tmp_path
