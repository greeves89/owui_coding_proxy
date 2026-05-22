# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format orientiert an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionen folgen [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.2.1] — 2026-05-22

### Hinzugefügt
- Strukturiertes Logging mit vollem Stacktrace für Debugging (`DEBUG`-Level).
- Validierung dass der Request-Body ein JSON-Objekt ist (nicht `null` oder Array).
- `WARNING`-Log wenn `aiter_lines()` einen Nicht-String-Wert liefert.

## [0.2.0] — 2026-05-22

### Hinzugefügt
- Healthcheck im Hauptcontainer (`docker-compose.yml`).
- Traefik-Variante (`docker-compose.traefik.yml`) für Setups mit Traefik-Reverse-Proxy.
- Automatische Konvertierung `reasoning_effort` → `reasoning.effort` für Open WebUI / Responses API.
- `POST /v1/responses` für Clients, die den OpenAI-Responses-Endpoint zwingend ansprechen
  (z.B. Continue ≤1.2.x bei `gpt-5*`/`o*`-Modellen). Body-Mapping
  `input`/`instructions`/`max_output_tokens` → Chat-Completions-Schema, SSE-Response 1:1.

### Behoben
- `'NoneType' object has no attribute 'startswith'` bei Requests mit `"model": null` oder unerwarteten Werten aus `aiter_lines()`.
- Streaming-Fehler werden jetzt als SSE-Error-Chunk zurückgegeben statt die Verbindung still zu trennen.

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
