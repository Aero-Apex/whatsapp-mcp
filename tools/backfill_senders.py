"""Repair message senders in a group chat by asking the phone for older history, in batches.

Messages stored without their real sender (sender = the group itself) are fixed by requesting history
before a message whose sender is known, then stepping back in time as the phone returns older batches.
Usage: python tools/backfill_senders.py <group_jid>@g.us [max_rounds]
The bridge must be running on this machine.
"""
import pathlib
import sqlite3
import sys
import time

import requests

# This script lives in tools/, so the bridge's store is one folder up.
DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "whatsapp-bridge" / "store" / "messages.db"
API = "http://127.0.0.1:8786/api"


def next_anchor(chat_jid: str):
    """Message to request history before, or None when no fixable unknown sender is left.

    Unknown senders newer than the newest known sender cannot be fixed by asking for older history,
    so they are skipped. The anchor is the oldest known message newer than the newest fixable unknown
    one, so each request covers the unknown messages just before it.
    """
    chat_user = chat_jid.split("@")[0]
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        newest_known = conn.execute(
            "SELECT MAX(timestamp) FROM messages WHERE chat_jid = ? AND sender != ?",
            (chat_jid, chat_user),
        ).fetchone()[0]
        if newest_known is None:
            return None
        newest_unknown = conn.execute(
            "SELECT MAX(timestamp) FROM messages WHERE chat_jid = ? AND sender = ? AND is_from_me = 0 "
            "AND timestamp < ?",
            (chat_jid, chat_user, newest_known),
        ).fetchone()[0]
        if newest_unknown is None:
            return None
        row = conn.execute(
            "SELECT id FROM messages WHERE chat_jid = ? AND sender != ? AND timestamp > ? "
            "ORDER BY timestamp ASC LIMIT 1",
            (chat_jid, chat_user, newest_unknown),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def unresolved_count(chat_jid: str) -> int:
    chat_user = chat_jid.split("@")[0]
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_jid = ? AND sender = ? AND is_from_me = 0",
            (chat_jid, chat_user),
        ).fetchone()[0]
    finally:
        conn.close()


def main() -> None:
    chat_jid = sys.argv[1]
    if not chat_jid.endswith("@g.us"):
        sys.exit("backfill_history.py only repairs group chats")
    max_rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    stalls = 0

    for round_number in range(1, max_rounds + 1):
        anchor = next_anchor(chat_jid)
        if anchor is None:
            print("no fixable unknown sender left", flush=True)
            break
        try:
            response = requests.post(
                f"{API}/load_history",
                json={"chat_jid": chat_jid, "count": 50, "before_message_id": anchor, "wait_seconds": 30},
                timeout=90,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"round {round_number}: request failed: {exc}", flush=True)
            stalls += 1
            if stalls >= 3:
                break
            time.sleep(10)
            continue

        data = body.get("data") or {}
        progress = bool(data.get("new_messages")) or bool(data.get("senders_resolved"))
        print(
            f"round {round_number}: anchor={anchor[:10]} new={data.get('new_messages')} "
            f"resolved={data.get('senders_resolved')} unresolved_left={unresolved_count(chat_jid)} "
            f"oldest={data.get('oldest_message_after')}",
            flush=True,
        )
        stalls = 0 if (body.get("success") and progress) else stalls + 1
        if stalls >= 2:
            print("no more progress, stopping", flush=True)
            break
        time.sleep(3)

    print(f"done; unknown senders left: {unresolved_count(chat_jid)}", flush=True)


if __name__ == "__main__":
    main()
