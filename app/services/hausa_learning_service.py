from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HausaLearningResult:
    is_hausa: bool
    original_text: str
    english_text: str
    explanation: str
    detected_terms: list[str]


class HausaLearningService:
    """Lightweight Hausa-English bridge for speaking practice."""

    _PHRASE_TRANSLATIONS = {
        "ina kwana": "Good morning",
        "ina yini": "Good afternoon",
        "yaya kake": "How are you?",
        "yaya kike": "How are you?",
        "lafiya lau": "I am very well",
        "lafiya kalau": "I am very well",
        "na gode": "Thank you",
        "don Allah": "please",
        "sunana": "my name is",
        "ina so": "I want",
        "ina son": "I like",
        "zan iya": "I can",
        "ba zan iya ba": "I cannot",
        "ban gane ba": "I do not understand",
        "ina bukata": "I need",
        "ina bukatar": "I need",
        "ina koyon turanci": "I am learning English",
        "ina son koyon turanci": "I want to learn English",
        "taimaka min": "help me",
        "ka taimaka min": "please help me",
        "ki taimaka min": "please help me",
        "me kake yi": "what are you doing?",
        "me kike yi": "what are you doing?",
        "ina zuwa makaranta": "I am going to school",
        "ina aiki": "I am working",
        "ina gida": "I am at home",
        "na tafi": "I went",
        "zan tafi": "I will go",
        "abinci": "food",
        "ruwa": "water",
        "makaranta": "school",
        "aiki": "work",
        "gida": "home",
    }

    _HAUSA_MARKERS = {
        "ina", "kana", "kake", "kike", "yaya", "lafiya", "lau", "kalau", "na", "gode",
        "don", "allah", "sunana", "so", "son", "zan", "iya", "ba", "ban", "gane",
        "bukata", "bukatar", "koyon", "turanci", "taimaka", "min", "makaranta",
        "aiki", "gida", "ruwa", "abinci", "kwana", "yini",
    }

    def process(self, text: str) -> HausaLearningResult:
        normalized = " ".join(text.strip().split())
        detected_terms = self._detect_terms(normalized)
        is_hausa = len(detected_terms) >= 2 or self._contains_known_phrase(normalized)
        if not is_hausa:
            return HausaLearningResult(
                is_hausa=False,
                original_text=text,
                english_text=text,
                explanation="",
                detected_terms=[],
            )

        english_text = self._translate(normalized)
        explanation = self._explain(normalized, english_text, detected_terms)
        return HausaLearningResult(
            is_hausa=True,
            original_text=text,
            english_text=english_text,
            explanation=explanation,
            detected_terms=detected_terms,
        )

    def _contains_known_phrase(self, text: str) -> bool:
        lower = text.lower()
        return any(phrase in lower for phrase in self._PHRASE_TRANSLATIONS)

    def _detect_terms(self, text: str) -> list[str]:
        words = re.findall(r"[A-Za-z]+", text.lower())
        return sorted({word for word in words if word in self._HAUSA_MARKERS})

    def _translate(self, text: str) -> str:
        translated = f" {text.lower()} "
        for hausa, english in sorted(self._PHRASE_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
            translated = re.sub(
                rf"(?<![A-Za-z]){re.escape(hausa)}(?![A-Za-z])",
                english,
                translated,
                flags=re.IGNORECASE,
            )
        translated = " ".join(translated.split())
        translated = self._polish_translation(translated)
        if translated and translated[-1] not in ".!?":
            translated += "."
        return translated

    def _polish_translation(self, text: str) -> str:
        replacements = {
            "I want learn English": "I want to learn English",
            "I like learn English": "I like learning English",
            "I want English": "I want to speak English",
            "please help me me": "please help me",
            "Thank you please": "Thank you, please",
        }
        polished = text
        for old, new in replacements.items():
            polished = polished.replace(old, new)
        if polished:
            polished = polished[0].upper() + polished[1:]
        return polished

    def _explain(self, original: str, english_text: str, detected_terms: list[str]) -> str:
        terms = ", ".join(detected_terms[:6])
        return (
            f"I detected Hausa words ({terms}) and translated your message into natural English: "
            f"\"{english_text}\" Keep practicing by repeating the English sentence aloud."
        )
