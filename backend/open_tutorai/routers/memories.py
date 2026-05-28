from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.models.database import Memory

router = APIRouter(tags=["memories"])


class MemoryCreate(BaseModel):
    memory_type: str
    content: str
    memory_metadata: Optional[dict] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    memory_metadata: Optional[dict] = None


class MemoryOut(BaseModel):
    id: str
    user_id: str
    memory_type: str
    content: str
    memory_metadata: Optional[dict] = None

    model_config = {"from_attributes": True}


@router.get("/memories/", response_model=list[MemoryOut])
def list_memories(
    memory_type: Optional[str] = None,
    user=Depends(get_verified_user),
):
    with get_db() as db:
        q = db.query(Memory).filter(Memory.user_id == user.id)
        if memory_type:
            q = q.filter(Memory.memory_type == memory_type)
        return [MemoryOut.model_validate(m) for m in q.order_by(Memory.created_at.desc()).all()]


@router.post("/memories/add", response_model=MemoryOut)
def add_memory(
    body: MemoryCreate,
    user=Depends(get_verified_user),
):
    with get_db() as db:
        mem = Memory(
            id=uuid4().hex,
            user_id=user.id,
            memory_type=body.memory_type,
            content=body.content,
            memory_metadata=body.memory_metadata or {},
        )
        db.add(mem)
        db.commit()
        db.refresh(mem)
        return MemoryOut.model_validate(mem)


@router.post("/memories/query", response_model=list[MemoryOut])
def query_memories(
    body: dict,
    user=Depends(get_verified_user),
):
    query_text = (body.get("query") or "").lower()
    memory_type = body.get("memory_type")
    with get_db() as db:
        q = db.query(Memory).filter(Memory.user_id == user.id)
        if memory_type:
            q = q.filter(Memory.memory_type == memory_type)
        results = [m for m in q.all() if query_text in m.content.lower()]
        return [MemoryOut.model_validate(m) for m in results[:20]]


@router.put("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: str,
    body: MemoryUpdate,
    user=Depends(get_verified_user),
):
    with get_db() as db:
        mem = db.query(Memory).filter(
            Memory.id == memory_id, Memory.user_id == user.id
        ).first()
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found")
        if body.content is not None:
            mem.content = body.content
        if body.memory_metadata is not None:
            mem.memory_metadata = body.memory_metadata
        db.commit()
        db.refresh(mem)
        return MemoryOut.model_validate(mem)


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(
    memory_id: str,
    user=Depends(get_verified_user),
):
    with get_db() as db:
        mem = db.query(Memory).filter(
            Memory.id == memory_id, Memory.user_id == user.id
        ).first()
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found")
        db.delete(mem)
        db.commit()
