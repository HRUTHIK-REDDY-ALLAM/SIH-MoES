"""
Varsha — Translation Adapter

Wraps Bhashini or IndicTrans2 for translating advisory text.
Uses a reviewed glossary to ensure crop/weather terms are correctly translated.

For the prototype, uses pre-written translations from advisory_rules.yaml.
Falls back to glossary-based template substitution when API is unavailable.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class TranslationAdapter:
    """
    Translates advisory text from English to regional Indian languages.

    Priority:
    1. Pre-written template translations (from advisory_rules.yaml)
    2. Bhashini API (if BHASHINI_API_KEY is set)
    3. Glossary-based keyword substitution (fallback)
    """

    def __init__(self):
        self.glossaries = {}
        self._load_glossaries()
        self.bhashini_available = bool(os.getenv("BHASHINI_API_KEY"))

    def _load_glossaries(self):
        """Load language glossaries."""
        glossary_dir = Path(__file__).parent
        for lang in ["te", "hi"]:
            path = glossary_dir / f"glossary_{lang}.yaml"
            if path.exists():
                with open(path) as f:
                    self.glossaries[lang] = yaml.safe_load(f)
                logger.info(f"Loaded {lang} glossary ({sum(len(v) for v in self.glossaries[lang].values())} terms)")

    def translate(self, text: str, target_lang: str, source_lang: str = "en") -> str:
        """
        Translate text to target language.

        Args:
            text: English text to translate
            target_lang: Target language code ('te', 'hi')
            source_lang: Source language code (default 'en')

        Returns:
            Translated text
        """
        if target_lang == source_lang:
            return text

        # Try Bhashini API first
        if self.bhashini_available:
            translated = self._translate_bhashini(text, target_lang, source_lang)
            if translated:
                return self._apply_glossary(translated, target_lang)

        # Fallback to glossary substitution
        logger.debug(f"Using glossary fallback for {source_lang} → {target_lang}")
        return self._glossary_substitute(text, target_lang)

    def _translate_bhashini(self, text: str, target_lang: str, source_lang: str) -> Optional[str]:
        """Translate using Bhashini API."""
        try:
            import httpx

            api_key = os.getenv("BHASHINI_API_KEY")
            user_id = os.getenv("BHASHINI_USER_ID")

            # Language codes for Bhashini
            lang_map = {"en": "en", "te": "te", "hi": "hi"}

            # This is a simplified Bhashini API call — actual implementation
            # requires pipeline discovery via ULCA
            headers = {
                "Authorization": api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "pipelineTasks": [{
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": lang_map[source_lang],
                            "targetLanguage": lang_map[target_lang],
                        }
                    }
                }],
                "inputData": {
                    "input": [{"source": text}]
                }
            }

            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    return result.get("pipelineResponse", [{}])[0].get("output", [{}])[0].get("target", text)

        except Exception as e:
            logger.warning(f"Bhashini translation failed: {e}")

        return None

    def _apply_glossary(self, text: str, lang: str) -> str:
        """Apply glossary corrections to machine-translated text."""
        glossary = self.glossaries.get(lang, {})
        # This ensures domain-specific terms are correctly translated
        # even if the MT engine gets them wrong
        # For now, this is a placeholder for post-editing
        return text

    def _glossary_substitute(self, text: str, target_lang: str) -> str:
        """
        Simple keyword substitution using the glossary.
        Not a real translation — used as fallback when no API is available.
        """
        glossary = self.glossaries.get(target_lang, {})
        result = text

        # Flatten glossary
        all_terms = {}
        for category in glossary.values():
            if isinstance(category, dict):
                all_terms.update(category)

        # Replace English terms with target language
        for en_term, translated_term in all_terms.items():
            # Simple case-insensitive replacement
            import re
            pattern = re.compile(re.escape(en_term.replace("_", " ")), re.IGNORECASE)
            result = pattern.sub(translated_term, result)

        return result


# Module-level singleton
_adapter = None


def get_adapter() -> TranslationAdapter:
    """Get or create the translation adapter singleton."""
    global _adapter
    if _adapter is None:
        _adapter = TranslationAdapter()
    return _adapter


def translate(text: str, target_lang: str) -> str:
    """Convenience function for translation."""
    return get_adapter().translate(text, target_lang)
