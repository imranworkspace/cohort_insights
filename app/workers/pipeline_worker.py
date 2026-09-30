import asyncio
import random
from datetime import datetime, timezone
from app.db.mongodb import documents
from app.services.cache import ContentCache
from app.services.rate_limit import ActiveJobLimiter

def now():
    return datetime.now(timezone.utc)

def make_summary(content: str) -> str:
    words = content.split()
    return " ".join(words[:40]) + ("..." if len(words) > 40 else "")

def make_tags(content: str) -> list[str]:
    words = []
    for w in content.lower().split():
        clean = "".join(c for c in w if c.isalnum())
        if len(clean) >= 4 and clean not in words:
            words.append(clean)
        if len(words) == 5:
            break
    return words

async def claim_job():
    # Atomic claim: only one worker can change queued -> processing.
    return await documents.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "processing", "processing.status": "running",
                  "processing.started_at": now(),
                  "updated_at": now()}},
        return_document=True,
    )

async def run_stage1(doc):
    doc_id = doc["_id"]
    version = doc["content_version"]
    await asyncio.sleep(random.uniform(10, 20))
    if random.random() < 0.10:
        await documents.update_one(
            {"_id": doc_id, "content_version": version},
            {"$set": {
                "status": "failed",
                "processing.status": "failed",
                "processing.content_version": version,
                "processing.failed_at": now(),
                "processing.error": "simulated processing failure",
                "updated_at": now(),
            }}
        )
        return False

    result = make_summary(doc["content"])
    # Version predicate prevents an old worker from overwriting a PATCHed version.
    updated = await documents.update_one(
        {"_id": doc_id, "content_version": version},
        {"$set": {
            "processing.status": "completed",
            "processing.content_version": version,
            "processing.summary": result,
            "processing.completed_at": now(),
            "status": "enriching",
            "enriching.status": "queued",
            "updated_at": now(),
        }}
    )
    return updated.modified_count == 1

async def run_stage2(doc):
    doc_id = doc["_id"]
    version = doc["content_version"]
    await asyncio.sleep(random.uniform(5, 15))
    if random.random() < 0.10:
        await documents.update_one(
            {"_id": doc_id, "content_version": version},
            {"$set": {
                "status": "failed",
                "enriching.status": "failed",
                "enriching.content_version": version,
                "enriching.failed_at": now(),
                "enriching.error": "simulated enriching failure",
                "updated_at": now(),
            }}
        )
        return False

    current = await documents.find_one(
        {"_id": doc_id, "content_version": version}
    )
    if not current or current["processing"].get("content_version") != version:
        return False

    tags = make_tags(current["processing"]["summary"])
    updated = await documents.update_one(
        {"_id": doc_id, "content_version": version},
        {"$set": {
            "enriching.status": "completed",
            "enriching.content_version": version,
            "enriching.tags": tags,
            "enriching.completed_at": now(),
            "status": "completed",
            "updated_at": now(),
        }}
    )
    return updated.modified_count == 1

async def worker_loop(redis, stop_event: asyncio.Event):
    cache = ContentCache(redis)
    limiter = ActiveJobLimiter(redis)
    while not stop_event.is_set():
        doc = await claim_job()
        if not doc:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
            continue

        try:
            ok = await run_stage1(doc)
            if not ok:
                # Old-version work or stage-1 failure. Release the active slot.
                await limiter.release(doc["user_id"])
                continue

            latest = await documents.find_one({"_id": doc["_id"]})
            if not latest or latest["content_version"] != doc["content_version"]:
                await limiter.release(doc["user_id"])
                continue

            ok = await run_stage2(latest)
            if ok:
                final = await documents.find_one({"_id": doc["_id"]})
                if final:
                    result = {
                        "summary": final["processing"].get("summary"),
                        "tags": final["enriching"].get("tags"),
                        "content_version": final["content_version"],
                        "content_hash": final["content_hash"],
                    }
                    await cache.set(final["content_hash"], result)
            await limiter.release(doc["user_id"])
        except Exception:
            # Persist a controlled failure rather than silently swallowing errors.
            await documents.update_one(
                {"_id": doc["_id"], "content_version": doc["content_version"]},
                {"$set": {
                    "status": "failed",
                    "failed_stage": "worker",
                    "updated_at": now(),
                }}
            )
            await limiter.release(doc["user_id"])
