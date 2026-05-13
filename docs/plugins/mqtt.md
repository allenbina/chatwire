# MQTT

## What it does

The MQTT plugin has two directions:

**Inbound → MQTT**: publishes every inbound iMessage to an MQTT broker as a JSON event. Home-automation systems (Home Assistant, Node-RED, OpenHAB, etc.) can react to your messages — trigger lights, log conversations, forward to other channels — without polling or screen-scraping.

**MQTT → iMessage (outbound relay)**: subscribe to a designated send topic and chatwire will send an iMessage on your behalf when a message arrives. This lets automations send replies, notifications, or proactive messages via iMessage from any MQTT-capable system.

Every inbound message is published to a topic derived from the sender's handle or group chat identifier. The JSON payload includes the sender handle, message text, direction (`is_from_me`), and structured chat metadata.

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
| `topic` | string | `"chatwire/messages"` | Base topic prefix for inbound publishes. |
| `username` | string | `""` | Broker username (optional). |
| `password` | string | `""` | Broker password (optional). |
| `qos` | integer | `0` | Quality of Service: `0` at-most-once, `1` at-least-once, `2` exactly-once. |
| `client_id` | string | `"chatwire"` | MQTT client identifier. Must be unique on the broker. |
| `use_tls` | boolean | `false` | Enable TLS/SSL encryption. |
| `ca_cert` | string | `""` | Path to a PEM CA certificate. Blank = system CA bundle. |
| `send_topic` | string | `""` | Subscribe to this topic to relay outbound iMessages. Blank = disabled. |

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

### Full config with TLS and outbound relay

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
      "ca_cert": "/etc/ssl/certs/mosquitto-ca.pem",
      "send_topic": "chatwire/send"
    }
  }
}
```

## Outbound relay (MQTT → iMessage)

Set `send_topic` to any topic string (e.g. `chatwire/send`) and chatwire will subscribe to it on the broker. Publish a JSON payload to that topic to send an iMessage:

**1:1 message:**
```json
{"handle": "+15551234567", "text": "Hello from Node-RED!"}
```

**Group chat** (use the `chat.guid` from an inbound payload):
```json
{"chat": "iMessage;+;chat629...", "text": "Hi team!", "label": "My Group"}
```

Both `handle` (or `chat`) and `text` are required. `label` is optional and only used for log lines.

### Node-RED example

Use an **MQTT Out** node targeting `chatwire/send`:

```json
{
  "handle": "{{contact_handle}}",
  "text": "Your alert: {{msg.payload}}"
}
```

### Home Assistant send example

```yaml
action:
  - service: mqtt.publish
    data:
      topic: "chatwire/send"
      payload: >
        {"handle": "+15551234567", "text": "Motion detected in {{ trigger.entity_id }}!"}
```

## Home Assistant receive example

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
