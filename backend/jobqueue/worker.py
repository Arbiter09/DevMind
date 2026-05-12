"""Async worker pool that consumes jobs from Redis Streams and runs the agent loop."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

import structlog

from ..agent.loop import AgentOrchestrator
from .streams import get_job_queue

logger = structlog.get_logger(__name__)

WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))


async def run_worker(worker_id: str) -> None:
    queue = get_job_queue()
    orchestrator = AgentOrchestrator()

    logger.info("worker.started", worker_id=worker_id)

    while True:
        try:
            messages = await queue.consume(consumer_name=worker_id, count=1, block_ms=2000)
            if not messages:
                continue

            for entry_id, fields in messages:
                job_id = fields.get("job_id", str(uuid.uuid4()))
                pr_number = int(fields.get("pr_number", 0))
                repo = fields.get("repo", "")

                log = logger.bind(job_id=job_id, pr=pr_number, repo=repo)
                log.info("worker.job_received")

                try:
                    await orchestrator.run(job_id=job_id, pr_number=pr_number, repo=repo)
                    await queue.ack(entry_id)
                    log.info("worker.job_completed")
                except Exception as exc:
                    log.error("worker.job_failed", error=str(exc))
                    await queue.nack(entry_id, fields)

        except asyncio.CancelledError:
            logger.info("worker.stopping", worker_id=worker_id)
            break
        except Exception as exc:
            logger.error("worker.error", worker_id=worker_id, error=str(exc))
            await asyncio.sleep(1)


async def start_worker_pool() -> list[asyncio.Task]:
    queue = get_job_queue()
    await queue.setup()

    tasks = []
    for i in range(WORKER_CONCURRENCY):
        worker_id = f"worker-{i}"
        task = asyncio.create_task(run_worker(worker_id), name=worker_id)
        tasks.append(task)

    logger.info("worker_pool.started", concurrency=WORKER_CONCURRENCY)
    return tasks
