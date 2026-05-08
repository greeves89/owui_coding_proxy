# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format orientiert an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionen folgen [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt
- Healthcheck im Hauptcontainer (`docker-compose.yml`).
- Traefik-Variante (`docker-compose.traefik.yml`) für Setups mit Traefik-Reverse-Proxy.
- Automatische Konvertierung `reasoning_effort` → `reasoning.effort` für Open WebUI / Responses API.

## [0.1.0] — 2026-05-08

### Hinzugefügt
- Erste Veröffentlichung.
- `POST /v1/chat/completions` mit On-the-fly-Übersetzung von Responses-API-SSE
  (`event: response.output_text.delta` etc.) zu klassischem Chat-Completions-SSE
  (`chat.completion.chunk`).
- Tool-Call-Streaming: `response.function_call_arguments.delta` →
  `tool_calls[].function.arguments`-Deltas.
- Non-Streaming-Pass-Through für `stream: false`-Requests.
- `GET /v1/models` als Pass-through zu `${UPSTREAM}/api/models`.
- `GET /health` für Monitoring.
- Dockerfile + `docker-compose.yml` für Deployment im `openwebui_default`-Netzwerk.
- nginx-Snippet im README für Path-basiertes Routing (`/coder/`).
- Optionale `.env`-Konfiguration (siehe `.env.example`).
- Lizenzierung unter Apache License 2.0.
