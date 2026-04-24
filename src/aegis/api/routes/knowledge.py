"""Knowledge base API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...storage.repositories.knowledge import KnowledgeDocCreate
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/agents/{agent_id}/knowledge", tags=["knowledge"])


class AddUrlRequest(BaseModel):
    url: str
    name: str = ""


class AddTextRequest(BaseModel):
    text: str
    name: str = ""


class UpdateDocRequest(BaseModel):
    name: str | None = None
    text: str | None = None  # Replace text content (text docs only)
    refetch: bool = False    # Re-fetch URL (url docs only)


@router.get("")
async def list_knowledge(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    docs = await repos.knowledge.list_by_agent(agent_id)
    return {
        "documents": [{**d.model_dump(), "content": None} for d in docs],
        "count": len(docs),
    }


@router.get("/{doc_id}")
async def get_knowledge_doc(
    agent_id: str,
    doc_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = await repos.knowledge.get(doc_id)
    if not doc or doc.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"document": doc.model_dump()}


@router.post("/url", status_code=201)
async def add_url(
    agent_id: str,
    data: AddUrlRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    kb_service = getattr(request.app.state, 'knowledge_service', None)
    if not kb_service:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    doc = await repos.knowledge.create(KnowledgeDocCreate(
        agent_id=agent_id, user_id=user.id,
        name=data.name or data.url, source_type="url", source_url=data.url,
    ))
    await repos.knowledge.update_status(doc.id, "processing")

    try:
        preview, chunk_count, fetched_text = await kb_service.add_url(agent_id, doc.id, data.url)
        await repos.knowledge.update_content(doc.id, fetched_text)
        await repos.knowledge.update_status(doc.id, "ready", chunk_count=chunk_count)
        doc = await repos.knowledge.get(doc.id)
        return {"document": doc.model_dump() if doc else {}}
    except Exception as e:
        await repos.knowledge.update_status(doc.id, "error", error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to add URL: {e}")


@router.post("/text", status_code=201)
async def add_text(
    agent_id: str,
    data: AddTextRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    kb_service = getattr(request.app.state, 'knowledge_service', None)
    if not kb_service:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    doc = await repos.knowledge.create(KnowledgeDocCreate(
        agent_id=agent_id, user_id=user.id,
        name=data.name or "Text snippet", source_type="text",
        content_hash=kb_service.content_hash(data.text),
    ))

    try:
        chunk_count = await kb_service.add_text(agent_id, doc.id, data.text, source_name=data.name)
        await repos.knowledge.update_content(doc.id, data.text)
        await repos.knowledge.update_status(doc.id, "ready", chunk_count=chunk_count)
        doc = await repos.knowledge.get(doc.id)
        return {"document": doc.model_dump() if doc else {}}
    except Exception as e:
        await repos.knowledge.update_status(doc.id, "error", error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to add text: {e}")


@router.post("/upload", status_code=201)
async def upload_file(
    agent_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    kb_service = getattr(request.app.state, 'knowledge_service', None)
    if not kb_service:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    # Read file content
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Only text-based files are supported (txt, md, csv)")

    doc = await repos.knowledge.create(KnowledgeDocCreate(
        agent_id=agent_id, user_id=user.id,
        name=file.filename or "Uploaded file", source_type="file",
        content_hash=kb_service.content_hash(text),
    ))

    try:
        chunk_count = await kb_service.add_text(agent_id, doc.id, text, source_name=file.filename or "")
        await repos.knowledge.update_content(doc.id, text)
        await repos.knowledge.update_status(doc.id, "ready", chunk_count=chunk_count)
        doc = await repos.knowledge.get(doc.id)
        return {"document": doc.model_dump() if doc else {}}
    except Exception as e:
        await repos.knowledge.update_status(doc.id, "error", error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to process file: {e}")


@router.patch("/{doc_id}")
async def update_knowledge(
    agent_id: str,
    doc_id: str,
    data: UpdateDocRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = await repos.knowledge.get(doc_id)
    if not doc or doc.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Document not found")

    kb_service = getattr(request.app.state, 'knowledge_service', None)
    if not kb_service:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    # Update name
    if data.name is not None:
        await repos.knowledge.update_name(doc_id, data.name)

    # Re-fetch URL
    if data.refetch and doc.source_type == "url" and doc.source_url:
        await repos.knowledge.update_status(doc_id, "processing")
        try:
            await kb_service.delete_document(agent_id, doc_id)
            _, chunk_count, fetched_text = await kb_service.add_url(agent_id, doc_id, doc.source_url)
            await repos.knowledge.update_content(doc_id, fetched_text)
            await repos.knowledge.update_status(doc_id, "ready", chunk_count=chunk_count)
        except Exception as e:
            await repos.knowledge.update_status(doc_id, "error", error=str(e))
            raise HTTPException(status_code=400, detail=f"Re-fetch failed: {e}")

    # Replace text content
    if data.text is not None and doc.source_type in ("text", "file"):
        await repos.knowledge.update_status(doc_id, "processing")
        try:
            await kb_service.delete_document(agent_id, doc_id)
            chunk_count = await kb_service.add_text(
                agent_id, doc_id, data.text,
                source_name=data.name or doc.name,
            )
            await repos.knowledge.update_content(doc_id, data.text)
            await repos.knowledge.update_status(doc_id, "ready", chunk_count=chunk_count)
        except Exception as e:
            await repos.knowledge.update_status(doc_id, "error", error=str(e))
            raise HTTPException(status_code=400, detail=f"Update failed: {e}")

    updated = await repos.knowledge.get(doc_id)
    return {"document": updated.model_dump() if updated else {}}


@router.delete("/{doc_id}", status_code=204)
async def delete_knowledge(
    agent_id: str,
    doc_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = await repos.knowledge.get(doc_id)
    if not doc or doc.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Document not found")

    kb_service = getattr(request.app.state, 'knowledge_service', None)
    if kb_service:
        await kb_service.delete_document(agent_id, doc_id)
    await repos.knowledge.delete(doc_id)
