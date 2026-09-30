from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis
from app.db.mongodb import documents
from app.schemas.document import DocumentCreate, DocumentPatch, DocumentResponse
from app.services.document_service import content_hash, get_owned, oid, public
from app.services.rate_limit import ActiveJobLimiter
from app.services.cache import ContentCache

router = APIRouter(prefix="/documents", tags=["documents"])

def get_redis(request: Request):
    return request.app.state.redis

@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(payload: DocumentCreate, redis: Redis = Depends(get_redis)):
    limiter = ActiveJobLimiter(redis)
    if not await limiter.reserve(payload.user_id):
        raise HTTPException(status_code=429, detail="Maximum 3 active documents reached")

    h = content_hash(payload.content)
    cache = ContentCache(redis)
    cached = await cache.get(h)

    try:
        if cached:
            now = datetime.now(timezone.utc)
            doc = {
                "user_id": payload.user_id,
                "title": payload.title,
                "content": payload.content,
                "content_hash": h,
                "content_version": 1,
                "status": "completed",
                "processing": {
                    "status": "completed", "content_version": 1,
                    "summary": cached["summary"], "completed_at": now
                },
                "enriching": {
                    "status": "completed", "content_version": 1,
                    "tags": cached["tags"], "completed_at": now
                },
                "client_doc_ref": payload.client_doc_ref,
                "created_at": now,
                "updated_at": now,
            }
            result = await documents.insert_one(doc)
            doc["_id"] = result.inserted_id
            await limiter.release(payload.user_id)
            return public(doc)

        now = datetime.now(timezone.utc)
        doc = {
            "user_id": payload.user_id,
            "title": payload.title,
            "content": payload.content,
            "content_hash": h,
            "content_version": 1,
            "status": "queued",
            "processing": {"status": "queued", "content_version": None},
            "enriching": {"status": "blocked", "content_version": None},
            "client_doc_ref": payload.client_doc_ref,
            "created_at": now,
            "updated_at": now,
        }
        result = await documents.insert_one(doc)
        doc["_id"] = result.inserted_id
        return public(doc)
    except DuplicateKeyError:
        await limiter.release(payload.user_id)
        if payload.client_doc_ref:
            existing = await documents.find_one({"client_doc_ref": payload.client_doc_ref})
            if existing and existing["content_hash"] == h:
                return public(existing)
        raise HTTPException(status_code=409, detail="client_doc_ref already exists with different content")
    except Exception:
        await limiter.release(payload.user_id)
        raise

@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(document_id: str, payload: DocumentPatch, redis: Redis = Depends(get_redis)):
    doc = await documents.find_one({"_id": oid(document_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    limiter = ActiveJobLimiter(redis)
    if not await limiter.reserve(doc["user_id"]):
        raise HTTPException(status_code=429, detail="Maximum 3 active documents reached")

    new_version = doc["content_version"] + 1
    h = content_hash(payload.content)
    now = datetime.now(timezone.utc)

    updated = await documents.find_one_and_update(
        {"_id": doc["_id"], "content_version": doc["content_version"]},
        {"$set": {
            "content": payload.content,
            "content_hash": h,
            "content_version": new_version,
            "status": "queued",
            "processing": {"status": "queued", "content_version": None},
            "enriching": {"status": "blocked", "content_version": None},
            "updated_at": now,
        }},
        return_document=True,
    )
    if not updated:
        await limiter.release(doc["user_id"])
        raise HTTPException(status_code=409, detail="Document was modified concurrently")
    # The previous active slot belonged to the old run. The new reservation is
    # intentionally retained for the new run; an old worker releases its slot
    # when it notices the version mismatch.
    return public(updated)

@router.get("/by-ref/{client_doc_ref}", response_model=DocumentResponse)
async def get_by_ref(client_doc_ref: str):
    doc = await documents.find_one({"client_doc_ref": client_doc_ref})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return public(doc)

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, user_id: str = Query(..., min_length=1)):
    return public(await get_owned(document_id, user_id))

@router.get("/user/{user_id}", response_model=dict)
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
