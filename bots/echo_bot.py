import logging

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount, ConversationAccount, ConversationReference

from core.text import combine_messages, is_reset_command

logger = logging.getLogger(__name__)


def reference_to_dict(reference: ConversationReference) -> dict:
    def account(a):
        if a is None:
            return None
        return {
            "id": a.id,
            "name": a.name,
            "aadObjectId": getattr(a, "aad_object_id", None),
            "role": getattr(a, "role", None),
        }

    def conversation(c):
        if c is None:
            return None
        return {
            "id": c.id,
            "name": getattr(c, "name", None),
            "isGroup": getattr(c, "is_group", None),
            "conversationType": getattr(c, "conversation_type", None),
            "tenantId": getattr(c, "tenant_id", None),
            "aadObjectId": getattr(c, "aad_object_id", None),
        }

    return {
        "activityId": reference.activity_id,
        "user": account(reference.user),
        "bot": account(reference.bot),
        "conversation": conversation(reference.conversation),
        "channelId": reference.channel_id,
        "locale": getattr(reference, "locale", None),
        "serviceUrl": reference.service_url,
    }


def reference_from_dict(data: dict) -> ConversationReference:
    def account(a):
        if not a:
            return None
        return ChannelAccount(
            id=a.get("id"),
            name=a.get("name"),
            aad_object_id=a.get("aadObjectId"),
            role=a.get("role"),
        )

    def conversation(c):
        if not c:
            return None
        return ConversationAccount(
            id=c.get("id"),
            name=c.get("name"),
            is_group=c.get("isGroup"),
            conversation_type=c.get("conversationType"),
            tenant_id=c.get("tenantId"),
            aad_object_id=c.get("aadObjectId"),
        )

    return ConversationReference(
        activity_id=data.get("activityId"),
        user=account(data.get("user")),
        bot=account(data.get("bot")),
        conversation=conversation(data.get("conversation")),
        channel_id=data.get("channelId"),
        locale=data.get("locale"),
        service_url=data.get("serviceUrl"),
    )


class EchoBot(ActivityHandler):
    def __init__(self, adapter, buffer, generator, settings):
        self._adapter = adapter
        self._buffer = buffer
        self._generator = generator
        self._settings = settings

    @staticmethod
    def _conversation_id(turn_context: TurnContext) -> str:
        activity = turn_context.activity
        conversation = activity.conversation.id if activity.conversation else "unknown"
        return f"{activity.channel_id}:{conversation}"

    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()
        if not text:
            return

        conversation_id = self._conversation_id(turn_context)

        if is_reset_command(text):
            await self._buffer.clear(conversation_id)
            await turn_context.send_activity("Cleared anything you had queued up. Go ahead.")
            return

        reference = TurnContext.get_conversation_reference(turn_context.activity)
        existing = await self._buffer.pending(conversation_id)

        await self._buffer.add(conversation_id, text, reference_to_dict(reference))

        if not existing:
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))

    async def respond(self, reference_dict: dict, messages) -> None:
        reference = reference_from_dict(reference_dict)
        combined = combine_messages(messages)

        async def _send(turn_context: TurnContext):
            reply = await self._generator.generate(combined)
            await turn_context.send_activity(reply)

        await self._adapter.continue_conversation(reference, _send, self._settings.microsoft_app_id)
