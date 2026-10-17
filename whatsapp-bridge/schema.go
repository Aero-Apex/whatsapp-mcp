package main

import "database/sql"

// createSchema creates the tables and indexes that the bridge and the MCP server read.
// The indexes keep per-chat queries fast once a chat has tens of thousands of messages.
func createSchema(db *sql.DB) error {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS chats (
			jid TEXT PRIMARY KEY,
			name TEXT,
			last_message_time TIMESTAMP
		);

		CREATE TABLE IF NOT EXISTS messages (
			id TEXT,
			chat_jid TEXT,
			sender TEXT,
			content TEXT,
			timestamp TIMESTAMP,
			is_from_me BOOLEAN,
			media_type TEXT,
			filename TEXT,
			url TEXT,
			media_key BLOB,
			file_sha256 BLOB,
			file_enc_sha256 BLOB,
			file_length INTEGER,
			PRIMARY KEY (id, chat_jid),
			FOREIGN KEY (chat_jid) REFERENCES chats(jid)
		);

		CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages (chat_jid, timestamp);
		CREATE INDEX IF NOT EXISTS idx_messages_chat_sender ON messages (chat_jid, sender);
		CREATE INDEX IF NOT EXISTS idx_messages_time ON messages (timestamp);
		CREATE INDEX IF NOT EXISTS idx_chats_last_message ON chats (last_message_time);
	`)
	return err
}
