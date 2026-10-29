"""28 Oct: "i dislike that when i hit cmd q, quitting the app takes a while". The app's live-update stream never ends
on its own, so the server waited out its whole grace period (two seconds) for it before stopping, then stopped its
parts one after another. A stop request now ends the streams at once."""

import asyncio
import signal

import uvicorn
from fastapi import FastAPI

from friday.server.events import Hub
from friday.server.main import Quick


def test_asking_the_server_to_stop_ends_the_live_streams_at_once() -> None:
    hub = Hub()
    server = Quick(uvicorn.Config(FastAPI()), hub)

    async def listen() -> list[str]:
        got = []
        async for message in hub.stream():
            got.append(message.event)
        return got

    async def scenario() -> list[str]:
        task = asyncio.create_task(listen())
        await asyncio.sleep(0)  # subscribed
        hub.publish("plan.changed")
        await asyncio.sleep(0.01)
        server.handle_exit(signal.SIGTERM, None)
        return await asyncio.wait_for(task, timeout=1)

    assert asyncio.run(scenario()) == ["plan.changed"]
    assert server.should_exit
