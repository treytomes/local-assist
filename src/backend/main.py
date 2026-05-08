import uuid
import os
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

from .database import get_connection, init_db
from .cost import (
    seed_pricing, record_usage, get_conversation_cost, get_daily_costs,
    get_model_comparison, upsert_pricing, get_pricing, list_pricing,
)
from . import router as provider_router
from .rag import embed_conversation, retrieve_context
from . import database as db

CONTEXT_WINDOW = 20  # default rolling message depth sent to model


# --- App lifecycle ---

_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn
    _conn = get_connection()
    init_db(_conn)
    seed_pricing(_conn)
    yield
    if _conn:
        _conn.close()


app = FastAPI(title="local-assist backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def conn():
    return _conn


# --- Pydantic models ---

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    model: str = "gpt-5.3-chat"
    messages: list[Message]
    max_tokens: int = Field(default=2048, ge=1, le=16384)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = True
    context_window: int | None = Field(default=None, ge=1, le=200)


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    model: str = "gpt-5.3-chat"


class ConversationUpdate(BaseModel):
    title: str | None = None
    model: str | None = None


# --- Health ---

@app.get("/v1/health")
async def health():
    return await provider_router.get_health()


# --- Conversations ---

@app.get("/v1/conversations")
def list_convs():
    rows = db.list_conversations(conn())
    return [dict(r) for r in rows]


@app.post("/v1/conversations", status_code=201)
def create_conv(body: ConversationCreate):
    conv_id = str(uuid.uuid4())
    provider = "azure"
    with db.transaction(conn()):
        row = db.create_conversation(conn(), conv_id, body.title, body.model, provider)
    return dict(row)


@app.get("/v1/conversations/{conv_id}")
def get_conv(conv_id: str):
    row = db.get_conversation(conn(), conv_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    messages = db.get_messages(conn(), conv_id)
    return {**dict(row), "messages": [dict(m) for m in messages]}


@app.patch("/v1/conversations/{conv_id}")
def patch_conv(conv_id: str, body: ConversationUpdate):
    row = db.get_conversation(conn(), conv_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    if body.title is None and body.model is None:
        return dict(row)
    with db.transaction(conn()):
        row = db.update_conversation(conn(), conv_id, body.title, body.model)
    return dict(row)


@app.delete("/v1/conversations/{conv_id}", status_code=204)
def delete_conv(conv_id: str):
    db.delete_conversation(conn(), conv_id)
    conn().commit()


@app.post("/v1/conversations/{conv_id}/embed")
async def embed_conv(conv_id: str):
    """Embed a conversation's assistant turns into the RAG store."""
    row = db.get_conversation(conn(), conv_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    await embed_conversation(conn(), conv_id)
    return {"status": "ok"}


# --- Chat completions (streaming) ---

@app.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest):
    # Ensure conversation exists
    conv_id = body.conversation_id or str(uuid.uuid4())
    if not db.get_conversation(conn(), conv_id):
        with db.transaction(conn()):
            db.create_conversation(conn(), conv_id, "New conversation", body.model, "azure")

    # Persist user messages
    last_user = next((m for m in reversed(body.messages) if m.role == "user"), None)
    if last_user:
        with db.transaction(conn()):
            db.insert_message(conn(), str(uuid.uuid4()), conv_id, "user", last_user.content)

    # Apply rolling context window
    messages_for_model = [m.model_dump() for m in body.messages]
    window = body.context_window or CONTEXT_WINDOW
    if len(messages_for_model) > window:
        # Always preserve a leading system message if present
        if messages_for_model[0]["role"] == "system":
            messages_for_model = [messages_for_model[0]] + messages_for_model[-(window - 1):]
        else:
            messages_for_model = messages_for_model[-window:]

    # Inject RAG context as a system message prefix when available
    if last_user:
        rag_chunks = await retrieve_context(conn(), last_user.content, exclude_conv_id=conv_id)
        if rag_chunks:
            rag_text = "\n\n".join(c["chunk_text"] for c in rag_chunks)
            rag_msg = {"role": "system", "content": f"Relevant context from past conversations:\n{rag_text}"}
            if messages_for_model and messages_for_model[0]["role"] == "system":
                messages_for_model.insert(1, rag_msg)
            else:
                messages_for_model.insert(0, rag_msg)

    provider, resolved_model, stream_iter = await provider_router.stream_chat(
        body.model,
        messages_for_model,
        body.max_tokens,
        body.temperature,
    )

    if not body.stream:
        # Collect full response
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        async for chunk in stream_iter:
            if chunk["type"] == "delta":
                full_text += chunk["content"]
            elif chunk["type"] == "usage":
                prompt_tokens = chunk["prompt_tokens"]
                completion_tokens = chunk["completion_tokens"]
            elif chunk["type"] == "error":
                raise HTTPException(502, chunk["message"])

        msg_id = str(uuid.uuid4())
        with db.transaction(conn()):
            db.insert_message(conn(), msg_id, conv_id, "assistant", full_text)
        cost = record_usage(conn(), str(uuid.uuid4()), conv_id, msg_id, provider, resolved_model,
                            prompt_tokens, completion_tokens)
        return {
            "conversation_id": conv_id,
            "model": resolved_model,
            "provider": provider,
            "message": {"role": "assistant", "content": full_text},
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost_usd": cost},
        }

    # Streaming response — SSE
    async def event_stream():
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        import json

        async for chunk in stream_iter:
            if chunk["type"] == "delta":
                full_text += chunk["content"]
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk['content'], 'conversation_id': conv_id})}\n\n"
            elif chunk["type"] == "usage":
                prompt_tokens = chunk["prompt_tokens"]
                completion_tokens = chunk["completion_tokens"]
            elif chunk["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': chunk['message']})}\n\n"
                return

        # Persist assistant reply + usage after stream ends
        msg_id = str(uuid.uuid4())
        with db.transaction(conn()):
            db.insert_message(conn(), msg_id, conv_id, "assistant", full_text)
        cost = record_usage(conn(), str(uuid.uuid4()), conv_id, msg_id, provider, resolved_model,
                            prompt_tokens, completion_tokens)
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'model': resolved_model, 'provider': provider, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'cost_usd': cost}})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Usage / cost ---

@app.get("/v1/usage")
def usage_summary(days: int = 30):
    return {
        "daily": get_daily_costs(conn(), days),
        "by_model": get_model_comparison(conn()),
    }


@app.get("/v1/usage/{conv_id}")
def conversation_usage(conv_id: str):
    return get_conversation_cost(conn(), conv_id)


# --- Pricing ---

class PricingUpdate(BaseModel):
    input_cost_per_1k: float = Field(ge=0.0)
    output_cost_per_1k: float = Field(ge=0.0)


@app.get("/v1/pricing")
def list_pricing_endpoint():
    return list_pricing(conn())


@app.get("/v1/pricing/{provider}/{model:path}")
def get_pricing_endpoint(provider: str, model: str):
    row = get_pricing(conn(), provider, model)
    if not row:
        raise HTTPException(404, "Pricing not found")
    return row


@app.post("/v1/pricing/{provider}/{model:path}", status_code=200)
def upsert_pricing_endpoint(provider: str, model: str, body: PricingUpdate):
    return upsert_pricing(conn(), provider, model, body.input_cost_per_1k, body.output_cost_per_1k)


# --- RAG context retrieval ---

@app.get("/v1/context")
async def get_context(query: str, exclude_conv_id: str | None = None):
    chunks = await retrieve_context(conn(), query, exclude_conv_id)
    return {"chunks": chunks}
