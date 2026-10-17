package main

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"google.golang.org/protobuf/proto"
)

// TouchChat makes sure a chat row exists and bumps its last-message time without
// overwriting a name that is already stored.
func (store *MessageStore) TouchChat(jid, name string, lastMessageTime time.Time) error {
	_, err := store.db.Exec(
		"INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?) "+
			"ON CONFLICT(jid) DO UPDATE SET last_message_time = excluded.last_message_time",
		jid, name, lastMessageTime,
	)
	return err
}

// recordSent stores a message sent through the REST API so it can be listed and deleted later.
func recordSent(chat types.JID, id string, content string) {
	if messageStoreForSend == nil {
		return
	}
	chatJID := chat.String()
	if err := messageStoreForSend.TouchChat(chatJID, chat.User, time.Now()); err != nil {
		fmt.Printf("failed to store chat: %v\n", err)
	}
	if err := messageStoreForSend.StoreMessage(id, chatJID, "me", content, time.Now(), true, "", "", "", nil, nil, nil, 0); err != nil {
		fmt.Printf("failed to store sent message: %v\n", err)
	}
}

// sendAndRecord sends msg to chat and records it. content is what the message looks like in the local history.
func sendAndRecord(ctx context.Context, client *whatsmeow.Client, chat types.JID, msg *waE2E.Message, content string) (string, interface{}, error) {
	sent, err := client.SendMessage(ctx, chat, msg)
	if err != nil {
		return "", nil, err
	}
	id := string(sent.ID)
	recordSent(chat, id, content)
	return fmt.Sprintf("Sent (id %s)", id), map[string]interface{}{"message_id": id}, nil
}

// inviteCode accepts either a bare invite code or a full chat.whatsapp.com link.
func inviteCode(link string) string {
	code := strings.TrimSpace(link)
	if i := strings.Index(code, "?"); i >= 0 {
		code = code[:i]
	}
	if i := strings.LastIndex(code, "/"); i >= 0 {
		code = code[i+1:]
	}
	return code
}

// registerMoreActionRoutes adds replies, polls, locations, contacts, chat management,
// invite links and account/profile endpoints to the localhost REST API.
func registerMoreActionRoutes(client *whatsmeow.Client) {
	route(client, "/api/reply", func(ctx context.Context, req replyRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		if req.MessageID == "" || req.Text == "" {
			return "", nil, fmt.Errorf("message_id and text are required")
		}
		participant := req.SenderJID
		if participant == "" && chat.Server != types.GroupServer {
			participant = chat.String()
		}
		contextInfo := &waE2E.ContextInfo{StanzaID: proto.String(req.MessageID)}
		if participant != "" {
			contextInfo.Participant = proto.String(participant)
		}
		if req.QuotedText != "" {
			contextInfo.QuotedMessage = &waE2E.Message{Conversation: proto.String(req.QuotedText)}
		}
		msg := &waE2E.Message{ExtendedTextMessage: &waE2E.ExtendedTextMessage{
			Text:        proto.String(req.Text),
			ContextInfo: contextInfo,
		}}
		return sendAndRecord(ctx, client, chat, msg, req.Text)
	})

	route(client, "/api/send_location", func(ctx context.Context, req locationRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		if req.Latitude < -90 || req.Latitude > 90 || req.Longitude < -180 || req.Longitude > 180 {
			return "", nil, fmt.Errorf("latitude must be between -90 and 90 and longitude between -180 and 180")
		}
		location := &waE2E.LocationMessage{
			DegreesLatitude:  proto.Float64(req.Latitude),
			DegreesLongitude: proto.Float64(req.Longitude),
		}
		if req.Name != "" {
			location.Name = proto.String(req.Name)
		}
		if req.Address != "" {
			location.Address = proto.String(req.Address)
		}
		label := req.Name
		if label == "" {
			label = fmt.Sprintf("%.5f, %.5f", req.Latitude, req.Longitude)
		}
		return sendAndRecord(ctx, client, chat, &waE2E.Message{LocationMessage: location}, "[location] "+label)
	})

	route(client, "/api/send_contact", func(ctx context.Context, req contactRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		phone := strings.TrimPrefix(strings.TrimSpace(req.ContactPhone), "+")
		if req.ContactName == "" || phone == "" {
			return "", nil, fmt.Errorf("contact_name and contact_phone are required")
		}
		vcard := fmt.Sprintf("BEGIN:VCARD\nVERSION:3.0\nFN:%s\nTEL;type=CELL;waid=%s:+%s\nEND:VCARD", req.ContactName, phone, phone)
		msg := &waE2E.Message{ContactMessage: &waE2E.ContactMessage{
			DisplayName: proto.String(req.ContactName),
			Vcard:       proto.String(vcard),
		}}
		return sendAndRecord(ctx, client, chat, msg, "[contact] "+req.ContactName)
	})

	route(client, "/api/send_poll", func(ctx context.Context, req pollRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		if req.Question == "" {
			return "", nil, fmt.Errorf("question is required")
		}
		if len(req.Options) < 2 || len(req.Options) > 12 {
			return "", nil, fmt.Errorf("a poll needs between 2 and 12 options")
		}
		selectable := req.SelectableCount
		if selectable < 1 || selectable > len(req.Options) {
			selectable = 1
		}
		msg := client.BuildPollCreation(req.Question, req.Options, selectable)
		return sendAndRecord(ctx, client, chat, msg, "[poll] "+req.Question)
	})

	route(client, "/api/disappearing", func(ctx context.Context, req disappearingRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		if err := client.SetDisappearingTimer(ctx, chat, time.Duration(req.Seconds)*time.Second, time.Time{}); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Disappearing messages timer set to %d seconds", req.Seconds), nil, nil
	})

	route(client, "/api/group/invite", func(ctx context.Context, req inviteRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		link, err := client.GetGroupInviteLink(ctx, group, req.Reset)
		if err != nil {
			return "", nil, err
		}
		return "Invite link", map[string]interface{}{"link": link}, nil
	})

	route(client, "/api/group/link_info", func(ctx context.Context, req linkRequest) (string, interface{}, error) {
		code := inviteCode(req.Link)
		if code == "" {
			return "", nil, fmt.Errorf("an invite link is required")
		}
		info, err := client.GetGroupInfoFromLink(ctx, code)
		if err != nil {
			return "", nil, err
		}
		return "Group info from invite link", groupSummary(info), nil
	})

	route(client, "/api/group/join", func(ctx context.Context, req linkRequest) (string, interface{}, error) {
		code := inviteCode(req.Link)
		if code == "" {
			return "", nil, fmt.Errorf("an invite link is required")
		}
		jid, err := client.JoinGroupWithLink(ctx, code)
		if err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Joined group %s", jid), map[string]interface{}{"group_jid": jid.String()}, nil
	})

	route(client, "/api/status", func(ctx context.Context, req statusRequest) (string, interface{}, error) {
		text := req.Text
		if err := client.SetStatusMessage(ctx, types.SetStatusInput{Text: &text}); err != nil {
			return "", nil, err
		}
		return "Updated your About text", nil, nil
	})

	route(client, "/api/profile_picture", func(ctx context.Context, req jidRequest) (string, interface{}, error) {
		jid, err := parseUserJID(req.JID)
		if err != nil {
			return "", nil, err
		}
		info, err := client.GetProfilePictureInfo(ctx, jid, nil)
		if errors.Is(err, whatsmeow.ErrProfilePictureNotSet) {
			return "No profile picture set", nil, nil
		}
		if errors.Is(err, whatsmeow.ErrProfilePictureUnauthorized) {
			return "", nil, fmt.Errorf("the profile picture is hidden by privacy settings")
		}
		if err != nil {
			return "", nil, err
		}
		if info == nil {
			return "No profile picture set", nil, nil
		}
		return "Profile picture", map[string]interface{}{"url": info.URL, "id": info.ID, "type": info.Type}, nil
	})

	route(client, "/api/set_presence", func(ctx context.Context, req presenceAvailableRequest) (string, interface{}, error) {
		state := types.PresenceUnavailable
		if req.Available {
			state = types.PresenceAvailable
		}
		if err := client.SendPresence(ctx, state); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Presence set to %s", state), nil, nil
	})

	route(client, "/api/privacy", func(ctx context.Context, req emptyRequest) (string, interface{}, error) {
		s := client.GetPrivacySettings(ctx)
		return "Privacy settings", map[string]interface{}{
			"group_add":     string(s.GroupAdd),
			"last_seen":     string(s.LastSeen),
			"status":        string(s.Status),
			"profile":       string(s.Profile),
			"read_receipts": string(s.ReadReceipts),
			"call_add":      string(s.CallAdd),
			"online":        string(s.Online),
			"messages":      string(s.Messages),
			"stickers":      string(s.Stickers),
		}, nil
	})

	route(client, "/api/blocklist", func(ctx context.Context, req emptyRequest) (string, interface{}, error) {
		blocklist, err := client.GetBlocklist(ctx, "")
		if err != nil {
			return "", nil, err
		}
		items := make([]map[string]interface{}, 0, len(blocklist.Items))
		for _, item := range blocklist.Items {
			items = append(items, map[string]interface{}{
				"lid":    item.LID.String(),
				"phone":  item.PN.String(),
				"active": item.Active,
			})
		}
		return fmt.Sprintf("%d blocked", len(items)), items, nil
	})
}

type replyRequest struct {
	ChatJID    string `json:"chat_jid"`
	MessageID  string `json:"message_id"`
	Text       string `json:"text"`
	SenderJID  string `json:"sender_jid"`
	QuotedText string `json:"quoted_text"`
}

type locationRequest struct {
	ChatJID   string  `json:"chat_jid"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
	Name      string  `json:"name"`
	Address   string  `json:"address"`
}

type contactRequest struct {
	ChatJID      string `json:"chat_jid"`
	ContactName  string `json:"contact_name"`
	ContactPhone string `json:"contact_phone"`
}

type pollRequest struct {
	ChatJID         string   `json:"chat_jid"`
	Question        string   `json:"question"`
	Options         []string `json:"options"`
	SelectableCount int      `json:"selectable_count"`
}

type disappearingRequest struct {
	ChatJID string `json:"chat_jid"`
	Seconds int    `json:"seconds"`
}

type inviteRequest struct {
	GroupJID string `json:"group_jid"`
	Reset    bool   `json:"reset"`
}

type linkRequest struct {
	Link string `json:"link"`
}

type statusRequest struct {
	Text string `json:"text"`
}

type jidRequest struct {
	JID string `json:"jid"`
}

type presenceAvailableRequest struct {
	Available bool `json:"available"`
}
