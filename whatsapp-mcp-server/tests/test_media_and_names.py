import whatsapp
from conftest import ANNA


def test_contact_name_is_used_first(store):
    assert whatsapp.get_sender_name(ANNA) == "Anna Test"


def test_sender_name_table_is_used_without_a_contact(store):
    assert whatsapp.get_sender_name("5522222222") == "Ben Test"


def test_unknown_sender_falls_back_to_the_number(store):
    assert whatsapp.get_sender_name("5533333333@s.whatsapp.net") == "5533333333@s.whatsapp.net"


def test_names_are_cached(store, monkeypatch):
    assert whatsapp.get_sender_name(ANNA) == "Anna Test"

    def must_not_run(_sender):
        raise AssertionError("the name was looked up again instead of coming from the cache")

    monkeypatch.setattr(whatsapp, "_get_sender_name_uncached", must_not_run)
    assert whatsapp.get_sender_name(ANNA) == "Anna Test"


def test_allowed_file_passes(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "note.txt").write_text("hello")
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", str(allowed))
    assert whatsapp.check_media_path(str(allowed / "note.txt")) is None


def test_file_outside_allowed_folders_is_refused(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("hello")
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", str(allowed))
    assert "outside" in whatsapp.check_media_path(str(outside))


def test_hidden_files_are_refused(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    (allowed / ".ssh").mkdir(parents=True)
    secret = allowed / ".ssh" / "id_ed25519"
    secret.write_text("key")
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", str(allowed))
    assert "Hidden" in whatsapp.check_media_path(str(secret))


def test_missing_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", str(tmp_path))
    assert "not found" in whatsapp.check_media_path(str(tmp_path / "missing.txt"))


def test_send_file_refuses_hidden_files_without_calling_the_bridge(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    secret = allowed / ".env"
    secret.write_text("TOKEN=1")
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", str(allowed))

    def no_network(*args, **kwargs):
        raise AssertionError("the bridge must not be called for a refused file")

    monkeypatch.setattr(whatsapp.requests, "post", no_network)
    ok, message = whatsapp.send_file(ANNA, str(secret))
    assert ok is False
    assert "Hidden" in message


def test_store_folder_is_always_allowed(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", "/nonexistent-only")
    assert whatsapp.STORE_DIR in whatsapp.allowed_media_dirs()


def test_send_file_hands_an_allowed_file_to_the_bridge(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    photo = allowed / "photo.jpg"
    photo.write_bytes(b"not really a jpeg")
    monkeypatch.setenv("WHATSAPP_ALLOWED_MEDIA_DIRS", str(allowed))

    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"success": True, "message": "sent"}

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr(whatsapp.requests, "post", fake_post)
    assert whatsapp.send_file(ANNA, str(photo)) == (True, "sent")
    url, payload, timeout = calls[0]
    assert url.endswith("/send")
    assert payload == {"recipient": ANNA, "media_path": str(photo)}
    assert timeout == whatsapp.SEND_TIMEOUT_SECONDS
