"""
OpenWebUI Coding-Proxy

Zwei Endpoints, ein Upstream (OWUI `/api/chat/completions`):

* `POST /v1/chat/completions`
    Übersetzt OWUI's Responses-API-SSE on-the-fly in klassisches
    Chat-Completions-SSE (`chat.completion.chunk`). Für Clients, die das
    OpenAI-Chat-Completions-Protokoll sprechen (Cline, Roo Code, Continue
    mit `useResponsesApi: false`).

* `POST /v1/responses`
    Mappt einen Responses-API-Request-Body (`input`, `instructions`,
    `max_output_tokens`) auf das Chat-Completions-Schema und reicht OWUI's
    Responses-SSE 1:1 zurück. Für Clients, die `/v1/responses` erwarten
    (z.B. Continue ≤1.2.x bei `gpt-5*` / `o*`-Modellen).
"""
import json
import os
import time
import uuid
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

UPSTREAM = os.environ.get("UPSTREAM", "http://open-webui:8080")
UPSTREAM_PATH = "/api/chat/completions"
TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

app = FastAPI()


def _chunk(model: str, completion_id: str, delta: dict, finish_reason=None) -> bytes:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


async def _translate_stream(upstream_resp: httpx.Response, model: str) -> AsyncIterator[bytes]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    role_sent = False
    is_responses_api = False
    current_event = None
    finish_reason = "stop"
    tool_calls_open: dict[int, dict] = {}

    async for raw_line in upstream_resp.aiter_lines():
        if not isinstance(raw_line, str):
            continue
        line = raw_line.rstrip("\r")

        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
            if current_event.startswith("response."):
                is_responses_api = True
            continue

        if not line.startswith("data:"):
            if line == "":
                continue
            continue

        data_str = line[5:].lstrip()

        if not is_responses_api:
            yield (line + "\n\n").encode()
            continue

        if data_str == "[DONE]":
            yield b"data: [DONE]\n\n"
            return

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        ev_type = data.get("type") or current_event or ""

        if ev_type == "response.created" and not role_sent:
            yield _chunk(model, completion_id, {"role": "assistant", "content": ""})
            role_sent = True

        elif ev_type == "response.output_text.delta":
            delta = data.get("delta", "")
            if delta:
                if not role_sent:
                    yield _chunk(model, completion_id, {"role": "assistant", "content": ""})
                    role_sent = True
                yield _chunk(model, completion_id, {"content": delta})

        elif ev_type == "response.output_item.added":
            item = data.get("item", {})
            if item.get("type") == "function_call":
                idx = data.get("output_index", 0)
                tool_calls_open[idx] = {
                    "id": item.get("id") or f"call_{uuid.uuid4().hex[:16]}",
                    "name": item.get("name", ""),
                    "args": "",
                }
                yield _chunk(
                    model,
                    completion_id,
                    {
                        "tool_calls": [
                            {
                                "index": idx,
                                "id": tool_calls_open[idx]["id"],
                                "type": "function",
                                "function": {"name": tool_calls_open[idx]["name"], "arguments": ""},
                            }
                        ]
                    },
                )
                finish_reason = "tool_calls"

        elif ev_type == "response.function_call_arguments.delta":
            idx = data.get("output_index", 0)
            delta = data.get("delta", "")
            if delta and idx in tool_calls_open:
                tool_calls_open[idx]["args"] += delta
                yield _chunk(
                    model,
                    completion_id,
                    {
                        "tool_calls": [
                            {
                                "index": idx,
                                "function": {"arguments": delta},
                            }
                        ]
                    },
                )

        elif ev_type == "response.completed":
            yield _chunk(model, completion_id, {}, finish_reason=finish_reason)
            yield b"data: [DONE]\n\n"
            return

        elif ev_type == "response.error" or ev_type == "error":
            err = data.get("error") or data
            yield f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n".encode()
            yield b"data: [DONE]\n\n"
            return

    yield _chunk(model, completion_id, {}, finish_reason=finish_reason)
    yield b"data: [DONE]\n\n"


def _normalize_reasoning_effort(payload: dict) -> None:
    """Promote top-level `reasoning_effort` into the nested `reasoning.effort` shape."""
    if "reasoning_effort" not in payload:
        return
    effort = payload.pop("reasoning_effort")
    if effort and effort not in ("none", "off", None):
        reasoning = payload.get("reasoning") or {}
        reasoning.setdefault("effort", effort)
        payload["reasoning"] = reasoning


def _responses_body_to_chat(payload: dict) -> dict:
    """Translate an OpenAI Responses-API request body into the Chat-Completions schema OWUI expects."""
    if "messages" not in payload:
        inp = payload.pop("input", None)
        if isinstance(inp, list):
            payload["messages"] = inp
        elif isinstance(inp, str):
            payload["messages"] = [{"role": "user", "content": inp}]
        else:
            payload["messages"] = []
    else:
        payload.pop("input", None)

    instructions = payload.pop("instructions", None)
    if instructions:
        payload["messages"] = [{"role": "system", "content": instructions}] + payload["messages"]

    if "max_output_tokens" in payload and "max_tokens" not in payload:
        payload["max_tokens"] = payload.pop("max_output_tokens")

    return payload


async def _stream_translated(payload: dict, auth: str, model: str) -> StreamingResponse:
    """Stream OWUI's Responses-SSE, translated into Chat-Completions chunks."""
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    async def generator():
        client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            async with client.stream(
                "POST", f"{UPSTREAM}{UPSTREAM_PATH}", content=body, headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    err_body = await resp.aread()
                    yield f"data: {json.dumps({'error': err_body.decode('utf-8', 'replace')})}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                    return
                async for chunk in _translate_stream(resp, model):
                    yield chunk
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n".encode()
            yield b"data: [DONE]\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_passthrough(payload: dict, auth: str) -> StreamingResponse:
    """Forward OWUI's SSE response byte-for-byte (used for /v1/responses)."""
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    async def generator():
        client = httpx.AsyncClient(timeout=TIMEOUT)
        try:
            async with client.stream(
                "POST", f"{UPSTREAM}{UPSTREAM_PATH}", content=body, headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    err_body = await resp.aread()
                    yield f"event: error\ndata: {json.dumps({'error': err_body.decode('utf-8', 'replace')})}\n\n".encode()
                    return
                async for chunk in resp.aiter_raw():
                    yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _post_nonstream(payload: dict, auth: str) -> JSONResponse:
    """Forward a non-streaming request, returning OWUI's JSON response unchanged."""
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{UPSTREAM}{UPSTREAM_PATH}", content=body, headers=headers)
    try:
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception:
        return JSONResponse({"error": r.text}, status_code=r.status_code)


@app.get("/v1/models")
async def models(request: Request):
    auth = request.headers.get("authorization", "")
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{UPSTREAM}/api/models", headers={"Authorization": auth})
    return JSONResponse(content=r.json(), status_code=r.status_code)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    _normalize_reasoning_effort(payload)
    model = payload.get("model") or "unknown"
    auth = request.headers.get("authorization", "")

    if not payload.get("stream"):
        return await _post_nonstream(payload, auth)
    return await _stream_translated(payload, auth, model)


@app.post("/v1/responses")
async def responses(request: Request):
    """Continue ≤1.2.x trifft bei `gpt-5*`/`o*` diesen Pfad direkt — siehe Modul-Docstring."""
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    payload = _responses_body_to_chat(payload)
    _normalize_reasoning_effort(payload)
    auth = request.headers.get("authorization", "")

    if not payload.get("stream", True):
        return await _post_nonstream(payload, auth)
    return await _stream_passthrough(payload, auth)


@app.get("/health")
async def health():
    return {"ok": True}
