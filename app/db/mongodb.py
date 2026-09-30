from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

client = AsyncIOMotorClient(settings.mongo_uri)
db = client[settings.mongo_db]
documents = db["documents"]

async def create_indexes():
    await documents.create_index([("client_doc_ref", 1)], unique=True, sparse=True)
    await documents.create_index([("user_id", 1), ("created_at", -1)])
    await documents.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
    await documents.create_index([("content_hash", 1), ("pipeline_status", 1)])
    await documents.create_index([("status", 1), ("updated_at", 1)])
