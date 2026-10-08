import fakeredis.aioredis
import pytest

from core.buffer import MessageBuffer
from core.text import combine_messages


def make_buffer(window=5.0, max_wait=20.0):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return MessageBuffer(client, window_seconds=window, max_wait_seconds=max_wait, ttl_seconds=300), client


@pytest.mark.asyncio
async def test_three_rapid_messages_produce_one_combined_claim():
    buffer, _ = make_buffer()
    ref = {"conversation": {"id": "c1"}, "serviceUrl": "https://smba.trafficmanager.net"}

    t = 1000.0
    await buffer.add("teams:c1", "Hello..", ref, now=t)
    await buffer.add("teams:c1", "I want to make enquiry about your services", ref, now=t + 1)
    await buffer.add("teams:c1", "and what days of the week are you guys opened", ref, now=t + 2)

    assert await buffer.claim_due(now=t + 5) == []

    claimed = await buffer.claim_due(now=t + 7)
    assert len(claimed) == 1
    assert claimed[0].conversation_id == "teams:c1"
    assert len(claimed[0].messages) == 3
    assert claimed[0].messages[0] == "Hello.."
    assert claimed[0].messages[2] == "and what days of the week are you guys opened"

    assert await buffer.claim_due(now=t + 30) == []


@pytest.mark.asyncio
async def test_window_slides_with_each_new_message():
    buffer, _ = make_buffer(window=5.0)
    ref = {"conversation": {"id": "c1"}}

    await buffer.add("teams:c1", "first", ref, now=1000.0)
    await buffer.add("teams:c1", "second", ref, now=1003.0)

    assert await buffer.claim_due(now=1005.5) == []

    claimed = await buffer.claim_due(now=1008.5)
    assert len(claimed) == 1
    assert claimed[0].messages == ["first", "second"]


@pytest.mark.asyncio
async def test_max_wait_caps_a_never_ending_stream():
    buffer, _ = make_buffer(window=5.0, max_wait=8.0)
    ref = {"conversation": {"id": "c1"}}

    await buffer.add("teams:c1", "m1", ref, now=1000.0)
    await buffer.add("teams:c1", "m2", ref, now=1004.0)
    await buffer.add("teams:c1", "m3", ref, now=1007.0)

    claimed = await buffer.claim_due(now=1008.1)
    assert len(claimed) == 1
    assert claimed[0].messages == ["m1", "m2", "m3"]


@pytest.mark.asyncio
async def test_conversations_are_isolated():
    buffer, _ = make_buffer(window=5.0)
    ref_a = {"conversation": {"id": "a"}}
    ref_b = {"conversation": {"id": "b"}}

    await buffer.add("teams:a", "hi from a", ref_a, now=1000.0)
    await buffer.add("teams:b", "hi from b", ref_b, now=1000.0)

    claimed = await buffer.claim_due(now=1006.0)
    ids = {c.conversation_id for c in claimed}
    assert ids == {"teams:a", "teams:b"}
    for c in claimed:
        assert len(c.messages) == 1


@pytest.mark.asyncio
async def test_reset_clears_buffer():
    buffer, _ = make_buffer()
    ref = {"conversation": {"id": "c1"}}

    await buffer.add("teams:c1", "queued", ref, now=1000.0)
    await buffer.clear("teams:c1")

    assert await buffer.pending("teams:c1") == []
    assert await buffer.claim_due(now=1100.0) == []


def test_combine_messages_trims_and_orders():
    combined = combine_messages(["Hello..", "  enquiry  ", "", "  ", "opening days"])
    assert combined == "Hello..\nenquiry\nopening days"
