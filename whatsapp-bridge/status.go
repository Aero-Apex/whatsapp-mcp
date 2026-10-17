package main

import (
	"encoding/json"
	"net/http"
	"time"

	"go.mau.fi/whatsmeow"
)

// bridgeVersion is reported by /api/status so users and the MCP server can see which build is running.
const bridgeVersion = "1.0.0"

var bridgeStartedAt = time.Now()

// registerStatusRoutes adds GET /api/status. It answers even when WhatsApp is disconnected,
// so it can show why the bridge cannot send or receive.
func registerStatusRoutes(client *whatsmeow.Client, store *MessageStore) {
	http.HandleFunc("/api/status", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		status := map[string]interface{}{
			"version":        bridgeVersion,
			"uptime_seconds": int(time.Since(bridgeStartedAt).Seconds()),
			"connected":      client.IsConnected(),
			"logged_in":      client.IsLoggedIn(),
		}
		if client.Store != nil && client.Store.ID != nil {
			status["linked_number"] = client.Store.ID.User
		}

		var chats, messages, media int
		var newest string
		err := store.db.QueryRow(`SELECT
			(SELECT COUNT(*) FROM chats),
			(SELECT COUNT(*) FROM messages),
			(SELECT COUNT(*) FROM messages WHERE media_type IS NOT NULL AND media_type != ''),
			COALESCE((SELECT MAX(timestamp) FROM messages), '')`).Scan(&chats, &messages, &media, &newest)
		if err != nil {
			http.Error(w, "could not read the store: "+err.Error(), http.StatusInternalServerError)
			return
		}
		status["chats"] = chats
		status["messages"] = messages
		status["media_messages"] = media
		status["newest_message"] = newest

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": true,
			"message": "Bridge status",
			"data":    status,
		})
	})
}
