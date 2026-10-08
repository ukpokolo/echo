import json
import time
from dataclasses import dataclass
from typing import List, Optional


CLAIM_SCRIPT = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
local out = {}
for i = 1, #due do
  local cid = due[i]
  redis.call('ZREM', KEYS[1], cid)
  local mkey = ARGV[3] .. cid
  local rkey = ARGV[4] .. cid
  local fkey = ARGV[5] .. cid
  local msgs = redis.call('LRANGE', mkey, 0, -1)
  local ref = redis.call('GET', rkey)
  redis.call('DEL', mkey, rkey, fkey)
  if #msgs > 0 and ref then
    table.insert(out, cid)
    table.insert(out, ref)
    table.insert(out, tostring(#msgs))
    for j = 1, #msgs do
      table.insert(out, msgs[j])
    end
  end
end
return out
"""


@dataclass
class ClaimedConversation:
    conversation_id: str
    reference: dict
    messages: List[str]


class MessageBuffer:
    def __init__(
        self,
        redis_client,
        window_seconds: float = 5.0,
        max_wait_seconds: Optional[float] = 20.0,
        ttl_seconds: int = 300,
        prefix: str = "debounce",
    ):
        self._redis = redis_client
        self._window = float(window_seconds)
        self._max_wait = float(max_wait_seconds) if max_wait_seconds else None
        self._ttl = int(ttl_seconds)
        self._prefix = prefix
        self._due_key = f"{prefix}:due"
        self._msg_prefix = f"{prefix}:msgs:"
        self._ref_prefix = f"{prefix}:ref:"
        self._first_prefix = f"{prefix}:first:"
        self._claim = redis_client.register_script(CLAIM_SCRIPT)

    async def add(self, conversation_id: str, text: str, reference: dict, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now

        first_key = f"{self._first_prefix}{conversation_id}"
        await self._redis.set(first_key, repr(now), nx=True, ex=self._ttl)
        first_raw = await self._redis.get(first_key)
        try:
            first_seen = float(first_raw) if first_raw is not None else now
        except (TypeError, ValueError):
            first_seen = now

        due = now + self._window
        if self._max_wait is not None:
            due = min(due, first_seen + self._max_wait)

        pipe = self._redis.pipeline()
        pipe.rpush(f"{self._msg_prefix}{conversation_id}", json.dumps(text, ensure_ascii=False))
        pipe.expire(f"{self._msg_prefix}{conversation_id}", self._ttl)
        pipe.set(f"{self._ref_prefix}{conversation_id}", json.dumps(reference, ensure_ascii=False), ex=self._ttl)
        pipe.zadd(self._due_key, {conversation_id: due})
        await pipe.execute()
        return due

    async def claim_due(self, now: Optional[float] = None, limit: int = 50) -> List[ClaimedConversation]:
        now = time.time() if now is None else now
        raw = await self._claim(
            keys=[self._due_key],
            args=[repr(now), int(limit), self._msg_prefix, self._ref_prefix, self._first_prefix],
        )
        claimed: List[ClaimedConversation] = []
        i = 0
        while i < len(raw):
            cid = raw[i]
            ref_raw = raw[i + 1]
            count = int(raw[i + 2])
            i += 3
            messages = list(raw[i : i + count])
            i += count
            try:
                reference = json.loads(ref_raw)
            except (TypeError, ValueError):
                reference = None
            if reference is None:
                continue
            claimed.append(
                ClaimedConversation(
                    conversation_id=cid,
                    reference=reference,
                    messages=[self._decode(m) for m in messages],
                )
            )
        return claimed

    async def clear(self, conversation_id: str) -> None:
        await self._redis.delete(
            f"{self._msg_prefix}{conversation_id}",
            f"{self._ref_prefix}{conversation_id}",
            f"{self._first_prefix}{conversation_id}",
        )
        await self._redis.zrem(self._due_key, conversation_id)

    async def pending(self, conversation_id: str) -> List[str]:
        raw = await self._redis.lrange(f"{self._msg_prefix}{conversation_id}", 0, -1)
        return [self._decode(m) for m in raw]

    @staticmethod
    def _decode(value):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return value
        return decoded if isinstance(decoded, str) else str(decoded)
