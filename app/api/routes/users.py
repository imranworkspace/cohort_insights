from fastapi import APIRouter, Query
from app.db.mongodb import documents
from app.services.document_service import public

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}/documents")
async def list_user_documents(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    query = {"user_id": user_id}
    if status:
        query["status"] = status
    total = await documents.count_documents(query)
    cursor = documents.find(query).sort([("created_at", -1)]).skip((page - 1) * page_size).limit(page_size)
    items = [public(d) async for d in cursor]
    return {"items": items, "page": page, "page_size": page_size, "total": total}
