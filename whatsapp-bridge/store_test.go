package main

import (
	"bytes"
	"database/sql"
	"testing"
	"time"
)

// openTestStore returns a store backed by a fresh in-memory database with the real schema.
func openTestStore(t *testing.T) *MessageStore {
	t.Helper()
	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	// Each connection to :memory: is its own database, so keep a single connection.
	db.SetMaxOpenConns(1)
	t.Cleanup(func() { db.Close() })
	if err := createSchema(db); err != nil {
		t.Fatal(err)
	}
	return &MessageStore{db: db}
}

// A later copy of a message without media details must not erase the download link or key.
func TestStoreMessageKeepsMediaWhenCopyHasNone(t *testing.T) {
	store := openTestStore(t)
	chat := "123456789012345678@g.us"
	if err := store.StoreChat(chat, "Test group", time.Now()); err != nil {
		t.Fatal(err)
	}

	key := []byte("0123456789abcdef0123456789abcdef")
	now := time.Now()
	if err := store.StoreMessage("M1", chat, "5511234567", "", now, false,
		"image", "photo.jpg", "https://example.test/media?oh=1", key, key, key, 1234); err != nil {
		t.Fatal(err)
	}
	if err := store.StoreMessage("M1", chat, "5511234567", "caption", now, false,
		"", "", "", nil, nil, nil, 0); err != nil {
		t.Fatal(err)
	}

	var content, mediaType, filename, url string
	var length int
	var mediaKey []byte
	err := store.db.QueryRow(
		"SELECT content, media_type, filename, url, file_length, media_key FROM messages WHERE id = ? AND chat_jid = ?",
		"M1", chat,
	).Scan(&content, &mediaType, &filename, &url, &length, &mediaKey)
	if err != nil {
		t.Fatal(err)
	}
	if content != "caption" {
		t.Errorf("content = %q, want the newer caption", content)
	}
	if mediaType != "image" || filename != "photo.jpg" || url == "" || length != 1234 {
		t.Errorf("media details were erased: type=%q file=%q url=%q length=%d", mediaType, filename, url, length)
	}
	if !bytes.Equal(mediaKey, key) {
		t.Errorf("media key was erased")
	}
}

// An empty chat name from a later update must not erase the name we already have.
func TestStoreChatKeepsNameOnEmptyUpdate(t *testing.T) {
	store := openTestStore(t)
	chat := "123456789012345678@g.us"
	if err := store.StoreChat(chat, "Test group", time.Now()); err != nil {
		t.Fatal(err)
	}
	if err := store.StoreChat(chat, "", time.Now()); err != nil {
		t.Fatal(err)
	}

	var name string
	var count int
	if err := store.db.QueryRow("SELECT COUNT(*), MAX(name) FROM chats WHERE jid = ?", chat).Scan(&count, &name); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Errorf("chat rows = %d, want 1", count)
	}
	if name != "Test group" {
		t.Errorf("name = %q, want %q", name, "Test group")
	}
}

// A renamed chat still gets its new name.
func TestStoreChatAcceptsNewName(t *testing.T) {
	store := openTestStore(t)
	chat := "123456789012345678@g.us"
	if err := store.StoreChat(chat, "Old name", time.Now()); err != nil {
		t.Fatal(err)
	}
	if err := store.StoreChat(chat, "New name", time.Now()); err != nil {
		t.Fatal(err)
	}
	var name string
	if err := store.db.QueryRow("SELECT name FROM chats WHERE jid = ?", chat).Scan(&name); err != nil {
		t.Fatal(err)
	}
	if name != "New name" {
		t.Errorf("name = %q, want %q", name, "New name")
	}
}

// The indexes that keep per-chat queries fast must exist after the schema is created.
func TestSchemaCreatesIndexes(t *testing.T) {
	store := openTestStore(t)
	want := []string{"idx_messages_chat_time", "idx_messages_chat_sender", "idx_messages_time", "idx_chats_last_message"}
	for _, name := range want {
		var found string
		err := store.db.QueryRow("SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?", name).Scan(&found)
		if err != nil {
			t.Errorf("index %s is missing: %v", name, err)
		}
	}
}
