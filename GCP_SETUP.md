# GCP Setup: Adding Vertex AI (Mistral) as a Provider

**Goal:** Add `gcp` as a runtime-selectable provider alongside the existing `azure` provider, so the app can call Mistral models on Google Cloud Vertex AI without replacing the Azure path.

---

## 1. Overview

### What GCP service hosts Mistral models

Mistral models on GCP run as **serverless managed endpoints in Vertex AI Model Garden** (also called "Partner Models"). No GPU provisioning, no instance management, no container images — you call an HTTP endpoint and pay per token. This is the same deployment model as Azure AI Inference: managed, pay-as-you-go, no infrastructure to babysit.

### Critical finding: Mistral Large 3 is not currently on Vertex AI

As of May 2026, the Mistral models listed in Vertex AI Model Garden are:

| Model name in docs | API model ID | Notes |
|---|---|---|
| Mistral Medium 3 (25.05) | `mistral-medium-2505` | Closest current match to Large 3 in capability |
| Mistral Small 3.1 (25.03) | `mistral-small-2503` | Fast, cheap, 128K context |
| Mistral OCR (25.05) | `mistral-ocr-2505` | Document/OCR specialist |
| Codestral 2 (25.08) | `codestral-2` | Code generation specialist |

**Mistral Large 3 is not listed.** Mistral's own documentation for Vertex AI does not mention it. Mistral's Medium 3 announcement blog post (May 2025) notes that Medium 3 is "coming soon to Google Cloud Vertex." It appears Large 3 may have been skipped in favor of Medium 3 on GCP, or its availability may have changed.

**Recommended path:** Use `mistral-medium-2505` as the GCP equivalent. Mistral Medium 3 is benchmarked at approximately 90% of Claude Sonnet 3.7 in STEM and coding, with pricing significantly lower than Large 3 on Azure. If Large 3 becomes available on Vertex AI, the model ID would likely follow the pattern `mistral-large-YYMM` (e.g. `mistral-large-2503`).

**Action before implementation:** Verify current availability by checking the Model Garden console at:
`https://console.cloud.google.com/vertex-ai/model-garden` (search "Mistral")

### Comparison to Azure setup

| Dimension | Azure (current) | GCP Vertex AI |
|---|---|---|
| Service | Azure AI Inference (OpenAI-compat endpoint) | Vertex AI Model Garden (Partner Models API) |
| Model | `Mistral-Large-3` | `mistral-medium-2505` (Large 3 TBD) |
| Protocol | OpenAI-compatible REST + SSE | Mistral-native REST + SSE via `rawPredict`/`streamRawPredict` |
| Auth | `api-key` header | Google ADC (OAuth2 bearer token) |
| SDK in use | Raw `httpx` against OpenAI-format endpoint | `mistralai[gcp]` Python package (`MistralGCP` client) |
| Streaming | `data: {...}\n\n` SSE, `[DONE]` terminator | Same SSE format via `streamRawPredict` endpoint |
| Infrastructure | Fully managed | Fully managed |
| Regions | Azure eastus / westus | `us-central1`, `europe-west4` |

---

## 2. Prerequisites and Quota

### GPU quota situation

Because Vertex AI serves Mistral as a **serverless managed endpoint**, you do **not** need to request a GPU quota increase for the serverless API path. There is no self-deployment involved, no NVIDIA A100 or L4 provisioning.

The GPU quota warning the user heard about applies to the **self-hosted deployment path** in Model Garden, where you would deploy the model weights onto a dedicated VM with GPUs. That path costs much more and requires quota. **The serverless API path does not require a GPU quota increase.**

The relevant quota for serverless partner models is a **requests-per-minute (RPM)** or **tokens-per-minute (TPM)** soft limit, not a GPU quota. These start at a default (typically 60 RPM for new accounts) and can be raised via the Quotas console if needed.

### Steps to enable access

1. **Enable the Vertex AI API** in your GCP project:
   ```
   gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
   ```

2. **Accept the model's terms of service** — Partner models require a one-time "Enable" click in Model Garden. Open the model card at:
   `https://console.cloud.google.com/vertex-ai/model-garden` → search "Mistral Medium" → click "Enable" or "Subscribe". This creates a `ConsumerProcurementEntitlement` in your project. Without it, API calls return 403.

3. **Grant IAM roles** to the service account or user running the app:
   - `roles/aiplatform.user` — allows calling prediction endpoints
   - `roles/consumerprocurement.entitlementManager` — allows activating/checking entitlements

4. **Check requests-per-minute quota** (optional, only if you hit 429s):
   - Console → IAM & Admin → Quotas → filter by "aiplatform.googleapis.com"
   - Look for `online_prediction_requests_per_base_model` or similar per-model quota
   - Submit a quota increase request inline (quota increases for serverless partner models are typically approved within minutes to a few hours, not days)

---

## 3. Authentication Setup

Vertex AI uses **Google Application Default Credentials (ADC)**, not API keys. The `MistralGCP` client calls `google.auth.default()` internally and handles token refresh automatically.

### Local development

```bash
# Install the Google Cloud CLI if not already installed:
# https://cloud.google.com/sdk/docs/install

# Authenticate your local machine:
gcloud auth application-default login

# Optional: set a default project:
gcloud config set project YOUR_PROJECT_ID
```

After `gcloud auth application-default login`, credentials are written to `~/.config/gcloud/application_default_credentials.json` and picked up automatically by any GCP client library.

### Production / deployed app

For a deployed service (VM, Cloud Run, etc.), attach a **service account** to the instance rather than using user credentials:

```bash
# Create service account:
gcloud iam service-accounts create local-assist-backend \
    --display-name="local-assist backend" \
    --project=YOUR_PROJECT_ID

# Grant Vertex AI User role:
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:local-assist-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# Grant entitlement manager role:
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:local-assist-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/consumerprocurement.entitlementManager"
```

For local testing with a service account key (not recommended for production):
```bash
gcloud iam service-accounts keys create key.json \
    --iam-account=local-assist-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com

export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### Environment variables the app needs

```bash
GCP_PROJECT_ID=your-project-id       # required
GCP_REGION=us-central1               # optional; defaults to europe-west4 in the SDK
GCP_MODEL=mistral-medium-2505        # optional; set your preferred default here
```

The `MistralGCP` client reads `GCP_PROJECT_ID` and `GCP_REGION` from the environment automatically (or they can be passed as constructor arguments). No `GCP_API_KEY` is needed — ADC handles auth.

---

## 4. Python SDK

### Installation

```bash
pip install "mistralai[gcp]"
```

This installs `mistralai>=2.0.0` plus the `google-auth` and `google-auth-httpx2` extras needed for ADC token injection. The current stable version as of May 2026 is `2.4.5`.

Add to `requirements.txt` or `pyproject.toml`:
```
mistralai[gcp]>=2.4.0
```

### Synchronous call (reference)

```python
import os
from mistralai.gcp.client import MistralGCP

client = MistralGCP(
    project_id=os.environ.get("GCP_PROJECT_ID"),
    region=os.environ.get("GCP_REGION", "us-central1"),
)

resp = client.chat.complete(
    model="mistral-medium-2505",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

### Streaming call (reference)

The `MistralGCP` client exposes `client.chat.stream()`, which returns a context-manager-based event generator yielding `CompletionEvent` objects (SSE-backed, same protocol as the standard Mistral client):

```python
with client.chat.stream(
    model="mistral-medium-2505",
    messages=[{"role": "user", "content": "Hello"}],
) as event_stream:
    for event in event_stream:
        # event is a CompletionEvent; delta text is in:
        # event.data.choices[0].delta.content
        chunk = event.data.choices[0].delta.content
        if chunk:
            print(chunk, end="", flush=True)
```

The async equivalent (needed for FastAPI):

```python
async with await client.chat.stream_async(
    model="mistral-medium-2505",
    messages=[{"role": "user", "content": "Hello"}],
) as event_stream:
    async for event in event_stream:
        chunk = event.data.choices[0].delta.content
        if chunk:
            print(chunk, end="", flush=True)
```

> **Streaming note — verify before committing:** The `MistralGCP` examples in the official repository only show non-streaming (`async_chat_no_streaming.py`). Streaming is documented as available on the Mistral Python SDK via `chat.stream()`, and the underlying Vertex AI endpoint supports `streamRawPredict`, so streaming should work. However, there is no confirmed GCP streaming code example in the official docs as of this writing. The fallback alternative is to implement streaming manually via `httpx` against the `streamRawPredict` REST endpoint (see Section 6 below).

---

## 5. Streaming Details

### How Vertex AI streaming works

Vertex AI's REST API for partner models exposes two endpoints:
- `rawPredict` — single-shot, returns full JSON
- `streamRawPredict` — streams SSE in the same `data: {...}\n\ndata: [DONE]\n\n` format used by OpenAI/Azure

The endpoint URL structure is:
```
https://REGION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/publishers/mistralai/models/MODEL_ID:streamRawPredict
```

Example for `us-central1`:
```
https://us-central1-aiplatform.googleapis.com/v1/projects/my-project/locations/us-central1/publishers/mistralai/models/mistral-medium-2505:streamRawPredict
```

The request body is the standard Mistral chat completions JSON with `"stream": true`.

### Comparison to Azure streaming

The Azure adapter in `src/backend/providers/azure.py` already parses the standard SSE format:
- Lines prefixed `data: `
- Terminator `[DONE]`
- Chunks contain `choices[0].delta.content` and optionally `usage`

The GCP `streamRawPredict` endpoint produces the same format. A raw-httpx implementation of the GCP adapter could reuse almost identical SSE-parsing logic, just with different auth (bearer token instead of `api-key` header).

---

## 6. Pricing Comparison

### GCP Vertex AI — Mistral pricing

GCP pricing for Mistral partner models was not available on the public pricing page at the time of this research (May 2026). The Vertex AI pricing page covers Google-first models only; Mistral pricing may be listed in the Cloud SKU catalog or the Model Garden model card after entitlement.

**Known reference point from Mistral's own announcement:** Mistral Medium 3 pricing on Mistral's own API is `$0.40 input / $2.00 output per million tokens` (`$0.00040 / $0.00200 per 1K tokens`). Vertex AI pricing for partner models is typically the same or slightly higher than the model provider's direct pricing.

### Pricing table

| Provider | Model | Input ($/1K tokens) | Output ($/1K tokens) | Notes |
|---|---|---|---|---|
| Azure | Mistral-Large-3 | $0.002 | $0.006 | Current app (estimated) |
| Azure | gpt-4o | $0.0025 | $0.010 | For reference |
| GCP | mistral-medium-2505 | ~$0.00040 | ~$0.00200 | Mistral.ai direct price; GCP may differ |
| GCP | mistral-small-2503 | ~$0.00010 | ~$0.00030 | Mistral.ai direct price; GCP may differ |

**Cost implication:** If GCP prices match Mistral's own API, `mistral-medium-2505` on GCP would be roughly **3–5x cheaper** than `Mistral-Large-3` on Azure. For a user with a $300 intro GCP credit, even at Azure-equivalent rates the budget goes a long way.

**Verification steps:**
1. After enabling the model in Model Garden, check the model card — the GCP-specific price per token is often displayed there.
2. Check Google Cloud SKU catalog: `https://cloud.google.com/skus/` and search "mistral".
3. Use the GCP Pricing Calculator at `https://cloud.google.com/products/calculator`.

---

## 7. Implementation Plan

### 7.1 New file: `src/backend/providers/gcp.py`

Model this after `azure.py`. Key differences:

- Auth: use `google.auth.default()` + refresh cycle, or delegate entirely to `MistralGCP` client
- Model ID: `mistral-medium-2505` (configurable via env var)
- Streaming: use `MistralGCP.chat.stream_async()` if confirmed working, else raw `httpx` + `streamRawPredict`
- No embeddings (the app's RAG embeddings go through Azure `text-embedding-3-small`; keep that on Azure regardless of which provider handles chat)

```python
# src/backend/providers/gcp.py
import os
import json
from typing import AsyncIterator

GCP_REGION = os.getenv("GCP_REGION", "us-central1")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
DEFAULT_MODEL = os.getenv("GCP_MODEL", "mistral-medium-2505")


def _model_id() -> str:
    return DEFAULT_MODEL


async def health_check() -> bool:
    """Lightweight probe: attempt a minimal non-streaming call."""
    try:
        from mistralai.gcp.client import MistralGCP
        client = MistralGCP(project_id=GCP_PROJECT_ID, region=GCP_REGION)
        resp = await client.chat.complete_async(
            model=_model_id(),
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        return bool(resp.choices)
    except Exception:
        return False


async def stream_chat(
    model: str,
    messages: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> AsyncIterator[dict]:
    """
    Yields dicts:
      {"type": "delta",   "content": str}
      {"type": "usage",   "prompt_tokens": int, "completion_tokens": int}
      {"type": "error",   "message": str}
    """
    from mistralai.gcp.client import MistralGCP
    client = MistralGCP(project_id=GCP_PROJECT_ID, region=GCP_REGION)
    try:
        # NOTE: verify stream_async() works with MistralGCP before shipping.
        # If not, fall back to the raw httpx approach shown below.
        async with await client.chat.stream_async(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ) as event_stream:
            prompt_tokens = 0
            completion_tokens = 0
            async for event in event_stream:
                delta = event.data.choices[0].delta.content if event.data.choices else None
                if delta:
                    yield {"type": "delta", "content": delta}
                usage = getattr(event.data, "usage", None)
                if usage:
                    prompt_tokens = usage.prompt_tokens or 0
                    completion_tokens = usage.completion_tokens or 0
            yield {
                "type": "usage",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}


async def call_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 2048,
) -> dict:
    """
    Non-streaming tool call.
    Returns {"role": "assistant", "content": ..., "tool_calls": [...] | None}
    """
    from mistralai.gcp.client import MistralGCP
    client = MistralGCP(project_id=GCP_PROJECT_ID, region=GCP_REGION)
    resp = await client.chat.complete_async(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=max_tokens,
    )
    msg = resp.choices[0].message
    # Normalize to the same dict shape azure.py returns
    tool_calls = None
    if msg.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": tool_calls,
    }
```

**Raw httpx fallback for streaming** (use this if `chat.stream_async()` does not work with `MistralGCP`):

```python
# Alternative stream_chat() using raw httpx against streamRawPredict:
import httpx
import google.auth
import google.auth.transport.requests

async def stream_chat_raw(model, messages, max_tokens=2048, temperature=0.7):
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    token = credentials.token

    url = (
        f"https://{GCP_REGION}-aiplatform.googleapis.com/v1"
        f"/projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}"
        f"/publishers/mistralai/models/{model}:streamRawPredict"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                yield {"type": "error", "message": f"GCP HTTP {resp.status_code}: {body.decode()[:200]}"}
                return
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for choice in chunk.get("choices", []):
                    text = choice.get("delta", {}).get("content")
                    if text:
                        yield {"type": "delta", "content": text}
                if chunk.get("usage"):
                    u = chunk["usage"]
                    yield {
                        "type": "usage",
                        "prompt_tokens": u.get("prompt_tokens", 0),
                        "completion_tokens": u.get("completion_tokens", 0),
                    }
```

Note: the raw httpx fallback calls `credentials.refresh()` synchronously. In production, wrap this in `asyncio.get_event_loop().run_in_executor(None, credentials.refresh, request)` or use `google.auth.transport.aiohttp.Request` to avoid blocking the event loop.

### 7.2 Provider toggle

The cleanest approach is an environment variable that the router checks at startup. This keeps the toggle out of the database schema and makes it easy to change via `.env`.

**New env var:**
```bash
# Options: azure | gcp | auto
# "auto" = try GCP, fall back to Azure, then Ollama (same health-check pattern)
PREFERRED_PROVIDER=azure
```

**Changes to `src/backend/router.py`:**

```python
import os
from .providers import azure, ollama, gcp  # add gcp import

PREFERRED_PROVIDER = os.getenv("PREFERRED_PROVIDER", "azure")  # "azure" | "gcp" | "auto"

# Add GCP health cache alongside the existing Azure one:
_gcp_healthy: bool | None = None
```

The `_resolve_provider_model()` function currently hardcodes `"azure"` for non-Ollama models. Change it to respect `PREFERRED_PROVIDER`:

```python
def _resolve_provider_model(requested_model: str) -> tuple[str, str]:
    if requested_model in OLLAMA_MODELS:
        return "ollama", requested_model
    if PREFERRED_PROVIDER == "gcp":
        # Map the Azure-style model name to the GCP equivalent
        return "gcp", _azure_to_gcp_model(requested_model)
    return "azure", requested_model


GCP_MODEL_MAP = {
    "Mistral-Large-3": "mistral-medium-2505",   # best available equivalent on GCP today
    "mistral-large-latest": "mistral-medium-2505",
    # Add more mappings as new models become available
}

def _azure_to_gcp_model(azure_model: str) -> str:
    return GCP_MODEL_MAP.get(azure_model, gcp.DEFAULT_MODEL)
```

Update `stream_chat()` and `call_with_tools()` in the router to dispatch to `gcp.*` when `provider == "gcp"`, and update `get_health()` to include a GCP health check.

### 7.3 Cost tracking

Add GCP pricing entries to `src/backend/cost.py`'s `PRICING_SEED`:

```python
# GCP Vertex AI — prices estimated from Mistral's own API (verify against GCP SKU)
("gcp", "mistral-medium-2505",  0.00040, 0.00200),
("gcp", "mistral-small-2503",   0.00010, 0.00030),
```

The `record_usage()` call in `main.py` already passes `provider` through correctly, so no other changes are needed in the cost module.

### 7.4 Embeddings

Leave Azure as the embeddings provider regardless of which provider handles chat. The RAG pipeline calls `azure.get_embedding()` directly. No changes needed there.

If you eventually want GCP embeddings (e.g. Vertex AI text-embedding models), that is a separate adapter task — the RAG module would need to be parameterized on the embedding provider.

### 7.5 Model name normalization in the frontend

The frontend sends `model: "Mistral-Large-3"` (the Azure deployment name). The GCP adapter needs to accept this name and translate it. The `_azure_to_gcp_model()` mapping in the router handles this transparently — the frontend does not need changes.

### 7.6 Summary of files to create/change

| File | Change |
|---|---|
| `src/backend/providers/gcp.py` | **Create** — new provider adapter |
| `src/backend/router.py` | **Edit** — add GCP import, health cache, `PREFERRED_PROVIDER` dispatch |
| `src/backend/cost.py` | **Edit** — add GCP pricing seed rows |
| `.env` | **Edit** — add `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_MODEL`, `PREFERRED_PROVIDER` |
| `requirements.txt` / `pyproject.toml` | **Edit** — add `mistralai[gcp]>=2.4.0` |

---

## 8. Open Questions and Risks

### 8.1 Mistral Large 3 availability on Vertex AI (HIGH priority)

Mistral Large 3 is not listed in Vertex AI Model Garden as of May 2026. The current best equivalent is `mistral-medium-2505`. Before starting implementation, confirm the current model catalog in the GCP console. If Large 3 becomes available, its model ID will likely be `mistral-large-YYMM` and just needs to be added to the `GCP_MODEL_MAP`.

### 8.2 Streaming support via MistralGCP client (MEDIUM priority)

The official GCP examples only show non-streaming async calls. The `chat.stream()` / `chat.stream_async()` methods exist on the base `MistralAI` client and should be inherited by `MistralGCP`, but this has not been confirmed with a working code example. **Test streaming before committing to this approach.** The raw `httpx` + `streamRawPredict` fallback (Section 7.1) is a reliable alternative if the SDK streaming does not work.

### 8.3 Tool call response format (MEDIUM priority)

The `call_with_tools()` sketch above normalizes the `MistralGCP` response to match the dict shape that `router.py` and `main.py` expect (`{"role": ..., "content": ..., "tool_calls": [...]}`). The normalization code needs to be tested against the actual SDK response object — the `tc.function.arguments` field may be a string or a dict depending on the SDK version.

### 8.4 GCP pricing confirmation (LOW priority — affects budget planning)

GCP-specific per-token pricing for Mistral partner models was not found on the public pricing page. The estimates in Section 6 use Mistral's own API pricing. Actual GCP prices may differ (typically within 10–20%). Confirm via the Model Garden model card or Cloud SKU catalog after enabling the model.

### 8.5 ADC token refresh in async context (LOW priority)

The raw `httpx` fallback calls `credentials.refresh()` synchronously. In an async FastAPI handler this blocks the event loop. Use `run_in_executor` or switch to `google.auth.transport.aiohttp` for production-quality async token refresh. The `MistralGCP` client handles this internally, which is one reason to prefer it over the raw httpx approach.

### 8.6 Region latency (LOW priority)

`us-central1` (Iowa) is typically the lowest-latency GCP region from North America. `europe-west4` (Netherlands) is the SDK default. Explicitly set `GCP_REGION=us-central1` in `.env` unless the user is in Europe.

### 8.7 Model Garden terms / entitlement (LOW priority, one-time)

The first API call will fail with 403 if the model's terms have not been accepted in the Model Garden UI. This is a one-time click per model per project, not a recurring issue. Document it in the app's README as a setup step.

---

## 9. Quick-Start Checklist

```
[ ] 1. gcloud auth application-default login
[ ] 2. Enable Vertex AI API: gcloud services enable aiplatform.googleapis.com
[ ] 3. Open Model Garden, find "Mistral Medium 3", click Enable/Subscribe
[ ] 4. Verify Mistral Large 3 availability (if desired)
[ ] 5. pip install "mistralai[gcp]>=2.4.0"
[ ] 6. Add to .env: GCP_PROJECT_ID, GCP_REGION=us-central1, PREFERRED_PROVIDER=gcp
[ ] 7. Create src/backend/providers/gcp.py
[ ] 8. Update src/backend/router.py
[ ] 9. Update src/backend/cost.py with GCP pricing rows
[ ] 10. Test health_check() -> True
[ ] 11. Test non-streaming call_with_tools() with a simple message
[ ] 12. Test stream_chat() yields delta chunks
[ ] 13. Test full conversation round-trip via POST /v1/chat/completions
[ ] 14. Verify cost tracking records "gcp" provider in usage table
```
