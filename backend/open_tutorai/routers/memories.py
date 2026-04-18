from enum import Enum
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from open_webui.internal.db import JSONField, get_db
from open_webui.utils.auth import get_verified_user
from open_webui.models.users import Users
from open_tutorai.models.database import Memory

router = APIRouter(tags=["memories"])


class MemoryType(str, Enum):
    episodic = "episodic"
    semantic = "semantic"
    procedural = "procedural"
    behavioral = "behavioral"


class MemoryForm(BaseModel):
    memory_type: MemoryType = Field(..., description="Memory category")
    content: str = Field(..., min_length=1, description="Memory text content")
    memory_metadata: Optional[dict] = Field(None, description="Optional structured metadata")


class MemoryUpdateForm(BaseModel):
    memory_type: Optional[MemoryType] = Field(None, description="Memory category")
    content: Optional[str] = Field(None, description="Memory text content")
    memory_metadata: Optional[dict] = Field(None, description="Optional structured metadata")


class MemoryQueryForm(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    memory_type: Optional[MemoryType] = Field(None, description="Optional memory filter")
    limit: Optional[int] = Field(20, ge=1, le=200, description="Max number of results")


class MemoryResponse(BaseModel):
    id: str
    memory_type: MemoryType
    content: str
    memory_metadata: Optional[dict]
    created_at: Optional[float]
    updated_at: Optional[float]

    class Config:
        orm_mode = True


def serialize_memory(memory: Memory) -> dict:
    return {
        "id": memory.id,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "memory_metadata": memory.memory_metadata,
        "created_at": memory.created_at.timestamp() if memory.created_at else None,
        "updated_at": memory.updated_at.timestamp() if memory.updated_at else None,
    }


@router.get("/memories/", response_model=List[MemoryResponse])
async def get_memories(
    memory_type: Optional[MemoryType] = Query(None, alias="memory_type"),
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        query = db.query(Memory).filter(Memory.user_id == user.id)
        if memory_type is not None:
            query = query.filter(Memory.memory_type == memory_type.value)
        memories = query.order_by(Memory.updated_at.desc().nullslast(), Memory.created_at.desc()).all()
        return [serialize_memory(memory) for memory in memories]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/memories/add", response_model=MemoryResponse)
async def add_memory(
    form_data: MemoryForm,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        memory = Memory(
            id=uuid4().hex,
            user_id=user.id,
            memory_type=form_data.memory_type.value,
            content=form_data.content.strip(),
            memory_metadata=form_data.memory_metadata,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return serialize_memory(memory)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/memories/query", response_model=List[MemoryResponse])
async def query_memory(
    query_data: MemoryQueryForm,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        query = db.query(Memory).filter(Memory.user_id == user.id)
        if query_data.memory_type is not None:
            query = query.filter(Memory.memory_type == query_data.memory_type.value)
        query = query.filter(Memory.content.ilike(f"%{query_data.query}%"))
        memories = query.order_by(Memory.updated_at.desc().nullslast(), Memory.created_at.desc()).limit(query_data.limit).all()
        return [serialize_memory(memory) for memory in memories]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/memories/{memory_id}/update", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    update_data: MemoryUpdateForm,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user.id).first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        if update_data.content is not None:
            memory.content = update_data.content.strip()
        if update_data.memory_type is not None:
            memory.memory_type = update_data.memory_type.value
        if update_data.memory_metadata is not None:
            memory.memory_metadata = update_data.memory_metadata

        db.add(memory)
        db.commit()
        db.refresh(memory)
        return serialize_memory(memory)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user.id).first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        db.delete(memory)
        db.commit()
        return {"success": True, "id": memory_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/memories/delete/user")
async def delete_memories_by_user(
    user=Depends(get_verified_user),
    db=Depends(get_db),
):
    try:
        db.query(Memory).filter(Memory.user_id == user.id).delete(synchronize_session=False)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
