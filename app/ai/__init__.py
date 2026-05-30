"""AI integration components.

Exports are resolved lazily so general FastAPI startup does not import the
OpenAI SDK until an OpenAI-backed feature is actually used.
"""

__all__ = [
    "OpenAIClient",
    "OpenAIService",
    "OpenAIServiceResult",
    "TemporaryConversationalResponseEngine",
]


def __getattr__(name: str):
    if name in {"OpenAIClient", "OpenAIService", "OpenAIServiceResult"}:
        from app.ai.openai_service import OpenAIService, OpenAIServiceResult

        values = {
            "OpenAIClient": OpenAIService,
            "OpenAIService": OpenAIService,
            "OpenAIServiceResult": OpenAIServiceResult,
        }
        return values[name]

    if name == "TemporaryConversationalResponseEngine":
        from app.ai.temporary_response_engine import TemporaryConversationalResponseEngine

        return TemporaryConversationalResponseEngine

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
