import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.core.config import settings
from app.db.mongodb import client, db, create_indexes
from app.api.routes.documents import router as documents_router
from app.api.routes.users import router as users_router
from app.workers.pipeline_worker import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):

    # MongoDB indexes
    await create_indexes()

    # Redis connection
    app.state.redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True
    )

    # Check Redis connection
    await app.state.redis.ping()

    # Worker
    stop_event = asyncio.Event()

    app.state.worker_stop = stop_event

    app.state.worker_task = asyncio.create_task(
        worker_loop(
            app.state.redis,
            stop_event
        )
    )

    yield

    # Shutdown
    stop_event.set()

    await app.state.worker_task

    await app.state.redis.close()

    client.close()


app = FastAPI(
    title="Cohort Insights API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(documents_router)
app.include_router(users_router)


@app.get("/health")
async def health():

    await db.command("ping")
    await app.state.redis.ping()

    return {
        "status": "ok",
        "mongo": "ok",
        "redis": "ok"
    }