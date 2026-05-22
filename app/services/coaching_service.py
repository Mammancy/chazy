from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor
import re

from app.ai.english_learning_pipeline import GrammarAnalysis


@dataclass(frozen=True)
class CoachingMetrics:
    fluency_score: int
    vocabulary_suggestions: list[str]
    daily_challenge: str
    speaking_prompt: str
    mistake_summary: str


class MistakeTracker:
    def summarize(self, grammar_analysis: GrammarAnalysis) -> str:
        if not grammar_analysis.has_grammar_mistakes:
            return "No major grammar mistake detected. Focus on speaking more naturally."
        mistakes = ", ".join(grammar_analysis.detected_mistakes[:3]) or "grammar accuracy"
        return f"Practice focus: {mistakes}."


class VocabularyBuilder:
    COMMON_UPGRADES = {
        "good": "excellent",
        "bad": "difficult",
        "happy": "pleased",
        "sad": "upset",
        "big": "significant",
        "small": "minor",
        "like": "enjoy",
        "want": "would like",
        "get": "receive",
        "make": "create",
    }

    def suggest(self, text: str) -> list[str]:
        lower = text.lower()
        suggestions: list[str] = []
        for basic, stronger in self.COMMON_UPGRADES.items():
            if re.search(rf"\b{re.escape(basic)}\b", lower):
                suggestions.append(f"{basic} -> {stronger}")
            if len(suggestions) >= 3:
                break
        if suggestions:
            return suggestions
        return ["Try adding one detail", "Use a complete sentence", "Say it aloud once"]


class DailyChallengeService:
    CHALLENGES = [
        "Speak for 30 seconds about your day using past tense.",
        "Describe one goal using: I would like to...",
        "Tell a short story with: first, then, after that, finally.",
        "Practice asking one clear follow-up question.",
        "Use three new adjectives to describe a person or place.",
        "Explain your opinion using: I think... because...",
        "Record yourself saying the corrected sentence three times.",
    ]

    def today(self) -> str:
        index = date.today().toordinal() % len(self.CHALLENGES)
        return self.CHALLENGES[index]


class FluencyScorer:
    def score(self, original_message: str, grammar_analysis: GrammarAnalysis) -> int:
        words = re.findall(r"\b\w+\b", original_message)
        word_count = len(words)
        base = 55
        if word_count >= 8:
            base += 10
        if word_count >= 16:
            base += 10
        if not grammar_analysis.has_grammar_mistakes:
            base += 15
        else:
            base -= min(len(grammar_analysis.detected_mistakes) * 6, 18)
        if any(mark in original_message for mark in ".?!"):
            base += 5
        return max(1, min(100, floor(base)))


class VoicePracticeService:
    def prompt(self, corrected_sentence: str) -> str:
        sentence = corrected_sentence.strip() or "Say your sentence again slowly and clearly."
        return f"Voice practice: say this aloud 3 times: \"{sentence}\""


class CoachingService:
    def __init__(self) -> None:
        self.mistake_tracker = MistakeTracker()
        self.vocabulary_builder = VocabularyBuilder()
        self.daily_challenge_service = DailyChallengeService()
        self.fluency_scorer = FluencyScorer()
        self.voice_practice_service = VoicePracticeService()

    def build_metrics(self, *, text: str, grammar_analysis: GrammarAnalysis) -> CoachingMetrics:
        return CoachingMetrics(
            fluency_score=self.fluency_scorer.score(text, grammar_analysis),
            vocabulary_suggestions=self.vocabulary_builder.suggest(text),
            daily_challenge=self.daily_challenge_service.today(),
            speaking_prompt=self.voice_practice_service.prompt(grammar_analysis.corrected_sentence),
            mistake_summary=self.mistake_tracker.summarize(grammar_analysis),
        )
