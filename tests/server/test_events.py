"""The SSE hub hands events published on any thread to every open stream."""

import asyncio
import threading

from friday.server.events import Hub


def test_events_published_on_another_thread_reach_every_stream() -> None:
    hub = Hub()

    async def listen() -> list[tuple[str | None, object]]:
        streams = [hub.stream(), hub.stream()]
        firsts = [asyncio.ensure_future(anext(s)) for s in streams]
        await asyncio.sleep(0.01)  # both have subscribed
        threading.Thread(target=hub.publish, args=("plan.changed", {"plan_id": 7})).start()
        got = [await f for f in firsts]
        hub.close()
        return [(m.event, m.data) for m in got]

    assert asyncio.run(listen()) == [("plan.changed", {"plan_id": 7})] * 2


def test_an_event_without_data_still_sends_a_data_line() -> None:
    """A browser's EventSource ignores an event with no data line, so app refreshes depend on it."""
    hub = Hub()

    async def listen() -> object:
        stream = hub.stream()
        first = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.01)
        hub.publish("items.changed")
        message = await first
        hub.close()
        return message.data

    assert asyncio.run(listen()) == {}
