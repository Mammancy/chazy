from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from app.ai.english_learning_pipeline import EnglishLearningPipeline, GrammarAnalysis
from app.emotions.analyzer import EmotionAnalyzer


@dataclass
class SessionContext:
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    emotional_patterns: dict[str, int] = field(default_factory=dict)
    user_details: dict[str, str] = field(default_factory=dict)
    memory_summaries: list[str] = field(default_factory=list)


class TemporaryConversationalResponseEngine:
    """Local fallback engine for English learning conversation when OpenAI is unavailable."""

    _TONE_OPENERS = {
        "happy": "That sounds positive.",
        "excited": "Your excitement comes through clearly.",
        "sad": "I hear that this feels difficult.",
        "angry": "I can hear the frustration in that.",
        "lonely": "That sounds lonely, and I am here with you.",
        "stressed": "That sounds stressful, so let us keep this simple.",
        "confused": "That is understandable; we can make it clearer step by step.",
        "neutral": "I understand.",
    }

    def __init__(self) -> None:
        self._emotion_analyzer = EmotionAnalyzer()
        self._english_pipeline = EnglishLearningPipeline()
        self._contexts: dict[str, SessionContext] = {}
        self._lock = Lock()

    def generate_response(self, *, session_id: str, user_message: str) -> str:
        return self.generate_learning_response(session_id=session_id, user_message=user_message)["reply"]

    def generate_learning_response(
        self,
        *,
        session_id: str,
        user_message: str,
        grammar_analysis: GrammarAnalysis | None = None,
    ) -> dict[str, str]:
        with self._lock:
            context = self._contexts.setdefault(session_id, SessionContext())
            analysis = self._emotion_analyzer.analyze(user_message)
            tone = analysis.emotion
            grammar_analysis = grammar_analysis or self._english_pipeline.analyze(user_message)
            context.emotional_patterns[tone] = context.emotional_patterns.get(tone, 0) + 1

            self._remember_user_detail(context, user_message)
            self._append_message(context, role="user", content=user_message)
            self._refresh_summary(context)

            reply = self._build_reply(context=context, tone=tone, message=user_message)
            follow_up = self._suggested_topic(tone=tone)
            self._append_message(context, role="assistant", content=reply)
            return {
                "correction": grammar_analysis.corrected_sentence,
                "explanation": self._simple_explanation(grammar_analysis),
                "reply": reply,
                "suggested_topic": follow_up,
            }

    def get_memory_context(self, *, session_id: str) -> dict:
        with self._lock:
            context = self._contexts.get(session_id)
            if context is None:
                return {
                    "conversation_history": [],
                    "emotional_patterns": {},
                    "important_user_details": {},
                    "memory_summaries": [],
                }

            return {
                "conversation_history": list(context.conversation_history),
                "emotional_patterns": dict(context.emotional_patterns),
                "important_user_details": dict(context.user_details),
                "memory_summaries": list(context.memory_summaries),
            }

    def _append_message(self, context: SessionContext, *, role: str, content: str) -> None:
        context.conversation_history.append({"role": role, "content": content})
        if len(context.conversation_history) > 20:
            context.conversation_history = context.conversation_history[-20:]

    def _remember_user_detail(self, context: SessionContext, message: str) -> None:
        lower = message.lower()
        if "my name is " in lower:
            context.user_details["name"] = message[lower.index("my name is ") + len("my name is ") :].strip(" .,!?")
        if "i like " in lower:
            context.user_details["likes"] = message[lower.index("i like ") + len("i like ") :].strip(" .,!?")
        if "i work as " in lower:
            context.user_details["work"] = message[lower.index("i work as ") + len("i work as ") :].strip(" .,!?")
        if "i live in " in lower:
            context.user_details["location"] = message[lower.index("i live in ") + len("i live in ") :].strip(" .,!?")

    def _refresh_summary(self, context: SessionContext) -> None:
        user_messages = [m["content"] for m in context.conversation_history if m["role"] == "user"]
        if not user_messages:
            return
        last_point = user_messages[-1]
        top_tone = max(context.emotional_patterns, key=context.emotional_patterns.get, default="neutral")
        details = ", ".join(f"{key}={value}" for key, value in context.user_details.items()) or "no key details yet"
        summary = f"User is practicing English; emotion={top_tone}; latest focus: {last_point}; details: {details}."
        if not context.memory_summaries or context.memory_summaries[-1] != summary:
            context.memory_summaries.append(summary)
        if len(context.memory_summaries) > 5:
            context.memory_summaries = context.memory_summaries[-5:]

    @staticmethod
    def _simple_explanation(grammar_analysis: GrammarAnalysis) -> str:
        if not grammar_analysis.has_grammar_mistakes:
            return "Your sentence is understandable. I polished the punctuation and natural flow."
        mistakes = ", ".join(grammar_analysis.detected_mistakes) or "grammar"
        return f"I noticed {mistakes}. I corrected it to make the sentence sound more natural."

    def _build_reply(self, *, context: SessionContext, tone: str, message: str) -> str:
        opener = self._TONE_OPENERS.get(tone, self._TONE_OPENERS["neutral"])
        recall = self._memory_recall_line(context)
        return " ".join(part for part in [opener, recall, f"Tell me a little more about this: {message}"] if part)

    def _memory_recall_line(self, context: SessionContext) -> str:
        name = context.user_details.get("name")
        likes = context.user_details.get("likes")
        if name and likes:
            return f"{name}, I remember you like {likes}."
        if name:
            return f"{name}, let us practice this in a natural way."
        return "Let us practice this in a natural way."

    @staticmethod
    def _suggested_topic(*, tone: str) -> str:
        if tone in {"sad", "lonely", "stressed", "angry", "confused"}:
            return "Can you write one sentence about what happened and one sentence about how you feel?"
        if tone in {"happy", "excited"}:
            return "Can you describe what made you feel good in three clear English sentences?"
        return "Can you tell me about your day using past tense?"

