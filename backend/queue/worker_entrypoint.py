"""Standalone worker entrypoint for Railway / Docker deployments.

This is the only process that runs the Redis Streams consumer loop.
The Vercel API (webhooks, jobs endpoints) enqueues jobs;
this worker picks them up and runs the full agentic loop.

Run:
    python -m backend.queue.worker_entrypoint
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import structlog

from ..telemetry import setup_telemetry
from .worker import start_worker_pool

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

logger = structlog.get_logger(__name__)


async def main() -> None:
    setup_telemetry()

    logger.info(
        "devmind.worker.starting",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        concurrency=os.getenv("WORKER_CONCURRENCY", "4"),
    )

    tasks = await start_worker_pool()

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("devmind.worker.shutdown_signal", signal=sig.name)
        for task in tasks:
            task.cancel()
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown, sig)

    logger.info("devmind.worker.ready", task_count=len(tasks))

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("devmind.worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
