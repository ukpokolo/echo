import logging

logger = logging.getLogger(__name__)


class ReplyGenerator:
    def __init__(self, settings):
        self._settings = settings
        self._client = None
        self._model = None
        self._is_azure = settings.llm_provider == "azure"

        if self._is_azure:
            from openai import AsyncAzureOpenAI

            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
            )
            self._model = settings.azure_openai_deployment
        else:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_model

    async def generate(self, combined_text: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._settings.system_prompt},
                    {"role": "user", "content": combined_text},
                ],
                temperature=0.4,
                max_tokens=600,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("LLM call failed; using fallback response")
            return self._fallback(combined_text)

    @staticmethod
    def _fallback(combined_text: str) -> str:
        return (
            "Thanks for reaching out! I've got your message and will get back to you shortly."
        )
