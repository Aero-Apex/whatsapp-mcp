package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/hmac"
	"crypto/sha256"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
)

// mediaMACLength is the length of the authentication tag at the end of every encrypted WhatsApp media file.
const mediaMACLength = 10

// downloadRetriedMedia fetches a copy of a media file that the phone uploaded again after a retry request,
// and decrypts it with the message's media key.
//
// The re-uploaded copy can differ from the original upload, so the hashes stored for the original cannot
// check it. The file's own authentication tag, made with the media key, still proves the copy came from
// the phone that sent the message, so that tag is the check used here.
func downloadRetriedMedia(storedURL, directPath string, mediaKey []byte, mediaType whatsmeow.MediaType, mmsType string) ([]byte, error) {
	if len(mediaKey) != 32 {
		return nil, fmt.Errorf("unexpected media key length %d", len(mediaKey))
	}
	parsed, err := url.Parse(storedURL)
	if err != nil || parsed.Host == "" {
		return nil, fmt.Errorf("cannot work out the media host from the stored link")
	}
	if !strings.HasPrefix(directPath, "/") {
		return nil, fmt.Errorf("media download path does not start with slash: %s", directPath)
	}
	separator := "?"
	if strings.Contains(directPath, "?") {
		separator = "&"
	}
	target := fmt.Sprintf("https://%s%s%smms-type=%s&__wa-mms=", parsed.Host, directPath, separator, mmsType)

	request, err := http.NewRequest(http.MethodGet, target, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Origin", "https://web.whatsapp.com")
	request.Header.Set("Referer", "https://web.whatsapp.com/")
	client := &http.Client{Timeout: 3 * time.Minute}
	response, err := client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("could not fetch the re-uploaded media: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("the re-uploaded media returned HTTP %d", response.StatusCode)
	}
	data, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	if len(data) <= mediaMACLength || (len(data)-mediaMACLength)%aes.BlockSize != 0 {
		return nil, fmt.Errorf("the re-uploaded media has an unexpected size (%d bytes)", len(data))
	}

	expanded, err := hkdf.Key(sha256.New, mediaKey, nil, string(mediaType), 112)
	if err != nil {
		return nil, err
	}
	iv, cipherKey, macKey := expanded[:16], expanded[16:48], expanded[48:80]
	ciphertext, tag := data[:len(data)-mediaMACLength], data[len(data)-mediaMACLength:]

	mac := hmac.New(sha256.New, macKey)
	mac.Write(iv)
	mac.Write(ciphertext)
	if !hmac.Equal(mac.Sum(nil)[:mediaMACLength], tag) {
		return nil, fmt.Errorf("the phone sent a new copy, but it could not be verified with this message's media key")
	}

	block, err := aes.NewCipher(cipherKey)
	if err != nil {
		return nil, err
	}
	plain := make([]byte, len(ciphertext))
	cipher.NewCBCDecrypter(block, iv).CryptBlocks(plain, ciphertext)
	return unpadPKCS7(plain)
}

// unpadPKCS7 removes the padding that WhatsApp media encryption adds to reach a whole cipher block.
func unpadPKCS7(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return nil, fmt.Errorf("empty media")
	}
	padding := int(data[len(data)-1])
	if padding < 1 || padding > aes.BlockSize || padding > len(data) {
		return nil, fmt.Errorf("invalid media padding")
	}
	return data[:len(data)-padding], nil
}
