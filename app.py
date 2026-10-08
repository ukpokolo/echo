import asyncio
import logging
import sys

import redis.asyncio as aioredis
from aiohttp import web
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity

from bots.echo_bot import EchoBot
from config import load_settings
from core.buffer import MessageBuffer
from core.llm import ReplyGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("echo-bot")

settings = load_settings()

adapter = BotFrameworkAdapter(
    BotFrameworkAdapterSettings(
        app_id=settings.microsoft_app_id,
        app_password=settings.microsoft_app_password,
        channel_auth_tenant=settings.microsoft_app_tenant_id or None,
    )
)


async def on_error(context: TurnContext, error: Exception):
    logger.exception("Turn error: %s", error)
    try:
        await context.send_activity("Sorry, something went wrong on my side. Please try again.")
    except Exception:
        pass


adapter.on_turn_error = on_error

redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
buffer = MessageBuffer(
    redis_client,
    window_seconds=settings.debounce_seconds,
    max_wait_seconds=settings.debounce_max_wait_seconds,
    ttl_seconds=settings.buffer_ttl_seconds,
)
generator = ReplyGenerator(settings)
bot = EchoBot(adapter, buffer, generator, settings)

_stop = asyncio.Event()


async def debounce_worker():
    logger.info(
        "Debounce worker started (window=%.1fs, max_wait=%.1fs, poll=%.2fs)",
        settings.debounce_seconds,
        settings.debounce_max_wait_seconds,
        settings.poll_interval_seconds,
    )
    while not _stop.is_set():
        try:
            for claimed in await buffer.claim_due():
                try:
                    await bot.respond(claimed.reference, claimed.messages)
                except Exception:
                    logger.exception("Failed replying to %s", claimed.conversation_id)
        except Exception:
            logger.exception("Debounce worker cycle failed")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=settings.poll_interval_seconds)
        except asyncio.TimeoutError:
            pass


async def messages(req: web.Request) -> web.Response:
    if "application/json" not in req.headers.get("Content-Type", ""):
        return web.Response(status=415)
    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")
    try:
        response = await adapter.process_activity(auth_header, activity, bot.on_turn)
        if response:
            return web.json_response(data=response.body, status=response.status)
        return web.Response(status=201)
    except Exception:
        logger.exception("process_activity failed")
        return web.Response(status=500)


async def on_startup(app: web.Application):
    app["worker"] = asyncio.create_task(debounce_worker())


async def on_cleanup(app: web.Application):
    _stop.set()
    worker = app.get("worker")
    if worker:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    await redis_client.aclose()


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/", lambda _: web.Response(text="Echo bot is running."))
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=settings.port)
