from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GrammarAnalysis:
    original_message: str
    has_grammar_mistakes: bool
    corrected_sentence: str
    detected_mistakes: list[str] = field(default_factory=list)


class EnglishLearningPipeline:
    """Lightweight pre-OpenAI grammar pipeline for CHAZY chat messages."""

    _WORD_REPLACEMENTS = {
        "im": "I am",
        "i'm": "I am",
        "dont": "do not",
        "doesnt": "does not",
        "cant": "cannot",
        "wont": "will not",
        "isnt": "is not",
        "arent": "are not",
        "wasnt": "was not",
        "werent": "were not",
        "wanna": "want to",
        "gonna": "going to",
        "gotta": "have to",
        "kinda": "kind of",
        "alot": "a lot",
    }

    _PHRASE_REPLACEMENTS = {
        " i am fine": " I am fine",
        " i want": " I want",
        " i like": " I like",
        " i feel": " I feel",
        " i have": " I have",
        " i need": " I need",
        " i don't": " I don't",
        " i do not": " I do not",
    }

    def analyze(self, message: str) -> GrammarAnalysis:
        original = message.strip()
        normalized = " ".join(original.split())
        mistakes: list[str] = []

        if not normalized:
            return GrammarAnalysis(
                original_message=message,
                has_grammar_mistakes=True,
                corrected_sentence="Please write a complete sentence.",
                detected_mistakes=["empty_message"],
            )

        corrected = normalized
        if corrected and corrected[0].islower():
            corrected = corrected[0].upper() + corrected[1:]
            mistakes.append("capitalization")

        corrected = self._replace_words(corrected, mistakes)
        corrected = self._replace_phrases(corrected, mistakes)
        corrected = self._fix_simple_agreement(corrected, mistakes)
        corrected = self._fix_spacing(corrected)

        if corrected and corrected[-1] not in ".!?":
            corrected += "."
            mistakes.append("punctuation")

        return GrammarAnalysis(
            original_message=message,
            has_grammar_mistakes=bool(mistakes) or corrected != normalized,
            corrected_sentence=corrected,
            detected_mistakes=sorted(set(mistakes)),
        )

    def _replace_words(self, text: str, mistakes: list[str]) -> str:
        def replace(match: re.Match[str]) -> str:
            word = match.group(0)
            replacement = self._WORD_REPLACEMENTS[word.lower()]
            mistakes.append("word_choice")
            return replacement

        pattern = r"\b(" + "|".join(re.escape(word) for word in self._WORD_REPLACEMENTS) + r")\b"
        return re.sub(pattern, replace, text, flags=re.IGNORECASE)

    def _replace_phrases(self, text: str, mistakes: list[str]) -> str:
        padded = f" {text}"
        for old, new in self._PHRASE_REPLACEMENTS.items():
            if old in padded:
                padded = padded.replace(old, new)
                mistakes.append("capitalization")
        return padded.strip()

    @staticmethod
    def _fix_simple_agreement(text: str, mistakes: list[str]) -> str:
        replacements = {
            r"\bI is\b": "I am",
            r"\bI are\b": "I am",
            r"\bhe are\b": "he is",
            r"\bshe are\b": "she is",
            r"\bit are\b": "it is",
            r"\bwe is\b": "we are",
            r"\bthey is\b": "they are",
            r"\byou is\b": "you are",
        }
        corrected = text
        for pattern, replacement in replacements.items():
            corrected_new = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
            if corrected_new != corrected:
                mistakes.append("subject_verb_agreement")
                corrected = corrected_new
        return corrected

    @staticmethod
    def _fix_spacing(text: str) -> str:
        text = re.sub(r"\s+([,.!?])", r"\1", text)
        text = re.sub(r"([,.!?])([^\s])", r"\1 \2", text)
        return " ".join(text.split())

