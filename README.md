# Echo

A Microsoft Teams chatbot that solves the "3 separate replies" problem: when a user
fires off several short messages in a row (`Hello..` / `I want to make enquiry about your
services` / `and what days of the week are you guys opened`), the bot **waits, collects
them into one context, and replies once**.

Yes — this is built entirely in **Python** and runs as a **Microsoft Teams** bot.

## How it works

```
Teams user ──▶ Bot Framework ──▶ /api/messages ──▶ EchoBot.on_message_activity
                                                        │
                                                        ▼
                                  Redis buffer  (per conversation, sliding timer)
                                                        │
                                     background worker polls for "due" conversations
                                                        ▼
                                    combine messages ──▶ LLM ──▶ ONE reply
                                                        │
                                          adapter.continue_conversation(...)
```

The key detail: the bot framework is **stateless per request**, so you cannot hold an
in-memory `Timer` and reply later from it. Instead:

1. Each inbound message is pushed into a Redis list keyed by conversation, and a
   timestamp is written into a Redis **sorted set** (`debounce:due`, score = "reply at").
2. Every new message **resets (slides)** the timer for that conversation.
3. A background worker atomically claims conversations whose timer has expired (a Lua
   script, so concurrent messages can never be lost or double-replied) and fetches the
   stored `ConversationReference`.
4. It concatenates the buffered messages, asks the LLM for one natural answer, and sends
   it via `adapter.continue_conversation(...)`.
5. A `DEBOUNCE_MAX_WAIT_SECONDS` cap stops an endless stream from being delayed forever.
6. The first message of a batch triggers a **typing** indicator (not a reply), so the user
   sees the bot is "about to type".

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | aiohttp server, Bot Framework adapter, `/api/messages`, background worker |
| `bots/echo_bot.py` | `ActivityHandler` that buffers messages + ConversationReference (de)serialisation |
| `core/buffer.py` | Redis-backed debounce buffer (sliding window, atomic claim, max-wait cap) |
| `core/llm.py` | Azure OpenAI / OpenAI reply generation with graceful fallback |
| `core/text.py` | message combining + reset-command detection |
| `config.py` | env-driven settings |
| `demo.py` | offline demo of the exact challenge scenario (no Teams/Redis needed) |
| `tests/test_buffer.py` | unit tests for debouncing, sliding window, isolation, max-wait |

## Try the logic instantly (no infra)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install fakeredis lupa
.\.venv\Scripts\python.exe demo.py     # prints the single combined reply
.\.venv\Scripts\python.exe -m pytest -q
```

## Run it for real

1. Install everything:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
2. Start Redis (Docker):
   ```powershell
   docker run --name redis -p 6379:6379 -d redis:7
   ```
3. Copy `.env.example` to `.env` and fill in your bot + LLM credentials.
4. Run the bot:
   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```
5. Expose it and register with Teams:
   - `ngrok http 3978` → note the public HTTPS URL.
   - Create an **Azure Bot** resource, set its messaging endpoint to
     `https://<your-ngrok-host>/api/messages`.
   - Put the bot's `MICROSOFT_APP_ID` / `MICROSOFT_APP_PASSWORD` in `.env`.
   - Add the **Microsoft Teams** channel to the Azure Bot, then use
     **Test in Web Chat** or Teams itself.

## Tuning

| Env var | Meaning | Default |
| --- | --- | --- |
| `DEBOUNCE_SECONDS` | quiet period to wait after the last message | `5` |
| `DEBOUNCE_MAX_WAIT_SECONDS` | hard cap so a constant chatter still gets a reply | `20` |
| `POLL_INTERVAL_SECONDS` | how often the worker checks for due conversations | `0.5` |
| `BUFFER_TTL_SECONDS` | safety expiry for orphaned buffers | `300` |

## Notes / production hardening

- The "due" scan builds per-conversation keys inside Lua from a prefix argument. That is
  fine on a single Redis instance or a replica; on **Redis Cluster** you would pass those keys
  explicitly to keep them in the same hash slot.
- Use **Azure Cache for Redis** and run the bot on **App Service / Container Apps** for a
  managed deployment; the design already tolerates multiple instances because state lives
  in Redis and claims are atomic.
- Return the `typing` activity only on the first message of a batch to avoid spamming.
