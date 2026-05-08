# owui_coding_proxy

Mini-Proxy der OpenWebUI's Responses-API-SSE in klassisches Chat-Completions-SSE übersetzt, damit VSCode-Extensions (Roo Code, Cline, Continue, ...) Streaming-Responses parsen können.

## Endpoints

- `POST /v1/chat/completions` — OpenAI-kompatibel, leitet an `${UPSTREAM}/api/chat/completions` weiter und konvertiert SSE-Format on-the-fly
- `GET /v1/models` — Pass-through zu `${UPSTREAM}/api/models`
- `GET /health` — Healthcheck

## Konfiguration

| ENV | Default | Zweck |
|---|---|---|
| `UPSTREAM` | `http://open-webui:8080` | OpenWebUI-Backend (im selben Docker-Netz) |

## Deploy via Docker Compose

```bash
docker compose up -d --build
```

Container läuft auf `127.0.0.1:4002` (host) und ist im `openwebui_default` Netzwerk.

## nginx-Snippet (chat.daniel-alisch.site)

```nginx
location /coder/ {
    proxy_pass http://127.0.0.1:4002/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
    chunked_transfer_encoding on;
}
```

## Roo Code / Cline / Continue Konfig

- **Base URL**: `https://chat.daniel-alisch.site/coder/v1`
- **API Key**: dein OpenWebUI-Key
- **Model**: `gpt-5.3-codex` (oder beliebiges OpenWebUI-Modell)
