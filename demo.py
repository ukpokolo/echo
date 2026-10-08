"""Offline demo of the debounce pipeline: simulates the exact scenario from the
challenge (3 rapid messages) and prints the single combined reply that goes out.

Run:  python demo.py
"""

import asyncio

import fakeredis.aioredis

from core.buffer import MessageBuffer
from core.text import combine_messages

SCENARIO = [
    ("Hello..", 0.0),
    ("I want to make enquiry about your services", 0.9),
    ("and what days of the week are you guys opened", 1.5),
]

WINDOW = 3.0


async def fake_llm(combined: str) -> str:
    await asyncio.sleep(0.2)
    return (
        "Hi! Thanks for reaching out. Happy to help with our services.\n"
        "We're open Monday to Friday, 9am-5pm. What would you like to know?\n\n"
        "(I answered all three of your messages at once.)"
    )


async def main():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    buffer = MessageBuffer(client, window_seconds=WINDOW, max_wait_seconds=10.0)

    ref = {"conversation": {"id": "demo"}, "serviceUrl": "https://smba.trafficmanager.net"}
    cid = "teams:demo"
    clock = 100.0

    async def worker():
        while True:
            for claimed in await buffer.claim_due(now=clock):
                combined = combine_messages(claimed.messages)
                print("\n--- buffer flushed, ONE reply sent ---")
                print(await fake_llm(combined))
                return
            await asyncio.sleep(0.05)

    task = asyncio.create_task(worker())

    for text, offset in SCENARIO:
        clock += offset
        await buffer.add(cid, text, ref, now=clock)
        print(f"[{offset:>4.1f}s] user sent: {text!r}")

    clock += WINDOW + 0.1
    await asyncio.wait_for(task, timeout=5)

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
