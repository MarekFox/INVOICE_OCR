"""
FAKTURA BOT v5.0 - Template Matcher
====================================
Automatyczne dopasowanie najlepszego szablonu do tekstu faktury
"""

import re
import logging
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass

from template_loader import TemplateLoader, InvoiceTemplate

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Wynik dopasowania szablonu"""
    template: InvoiceTemplate
    score: float
    matched_keywords: List[str]
    excluded_keywords: List[str]
    details: Dict[str, any]


class TemplateMatcher:
    """
    Dopasowuje najlepszy szablon do tekstu faktury.
    Używa wielu strategii dopasowania.
    """

    def __init__(self, loader: TemplateLoader):
        self.loader = loader

    def find_best_match(self, text: str, language: str = "Polski") -> Optional[InvoiceTemplate]:
        """
        Znajduje najlepiej pasujący szablon.

        Args:
            text: Tekst OCR faktury
            language: Preferowany język

        Returns:
            Najlepszy szablon lub None
        """
        results = self.match_all(text, language)

        if not results:
            return None

        # Zwróć szablon z najwyższym score
        best = max(results, key=lambda r: r.score)

        logger.info(f"🎯 Najlepsze dopasowanie: {best.template.issuer} (score: {best.score:.2f})")

        return best.template

    def match_all(self, text: str, language: str = "Polski") -> List[MatchResult]:
        """
        Dopasowuje wszystkie szablony i zwraca posortowaną listę.
        """
        results = []
        text_upper = text.upper()

        # Najpierw szablony dla konkretnego języka
        templates = self.loader.get_templates_by_language(language)

        # Dodaj szablony domyślne (generic)
        all_templates = self.loader.get_all_templates()
        for t in all_templates:
            if t not in templates:
                templates.append(t)

        for template in templates:
            result = self._match_template(text, text_upper, template)
            if result and result.score > 0:
                results.append(result)

        # Sortuj wg score (malejąco)
        results.sort(key=lambda r: r.score, reverse=True)

        return results

    def _match_template(self, text: str, text_upper: str, 
                        template: InvoiceTemplate) -> Optional[MatchResult]:
        """
        Dopasowuje pojedynczy szablon do tekstu.
        """
        score = 0.0
        matched_keywords = []
        excluded_keywords = []
        details = {
            'keyword_score': 0,
            'pattern_score': 0,
            'priority_bonus': 0,
            'exclude_penalty': 0
        }

        # 1. Sprawdź wykluczenia
        for keyword in template.exclude_keywords:
            if keyword.upper() in text_upper:
                excluded_keywords.append(keyword)
                # Jeśli jest wykluczenie, zwróć None
                return None

        # 2. Dopasowanie słów kluczowych
        keyword_matches = 0
        for keyword in template.keywords:
            if keyword.upper() in text_upper:
                keyword_matches += 1
                matched_keywords.append(keyword)

        if template.keywords:
            keyword_score = (keyword_matches / len(template.keywords)) * 50
            details['keyword_score'] = keyword_score
            score += keyword_score

        # 3. Dopasowanie wzorców regex z pól
        pattern_matches = 0
        total_patterns = 0

        for field_name, patterns in template._compiled_patterns.items():
            if field_name.startswith('_'):  # Pomiń wewnętrzne
                continue

            total_patterns += len(patterns)
            for pattern in patterns:
                if pattern.search(text):
                    pattern_matches += 1
                    break  # Jeden match na pole wystarczy

        if total_patterns > 0:
            pattern_score = (pattern_matches / total_patterns) * 30
            details['pattern_score'] = pattern_score
            score += pattern_score

        # 4. Bonus za priorytet szablonu
        priority_bonus = template.priority / 10  # max 10 punktów
        details['priority_bonus'] = priority_bonus
        score += priority_bonus

        # 5. Bonus za dopasowanie języka
        if self._detect_language(text) == template.language:
            score += 5
            details['language_bonus'] = 5

        # 6. Specjalne dopasowania (NIP dostawcy, nazwa firmy)
        issuer_score = self._match_issuer_specifics(text, template)
        details['issuer_score'] = issuer_score
        score += issuer_score

        return MatchResult(
            template=template,
            score=score,
            matched_keywords=matched_keywords,
            excluded_keywords=excluded_keywords,
            details=details
        )

    def _detect_language(self, text: str) -> str:
        """Wykrywa język tekstu na podstawie słów kluczowych"""
        text_upper = text.upper()

        lang_scores = {
            'Polski': 0,
            'Niemiecki': 0,
            'Rumuński': 0,
            'Angielski': 0
        }

        polish_keywords = ['FAKTURA', 'NIP', 'SPRZEDAWCA', 'NABYWCA', 'PŁATNOŚCI', 'BRUTTO', 'NETTO']
        german_keywords = ['RECHNUNG', 'UST', 'KÄUFER', 'VERKÄUFER', 'ZAHLUNG', 'BRUTTO', 'NETTO']
        romanian_keywords = ['FACTURĂ', 'CUI', 'FURNIZOR', 'CUMPĂRĂTOR', 'PLATĂ', 'TVA']
        english_keywords = ['INVOICE', 'VAT', 'SELLER', 'BUYER', 'PAYMENT', 'TOTAL', 'TAX']

        for kw in polish_keywords:
            if kw in text_upper:
                lang_scores['Polski'] += 1

        for kw in german_keywords:
            if kw in text_upper:
                lang_scores['Niemiecki'] += 1

        for kw in romanian_keywords:
            if kw in text_upper:
                lang_scores['Rumuński'] += 1

        for kw in english_keywords:
            if kw in text_upper:
                lang_scores['Angielski'] += 1

        return max(lang_scores, key=lang_scores.get)

    def _match_issuer_specifics(self, text: str, template: InvoiceTemplate) -> float:
        """
        Dopasowanie specyficzne dla wystawcy.
        Szuka NIP lub nazwy firmy w tekście.
        """
        score = 0.0

        # Sprawdź czy szablon ma zdefiniowane specyficzne dane wystawcy
        # (np. w polu description lub w metadanych)
        issuer_name = template.issuer.upper()

        # Jeśli nazwa wystawcy z szablonu występuje w tekście
        if issuer_name in text.upper():
            score += 15  # Silne dopasowanie

        # Sprawdź częściowe dopasowanie nazwy
        issuer_words = issuer_name.split()
        matches = sum(1 for word in issuer_words if word in text.upper() and len(word) > 3)
        if matches > 0:
            score += matches * 3

        return min(score, 20)  # Max 20 punktów za specyfiki wystawcy

    def get_match_report(self, text: str, language: str = "Polski") -> str:
        """
        Generuje raport z dopasowania wszystkich szablonów.
        Przydatne do debugowania.
        """
        results = self.match_all(text, language)

        lines = ["=" * 60]
        lines.append("RAPORT DOPASOWANIA SZABLONÓW")
        lines.append("=" * 60)
        lines.append(f"Język: {language}")
        lines.append(f"Znaleziono {len(results)} pasujących szablonów")
        lines.append("")

        for i, result in enumerate(results[:10], 1):  # Top 10
            lines.append(f"{i}. {result.template.issuer}")
            lines.append(f"   Score: {result.score:.2f}")
            lines.append(f"   Priorytet: {result.template.priority}")
            lines.append(f"   Dopasowane słowa: {', '.join(result.matched_keywords[:5])}")
            lines.append(f"   Szczegóły: {result.details}")
            lines.append("")

        return "\n".join(lines)
