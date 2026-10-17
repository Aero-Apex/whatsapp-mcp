package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/store/sqlstore"
	waLog "go.mau.fi/whatsmeow/util/log"
)

// The status endpoint must answer even when WhatsApp is not connected, and say so.
func TestStatusEndpointReportsDisconnected(t *testing.T) {
	store := openTestStore(t)
	container, err := sqlstore.New(context.Background(), "sqlite3",
		"file:"+filepath.Join(t.TempDir(), "whatsapp.db")+"?_foreign_keys=on", waLog.Stdout("Test", "ERROR", true))
	if err != nil {
		t.Fatal(err)
	}
	client := whatsmeow.NewClient(container.NewDevice(), waLog.Stdout("Test", "ERROR", true))

	registerStatusRoutes(client, store)

	recorder := httptest.NewRecorder()
	http.DefaultServeMux.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/status", nil))
	if recorder.Code != http.StatusOK {
		t.Fatalf("status code = %d, want 200", recorder.Code)
	}

	var body struct {
		Success bool                   `json:"success"`
		Data    map[string]interface{} `json:"data"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("response is not JSON: %v", err)
	}
	if !body.Success {
		t.Error("success = false, want true")
	}
	if body.Data["connected"] != false || body.Data["logged_in"] != false {
		t.Errorf("connected/logged_in = %v/%v, want false/false", body.Data["connected"], body.Data["logged_in"])
	}
	if body.Data["version"] != bridgeVersion {
		t.Errorf("version = %v, want %s", body.Data["version"], bridgeVersion)
	}
	if body.Data["messages"] != float64(0) {
		t.Errorf("messages = %v, want 0 for an empty store", body.Data["messages"])
	}
}
