package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"google.golang.org/protobuf/proto"
)

// registerActionRoutes adds endpoints for editing, reacting, read receipts, groups,
// contacts, presence and blocking. All of them are served on the localhost REST API.
func registerActionRoutes(client *whatsmeow.Client) {
	route(client, "/api/edit", func(ctx context.Context, req editRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		if req.Text == "" || req.MessageID == "" {
			return "", nil, fmt.Errorf("message_id and text are required")
		}
		newContent := &waE2E.Message{Conversation: proto.String(req.Text)}
		if _, err := client.SendMessage(ctx, chat, client.BuildEdit(chat, types.MessageID(req.MessageID), newContent)); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Edited message %s", req.MessageID), nil, nil
	})

	route(client, "/api/react", func(ctx context.Context, req reactRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		sender, err := optionalJID(req.SenderJID)
		if err != nil {
			return "", nil, err
		}
		if req.MessageID == "" {
			return "", nil, fmt.Errorf("message_id is required")
		}
		if _, err := client.SendMessage(ctx, chat, client.BuildReaction(chat, sender, types.MessageID(req.MessageID), req.Emoji)); err != nil {
			return "", nil, err
		}
		if req.Emoji == "" {
			return fmt.Sprintf("Removed reaction from %s", req.MessageID), nil, nil
		}
		return fmt.Sprintf("Reacted %s to %s", req.Emoji, req.MessageID), nil, nil
	})

	route(client, "/api/mark_read", func(ctx context.Context, req markReadRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		sender, err := optionalJID(req.SenderJID)
		if err != nil {
			return "", nil, err
		}
		ids := make([]types.MessageID, 0, len(req.MessageIDs))
		for _, id := range req.MessageIDs {
			ids = append(ids, types.MessageID(id))
		}
		if err := client.MarkRead(ctx, ids, time.Now(), chat, sender); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Marked %d message(s) as read", len(ids)), nil, nil
	})

	route(client, "/api/group/create", func(ctx context.Context, req createGroupRequest) (string, interface{}, error) {
		if req.Name == "" {
			return "", nil, fmt.Errorf("name is required")
		}
		participants, err := parseUserJIDs(req.Participants)
		if err != nil {
			return "", nil, err
		}
		info, err := client.CreateGroup(ctx, whatsmeow.ReqCreateGroup{Name: req.Name, Participants: participants})
		if err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Created group %s", info.JID), groupSummary(info), nil
	})

	route(client, "/api/group/info", func(ctx context.Context, req groupRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		info, err := client.GetGroupInfo(ctx, group)
		if err != nil {
			return "", nil, err
		}
		return "Group info", groupSummary(info), nil
	})

	route(client, "/api/group/joined", func(ctx context.Context, req emptyRequest) (string, interface{}, error) {
		groups, err := client.GetJoinedGroups(ctx)
		if err != nil {
			return "", nil, err
		}
		list := make([]map[string]interface{}, 0, len(groups))
		for _, g := range groups {
			list = append(list, map[string]interface{}{"jid": g.JID.String(), "name": g.Name})
		}
		return fmt.Sprintf("%d group(s)", len(list)), list, nil
	})

	route(client, "/api/group/participants", func(ctx context.Context, req groupParticipantsRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		participants, err := parseUserJIDs(req.Participants)
		if err != nil {
			return "", nil, err
		}
		var change whatsmeow.ParticipantChange
		switch req.Action {
		case "add":
			change = whatsmeow.ParticipantChangeAdd
		case "remove":
			change = whatsmeow.ParticipantChangeRemove
		case "promote":
			change = whatsmeow.ParticipantChangePromote
		case "demote":
			change = whatsmeow.ParticipantChangeDemote
		default:
			return "", nil, fmt.Errorf("action must be add, remove, promote or demote")
		}
		results, err := client.UpdateGroupParticipants(ctx, group, participants, change)
		if err != nil {
			return "", nil, err
		}
		list := make([]map[string]interface{}, 0, len(results))
		for _, p := range results {
			list = append(list, map[string]interface{}{"jid": p.JID.String(), "is_admin": p.IsAdmin, "is_super_admin": p.IsSuperAdmin})
		}
		return fmt.Sprintf("Applied %s to %d participant(s)", req.Action, len(participants)), list, nil
	})

	route(client, "/api/group/name", func(ctx context.Context, req groupNameRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		if req.Name == "" {
			return "", nil, fmt.Errorf("name is required")
		}
		if err := client.SetGroupName(ctx, group, req.Name); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Renamed group to %s", req.Name), nil, nil
	})

	route(client, "/api/group/topic", func(ctx context.Context, req groupTopicRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		info, err := client.GetGroupInfo(ctx, group)
		if err != nil {
			return "", nil, err
		}
		newID := string(whatsmeow.GenerateMessageID())
		if err := client.SetGroupTopic(ctx, group, info.TopicID, newID, req.Topic); err != nil {
			return "", nil, err
		}
		return "Updated group description", nil, nil
	})

	route(client, "/api/group/announce", func(ctx context.Context, req groupFlagRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		if err := client.SetGroupAnnounce(ctx, group, req.Enabled); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Only admins can send: %t", req.Enabled), nil, nil
	})

	route(client, "/api/group/locked", func(ctx context.Context, req groupFlagRequest) (string, interface{}, error) {
		group, err := parseJID(req.GroupJID)
		if err != nil {
			return "", nil, err
		}
		if err := client.SetGroupLocked(ctx, group, req.Enabled); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Only admins can edit group info: %t", req.Enabled), nil, nil
	})

	route(client, "/api/check_whatsapp", func(ctx context.Context, req checkRequest) (string, interface{}, error) {
		if len(req.Phones) == 0 {
			return "", nil, fmt.Errorf("phones is required")
		}
		results, err := client.IsOnWhatsApp(ctx, req.Phones)
		if err != nil {
			return "", nil, err
		}
		list := make([]map[string]interface{}, 0, len(results))
		for _, r := range results {
			list = append(list, map[string]interface{}{"query": r.Query, "jid": r.JID.String(), "on_whatsapp": r.IsIn})
		}
		return fmt.Sprintf("Checked %d number(s)", len(list)), list, nil
	})

	route(client, "/api/user_info", func(ctx context.Context, req userInfoRequest) (string, interface{}, error) {
		jids, err := parseUserJIDs(req.JIDs)
		if err != nil {
			return "", nil, err
		}
		infos, err := client.GetUserInfo(ctx, jids)
		if err != nil {
			return "", nil, err
		}
		list := make([]map[string]interface{}, 0, len(infos))
		for jid, info := range infos {
			list = append(list, map[string]interface{}{"jid": jid.String(), "status": info.Status, "picture_id": info.PictureID})
		}
		return fmt.Sprintf("Info for %d user(s)", len(list)), list, nil
	})

	route(client, "/api/presence", func(ctx context.Context, req presenceRequest) (string, interface{}, error) {
		chat, err := parseJID(req.ChatJID)
		if err != nil {
			return "", nil, err
		}
		state := types.ChatPresencePaused
		label := "stopped typing"
		if req.Typing {
			state = types.ChatPresenceComposing
			label = "typing"
		}
		if err := client.SendChatPresence(ctx, chat, state, types.ChatPresenceMediaText); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("Set presence to %s in %s", label, req.ChatJID), nil, nil
	})

	route(client, "/api/block", func(ctx context.Context, req blockRequest) (string, interface{}, error) {
		user, err := parseUserJID(req.JID)
		if err != nil {
			return "", nil, err
		}
		blocklist, err := client.GetBlocklist(ctx, "")
		if err != nil {
			return "", nil, err
		}
		action := events.BlocklistChangeActionUnblock
		label := "Unblocked"
		if req.Block {
			action = events.BlocklistChangeActionBlock
			label = "Blocked"
		}
		if _, err := client.UpdateBlocklist(ctx, user, action, blocklist.DHash); err != nil {
			return "", nil, err
		}
		return fmt.Sprintf("%s %s", label, user.String()), nil, nil
	})
}

type editRequest struct {
	ChatJID   string `json:"chat_jid"`
	MessageID string `json:"message_id"`
	Text      string `json:"text"`
}

type reactRequest struct {
	ChatJID   string `json:"chat_jid"`
	MessageID string `json:"message_id"`
	SenderJID string `json:"sender_jid"`
	Emoji     string `json:"emoji"`
}

type markReadRequest struct {
	ChatJID    string   `json:"chat_jid"`
	MessageIDs []string `json:"message_ids"`
	SenderJID  string   `json:"sender_jid"`
}

type createGroupRequest struct {
	Name         string   `json:"name"`
	Participants []string `json:"participants"`
}

type groupRequest struct {
	GroupJID string `json:"group_jid"`
}

type emptyRequest struct{}

type groupParticipantsRequest struct {
	GroupJID     string   `json:"group_jid"`
	Action       string   `json:"action"`
	Participants []string `json:"participants"`
}

type groupNameRequest struct {
	GroupJID string `json:"group_jid"`
	Name     string `json:"name"`
}

type groupTopicRequest struct {
	GroupJID string `json:"group_jid"`
	Topic    string `json:"topic"`
}

type groupFlagRequest struct {
	GroupJID string `json:"group_jid"`
	Enabled  bool   `json:"enabled"`
}

type checkRequest struct {
	Phones []string `json:"phones"`
}

type userInfoRequest struct {
	JIDs []string `json:"jids"`
}

type presenceRequest struct {
	ChatJID string `json:"chat_jid"`
	Typing  bool   `json:"typing"`
}

type blockRequest struct {
	JID   string `json:"jid"`
	Block bool   `json:"block"`
}

type actionResult struct {
	Success bool        `json:"success"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// route registers a POST endpoint that decodes its JSON body into T and runs fn.
func route[T any](client *whatsmeow.Client, path string, fn func(ctx context.Context, req T) (string, interface{}, error)) {
	http.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var req T
		if r.ContentLength != 0 {
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, "Invalid request format", http.StatusBadRequest)
				return
			}
		}
		if !client.IsConnected() {
			writeActionResult(w, http.StatusServiceUnavailable, actionResult{Message: "Not connected to WhatsApp"})
			return
		}
		message, data, err := fn(r.Context(), req)
		if err != nil {
			writeActionResult(w, http.StatusInternalServerError, actionResult{Message: err.Error()})
			return
		}
		writeActionResult(w, http.StatusOK, actionResult{Success: true, Message: message, Data: data})
	})
}

func writeActionResult(w http.ResponseWriter, status int, result actionResult) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(result)
}

// parseJID parses a full JID such as 123@g.us or 123@s.whatsapp.net.
func parseJID(raw string) (types.JID, error) {
	if raw == "" {
		return types.EmptyJID, fmt.Errorf("a chat or group JID is required")
	}
	return types.ParseJID(raw)
}

// parseUserJID accepts either a full JID or a bare phone number (digits only).
func parseUserJID(raw string) (types.JID, error) {
	if raw == "" {
		return types.EmptyJID, fmt.Errorf("a phone number or JID is required")
	}
	if strings.Contains(raw, "@") {
		return types.ParseJID(raw)
	}
	return types.JID{User: raw, Server: "s.whatsapp.net"}, nil
}

func parseUserJIDs(raw []string) ([]types.JID, error) {
	jids := make([]types.JID, 0, len(raw))
	for _, s := range raw {
		jid, err := parseUserJID(s)
		if err != nil {
			return nil, err
		}
		jids = append(jids, jid)
	}
	return jids, nil
}

// optionalJID returns the empty JID (meaning "this account") when raw is blank.
func optionalJID(raw string) (types.JID, error) {
	if raw == "" {
		return types.EmptyJID, nil
	}
	return parseUserJID(raw)
}

func groupSummary(info *types.GroupInfo) map[string]interface{} {
	participants := make([]map[string]interface{}, 0, len(info.Participants))
	for _, p := range info.Participants {
		participants = append(participants, map[string]interface{}{
			"jid":            p.JID.String(),
			"is_admin":       p.IsAdmin,
			"is_super_admin": p.IsSuperAdmin,
		})
	}
	return map[string]interface{}{
		"jid":              info.JID.String(),
		"name":             info.Name,
		"topic":            info.Topic,
		"owner":            info.OwnerJID.String(),
		"only_admins_send": info.IsAnnounce,
		"only_admins_edit": info.IsLocked,
		"is_community":     info.IsParent,
		"parent_community": info.LinkedParentJID.String(),
		"is_default_sub":   info.IsDefaultSubGroup,
		"participants":     participants,
	}
}
