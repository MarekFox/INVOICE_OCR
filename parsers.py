"""
FAKTURA BOT v5.0 - Invoice Parsers
====
Zaawansowane parsery do ekstrakcji danych z faktur
UPDATED: Ulepszone wykrywanie numeru faktury, waluty, oryginał/kopia
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

from utils import TextUtils, MoneyUtils, DateUtils, ValidationUtils, BankAccountUtils
from language_config import get_language_config
from validators import InvoiceValidator

logger = logging.getLogger(__name__)


# ==============================================================================
# DATACLASS: ParsedInvoice
# ==============================================================================

@dataclass
class ParsedInvoice:
    """Struktura sparsowanej faktury"""
    # Pola WYMAGANE (bez wartości domyślnych) muszą być PIERWSZE
    invoice_id: str
    invoice_type: str  # FAKTURA VAT, PROFORMA, KOREKTA
    issue_date: datetime
    sale_date: datetime
    due_date: datetime

    # Dostawca - pola wymagane
    supplier_name: str
    supplier_tax_id: str
    supplier_address: str
    supplier_accounts: List[str]

    # Nabywca - pola wymagane
    buyer_name: str
    buyer_tax_id: str
    buyer_address: str

    # Finanse - pola wymagane
    currency: str
    language: str
    raw_text: str

    # Pola OPCJONALNE (z wartościami domyślnymi) muszą być NA KOŃCU
    supplier_email: Optional[str] = None
    supplier_phone: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_phone: Optional[str] = None

    # Pozycje
    line_items: List[Dict] = field(default_factory=list)

    # Podsumowanie
    total_net: Decimal = Decimal('0')
    total_vat: Decimal = Decimal('0')
    total_gross: Decimal = Decimal('0')
    vat_breakdown: List[Dict] = field(default_factory=list)

    # Płatność
    payment_method: str = 'przelew'
    payment_status: str = 'nieopłacona'
    paid_amount: Decimal = Decimal('0')

    # Metadane
    confidence: float = 0.0
    parsing_errors: List[str] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)
    page_range: Tuple[int, int] = (1, 1)

    # Flagi
    is_correction: bool = False
    is_proforma: bool = False
    is_duplicate: bool = False
    is_verified: bool = False
    belongs_to_user: bool = False

    # NOWE: Typ dokumentu (oryginał/kopia)
    document_type: str = 'nieznany'  # 'oryginał', 'kopia', 'duplikat', 'nieznany'

    # NOWE: Seria faktury (dla rumuńskich faktur)
    invoice_series: Optional[str] = None


# ==============================================================================
# KLASA: CurrencyDetector - Inteligentne wykrywanie waluty
# ==============================================================================

class CurrencyDetector:
    """Inteligentne wykrywanie waluty z ignorowaniem numerów kont i EU VAT"""

    # Definicje walut i ich fraz
    CURRENCY_PATTERNS = {
        'PLN': {
            'codes': ['PLN'],
            'symbols': ['zł', 'złotych', 'złoty', 'złote', 'zlotych', 'zloty'],
            'weight': 1.0
        },
        'RON': {
            'codes': ['RON'],
            'symbols': ['lei', 'leu', 'LEI', 'LEU'],
            'weight': 1.0
        },
        'EUR': {
            'codes': ['EUR'],
            'symbols': ['€', 'euro', 'EURO', 'eur'],
            'weight': 1.0
        },
        'USD': {
            'codes': ['USD'],
            'symbols': ['$', 'dolar', 'dolarów', 'dollars'],
            'weight': 1.0
        },
        'GBP': {
            'codes': ['GBP'],
            'symbols': ['£', 'funt', 'funtów', 'pounds'],
            'weight': 1.0
        },
        'CZK': {
            'codes': ['CZK'],
            'symbols': ['Kč', 'korun', 'korona'],
            'weight': 1.0
        },
        'CHF': {
            'codes': ['CHF'],
            'symbols': ['frank', 'franków', 'franken'],
            'weight': 1.0
        }
    }

    # Wzorce do ignorowania (numery kont, EU VAT, itp.)
    IGNORE_PATTERNS = [
        # IBAN - różne formaty
        r'[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?[\d]{4}[\s]?[\d]{4}[\s]?[\d]{4}[\s]?[\d]{4}[\s]?[\d]{0,4}',
        r'[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{0,4}',
        # Numer konta bez IBAN
        r'\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}',
        # EU VAT ID (np. PL1234567890, RO12345678)
        r'(?:PL|RO|DE|FR|IT|ES|NL|BE|AT|CZ|SK|HU|BG|HR|SI|LT|LV|EE|FI|SE|DK|IE|PT|GR|CY|MT|LU)\s?\d{8,12}',
        # NIP z prefiksem kraju
        r'(?:NIP|VAT|CUI|CIF)[:\s]*(?:PL|RO|DE)?[\s-]?\d{8,12}',
        # Swift/BIC
        r'[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?',
    ]

    @classmethod
    def detect_currency(cls, text: str, default_language: str = 'Polski') -> Tuple[str, float]:
        """
        Wykrywa walutę w tekście z inteligentnym filtrowaniem.

        Returns:
            Tuple[str, float]: (kod_waluty, pewność 0.0-1.0)
        """
        # Krok 1: Usuń fragmenty do ignorowania
        clean_text = cls._remove_ignored_sections(text)

        # Krok 2: Zlicz wystąpienia każdej waluty
        currency_scores = {}

        for currency, config in cls.CURRENCY_PATTERNS.items():
            score = 0

            # Szukaj kodów walut (np. PLN, EUR)
            for code in config['codes']:
                # Szukaj kodu jako osobnego słowa (nie części innego słowa)
                pattern = r'\b' + re.escape(code) + r'\b'
                matches = re.findall(pattern, clean_text, re.IGNORECASE)
                score += len(matches) * 2  # Kody mają wyższą wagę

            # Szukaj symboli i nazw
            for symbol in config['symbols']:
                # Dla krótkich symboli (zł, €) szukaj dokładnie
                if len(symbol) <= 2:
                    pattern = re.escape(symbol)
                else:
                    # Dla dłuższych słów szukaj jako osobne słowo
                    pattern = r'\b' + re.escape(symbol) + r'\b'

                matches = re.findall(pattern, clean_text, re.IGNORECASE)
                score += len(matches)

            if score > 0:
                currency_scores[currency] = score * config['weight']

        logger.info(f"💰 Wykryte waluty: {currency_scores}")

        # Krok 3: Wybierz walutę z najwyższym wynikiem
        if currency_scores:
            best_currency = max(currency_scores, key=currency_scores.get)
            total_score = sum(currency_scores.values())
            confidence = currency_scores[best_currency] / total_score if total_score > 0 else 0.5

            logger.info(f"✅ Wybrana waluta: {best_currency} (pewność: {confidence:.2f})")
            return best_currency, confidence

        # Krok 4: Fallback na podstawie języka
        language_defaults = {
            'Polski': 'PLN',
            'Rumuński': 'RON',
            'Niemiecki': 'EUR',
            'Angielski': 'EUR'
        }

        default_currency = language_defaults.get(default_language, 'PLN')
        logger.warning(f"⚠️ Nie wykryto waluty, używam domyślnej: {default_currency}")
        return default_currency, 0.3

    @classmethod
    def _remove_ignored_sections(cls, text: str) -> str:
        """Usuwa sekcje do ignorowania (numery kont, VAT ID, itp.)"""
        clean_text = text

        for pattern in cls.IGNORE_PATTERNS:
            try:
                clean_text = re.sub(pattern, ' [IGNORED] ', clean_text, flags=re.IGNORECASE)
            except re.error:
                continue

        return clean_text


# ==============================================================================
# KLASA: InvoiceNumberExtractor - Zaawansowane wykrywanie numeru faktury
# ==============================================================================

class InvoiceNumberExtractor:
    """Zaawansowane wykrywanie numeru faktury z obsługą wielu formatów"""

    # Frazy poprzedzające numer faktury
    INVOICE_PREFIXES = [
        # Polski
        r'Faktura\s+VAT[_\s-]*(?:nr|numer)?[:\s]*',
        r'Faktura[_\s-]*(?:nr|numer)?[:\s]*',
        r'FV[_\s-]*(?:nr)?[:\s]*',
        r'F[_\s-]*(?:nr)?[:\s]*',
        r'Nr\s+faktury[:\s]*',
        r'Numer\s+faktury[:\s]*',
        r'Dokument[:\s]*',
        # Angielski
        r'Invoice[_\s-]*(?:no|number|#)?[:\s]*',
        r'Inv[_\s-]*(?:no|#)?[:\s]*',
        # Niemiecki
        r'Rechnung[_\s-]*(?:Nr|Nummer)?[:\s]*',
        r'Rechnungsnummer[:\s]*',
        # Rumuński
        r'Factura[_\s-]*(?:nr|numar)?[:\s]*',
        r'Factura\s+fiscala\s+seria\s+',
        r'Serie\s+si\s+numar[:\s]*',
    ]

    # Wzorce numerów faktur
    NUMBER_PATTERNS = [
        # FV/123/2025, FV/123/11/2025
        r'([A-Z]{1,4}[/\\-]\d{1,6}(?:[/\\-]\d{1,4}){0,2})',
        # 123/2025, 123/11/2025
        r'(\d{1,6}[/\\-]\d{2,4}(?:[/\\-]\d{1,4})?)',
        # FV-123-2025
        r'([A-Z]{1,4}[-_]\d{1,6}[-_]\d{2,4})',
        # 2025/FV/123
        r'(\d{4}[/\\-][A-Z]{1,4}[/\\-]\d{1,6})',
        # Ciągły numer z literami: 013111112025IG
        r'(\d{6,15}[A-Z]{1,4})',
        # Ciągły numer: 2025001234
        r'(\d{8,15})',
        # Seria + numer (rumuński): Dov H 00005164, ABC 123456
        r'([A-Z]{1,5}\s+[A-Z]?\s*\d{5,10})',
        # Z prefiksem literowym: ABC123456
        r'([A-Z]{2,5}\d{5,10})',
    ]

    @classmethod
    def extract(cls, text: str, language: str = 'Polski') -> Tuple[str, Optional[str]]:
        """
        Ekstraktuje numer faktury z tekstu.

        Returns:
            Tuple[str, Optional[str]]: (numer_faktury, seria_faktury lub None)
        """
        # Normalizuj tekst - zamień backslash na slash
        normalized_text = text.replace('\\', '/')

        # Krok 1: Szukaj numeru po frazach kluczowych
        for prefix_pattern in cls.INVOICE_PREFIXES:
            full_pattern = prefix_pattern + r'([^\n]{3,50})'

            match = re.search(full_pattern, normalized_text, re.IGNORECASE | re.MULTILINE)
            if match:
                candidate = match.group(1).strip()

                # Wyczyść kandydata
                invoice_number = cls._clean_invoice_number(candidate)

                if invoice_number and invoice_number.lower() != 'nr':
                    logger.info(f"✅ Numer faktury (po frazie): {invoice_number}")

                    # Sprawdź czy to rumuńska seria
                    series = cls._extract_romanian_series(candidate)
                    return invoice_number, series

        # Krok 2: Szukaj w następnej linii po frazie
        lines = normalized_text.split('\n')
        for i, line in enumerate(lines):
            line_upper = line.upper()

            if any(kw in line_upper for kw in ['FAKTURA', 'INVOICE', 'RECHNUNG', 'FACTURA']):
                # Sprawdź czy numer jest w tej samej linii
                for pattern in cls.NUMBER_PATTERNS:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        invoice_number = cls._clean_invoice_number(match.group(1))
                        if invoice_number and invoice_number.lower() != 'nr':
                            logger.info(f"✅ Numer faktury (ta sama linia): {invoice_number}")
                            return invoice_number, None

                # Sprawdź następną linię
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    for pattern in cls.NUMBER_PATTERNS:
                        match = re.search(pattern, next_line, re.IGNORECASE)
                        if match:
                            invoice_number = cls._clean_invoice_number(match.group(1))
                            if invoice_number and invoice_number.lower() != 'nr':
                                logger.info(f"✅ Numer faktury (następna linia): {invoice_number}")
                                return invoice_number, None

        # Krok 3: Szukaj wzorców numerów w całym tekście
        for pattern in cls.NUMBER_PATTERNS:
            matches = re.findall(pattern, normalized_text, re.IGNORECASE)
            for match in matches:
                invoice_number = cls._clean_invoice_number(match)
                if invoice_number and len(invoice_number) >= 5:
                    # Sprawdź czy to nie jest NIP, IBAN, data
                    if not cls._is_false_positive(invoice_number, normalized_text):
                        logger.info(f"✅ Numer faktury (wzorzec): {invoice_number}")
                        return invoice_number, None

        logger.warning("⚠️ Nie znaleziono numeru faktury")
        return "UNKNOWN", None

    @classmethod
    def _clean_invoice_number(cls, raw: str) -> str:
        """Czyści surowy numer faktury"""
        if not raw:
            return ""

        # Usuń zbędne znaki na początku i końcu
        cleaned = raw.strip()
        cleaned = re.sub(r'^[:\s-]+', '', cleaned)
        cleaned = re.sub(r'[:\s]+$', '', cleaned)

        # Usuń słowa kluczowe które mogły się wkraść
        cleaned = re.sub(r'^(?:nr|numer|no|number)[:\s]*', '', cleaned, flags=re.IGNORECASE)

        # Normalizuj separatory
        cleaned = cleaned.replace('\\', '/')

        # Usuń podwójne separatory
        cleaned = re.sub(r'[/]{2,}', '/', cleaned)
        cleaned = re.sub(r'[-]{2,}', '-', cleaned)

        return cleaned.strip()

    @classmethod
    def _extract_romanian_series(cls, text: str) -> Optional[str]:
        """Ekstraktuje serię faktury dla rumuńskich dokumentów"""
        # Wzorzec: "seria Dov H nr 00005164" -> seria = "Dov H"
        match = re.search(r'seria\s+([A-Z]{1,5}(?:\s+[A-Z])?)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @classmethod
    def _is_false_positive(cls, candidate: str, full_text: str) -> bool:
        """Sprawdza czy kandydat to fałszywy pozytyw (NIP, IBAN, data, itp.)"""
        # Sprawdź czy to NIP (10 cyfr)
        digits_only = re.sub(r'\D', '', candidate)
        if len(digits_only) == 10:
            # Sprawdź czy występuje w kontekście NIP
            nip_context = re.search(r'NIP[:\s]*' + re.escape(candidate), full_text, re.IGNORECASE)
            if nip_context:
                return True

        # Sprawdź czy to data
        if re.match(r'^\d{2}[./-]\d{2}[./-]\d{4}$', candidate):
            return True

        # Sprawdź czy to IBAN
        if re.match(r'^[A-Z]{2}\d{2}', candidate):
            return True

        return False


# ==============================================================================
# KLASA: DocumentTypeDetector - Wykrywanie oryginał/kopia
# ==============================================================================

class DocumentTypeDetector:
    """Wykrywanie typu dokumentu: oryginał, kopia, duplikat"""

    PATTERNS = {
        'oryginał': [
            r'\bORYGINAŁ\b',
            r'\bORYGINAL\b',
            r'\bORIGINAL\b',
            r'\bORIGINALE\b',
        ],
        'kopia': [
            r'\bKOPIA\b',
            r'\bCOPY\b',
            r'\bCOPIE\b',
            r'\bKOPIE\b',
        ],
        'duplikat': [
            r'\bDUPLIKAT\b',
            r'\bDUPLICATE\b',
            r'\bDUPLICAT\b',
        ]
    }

    @classmethod
    def detect(cls, text: str) -> Tuple[str, bool]:
        """
        Wykrywa typ dokumentu.

        Returns:
            Tuple[str, bool]: (typ_dokumentu, czy_znaleziono)
        """
        text_upper = text.upper()

        for doc_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_upper):
                    logger.info(f"📄 Wykryto typ dokumentu: {doc_type}")
                    return doc_type, True

        logger.info("📄 Typ dokumentu: nieznany (nie znaleziono oznaczenia)")
        return 'nieznany', False


# ==============================================================================
# KLASA: RomanianInvoiceParser - Specjalne parsowanie dla rumuńskich faktur
# ==============================================================================

class RomanianInvoiceParser:
    """Specjalne parsowanie dla rumuńskich faktur"""

    @classmethod
    def extract_cif(cls, text: str) -> List[str]:
        """
        Ekstraktuje rumuński CIF/CUI z różnych formatów.

        Obsługiwane formaty:
        - Cod-fiscal: RO246251
        - CUI: RO12345678
        - CIF: 12345678
        - C.I.F.: RO12345678
        """
        cif_list = []

        patterns = [
            # Cod-fiscal: RO246251
            r'Cod[-\s]?fiscal[:\s]*(?:RO)?\s*(\d{2,10})',
            # CUI/CIF z prefiksem RO
            r'(?:CUI|CIF|C\.I\.F\.)[:\s]*RO\s*(\d{2,10})',
            # CUI/CIF bez prefiksu
            r'(?:CUI|CIF|C\.I\.F\.)[:\s]*(\d{2,10})',
            # RO + cyfry (EU VAT)
            r'\bRO\s*(\d{2,10})\b',
            # Cod unic de inregistrare
            r'Cod\s+unic\s+de\s+inregistrare[:\s]*(\d{2,10})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                clean_cif = re.sub(r'\D', '', match)
                if 2 <= len(clean_cif) <= 10 and clean_cif not in cif_list:
                    cif_list.append(clean_cif)
                    logger.info(f"🇷🇴 Znaleziono CIF: {clean_cif}")

        return cif_list

    @classmethod
    def extract_invoice_series(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Ekstraktuje serię i numer faktury z rumuńskiego formatu.

        Format: "Factura fiscala seria Dov H nr 00005164"
        Returns: (seria, numer) np. ("Dov H", "00005164")
        """
        # Wzorzec dla pełnego formatu
        pattern = r'(?:Factura\s+fiscala\s+)?seria\s+([A-Z]{1,5}(?:\s+[A-Z])?)\s+nr\s+(\d{5,10})'

        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            series = match.group(1).strip()
            number = match.group(2).strip()
            logger.info(f"🇷🇴 Seria: {series}, Numer: {number}")
            return series, number

        return None, None


# ==============================================================================
# KLASA: BaseParser
# ==============================================================================

class BaseParser:
    """Bazowa klasa parsera"""

    def __init__(self, text: str, language: str = 'Polski'):
        self.text = text
        # Normalizuj backslashe na slashe
        self.text = self.text.replace('\\', '/')
        self.lines = [l.strip() for l in self.text.split('\n') if l.strip()]
        self.language = language
        self.lang_config = get_language_config(language)
        self.errors = []
        self.warnings = []

    def parse(self) -> ParsedInvoice:
        """Główna metoda parsowania - do nadpisania"""
        raise NotImplementedError

    def _find_by_keyword(self, keywords: List[str], max_distance: int = 50) -> Optional[str]:
        """Znajdź wartość po słowie kluczowym"""
        text_upper = self.text.upper()

        for keyword in keywords:
            keyword_upper = keyword.upper()
            pos = text_upper.find(keyword_upper)

            if pos != -1:
                # Znajdź wartość w pobliżu
                end_pos = min(pos + len(keyword) + max_distance, len(self.text))
                nearby_text = self.text[pos + len(keyword):end_pos]

                # Usuń dwukropek i białe znaki
                nearby_text = nearby_text.strip()
                if nearby_text.startswith(':'):
                    nearby_text = nearby_text[1:].strip()

                # Zwróć pierwszą linię
                lines = nearby_text.split('\n')
                if lines:
                    return lines[0].strip()

        return None

    def _find_pattern(self, patterns: List[re.Pattern], multiline: bool = False) -> Optional[str]:
        """Znajdź wartość używając regex"""
        search_text = self.text if multiline else ' '.join(self.lines)

        for pattern in patterns:
            match = pattern.search(search_text)
            if match:
                return match.group(1) if len(match.groups()) > 0 else match.group(0)

        return None

    def _extract_amount_near_keyword(self, keywords: List[str]) -> Optional[Decimal]:
        """Wyciągnij kwotę w pobliżu słowa kluczowego"""
        for keyword in keywords:
            value = self._find_by_keyword([keyword])
            if value:
                amount = MoneyUtils.parse_amount(value, self.language)
                if amount:
                    return amount

        return None


# ==============================================================================
# KLASA: SmartInvoiceParser - Główny parser
# ==============================================================================

class SmartInvoiceParser(BaseParser):
    """Inteligentny parser z uczeniem maszynowym kontekstu"""

    def __init__(self, text: str, language: str = 'Polski', user_tax_id: str = None):
        super().__init__(text, language)
        self.user_tax_id = user_tax_id

    def parse(self) -> ParsedInvoice:
        """Parsowanie z inteligentną detekcją"""

        # ==== NOWE: Wykryj typ dokumentu (oryginał/kopia) ====
        document_type, doc_type_found = DocumentTypeDetector.detect(self.text)

        # ==== NOWE: Ulepszone wykrywanie numeru faktury ====
        invoice_id, invoice_series = InvoiceNumberExtractor.extract(self.text, self.language)

        # Typ faktury
        invoice_type = self._detect_invoice_type()

        # Daty
        dates = self._extract_all_dates()
        issue_date = dates.get('issue', datetime.now())
        sale_date = dates.get('sale', issue_date)
        due_date = dates.get('due', issue_date)

        # ==== NOWE: Inteligentne wykrywanie waluty ====
        currency, currency_confidence = CurrencyDetector.detect_currency(self.text, self.language)

        # Utwórz obiekt z WSZYSTKIMI wymaganymi polami
        invoice = ParsedInvoice(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            issue_date=issue_date,
            sale_date=sale_date,
            due_date=due_date,
            supplier_name='Nie znaleziono',
            supplier_tax_id='Brak',
            supplier_address='Nie znaleziono',
            supplier_accounts=[],
            buyer_name='Nie znaleziono',
            buyer_tax_id='Brak',
            buyer_address='Nie znaleziono',
            currency=currency,
            language=self.language,
            raw_text=self.text,
            document_type=document_type,
            invoice_series=invoice_series
        )

        # Teraz ekstraktuj resztę danych i zaktualizuj obiekt
        self._extract_parties(invoice)
        self._extract_items(invoice)
        self._extract_summary(invoice)
        self._extract_payment_info(invoice)

        # Walidacja i oznaczanie
        self._validate_and_mark(invoice)

        # Dodaj ostrzeżenie jeśli waluta ma niską pewność
        if currency_confidence < 0.5:
            self.warnings.append(f"Niska pewność waluty ({currency}): {currency_confidence:.0%}")

        # Dodaj info o typie dokumentu
        if doc_type_found:
            logger.info(f"📄 Dokument oznaczony jako: {document_type.upper()}")

        invoice.parsing_errors = self.errors.copy()
        invoice.parsing_warnings = self.warnings.copy()

        return invoice

    def _extract_all_dates(self) -> Dict[str, datetime]:
        """Ekstraktuje daty z faktury - ULEPSZONA WERSJA z kontekstem"""

        # ==== KROK 1: Znajdź wszystkie daty w dokumencie ====
        all_dates_found = []

        date_patterns = [
            (r'(\d{2}\.\d{2}\.\d{4})', '%d.%m.%Y'),
            (r'(\d{2}-\d{2}-\d{4})', '%d-%m-%Y'),
            (r'(\d{2}/\d{2}/\d{4})', '%d/%m/%Y'),
            (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),
            (r'(\d{4}\.\d{2}\.\d{2})', '%Y.%m.%d'),
            (r'(\d{1,2}\.\d{1,2}\.\d{4})', '%d.%m.%Y'),
        ]

        for pattern_str, date_format in date_patterns:
            pattern = re.compile(pattern_str)
            matches = pattern.finditer(self.text)

            for match in matches:
                date_str = match.group(1)
                position = match.start()

                try:
                    normalized = date_str.replace('/', '-').replace('.', '-').replace(' ', '-')
                    parsed_date = datetime.strptime(
                        normalized, 
                        date_format.replace('.', '-').replace('/', '-').replace(' ', '-')
                    )

                    if datetime(1990, 1, 1) <= parsed_date <= datetime.now() + timedelta(days=730):
                        all_dates_found.append({
                            'date': parsed_date,
                            'position': position,
                            'raw': date_str
                        })
                        logger.info(f"📅 Data: {date_str} → {parsed_date.strftime('%d.%m.%Y')} (poz: {position})")
                except ValueError:
                    continue

        # Usuń duplikaty
        unique_dates = []
        for d in all_dates_found:
            if not any(d['date'] == u['date'] and abs(d['position'] - u['position']) < 5 for u in unique_dates):
                unique_dates.append(d)

        all_dates_found = sorted(unique_dates, key=lambda x: x['position'])
        logger.info(f"📊 Znaleziono {len(all_dates_found)} dat")

        # ==== KROK 2: Słowa kluczowe dla typów dat ====
        issue_keywords = [
            'DATA WYSTAWIENIA', 'DATA WYSTAWIENIA:', 'WYSTAWIENIA',
            'INVOICE DATE', 'ISSUE DATE', 'DATE OF ISSUE',
            'RECHNUNGSDATUM', 'AUSSTELLUNGSDATUM',
            'DATA EMITERII'
        ]

        sale_keywords = [
            'DATA SPRZEDAŻY', 'DATA SPRZEDAZY', 'DATA SPRZEDAŻY:', 
            'DATA DOSTAWY', 'DATA WYKONANIA', 'DOSTAWY/WYKONANIA USŁUGI',
            'DATĂ DOSTAWY', 'DAȚA DOSTAWY',
            'SALE DATE', 'DELIVERY DATE', 'SERVICE DATE',
            'LIEFERDATUM', 'LEISTUNGSDATUM'
        ]

        due_keywords = [
            'TERMIN PŁATNOŚCI', 'TERMIN PLATNOŚCI', 'TERMIN PŁATNOŚCI:',
            'DO DNIA', 'PŁATNE DO', 'ZAPŁATA DO',
            'DUE DATE', 'PAYMENT DUE', 'PAY BY',
            'ZAHLBAR BIS', 'FÄLLIGKEITSDATUM',
            'TERMEN DE PLATĂ', 'SCADENȚĂ'
        ]

        # ==== KROK 3: Szukaj dat przy frazach ====
        def find_date_near_keywords(keywords: list, search_range: int = 150) -> Optional[datetime]:
            for keyword in keywords:
                keyword_upper = keyword.upper()

                for match in re.finditer(re.escape(keyword_upper), self.text.upper()):
                    keyword_pos = match.start()

                    nearby_dates = [
                        d for d in all_dates_found
                        if keyword_pos <= d['position'] <= keyword_pos + search_range
                    ]

                    if not nearby_dates:
                        nearby_dates = [
                            d for d in all_dates_found
                            if abs(d['position'] - keyword_pos) <= search_range
                        ]

                    if nearby_dates:
                        nearby_dates.sort(key=lambda x: abs(x['position'] - keyword_pos))
                        found = nearby_dates[0]
                        logger.info(f"✅ '{keyword}' → {found['raw']} (odl: {abs(found['position'] - keyword_pos)})")
                        return found['date']

            return None

        issue_date = find_date_near_keywords(issue_keywords)
        sale_date = find_date_near_keywords(sale_keywords)
        due_date = find_date_near_keywords(due_keywords)

        # ==== KROK 4: Fallback logika ====
        if not issue_date and all_dates_found:
            issue_date = all_dates_found[0]['date']
            logger.warning(f"⚠️ Data wystawienia - fallback: {issue_date.strftime('%d.%m.%Y')}")

        if not sale_date:
            sale_date = issue_date if issue_date else datetime.now()
            logger.warning(f"⚠️ Data sprzedaży = data wystawienia: {sale_date.strftime('%d.%m.%Y')}")

        if not due_date:
            base = issue_date if issue_date else datetime.now()
            due_date = base + timedelta(days=14)
            logger.warning(f"⚠️ Termin płatności +14 dni: {due_date.strftime('%d.%m.%Y')}")

        # ==== KROK 5: Walidacja logiczna ====
        if not issue_date:
            issue_date = datetime.now()

        if sale_date and issue_date and sale_date > issue_date + timedelta(days=60):
            logger.warning(f"⚠️ Data sprzedaży podejrzanie późna - korekta")
            sale_date = issue_date

        if due_date and issue_date and due_date < issue_date:
            logger.warning(f"⚠️ Termin przed wystawieniem - korekta")
            due_date = issue_date + timedelta(days=14)

        result = {
            'issue': issue_date,
            'sale': sale_date,
            'due': due_date
        }

        logger.info(f"📅 FINALNE DATY:")
        logger.info(f"   Wystawienia: {result['issue'].strftime('%d.%m.%Y')}")
        logger.info(f"   Sprzedaży:   {result['sale'].strftime('%d.%m.%Y')}")
        logger.info(f"   Płatności:   {result['due'].strftime('%d.%m.%Y')}")

        return result

    def _extract_invoice_number(self) -> str:
        """DEPRECATED: Użyj InvoiceNumberExtractor.extract()"""
        invoice_id, _ = InvoiceNumberExtractor.extract(self.text, self.language)
        return invoice_id

    def _detect_invoice_type(self) -> str:
        """Wykrywa typ faktury"""
        text_upper = self.text.upper()

        if 'KOREKTA' in text_upper or 'CORRECTION' in text_upper:
            return 'KOREKTA'
        elif 'PROFORMA' in text_upper:
            return 'PROFORMA'
        elif 'ZALICZK' in text_upper:
            return 'ZALICZKOWA'
        elif 'KOŃCOWA' in text_upper or 'FINAL' in text_upper:
            return 'KOŃCOWA'
        else:
            return 'VAT'

    def _extract_parties(self, invoice: ParsedInvoice):
        """Ekstraktuje dane stron transakcji - ULEPSZONA LOGIKA"""
        # Znajdź wszystkie NIPy/CUI
        tax_ids = self._find_all_tax_ids()

        logger.info(f"🔎 Znalezione NIP-y: {tax_ids}")

        # Znajdź pozycje słów kluczowych w tekście
        seller_keywords = self.lang_config.keywords.get('seller', ['SPRZEDAWCA', 'DOSTAWCA'])
        buyer_keywords = self.lang_config.keywords.get('buyer', ['NABYWCA', 'KUPUJĄCY'])

        seller_pos = self._find_keyword_position(seller_keywords)
        buyer_pos = self._find_keyword_position(buyer_keywords)

        logger.info(f"📍 Pozycje słów kluczowych: SPRZEDAWCA={seller_pos}, NABYWCA={buyer_pos}")

        # ==== ULEPSZONA LOGIKA PRZYPISYWANIA ====
        supplier_tax = None
        buyer_tax = None

        user_nip_clean = None
        if self.user_tax_id:
            user_nip_clean = re.sub(r'\D', '', self.user_tax_id)
            logger.info(f"👤 Mój NIP: {user_nip_clean}")

        nip_distances = []

        for tax_id in tax_ids:
            positions = [m.start() for m in re.finditer(re.escape(tax_id), self.text)]

            for pos in positions:
                dist_to_seller = abs(pos - seller_pos) if seller_pos != -1 else 9999
                dist_to_buyer = abs(pos - buyer_pos) if buyer_pos != -1 else 9999

                nip_distances.append({
                    'nip': tax_id,
                    'position': pos,
                    'dist_seller': dist_to_seller,
                    'dist_buyer': dist_to_buyer,
                    'closer_to': 'seller' if dist_to_seller < dist_to_buyer else 'buyer'
                })

        for item in nip_distances:
            logger.info(f"  NIP {item['nip']}: pos={item['position']}, "
                       f"do_sprzedawcy={item['dist_seller']}, "
                       f"do_nabywcy={item['dist_buyer']}, "
                       f"bliżej: {item['closer_to']}")

        if nip_distances:
            seller_candidates = [x for x in nip_distances if x['closer_to'] == 'seller']
            if seller_candidates:
                seller_candidates.sort(key=lambda x: x['dist_seller'])
                supplier_tax = seller_candidates[0]['nip']

            buyer_candidates = [x for x in nip_distances if x['closer_to'] == 'buyer']
            if buyer_candidates:
                buyer_candidates.sort(key=lambda x: x['dist_buyer'])
                buyer_tax = buyer_candidates[0]['nip']

        if not supplier_tax and tax_ids:
            supplier_tax = tax_ids[0] if len(tax_ids) > 0 else None

        if not buyer_tax and tax_ids:
            buyer_tax = tax_ids[1] if len(tax_ids) > 1 else tax_ids[0]

        if user_nip_clean and user_nip_clean in tax_ids:
            logger.info(f"✅ Znaleziono mój NIP w dokumencie!")

            user_distances = [x for x in nip_distances if x['nip'] == user_nip_clean]

            if user_distances:
                if user_distances[0]['closer_to'] == 'buyer':
                    buyer_tax = user_nip_clean
                    invoice.belongs_to_user = True
                    others = [x for x in tax_ids if x != user_nip_clean]
                    if others:
                        supplier_tax = others[0]
                    logger.info("👤 Jestem NABYWCĄ")
                else:
                    supplier_tax = user_nip_clean
                    invoice.belongs_to_user = False
                    others = [x for x in tax_ids if x != user_nip_clean]
                    if others:
                        buyer_tax = others[0]
                    logger.info("🏢 Jestem SPRZEDAWCĄ")

        invoice.supplier_tax_id = supplier_tax or 'Nie znaleziono'
        invoice.buyer_tax_id = buyer_tax or 'Nie znaleziono'

        logger.info(f"✅ PRZYPISANE - Dostawca NIP: {invoice.supplier_tax_id}, Nabywca NIP: {invoice.buyer_tax_id}")

        invoice.supplier_name = self._extract_company_name_near_keyword(seller_keywords)
        invoice.buyer_name = self._extract_company_name_near_keyword(buyer_keywords)

        invoice.supplier_address = self._extract_address_near_tax_id(supplier_tax) or 'Nie znaleziono'
        invoice.buyer_address = self._extract_address_near_tax_id(buyer_tax) or 'Nie znaleziono'

        invoice.supplier_accounts = BankAccountUtils.extract_bank_accounts(self.text)

    def _find_all_tax_ids(self) -> List[str]:
        """Znajduje wszystkie numery identyfikacji podatkowej - ULEPSZONA WERSJA"""
        tax_ids = []

        # ==== SPECJALNE PARSOWANIE DLA RUMUŃSKICH FAKTUR ====
        if self.language == 'Rumuński':
            romanian_cifs = RomanianInvoiceParser.extract_cif(self.text)
            tax_ids.extend(romanian_cifs)

        # ==== STANDARDOWE PATTERNY ====
        patterns = [
            r'NIP[:\.\s-]*(\d{3}[-\s]\d{3}[-\s]\d{2}[-\s]\d{2})',
            r'NIP[:\.\s-]*(\d{3}[-\s]\d{2}[-\s]\d{2}[-\s]\d{3})',
            r'NIP[:\.\s-]*(\d{3}\.\d{3}\.\d{2}\.\d{2})',
            r'NIP[:\.\s-]*(\d{3}\s\d{3}\s\d{2}\s\d{2})',
            r'NIP[:\.\s-]*(\d{10})',
            r'(?:PL[-\s]?)(\d{10})',
            r'(?<!\d)(\d{3}[-\s]\d{3}[-\s]\d{2}[-\s]\d{2})(?!\d)',
            r'(?<!\d)(\d{10})(?!\d)'
        ]

        found_raw = []

        for pattern in patterns:
            matches = re.finditer(pattern, self.text, re.IGNORECASE)
            for match in matches:
                raw_nip = match.group(1) if match.lastindex else match.group(0)
                clean = re.sub(r'\D', '', raw_nip)
                position = match.start()

                is_valid = False

                if self.language == 'Polski':
                    if len(clean) == 10:
                        is_valid = ValidationUtils.validate_nip_pl(clean)
                elif self.language == 'Rumuński':
                    if 2 <= len(clean) <= 10:
                        is_valid = ValidationUtils.validate_cui_ro(clean)
                else:
                    if 8 <= len(clean) <= 12:
                        is_valid = True

                if is_valid and clean not in [x[1] for x in found_raw]:
                    found_raw.append((raw_nip, clean, position))
                    logger.info(f"🔍 Znaleziono NIP: {raw_nip} → {clean} (pozycja: {position})")

        unique_nips = list(dict.fromkeys([x[1] for x in found_raw]))

        # Dodaj CIF-y które nie są jeszcze na liście
        for cif in tax_ids:
            if cif not in unique_nips:
                unique_nips.append(cif)

        logger.info(f"📊 Suma unikalnych NIP-ów: {len(unique_nips)} → {unique_nips}")

        return unique_nips

    def _find_keyword_position(self, keywords: List[str]) -> int:
        """Znajduje pozycję pierwszego słowa kluczowego"""
        text_upper = self.text.upper()
        min_pos = -1

        for keyword in keywords:
            pos = text_upper.find(keyword.upper())
            if pos != -1:
                if min_pos == -1 or pos < min_pos:
                    min_pos = pos

        return min_pos

    def _extract_company_name_near_keyword(self, keywords: List[str]) -> str:
        """Ekstraktuje nazwę firmy w pobliżu słowa kluczowego"""
        for i, line in enumerate(self.lines):
            line_upper = line.upper()

            for keyword in keywords:
                if keyword.upper() in line_upper:
                    parts = line.split(':')
                    if len(parts) > 1:
                        name = parts[1].strip()
                        if len(name) > 3:
                            return name

                    if i + 1 < len(self.lines):
                        next_line = self.lines[i + 1].strip()
                        if (not re.search(r'\d{2}-\d{3}', next_line) and
                            not re.search(r'NIP|CUI|VAT', next_line, re.I) and
                            len(next_line) > 3):
                            return next_line

        return 'Nie znaleziono'

    def _extract_address_near_tax_id(self, tax_id: str) -> Optional[str]:
        """Ekstraktuje adres w pobliżu NIP"""
        if not tax_id or tax_id == 'Nie znaleziono':
            return None

        tax_pos = self.text.find(tax_id)
        if tax_pos == -1:
            return None

        nearby_text = self.text[max(0, tax_pos - 200):min(len(self.text), tax_pos + 200)]

        patterns = [
            r'(\d{2}-\d{3}\s+[A-ZĄŻŹĆŃŁÓĘŚ][a-zążźćńłóęś]+(?:\s+[A-ZĄŻŹĆŃŁÓĘŚ][a-zążźćńłóęś]+)*)',
            r'([A-Z][a-z]+\s+\d{5})',
            r'(\d{4}\s+[A-Z][a-z]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, nearby_text, re.I)
            if match:
                return match.group(1)

        return None

    def _extract_items(self, invoice: ParsedInvoice):
        """Ekstraktuje pozycje faktury"""
        items = []

        table_section = self._find_table_section()
        if table_section:
            items = self._parse_table_section(table_section)

        if not items:
            items = self._smart_item_detection()

        invoice.line_items = items

        if items and invoice.total_gross == 0:
            total = sum(Decimal(str(item.get('total', 0))) for item in items)
            invoice.total_gross = total
            invoice.total_net = total / Decimal('1.23')
            invoice.total_vat = total - invoice.total_net

    def _find_table_section(self) -> Optional[str]:
        """Znajduje sekcję z tabelą pozycji"""
        table_keywords = ['LP', 'NAZWA', 'ILOŚĆ', 'CENA', 'WARTOŚĆ', 'DESCRIPTION', 'QTY', 'PRICE']

        start_idx = -1
        end_idx = -1

        for i, line in enumerate(self.lines):
            line_upper = line.upper()

            if sum(1 for kw in table_keywords if kw in line_upper) >= 2:
                start_idx = i + 1

            if start_idx != -1 and any(kw in line_upper for kw in ['SUMA', 'RAZEM', 'TOTAL']):
                end_idx = i
                break

        if start_idx != -1:
            if end_idx == -1:
                end_idx = len(self.lines)
            return '\n'.join(self.lines[start_idx:end_idx])

        return None

    def _parse_table_section(self, section: str) -> List[Dict]:
        """Parsuje sekcję tabeli"""
        items = []
        lines = section.split('\n')

        for line in lines:
            if not line.strip():
                continue

            numbers = TextUtils.extract_numbers(line)

            if numbers:
                item = {
                    'description': re.sub(r'[\d\.,]+', '', line).strip(),
                    'quantity': int(numbers[0]) if numbers[0] < 1000 else 1,
                    'unit_price': 0,
                    'total': numbers[-1] if len(numbers) > 0 else 0
                }

                if item['quantity'] > 0:
                    item['unit_price'] = item['total'] / item['quantity']

                if item['description'] and item['total'] > 0:
                    items.append(item)

        return items

    def _smart_item_detection(self) -> List[Dict]:
        """Inteligentna detekcja pozycji"""
        items = []
        current_item = {}
        collecting_numbers = []

        for line in self.lines:
            if any(kw in line.upper() for kw in ['SUMA', 'RAZEM', 'TOTAL', 'DO ZAPŁATY']):
                break

            numbers = TextUtils.extract_numbers(line)

            if numbers:
                collecting_numbers.extend(numbers)
            else:
                clean_line = line.strip()
                if len(clean_line) > 5 and not any(kw in clean_line.upper() for kw in ['NIP', 'REGON', 'BANK']):
                    if current_item and collecting_numbers:
                        current_item['total'] = max(collecting_numbers) if collecting_numbers else 0
                        current_item['quantity'] = 1
                        current_item['unit_price'] = current_item['total']
                        items.append(current_item)

                    current_item = {'description': clean_line}
                    collecting_numbers = []

        if current_item and collecting_numbers:
            current_item['total'] = max(collecting_numbers)
            current_item['quantity'] = 1
            current_item['unit_price'] = current_item['total']
            items.append(current_item)

        return items

    def _extract_summary(self, invoice: ParsedInvoice):
        """Ekstraktuje podsumowanie finansowe"""
        keywords_gross = ['DO ZAPŁATY', 'RAZEM', 'TOTAL', 'SUMA', 'BRUTTO']
        keywords_net = ['NETTO', 'NET', 'PODSTAWA']
        keywords_vat = ['VAT', 'TAX', 'PODATEK']

        gross = self._extract_amount_near_keyword(keywords_gross)
        net = self._extract_amount_near_keyword(keywords_net)
        vat = self._extract_amount_near_keyword(keywords_vat)

        if gross and not net and not vat:
            net = gross / Decimal('1.23')
            vat = gross - net
        elif net and vat and not gross:
            gross = net + vat
        elif gross and net and not vat:
            vat = gross - net

        invoice.total_gross = gross or Decimal('0')
        invoice.total_net = net or Decimal('0')
        invoice.total_vat = vat or Decimal('0')

        # UWAGA: Waluta jest już ustawiona przez CurrencyDetector w metodzie parse()
        # Nie nadpisujemy jej tutaj prostym regex-em

    def _extract_payment_info(self, invoice: ParsedInvoice):
        """Ekstraktuje informacje o płatności"""
        if re.search(r'PRZELEW|TRANSFER|PRZELEWEM', self.text, re.I):
            invoice.payment_method = 'przelew'
        elif re.search(r'GOTÓWK|CASH|HOTOVOST', self.text, re.I):
            invoice.payment_method = 'gotówka'
        elif re.search(r'KART|CARD', self.text, re.I):
            invoice.payment_method = 'karta'

        if re.search(r'ZAPŁACON|OPŁACON|PAID|SETTLED', self.text, re.I):
            invoice.payment_status = 'opłacona'
            invoice.paid_amount = invoice.total_gross
        elif re.search(r'ZALICZK|ADVANCE|DEPOSIT', self.text, re.I):
            invoice.payment_status = 'częściowo opłacona'
            advance_amount = self._extract_amount_near_keyword(['ZALICZKA', 'ADVANCE'])
            if advance_amount:
                invoice.paid_amount = advance_amount

    def _validate_and_mark(self, invoice: ParsedInvoice):
        """Walidacja i oznaczanie faktur"""
        validator = InvoiceValidator(self.language)

        invoice_dict = {
            'invoice_id': invoice.invoice_id,
            'supplier': {
                'name': invoice.supplier_name,
                'tax_id': invoice.supplier_tax_id,
                'address': invoice.supplier_address,
                'bank_accounts': invoice.supplier_accounts
            },
            'buyer': {
                'name': invoice.buyer_name,
                'tax_id': invoice.buyer_tax_id,
                'address': invoice.buyer_address
            },
            'dates': {
                'issue_date': invoice.issue_date.strftime('%Y-%m-%d'),
                'sale_date': invoice.sale_date.strftime('%Y-%m-%d'),
                'due_date': invoice.due_date.strftime('%Y-%m-%d'),
                'payment_term_days': (invoice.due_date - invoice.issue_date).days
            },
            'line_items': invoice.line_items,
            'summary': {
                'total_net': float(invoice.total_net),
                'total_vat': float(invoice.total_vat),
                'total_gross': float(invoice.total_gross)
            }
        }

        validation_result = validator.validate(invoice_dict)

        invoice.confidence = validation_result.confidence
        invoice.is_verified = validation_result.is_valid

        self.errors.extend(validation_result.errors)
        self.warnings.extend(validation_result.warnings)
