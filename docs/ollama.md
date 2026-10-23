# Ollama connectivity

Rayflow contacts Ollama from FastAPI, never directly from the browser. Local
default: `http://127.0.0.1:11434`. In Connections, save the host and installed model,
then use Reconnect Ollama and Test selected model. Blank model means first installed
model. An explicit unavailable model is rejected, never silently replaced.

The old client ignored `storage/private/providers.json`, chose the first installed
model rather than the saved selection, rejected remote hosts, and timed out after
12 seconds. The UI also referenced a missing `/api/ollama/test` route. The new client
uses the shared settings reader, `/api/tags` discovery, and `/api/generate` inference.
The editor now honors the saved preferred provider. Explicit provider failures are
shown to the user; Automatic may fall back to existing local commands.

On this workstation, the actual `/api/tags` call returned `qwen3:8b`. A real call
through FastAPI's prompt-test endpoint returned HTTP 200 and `Ready.` after 21.67
seconds. Real structured inference also parsed a square/noir plan successfully.
This demonstrates why the previous 12-second deadline could fail despite a healthy
model server. No streaming existed in Rayflow; `stream: false` remains intentional.

```powershell
ollama serve
# In another terminal, if a model is not already installed:
ollama pull qwen3:8b
ollama list
```

Backend configuration:

```dotenv
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_GENERATION_TIMEOUT=180
AI_PROVIDER=ollama
```

Discovery uses two-second connect/read limits and retries a connection failure
once. Discovery timeouts are not retried. Generation uses a three-second connect
limit and a configurable 1–600 second read timeout (default 180). Inference is never
automatically replayed; use manual retry after checking server resources. Frontend
requests allow the maximum backend deadline plus discovery overhead. Empty, partial,
malformed and failed responses are not reported as successes. Diagnostics omit
transport exception text and server response bodies.

Production `OLLAMA_HOST` must resolve and be reachable **from the backend container**.
Loopback in a container refers to that container. Use an internal service DNS name,
VPN address or private network host; restrict access by firewall and use TLS when
crossing untrusted networks. Never publish an unauthenticated Ollama port publicly.
Remote URLs are permitted only when equal to operator-configured `OLLAMA_HOST` or
an entry in `OLLAMA_ALLOWED_HOSTS`; credentials in URLs and redirects are rejected.
TLS uses the system/Requests trust store; `REQUESTS_CA_BUNDLE` can supply a private CA.
Authenticated gateways needing custom headers are not implemented. Production
settings come from the process environment and cannot be edited in the browser.
OpenRouter and local commands remain available alternatives.
