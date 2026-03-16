# LAN Chat

A modern, modular LAN messenger built with Python and PySide6.  
Devices on the same local network automatically discover each other  
and can exchange text messages and files — no server required.

---

## Features

| Feature | Details |
|---|---|
| **Auto-discovery** | UDP broadcast – peers appear in the sidebar within seconds |
| **Text messaging** | TCP, delivered per-message; Enter to send, Shift+Enter for newline |
| **File transfer** | TCP streaming with live progress bar; files saved to `~/Downloads/LanChat/` |
| **Typing indicator** | "Alice is typing…" shown to the recipient, auto-hides |
| **Unread badges** | Red counter on sidebar rows for unread messages |
| **Rename yourself** | Click ✏️ in the toolbar; the new name is broadcast immediately |
| **Chat history** | Conversations are kept in memory for the session |
| **Dark UI** | Telegram-style grayscale theme; works on Windows and Linux |

---

## Requirements

```
Python 3.10+
PySide6
```

Install dependencies:

```bash
pip install PySide6
```

---

## Running

```bash
cd lan_chat
python main.py
```

Run on two or more machines on the **same subnet**.  
Firewall rules must allow UDP and TCP on ports **5555**, **5001**, **5002**.

---

## Project structure

```
lan_chat/
│
├── core/
│   ├── protocol.py        # Packet definition, framing helpers, constants
│   ├── discovery.py       # UDP broadcast peer discovery (DiscoveryService)
│   ├── messaging.py       # TCP text messages & typing (MessagingService)
│   ├── file_transfer.py   # TCP file streaming (FileTransferService)
│   └── encryption.py      # Pluggable cipher layer (XOR / Fernet / null)
│
├── ui/
│   ├── main_window.py     # Root QMainWindow; wires services ↔ UI
│   ├── device_sidebar.py  # Left panel: peer list + search (DeviceSidebar)
│   ├── chat_area.py       # Right panel: scrollable bubble history (ChatArea)
│   ├── message_bubble.py  # BubbleWidget + FileBubbleWidget
│   └── input_bar.py       # Text input + send + attach (InputBar)
│
├── assets/                # Icons / resources (extend as needed)
└── main.py                # Entry point; QApplication bootstrap
```

---

## Network protocol

### Discovery (UDP · port 5555)

```
Broadcast every 5 s:   HELLO   packet → peers learn we exist
Direct reply:          HELLO_ACK      → we learn about the broadcaster
Clean shutdown:        BYE broadcast  → peers remove us immediately
Timeout fallback:      15 s of silence → peer removed by reaper thread
```

### Messaging (TCP · port 5001)

Each message opens a short-lived TCP connection, sends one length-prefixed  
JSON packet, and closes.  This avoids managing persistent connections.

### File transfer (TCP · port 5002)

```
Client  →  FILE_OFFER header (framed JSON with filename + size)
Client  →  raw file bytes (streamed in 64 KB chunks)
Server  →  receives bytes, emits progress signals, saves file
```

### Packet format

```json
{
  "type":        "MESSAGE",
  "sender_name": "Alice",
  "sender_ip":   "192.168.1.42",
  "timestamp":   1700000000.0,
  "payload":     { "text": "Hello!" }
}
```

TCP packets are prefixed with a 4-byte big-endian length so the receiver  
knows exactly how many bytes to read before parsing JSON.

---

## Encryption (optional)

`core/encryption.py` provides three backends:

| Backend | Security | Dependency |
|---|---|---|
| `NullCipher` (default) | None – plain text | — |
| `XorCipher` | Obfuscation only | — |
| `FernetCipher` | AES-128-CBC + HMAC | `pip install cryptography` |

To enable encryption, wrap `Packet.to_json()` / `Packet.from_json()`  
calls through `cipher.encrypt()` / `cipher.decrypt()` in the service layer.

---

## Extending

- **Persistence** – serialize `_history` to SQLite or JSON on close/open.
- **Avatars** – add an `avatar_url` field to HELLO packets.
- **Group chat** – broadcast MESSAGE packets via UDP to all peers.
- **Read receipts** – add a `READ_ACK` packet type.
- **TLS** – replace raw sockets with `ssl.wrap_socket()`.
