import hashlib
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument
from app.db.mongodb import documents

def utcnow():
    return datetime.now(timezone.utc)

def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=404, detail="Document not found")
    return ObjectId(value)

def public(doc: dict, include_content_result=True) -> dict:
    current = doc["content_version"]
    processing = doc["processing"]
    enriching = doc["enriching"]
    response = {
        "document_id": str(doc["_id"]),
        "user_id": doc["user_id"],
        "title": doc["title"],
        "status": doc["status"],
        "content_version": current,
        "content_hash": doc["content_hash"],
        "processing": processing,
        "enriching": enriching,
        "client_doc_ref": doc.get("client_doc_ref"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }
    # Atomic document state plus version checks prevent mixed-version results.
    if (
        include_content_result
        and processing.get("content_version") == current
        and enriching.get("content_version") == current
        and processing.get("status") == "completed"
        and enriching.get("status") == "completed"
    ):
        response["summary"] = processing.get("summary")
        response["tags"] = enriching.get("tags")
    else:
        response["summary"] = None
        response["tags"] = None
    return response

async def get_owned(document_id: str, user_id: str):
    doc = await documents.find_one({"_id": oid(document_id), "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
