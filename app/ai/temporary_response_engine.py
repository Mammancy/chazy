from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.english_learning_pipeline import EnglishLearningPipeline, GrammarAnalysis


@dataclass
class SessionContext:
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    user_details: dict[str, str] = field(default_factory=dict)


class TemporaryConversationalResponseEngine:
    """Local fallback for English speaking coach responses when OpenAI is unavailable."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._english_pipeline = EnglishLearningPipeline()

    def generate_response(self, *, session_id: str, user_message: str) -> str:
        return self.generate_learning_response(session_id=session_id, user_message=user_message)["reply"]

    def generate_learning_response(
        self,
        *,
        session_id: str,
        user_message: str,
        grammar_analysis: GrammarAnalysis | None = None,
    ) -> dict[str, str]:
        context = self._sessions.setdefault(session_id, SessionContext())
        grammar_analysis = grammar_analysis or self._english_pipeline.analyze(user_message)
        fluency_score = self._score_fluency(user_message, grammar_analysis)
        vocabulary_suggestions = self._suggest_vocabulary(user_message)
        follow_up_question = "Can you say one more sentence about that?"
        self._remember_user_detail(context, user_message)
        self._append_message(context, role="user", content=user_message)
        reply = self._build_reply(grammar_analysis=grammar_analysis, fluency_score=fluency_score)
        self._append_message(context, role="assistant", content=reply)
        return {
            "correction": grammar_analysis.corrected_sentence,
            "explanation": self._build_explanation(grammar_analysis),
            "reply": reply,
            "suggested_topic": follow_up_question,
            "vocabulary": "; ".join(vocabulary_suggestions),
            "confidence_tip": "Speak slowly first, then repeat once with stronger voice.",
        }

    def get_memory_context(self, *, session_id: str) -> dict:
        context = self._sessions.get(session_id)
        if context is None:
            return {"important_user_details": {}, "conversation_turns": 0}
        return {
            "important_user_details": dict(context.user_details),
            "conversation_turns": len(context.conversation_history),
        }

    def _append_message(self, context: SessionContext, *, role: str, content: str) -> None:
        context.conversation_history.append({"role": role, "content": content})
        if len(context.conversation_history) > 12:
            context.conversation_history = context.conversation_history[-12:]

    def _remember_user_detail(self, context: SessionContext, message: str) -> None:
        lower = message.lower()
        if "my name is " in lower:
            context.user_details["name"] = message[lower.index("my name is ") + len("my name is ") :].strip(" .,!?")
        if "i want to improve " in lower:
            context.user_details["goal"] = message[lower.index("i want to improve ") + len("i want to improve ") :].strip(" .,!?")

    def _build_reply(self, *, grammar_analysis: GrammarAnalysis, fluency_score: int) -> str:
        if grammar_analysis.has_grammar_mistakes:
            return f"Good practice, your fluency score is {fluency_score}/100."
        return f"Nice sentence, your fluency score is {fluency_score}/100."

    @staticmethod
    def _score_fluency(text: str, grammar_analysis: GrammarAnalysis) -> int:
        word_count = len(text.split())
        score = 60 + (10 if word_count >= 8 else 0) + (15 if not grammar_analysis.has_grammar_mistakes else -10)
        return max(1, min(100, score))

    @staticmethod
    def _suggest_vocabulary(text: str) -> list[str]:
        lower = text.lower()
        if "good" in lower:
            return ["good -> excellent"]
        if "want" in lower:
            return ["want -> would like"]
        return ["Add one specific detail", "Use a complete sentence"]

    @staticmethod
    def _build_explanation(grammar_analysis: GrammarAnalysis) -> str:
        if not grammar_analysis.has_grammar_mistakes:
            return "Your sentence is clear; I polished it to sound more natural."
        mistakes = ", ".join(grammar_analysis.detected_mistakes[:2]) or "grammar"
        return f"I adjusted the {mistakes} so it sounds clearer."

