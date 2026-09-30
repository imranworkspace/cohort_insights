from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict

class DocumentCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=1_000_000)
    client_doc_ref: Optional[str] = Field(default=None, min_length=1, max_length=256)

class DocumentPatch(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)

class StageView(BaseModel):
    status: str
    content_version: Optional[int] = None
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None
    failed_at: Optional[Any] = None
    error: Optional[str] = None

class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document_id: str
    user_id: str
    title: str
    status: str
    content_version: int
    content_hash: str
    processing: StageView
    enriching: StageView
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    client_doc_ref: Optional[str] = None
    created_at: Any
    updated_at: Any

class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    page: int
    page_size: int
    total: int
