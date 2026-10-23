"""The SSE hub (DESIGN §18.2): items.changed, plan.provisional, plan.changed, status.changed.

Publishing happens on request threads, the worker supervisor and the job loop; each subscriber is an asyncio queue
on the server's event loop, so events are handed over with `call_soon_threadsafe`.
"""

import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi.sse import ServerSentEvent

QUEUE_LIMIT = 100  # a client this far behind has gone; it reconnects and refetches


class Hub:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()

    def publish(self, event: str, data: Any = None) -> None:
        # A browser's EventSource drops an event with no data line, so an event without data still sends "{}".
        message = ServerSentEvent(event=event, data={} if data is None else data)
        with self.lock:
            subscribers = list(self.subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(offer, queue, message)

    async def stream(self) -> AsyncIterator[ServerSentEvent]:
        queue: asyncio.Queue = asyncio.Queue(QUEUE_LIMIT)
        entry = (asyncio.get_running_loop(), queue)
        with self.lock:
            self.subscribers.add(entry)
        try:
            while True:
                message = await queue.get()
                if message is None:
                    return
                yield message
        finally:
            with self.lock:
                self.subscribers.discard(entry)

    def close(self) -> None:
        """End every stream, so the server can shut down."""
        with self.lock:
            subscribers = list(self.subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(offer, queue, None)


def offer(queue: asyncio.Queue, message: ServerSentEvent | None) -> None:
    if message is None or not queue.full():
        queue.put_nowait(message)
