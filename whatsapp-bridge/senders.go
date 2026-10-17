package main

import (
	"strings"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/types"
)

var senderNamesOnce sync.Once
var senderNamesErr error

// ensureSenderNames creates the table that remembers each person's WhatsApp display name.
func (store *MessageStore) ensureSenderNames() error {
	senderNamesOnce.Do(func() {
		_, senderNamesErr = store.db.Exec(
			"CREATE TABLE IF NOT EXISTS sender_names (user TEXT PRIMARY KEY, name TEXT, updated TIMESTAMP)",
		)
	})
	return senderNamesErr
}

// StoreSenderName remembers the display name (WhatsApp "push name") of a message sender.
func (store *MessageStore) StoreSenderName(user, name string) error {
	if user == "" || name == "" {
		return nil
	}
	if err := store.ensureSenderNames(); err != nil {
		return err
	}
	_, err := store.db.Exec(
		"INSERT INTO sender_names (user, name, updated) VALUES (?, ?, ?) "+
			"ON CONFLICT(user) DO UPDATE SET name = excluded.name, updated = excluded.updated",
		user, name, time.Now(),
	)
	return err
}

// historySender works out who sent a message that arrived through history sync.
//
// Messages in a group carry the participant on the message itself, not only on its key, and the
// participant can be a phone-number JID or a LID. The returned sender is the bare user part,
// the same form live messages are stored in.
func historySender(client *whatsmeow.Client, chat types.JID, fromMe bool, keyParticipant, messageParticipant string) (string, bool) {
	if fromMe {
		if client.Store.ID != nil {
			return client.Store.ID.User, true
		}
		return chat.User, true
	}
	participant := keyParticipant
	if participant == "" {
		participant = messageParticipant
	}
	if participant == "" {
		return chat.User, false
	}
	if parsed, err := types.ParseJID(participant); err == nil {
		return parsed.User, false
	}
	return participant, false
}

// keepKnownSender stops a history copy of a group message from replacing the sender already on record.
//
// Some history copies arrive without the participant, so they name the group itself as the sender.
// Storing that would throw away the real sender we already have, so the known sender is kept.
func keepKnownSender(store *MessageStore, id, chatJID, sender string, isFromMe bool) string {
	if isFromMe || id == "" || sender != strings.SplitN(chatJID, "@", 2)[0] {
		return sender
	}
	var known string
	err := store.db.QueryRow("SELECT sender FROM messages WHERE id = ? AND chat_jid = ?", id, chatJID).Scan(&known)
	if err == nil && known != "" && known != sender {
		return known
	}
	return sender
}
