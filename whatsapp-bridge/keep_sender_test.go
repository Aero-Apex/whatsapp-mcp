package main

import (
	"database/sql"
	"testing"
	"time"
)

// A history copy of a group message that names only the group must not replace the real sender.
func TestKeepKnownSender(t *testing.T) {
	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP, is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT, media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER, PRIMARY KEY (id, chat_jid))`); err != nil {
		t.Fatal(err)
	}
	store := &MessageStore{db: db}

	chat := "123456789012345678@g.us"
	group := "123456789012345678"
	person := "5511234567"
	now := time.Now()

	senderOf := func(id string) string {
		var sender string
		if err := db.QueryRow("SELECT sender FROM messages WHERE id = ? AND chat_jid = ?", id, chat).Scan(&sender); err != nil {
			t.Fatal(err)
		}
		return sender
	}

	// A live message stores the real sender.
	store.StoreMessage("M1", chat, person, "hello", now, false, "", "", "", nil, nil, nil, 0)

	// A history copy without a participant names the group: the real sender must survive.
	store.StoreMessage("M1", chat, group, "hello", now, false, "", "", "", nil, nil, nil, 0)
	if got := senderOf("M1"); got != person {
		t.Fatalf("history copy replaced the sender: got %q, want %q", got, person)
	}

	// A message only seen through history keeps the group as sender until a real one arrives.
	store.StoreMessage("M2", chat, group, "unknown", now, false, "", "", "", nil, nil, nil, 0)
	if got := senderOf("M2"); got != group {
		t.Fatalf("new unknown message: got %q, want %q", got, group)
	}
	store.StoreMessage("M2", chat, person, "unknown", now, false, "", "", "", nil, nil, nil, 0)
	if got := senderOf("M2"); got != person {
		t.Fatalf("real sender did not replace the unknown one: got %q, want %q", got, person)
	}
}
