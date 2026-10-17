import json

import pytest
import requests

import insights
from conftest import ANNA, GROUP


def test_chat_stats_totals(store):
    stats = insights.chat_stats(GROUP)
    assert stats["messages"] == 5
    assert stats["from_me"] == 1
    assert stats["with_media"] == 1
    assert stats["active_days"] == 3
    assert stats["media_types"] == {"image": 1}
    counts = {row["name"]: row["messages"] for row in stats["top_senders"]}
    assert counts["Anna Test"] == 2
    assert counts["Ben Test"] == 1
    assert counts["(unknown member)"] == 1
    assert counts["Me"] == 1


def test_chat_stats_until_is_exclusive(store):
    stats = insights.chat_stats(GROUP, since="2026-07-02", until="2026-07-03")
    assert stats["messages"] == 2  # M3 and M4 only; July 3rd is excluded
    assert stats["busiest_days"] == [{"day": "2026-07-02", "messages": 2}]


def test_bad_date_is_rejected(store):
    with pytest.raises(ValueError):
        insights.chat_stats(GROUP, since="yesterday")


def test_export_markdown(store):
    result = insights.export_chat(GROUP, format="markdown")
    assert result["messages"] == 5
    text = open(result["path"], encoding="utf-8").read()
    assert "# Test group" in text
    assert "[image: a.jpg] look" in text
    assert "Anna Test" in text
    assert "(unknown member)" in text


def test_export_json_with_date_range(store):
    result = insights.export_chat(GROUP, format="json", since="2026-07-01", until="2026-07-02")
    data = json.load(open(result["path"], encoding="utf-8"))
    assert data["chat"] == "Test group"
    assert [message["text"] for message in data["messages"]] == ["hello", "hi"]


def test_export_rejects_unknown_format(store):
    with pytest.raises(ValueError):
        insights.export_chat(GROUP, format="pdf")


def test_list_contacts_filters_by_name(store):
    found = insights.list_contacts("anna")
    assert found and found[0]["name"] == "Anna Test"
    assert found[0]["phone"] == "5511111111"
    assert insights.list_contacts("nobody-with-this-name") == []


def test_forward_text_message(store, monkeypatch):
    sent = []
    monkeypatch.setattr(insights.whatsapp, "send_message", lambda to, text: sent.append((to, text)) or (True, "sent"))
    ok, _ = insights.forward_message(GROUP, "M1", ANNA)
    assert ok
    assert sent == [(ANNA, "hello")]


def test_forward_unknown_message(store):
    ok, message = insights.forward_message(GROUP, "NOPE", ANNA)
    assert not ok
    assert "No such message" in message


def test_bridge_status_when_bridge_is_down(monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(insights.requests, "get", down)
    status = insights.bridge_status()
    assert status["reachable"] is False
    assert "did not answer" in status["error"]
