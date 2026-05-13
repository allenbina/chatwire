# MQTT Output

## What it does

The MQTT plugin publishes every inbound iMessage to an MQTT broker as a JSON event. This lets home-automation systems (Home Assistant, Node-RED, OpenHAB, etc.) react to your messages — trigger lights, log conversations, forward to other channels — without polling or screen-scraping.

Every message is published to a topic derived from the sender's handle or group chat identifier. The JSON payload includes the sender handle, message text, direction (`is_from_me`), and structured chat metadata.

## Install command

```bash
pipx inject chatwire chatwire-mqtt
# or inside the chatwire venv:
pip install chatwire-mqtt
```

Then restart the chatwire bridge:

```bash
launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge
```

## Configuration walkthrough

1. Open chatwire in your browser (`http://localhost:8723`).
2. Go to **Settings** → **Plugins** → **MQTT**.
3. Toggle **Enabled** to ON.
4. Enter your **Broker host** (IP or hostname of your MQTT broker).
5. Adjust **Port**, **Username/Password**, and **QoS** as needed.
6. For encrypted brokers: toggle **Use TLS/SSL** and (for self-signed CAs) enter the **CA certificate path**.
7. Changes save automatically. The plugin connects immediately upon save.

## Topic layout

```
<base_topic>/<sanitized_handle>           ← 1:1 conversation
<base_topic>/group/<sanitized_chat_id>    ← group chat
```

The default base topic is `chatwire/messages`. MQTT wildcard characters (`+`, `#`, `/`) in handle or chat identifiers are replaced with underscores.

**Examples:**

| Sender / chat | Published topic |
|---------------|-----------------|
| `+15551234567` (1:1) | `chatwire/messages/_15551234567` |
| `chat123` (group) | `chatwire/messages/group/chat123` |

## Payload schema (v=1)

```json
{
  "v": 1,
  "rowid": 12345,
  "handle": "+15551234567",
  "text": "Hey, what's up?",
  "is_from_me": false,
  "chat": {
    "guid": "iMessage;-;+15551234567",
    "identifier": "+15551234567",
    "name": null,
    "is_group": false
  }
}
```

`chat` is `null` when the message has no associated chat record.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `host` | string | *(required)* | Hostname or IP of the MQTT broker. |
| `port` | integer | `1883` | Broker port. Use `8883` for TLS. |
| `topic` | string | `"chatwire/messages"` | Base topic prefix. |
| `username` | string | `""` | Broker username (optional). |
| `password` | string | `""` | Broker password (optional). |
| `qos` | integer | `0` | Quality of Service: `0` at-most-once, `1` at-least-once, `2` exactly-once. |
| `client_id` | string | `"chatwire"` | MQTT client identifier. Must be unique on the broker. |
| `use_tls` | boolean | `false` | Enable TLS/SSL encryption. |
| `ca_cert` | string | `""` | Path to a PEM CA certificate. Blank = system CA bundle. |

Config file path: `~/.chatwire/config.json` under `integrations.chatwire_mqtt`.

### Minimal config

```json
{
  "integrations": {
    "chatwire_mqtt": {
      "enabled": true,
      "host": "192.168.1.100"
    }
  }
}
```

### Full config with TLS

```json
{
  "integrations": {
    "chatwire_mqtt": {
      "enabled": true,
      "host": "mqtt.home.example.com",
      "port": 8883,
      "topic": "chatwire/messages",
      "username": "chatwire",
      "password": "s3cr3t",
      "qos": 1,
      "client_id": "chatwire-bridge",
      "use_tls": true,
      "ca_cert": "/etc/ssl/certs/mosquitto-ca.pem"
    }
  }
}
```

## Home Assistant example

Add an MQTT trigger to an automation:

```yaml
trigger:
  - platform: mqtt
    topic: "chatwire/messages/+"
    value_template: "{{ value_json.text }}"

action:
  - service: notify.mobile_app_iphone
    data:
      message: "iMessage from {{ trigger.payload_json.handle }}: {{ trigger.payload_json.text }}"
```

Subscribe to all 1:1 messages with the `+` wildcard, or use `chatwire/messages/#` to include group chats.

## Troubleshooting / FAQ

**The plugin connects but no messages arrive.**
Confirm `is_from_me` filtering: the plugin publishes *all* messages, including outbound (`is_from_me: true`). Use your subscriber's filter or check `is_from_me` in the payload.

**Connection fails with "cannot connect".**
Verify `host` and `port` are reachable from the Mac running chatwire: `nc -zv <host> <port>`.

**TLS error: certificate verify failed.**
Either provide the CA certificate path in `ca_cert` or ensure the broker's cert is signed by a CA in the macOS system keychain.

**I want only messages from specific contacts.**
Subscribe to `chatwire/messages/_15551234567` (replace handle). MQTT topic filters are the cleanest way to scope consumption.

**Messages are delivered more than once.**
Switch to `qos: 2` (exactly-once) and ensure your broker supports it. Note QoS 2 adds round-trip overhead.

**The broker disconnects chatwire for duplicate client IDs.**
Set a unique `client_id` if you have multiple chatwire instances or other MQTT clients using the default `"chatwire"` ID.
