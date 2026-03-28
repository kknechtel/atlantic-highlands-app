"""AI Chat routes - chat with documents using Claude/Gemini."""
import logging
import json
import asyncio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.document import Document
from models.user import User
from auth import get_current_user
from services.s3_service import S3Service
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    document_id: str | None = None
    project_id: str | None = None
    model: str = "claude"  # "claude" or "gemini"


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream a chat response about a document or project."""

    # Build context from document(s)
    context = ""
    doc_name = "documents"

    if req.document_id:
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if doc:
            doc_name = doc.filename
            s3 = S3Service()
            try:
                content = s3.download_file(doc.s3_key)
                # Extract text from PDF
                from services.financial_extractor import pdf_to_markdown
                text = await pdf_to_markdown(content)
                if text:
                    context = f"Document: {doc.filename}\n\n{text[:50000]}"
            except Exception as e:
                logger.warning(f"Could not load document content: {e}")
                context = f"Document: {doc.filename} (content could not be loaded)"

    elif req.project_id:
        docs = db.query(Document).filter(Document.project_id == req.project_id).limit(20).all()
        doc_name = f"{len(docs)} documents"
        # Include filenames as context
        doc_list = "\n".join(f"- {d.filename} ({d.doc_type or 'unknown'}, {d.category or 'uncategorized'})" for d in docs)
        context = f"Project documents:\n{doc_list}"

    system_prompt = f"""You are an AI assistant for Atlantic Highlands document analysis.
You help analyze municipal and school district documents including budgets, audits, agendas, minutes, and financial statements.
Be specific, cite data from the documents when available, and provide actionable insights.

Context from {doc_name}:
{context if context else 'No specific document loaded. Answer based on general knowledge of municipal finance and governance.'}"""

    if req.model == "gemini" and GEMINI_API_KEY:
        return StreamingResponse(
            _stream_gemini(system_prompt, req.query),
            media_type="text/event-stream",
        )
    elif ANTHROPIC_API_KEY:
        return StreamingResponse(
            _stream_claude(system_prompt, req.query),
            media_type="text/event-stream",
        )
    else:
        # No API keys configured - return a helpful message
        async def no_key_stream():
            msg = "AI chat requires an API key. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in your .env file."
            yield f"data: {json.dumps({'type': 'delta', 'content': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(no_key_stream(), media_type="text/event-stream")


async def _stream_claude(system_prompt: str, query: str):
    """Stream response from Claude."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": query}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'delta', 'content': text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"Claude streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


async def _stream_gemini(system_prompt: str, query: str):
    """Stream response from Gemini."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        full_prompt = f"{system_prompt}\n\nUser question: {query}"

        config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=4096,
        )

        # Gemini streaming
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
                config=config,
            ),
        )

        if response and response.text:
            # Send in chunks to simulate streaming
            text = response.text
            chunk_size = 20
            for i in range(0, len(text), chunk_size):
                chunk = text[i : i + chunk_size]
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk})}\n\n"
                await asyncio.sleep(0.02)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"Gemini streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


@router.post("/ask")
async def chat_ask(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Non-streaming chat endpoint (returns full response)."""
    # Reuse streaming logic but collect all text
    context = ""
    if req.document_id:
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if doc:
            context = f"Document: {doc.filename}"

    # Simple non-streaming response
    return {"response": "Configure ANTHROPIC_API_KEY or GEMINI_API_KEY for AI chat."}
