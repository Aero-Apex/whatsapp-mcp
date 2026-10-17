package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
)

// ---------------------------------------------------------------------------
// On-demand history: ask the phone for messages older than a given message.
// ---------------------------------------------------------------------------

type loadHistoryRequest struct {
	ChatJID         string `json:"chat_jid"`
	Count           int    `json:"count"`
	BeforeMessageID string `json:"before_message_id"` // a message ID, "newest", or empty for the oldest stored message
	WaitSeconds     int    `json:"wait_seconds"`
}

type anchorMessage struct {
	id     string
	ts     time.Time
	fromMe bool
}

type chatStats struct {
	Messages       int    `json:"messages"`
	Oldest         string `json:"oldest"`
	KnownSenders   int    `json:"messages_with_known_sender"`
	chatUserSender string
}

func readChatStats(db *sql.DB, chat types.JID) (chatStats, error) {
	stats := chatStats{chatUserSender: chat.User}
	err := db.QueryRow(
		"SELECT COUNT(*), COALESCE(MIN(timestamp), ''), COALESCE(SUM(CASE WHEN sender != ? THEN 1 ELSE 0 END), 0) FROM messages WHERE chat_jid = ?",
		chat.User, chat.String(),
	).Scan(&stats.Messages, &stats.Oldest, &stats.KnownSenders)
	return stats, err
}

func findAnchor(db *sql.DB, chatJID, beforeID string) (anchorMessage, error) {
	var a anchorMessage
	var row *sql.Row
	switch beforeID {
	case "":
		row = db.QueryRow("SELECT id, timestamp, is_from_me FROM messages WHERE chat_jid = ? ORDER BY timestamp ASC LIMIT 1", chatJID)
	case "newest":
		row = db.QueryRow("SELECT id, timestamp, is_from_me FROM messages WHERE chat_jid = ? ORDER BY timestamp DESC LIMIT 1", chatJID)
	default:
		row = db.QueryRow("SELECT id, timestamp, is_from_me FROM messages WHERE chat_jid = ? AND id = ?", chatJID, beforeID)
	}
	if err := row.Scan(&a.id, &a.ts, &a.fromMe); err != nil {
		return a, fmt.Errorf("no stored message to anchor the request on: %w", err)
	}
	return a, nil
}

// registerHistoryRoutes adds the endpoint that loads older messages from the phone.
func registerHistoryRoutes(client *whatsmeow.Client) {
	route(client, "/api/load_history", func(ctx context.Context, req loadHistoryRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		if messageStoreForSend == nil {
			return "", nil, fmt.Errorf("message store is not ready")
		}
		db := messageStoreForSend.db

		count := req.Count
		if count <= 0 {
			count = 50
		}
		if count > 100 {
			count = 100
		}
		wait := req.WaitSeconds
		if wait <= 0 {
			wait = 20
		}
		if wait > 45 {
			wait = 45
		}

		anchor, err := findAnchor(db, chat.String(), req.BeforeMessageID)
		if err != nil {
			return "", nil, err
		}
		before, err := readChatStats(db, chat)
		if err != nil {
			return "", nil, err
		}

		info := &types.MessageInfo{
			MessageSource: types.MessageSource{
				Chat:     chat,
				IsFromMe: anchor.fromMe,
				IsGroup:  chat.Server == types.GroupServer,
			},
			ID:        types.MessageID(anchor.id),
			Timestamp: anchor.ts,
		}
		if _, err := client.SendPeerMessage(ctx, client.BuildHistorySyncRequest(info, count)); err != nil {
			return "", nil, fmt.Errorf("could not send the history request: %w", err)
		}

		// The phone answers asynchronously; the history handler stores what arrives.
		deadline := time.Now().Add(time.Duration(wait) * time.Second)
		after := before
		lastChange := time.Time{}
		for time.Now().Before(deadline) {
			time.Sleep(2 * time.Second)
			current, err := readChatStats(db, chat)
			if err != nil {
				break
			}
			if current != after {
				// The batch may still be arriving: remember the change and keep waiting until things go quiet
				after = current
				lastChange = time.Now()
				continue
			}
			if !lastChange.IsZero() && time.Since(lastChange) >= 4*time.Second {
				break
			}
		}

		result := map[string]interface{}{
			"anchor_message_id":    anchor.id,
			"before":               before,
			"after":                after,
			"new_messages":         after.Messages - before.Messages,
			"senders_resolved":     after.KnownSenders - before.KnownSenders,
			"oldest_message_after": after.Oldest,
		}
		if after == before {
			return "No new data arrived. The phone may be offline, or there is nothing older to load.", result, nil
		}
		return fmt.Sprintf("Loaded history: %d new message(s), %d sender(s) resolved", after.Messages-before.Messages, after.KnownSenders-before.KnownSenders), result, nil
	})
}

// ---------------------------------------------------------------------------
// Expired media: ask the phone to upload the file again, then download it.
// ---------------------------------------------------------------------------

var mediaRetryWaiters sync.Map // message ID -> chan *events.MediaRetry

// deliverMediaRetry hands a media-retry answer from the phone to whoever is waiting for it.
func deliverMediaRetry(evt *events.MediaRetry) {
	if ch, ok := mediaRetryWaiters.Load(string(evt.MessageID)); ok {
		select {
		case ch.(chan *events.MediaRetry) <- evt:
		default:
		}
	}
}

func isExpiredMediaError(err error) bool {
	if errors.Is(err, whatsmeow.ErrMediaDownloadFailedWith403) ||
		errors.Is(err, whatsmeow.ErrMediaDownloadFailedWith404) ||
		errors.Is(err, whatsmeow.ErrMediaDownloadFailedWith410) {
		return true
	}
	text := err.Error()
	return strings.Contains(text, "status code 403") || strings.Contains(text, "status code 404") || strings.Contains(text, "status code 410")
}

// groupSenderJID rebuilds a participant's full JID from the bare user stored in the database.
func groupSenderJID(client *whatsmeow.Client, user string) types.JID {
	lid := types.JID{User: user, Server: types.HiddenUserServer}
	if pn, err := client.Store.LIDs.GetPNForLID(context.Background(), lid); err == nil && !pn.IsEmpty() {
		return lid
	}
	return types.JID{User: user, Server: types.DefaultUserServer}
}

func redownloadViaPhone(client *whatsmeow.Client, store *MessageStore, messageID, chatJID, mediaType string, d *MediaDownloader) ([]byte, error) {
	chat, err := types.ParseJID(chatJID)
	if err != nil {
		return nil, err
	}

	var sender string
	var fromMe bool
	if err := store.db.QueryRow("SELECT sender, is_from_me FROM messages WHERE id = ? AND chat_jid = ?", messageID, chatJID).Scan(&sender, &fromMe); err != nil {
		return nil, fmt.Errorf("message not found: %w", err)
	}

	info := &types.MessageInfo{
		ID: types.MessageID(messageID),
		MessageSource: types.MessageSource{
			Chat:     chat,
			IsFromMe: fromMe,
			IsGroup:  chat.Server == types.GroupServer,
		},
	}
	if chat.Server == types.GroupServer && !fromMe {
		if sender == "" || sender == chat.User {
			return nil, fmt.Errorf("the original sender of this group message is unknown; load the chat history first")
		}
		info.Sender = groupSenderJID(client, sender)
	}

	waiter := make(chan *events.MediaRetry, 1)
	mediaRetryWaiters.Store(messageID, waiter)
	defer mediaRetryWaiters.Delete(messageID)

	ctx := context.Background()
	if err := client.SendMediaRetryReceipt(ctx, info, d.MediaKey); err != nil {
		return nil, fmt.Errorf("could not ask the phone for the media: %w", err)
	}

	select {
	case evt := <-waiter:
		notification, err := whatsmeow.DecryptMediaRetryNotification(evt, d.MediaKey)
		if err != nil {
			return nil, err
		}
		if result := notification.GetResult().String(); result != "SUCCESS" {
			return nil, fmt.Errorf("the phone could not provide the media (%s)", result)
		}
		return downloadRetriedMedia(d.URL, notification.GetDirectPath(), d.MediaKey, d.MediaType, mediaType)
	case <-time.After(45 * time.Second):
		return nil, fmt.Errorf("timed out waiting for the phone to upload the media again (is the phone online?)")
	}
}
