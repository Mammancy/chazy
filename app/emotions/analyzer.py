from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EmotionAnalysis:
    emotion: str
    sentiment: str
    intensity: float
    matched_keywords: list[str]


class EmotionAnalyzer:
    """Lightweight keyword and sentiment detector for early CHAZY memory tagging."""

    EMOTION_KEYWORDS: dict[str, set[str]] = {
        "happy": {
            "happy",
            "glad",
            "good",
            "great",
            "better",
            "peaceful",
            "grateful",
            "thankful",
            "love",
        },
        "sad": {
            "sad",
            "down",
            "hurt",
            "cry",
            "crying",
            "pain",
            "heartbroken",
            "depressed",
            "miserable",
        },
        "angry": {
            "angry",
            "mad",
            "annoyed",
            "furious",
            "frustrated",
            "irritated",
            "pissed",
        },
        "lonely": {
            "lonely",
            "alone",
            "isolated",
            "ignored",
            "abandoned",
            "nobody",
        },
        "stressed": {
            "stress",
            "stressed",
            "overwhelmed",
            "pressure",
            "tired",
            "exhausted",
            "burned",
            "burnout",
            "anxious",
            "worried",
        },
        "confused": {
            "confused",
            "lost",
            "unclear",
            "unsure",
            "stuck",
            "don't understand",
            "do not understand",
        },
        "excited": {
            "excited",
            "amazing",
            "awesome",
            "won",
            "passed",
            "celebrate",
            "can't wait",
            "cannot wait",
        },
    }

    POSITIVE_EMOTIONS = {"happy", "excited"}
    NEGATIVE_EMOTIONS = {"sad", "angry", "lonely", "stressed", "confused"}
    NEGATIONS = {"not", "never", "no", "hardly", "barely"}

    def analyze(self, text: str) -> EmotionAnalysis:
        normalized = self._normalize(text)
        words = normalized.split()
        scores: dict[str, float] = {emotion: 0.0 for emotion in self.EMOTION_KEYWORDS}
        matched: dict[str, list[str]] = {emotion: [] for emotion in self.EMOTION_KEYWORDS}

        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            for keyword in keywords:
                if self._contains_keyword(normalized, words, keyword):
                    weight = 1.4 if " " in keyword else 1.0
                    if self._is_negated(words, keyword):
                        weight *= -0.7
                    scores[emotion] += weight
                    matched[emotion].append(keyword)

        emotion = max(scores, key=scores.get)
        if scores[emotion] <= 0:
            emotion = "neutral"

        sentiment = self._sentiment_for(emotion)
        intensity = self._intensity(text=text, score=scores.get(emotion, 0.0))
        return EmotionAnalysis(
            emotion=emotion,
            sentiment=sentiment,
            intensity=intensity,
            matched_keywords=matched.get(emotion, []),
        )

    def detect(self, text: str) -> str:
        return self.analyze(text).emotion

    def detect_sentiment(self, text: str) -> str:
        return self.analyze(text).sentiment

    def detect_intensity(self, text: str) -> float:
        return self.analyze(text).intensity

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _contains_keyword(self, normalized: str, words: list[str], keyword: str) -> bool:
        if " " in keyword:
            return keyword in normalized
        return keyword in words

    def _is_negated(self, words: list[str], keyword: str) -> bool:
        first_word = keyword.split()[0]
        try:
            index = words.index(first_word)
        except ValueError:
            return False
        start = max(0, index - 3)
        return any(word in self.NEGATIONS for word in words[start:index])

    def _sentiment_for(self, emotion: str) -> str:
        if emotion in self.POSITIVE_EMOTIONS:
            return "positive"
        if emotion in self.NEGATIVE_EMOTIONS:
            return "negative"
        return "neutral"

    def _intensity(self, *, text: str, score: float) -> float:
        punctuation_boost = min(text.count("!") * 0.08, 0.24)
        uppercase_boost = 0.12 if len(text) >= 4 and text.upper() == text else 0.0
        score_boost = min(max(score, 0.0) * 0.12, 0.3)
        return min(0.35 + score_boost + punctuation_boost + uppercase_boost, 1.0)

