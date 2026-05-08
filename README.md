# owui_coding_proxy

> Übersetzungs-Proxy zwischen [Open WebUI](https://github.com/open-webui/open-webui) und VSCode-Coding-Extensions wie **Roo Code**, **Cline** und **Continue.dev**.

Open WebUI streamt Chat-Antworten neuerer OpenAI-Modelle (z.B. `gpt-5.x-codex`) im **Responses-API-Format** (`event: response.output_text.delta`). Coding-Extensions erwarten aber das klassische **Chat-Completions-Format** (`chat.completion.chunk`). Das Ergebnis: Streaming-Anfragen hängen, "API Request..." dreht sich endlos.

Dieser Proxy sitzt zwischen Extension und Open WebUI, übersetzt SSE-Events on-the-fly und verhält sich für die Extension wie ein ganz normaler OpenAI-kompatibler Endpoint.

```
VSCode Extension ──HTTPS──▶ owui_coding_proxy ──HTTP──▶ Open WebUI
   (chat.completion.chunk)       (translates)        (response.output_text.delta)
```

---

## Features

- **SSE-Format-Translation** — Responses-API → Chat Completions, on-the-fly, ohne Buffering
- **Tool-Calls** — `response.function_call_arguments.delta` wird zu `tool_calls[].function.arguments`-Deltas konvertiert
- **Models-Pass-Through** — `GET /v1/models` reicht die Open-WebUI-Modellliste durch
- **Non-Streaming-Pass-Through** — `stream: false` Requests laufen 1:1 durch
- **Healthcheck** — `GET /health` für Monitoring

---

## Setup

### 1. Deploy via Docker Compose

Auf dem Server, auf dem auch Open WebUI läuft:

```bash
git clone https://github.com/greeves89/owui_coding_proxy.git
cd owui_coding_proxy
cp .env.example .env       # optional, falls du UPSTREAM überschreiben willst
docker compose up -d --build
```

Der Container läuft auf `127.0.0.1:4002` (host) und ist im selben Docker-Netzwerk wie Open WebUI (default: `openwebui_default`).

**Voraussetzungen:**
- Open WebUI läuft als Docker-Container, der per Hostname `open-webui` im Netz `openwebui_default` erreichbar ist (Standard-Setup).
- Falls Container/Netz anders heißen: `UPSTREAM` und `networks.default.name` in `docker-compose.yml` anpassen oder via `.env` überschreiben.

**Konfiguration (`.env`):**

| ENV         | Default                     | Zweck                           |
|-------------|-----------------------------|---------------------------------|
| `UPSTREAM`  | `http://open-webui:8080`    | Open-WebUI-Backend (Container)  |

Mehr ist nicht nötig — Auth läuft per Bearer-Token, das die Extension mitschickt und der Proxy 1:1 an Open WebUI weiterreicht.

**Updates einspielen:**

```bash
git pull && docker compose up -d --build
```

### 2. Reverse-Proxy (nginx)

Füge eine `/coder/`-Location zur bestehenden Open-WebUI-Site hinzu:

```nginx
location /coder/ {
    proxy_pass http://127.0.0.1:4002/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
    chunked_transfer_encoding on;
}
```

```bash
nginx -t && systemctl reload nginx
```

### 3. Coding-Extension konfigurieren

| Feld          | Wert                                                |
|---------------|-----------------------------------------------------|
| Provider      | `OpenAI Compatible`                                 |
| Base URL      | `https://chat.example.com/coder/v1`                 |
| API Key       | dein Open-WebUI-Key                                 |
| Model         | beliebiges Open-WebUI-Modell (z.B. `gpt-5.3-codex`) |
| **Streaming** | **aktiviert**                                       |

> ⚠️ **Streaming muss eingeschaltet sein.** Non-Streaming geht zwar auch durch, aber der ganze Sinn dieses Proxys ist die SSE-Übersetzung.

---

## Endpoints

| Methode | Pfad                       | Funktion                                        |
|---------|----------------------------|-------------------------------------------------|
| `POST`  | `/v1/chat/completions`     | OpenAI-kompatibel; übersetzt Stream-Format      |
| `GET`   | `/v1/models`               | Pass-through zu `${UPSTREAM}/api/models`        |
| `GET`   | `/health`                  | `{"ok": true}`                                  |

---

## Testen

```bash
curl -X POST https://chat.example.com/coder/v1/chat/completions \
  -H "Authorization: Bearer $OWUI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.3-codex",
    "stream": true,
    "messages": [{"role": "user", "content": "Sag hi"}]
  }'
```

Erwartete Ausgabe (klassisches Chat-Completions-SSE):

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant","content":""}}]}
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hi"}}]}
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

---

## Lizenz

[Apache License 2.0](LICENSE) — frei nutzbar, auch kommerziell, mit Quellenangabe.

© 2026 Daniel Alisch
