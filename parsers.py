"""
FAKTURA BOT v5.1 - Invoice Parsers (YAML-Driven)
====
Parsery kierowane konfiguracją YAML - logika w Pythonie, dane w YAML
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

from utils import TextUtils, MoneyUtils, DateUtils, ValidationUtils, BankAccountUtils
from language_config import get_language_config
from validators import InvoiceValidator

logger = logging.getLogger(__name__)


# ============================================
# YAML CONFIG LOADER
# ============================================

class YAMLConfigLoader:
    """Ładuje i cache'uje konfigurację z plików YAML"""
    
    _cache: Dict[str, Dict] = {}
    _config_dir: Path = Path(__file__).parent
    
    # Mapowanie języków na pliki YAML
    LANGUAGE_FILES = {
        'Polski': 'pl_generic.yml',
        'Niemiecki': 'de_generic.yml',
        'Rumuński': 'ro_generic.yml',
        'Angielski': 'en_generic.yml',
        'Austriacki': 'at_generic.yml',
    }
    
    @classmethod
    def get_config(cls, language: str = 'Polski') -> Dict:
        """Ładuje konfigurację z pliku YAML"""
        filename = cls.LANGUAGE_FILES.get(language, 'pl_generic.yml')
        
        if filename in cls._cache:
            return cls._cache[filename]
        
        # Poprawiona ścieżka: templates/default/
        filepath = cls._config_dir / 'templates' / 'default' / filename
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                cls._cache[filename] = config
                logger.info(f"Załadowano konfigurację YAML: {filepath}")
                return config
        except FileNotFoundError:
            logger.warning(f"Nie znaleziono pliku YAML: {filepath}, używam domyślnej konfiguracji")
            return cls._get_default_config()
        except Exception as e:
            logger.error(f"Błąd ładowania YAML {filepath}: {e}")
            return cls._get_default_config()
    
    @classmethod
    def _get_default_config(cls) -> Dict:
        """Zwraca domyślną konfigurację gdy brak pliku YAML"""
        return {
            'currency': {'symbols': ['PLN', 'EUR', 'USD', 'zł'], 'default': 'PLN'},
            'invoice_number': {'prefixes': ['FV', 'FA', 'F/', 'NR'], 'patterns': []},
            'dates': {'formats': ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']},
        }


# ============================================
# DATACLASS: ParsedInvoice
# ============================================

@dataclass
class ParsedInvoice:
    """Struktura sparsowanej faktury"""
    # Pola WYMAGANE
    invoice_id: str
    invoice_type: str
    issue_date: datetime
    sale_date: datetime
    due_date: datetime
    supplier_name: str
    supplier_tax_id: str
    supplier_address: str
    supplier_accounts: List[str]
    buyer_name: str
    buyer_tax_id: str
    buyer_address: str
    currency: str
    language: str
    raw_text: str

    # Pola OPCJONALNE
    supplier_email: Optional[str] = None
    supplier_phone: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_phone: Optional[str] = None
    line_items: List[Dict] = field(default_factory=list)
    total_net: Decimal = Decimal('0')
    total_vat: Decimal = Decimal('0')
    total_gross: Decimal = Decimal('0')
    vat_breakdown: List[Dict] = field(default_factory=list)
    payment_method: str = 'przelew'
    payment_status: str = 'nieopłacona'
    paid_amount: Decimal = Decimal('0')
    confidence: float = 0.0
    parsing_errors: List[str] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)
    page_range: Tuple[int, int] = (1, 1)
    is_correction: bool = False
    is_proforma: bool = False
    is_duplicate: bool = False
    is_verified: bool = False
    belongs_to_user: bool = False
    document_type: str = 'nieznany'
    invoice_series: Optional[str] = None


# ============================================
# YAML-DRIVEN EXTRACTORS
# ============================================

class CurrencyDetector:
    """Wykrywanie waluty na podstawie konfiguracji YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('currency', {})
        self.default = self.config.get('default', 'PLN')
        self.patterns = self.config.get('patterns', {})
        self.ignore_patterns = self.config.get('ignore_patterns', [])
    
    def detect(self, text: str) -> Tuple[str, float]:
        """Wykrywa walutę w tekście"""
        clean_text = self._remove_ignored_sections(text)
        currency_scores = {}
        
        for currency, cfg in self.patterns.items():
            score = 0
            codes = cfg.get('codes', [])
            symbols = cfg.get('symbols', [])
            weight = cfg.get('weight', 1.0)
            
            # Szukaj kodów walut
            for code in codes:
                pattern = r'\b' + re.escape(code) + r'\b'
                matches = re.findall(pattern, clean_text, re.IGNORECASE)
                score += len(matches) * 2
            
            # Szukaj symboli
            for symbol in symbols:
                if len(symbol) <= 2:
                    pattern = re.escape(symbol)
                else:
                    pattern = r'\b' + re.escape(symbol) + r'\b'
                matches = re.findall(pattern, clean_text, re.IGNORECASE)
                score += len(matches)
            
            if score > 0:
                currency_scores[currency] = score * weight
        
        logger.debug(f"Wykryte waluty: {currency_scores}")
        
        if currency_scores:
            best = max(currency_scores, key=currency_scores.get)
            total = sum(currency_scores.values())
            confidence = currency_scores[best] / total if total > 0 else 0.5
            logger.info(f"Waluta: {best} (pewność: {confidence:.2f})")
            return best, confidence
        
        logger.warning(f"Nie wykryto waluty, domyślna: {self.default}")
        return self.default, 0.3
    
    def _remove_ignored_sections(self, text: str) -> str:
        """Usuwa sekcje do ignorowania"""
        clean = text
        for pattern in self.ignore_patterns:
            try:
                clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)
            except re.error:
                continue
        return clean


class InvoiceNumberExtractor:
    """Ekstrakcja numeru faktury na podstawie YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('invoice_number', {})
        self.prefixes = self.config.get('prefixes', [])
        self.patterns = self.config.get('patterns', [])
        self.line_keywords = self.config.get('line_keywords', [])
        self.series_pattern = self.config.get('series_pattern')
    
    def extract(self, text: str) -> Tuple[str, Optional[str]]:
        """Ekstraktuje numer faktury"""
        normalized = text.replace('\\', '/')
        
        # Krok 1: Szukaj po frazach kluczowych
        for prefix in self.prefixes:
            full_pattern = prefix + r'([^\n]{3,50})'
            match = re.search(full_pattern, normalized, re.IGNORECASE | re.MULTILINE)
            if match:
                candidate = match.group(1).strip()
                invoice_number = self._clean(candidate)
                if invoice_number and invoice_number.lower() != 'nr':
                    logger.info(f"Numer faktury (fraza): {invoice_number}")
                    series = self._extract_series(candidate)
                    return invoice_number, series
        
        # Krok 2: Szukaj w liniach ze słowami kluczowymi
        lines = normalized.split('\n')
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if any(kw.upper() in line_upper for kw in self.line_keywords):
                for pattern in self.patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        invoice_number = self._clean(match.group(1))
                        if invoice_number and invoice_number.lower() != 'nr':
                            logger.info(f"Numer faktury (linia): {invoice_number}")
                            return invoice_number, None
                
                # Sprawdź następną linię
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    for pattern in self.patterns:
                        match = re.search(pattern, next_line, re.IGNORECASE)
                        if match:
                            invoice_number = self._clean(match.group(1))
                            if invoice_number and invoice_number.lower() != 'nr':
                                logger.info(f"Numer faktury (następna linia): {invoice_number}")
                                return invoice_number, None
        
        # Krok 3: Szukaj wzorców w całym tekście
        for pattern in self.patterns:
            matches = re.findall(pattern, normalized, re.IGNORECASE)
            for match in matches:
                invoice_number = self._clean(match)
                if invoice_number and len(invoice_number) >= 5:
                    if not self._is_false_positive(invoice_number, normalized):
                        logger.info(f"Numer faktury (wzorzec): {invoice_number}")
                        return invoice_number, None
        
        logger.warning("Nie znaleziono numeru faktury")
        return "UNKNOWN", None
    
    def _clean(self, raw: str) -> str:
        """Czyści numer faktury"""
        if not raw:
            return ""
        cleaned = raw.strip()
        cleaned = re.sub(r'^[:\s-]+', '', cleaned)
        cleaned = re.sub(r'[:\s]+$', '', cleaned)
        cleaned = re.sub(r'^(?:nr|numer|no|number)[:\s]*', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('\\', '/')
        cleaned = re.sub(r'[/]{2,}', '/', cleaned)
        return cleaned.strip()
    
    def _extract_series(self, text: str) -> Optional[str]:
        """Ekstraktuje serię faktury"""
        if self.series_pattern:
            match = re.search(self.series_pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def _is_false_positive(self, candidate: str, full_text: str) -> bool:
        """Sprawdza fałszywe pozytywy"""
        digits = re.sub(r'\D', '', candidate)
        if len(digits) == 10:
            if re.search(r'NIP[:\s]*' + re.escape(candidate), full_text, re.IGNORECASE):
                return True
        if re.match(r'^\d{2}[./-]\d{2}[./-]\d{4}$', candidate):
            return True
        if re.match(r'^[A-Z]{2}\d{2}', candidate):
            return True
        return False


class InvoiceTypeDetector:
    """Wykrywanie typu faktury na podstawie YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('invoice_type', {})
        self.default = self.config.get('default', 'VAT')
        self.mapping = self.config.get('mapping', {})
    
    def detect(self, text: str) -> str:
        """Wykrywa typ faktury"""
        text_upper = text.upper()
        
        for inv_type, cfg in self.mapping.items():
            keywords = cfg.get('keywords', [])
            for kw in keywords:
                if kw.upper() in text_upper:
                    logger.info(f"Typ faktury: {inv_type}")
                    return inv_type
        
        return self.default


class DocumentTypeDetector:
    """Wykrywanie typu dokumentu (oryginał/kopia) na podstawie YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('document_type', {})
        self.default = self.config.get('default', 'nieznany')
        self.patterns = self.config.get('patterns', {})
    
    def detect(self, text: str) -> Tuple[str, bool]:
        """Wykrywa typ dokumentu"""
        text_upper = text.upper()
        
        for doc_type, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_upper):
                    logger.info(f"Typ dokumentu: {doc_type}")
                    return doc_type, True
        
        return self.default, False


class DateExtractor:
    """Ekstrakcja dat na podstawie YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('dates', {})
        self.formats = self.config.get('formats', [])
        self.issue_config = self.config.get('issue_date', {})
        self.sale_config = self.config.get('sale_date', {})
        self.due_config = self.config.get('due_date', {})
    
    def extract_all(self, text: str) -> Dict[str, datetime]:
        """Ekstraktuje wszystkie daty"""
        all_dates = self._find_all_dates(text)
        
        issue_date = self._find_date_by_keywords(
            text, all_dates,
            self.issue_config.get('keywords', []),
            self.issue_config.get('search_range', 150)
        )
        
        sale_date = self._find_date_by_keywords(
            text, all_dates,
            self.sale_config.get('keywords', []),
            self.sale_config.get('search_range', 150)
        )
        
        due_date = self._find_date_by_keywords(
            text, all_dates,
            self.due_config.get('keywords', []),
            self.due_config.get('search_range', 150)
        )
        
        # Fallback
        if not issue_date and all_dates:
            issue_date = all_dates[0]['date']
            logger.warning(f"Data wystawienia - fallback: {issue_date.strftime('%d.%m.%Y')}")
        
        if not issue_date:
            issue_date = datetime.now()
        
        if not sale_date:
            if self.sale_config.get('fallback') == 'use_issue_date':
                sale_date = issue_date
            else:
                sale_date = issue_date
        
        if not due_date:
            fallback_days = self.due_config.get('fallback_days', 14)
            due_date = issue_date + timedelta(days=fallback_days)
        
        # Walidacja logiczna
        if sale_date > issue_date + timedelta(days=60):
            sale_date = issue_date
        
        if due_date < issue_date:
            due_date = issue_date + timedelta(days=14)
        
        return {
            'issue': issue_date,
            'sale': sale_date,
            'due': due_date
        }
    
    def _find_all_dates(self, text: str) -> List[Dict]:
        """Znajduje wszystkie daty w tekście"""
        dates_found = []
        
        for fmt_config in self.formats:
            pattern_str = fmt_config.get('pattern', '')
            date_format = fmt_config.get('format', '')
            
            if not pattern_str or not date_format:
                continue
            
            try:
                pattern = re.compile(pattern_str)
                for match in pattern.finditer(text):
                    date_str = match.group(1) if match.lastindex else match.group(0)
                    position = match.start()
                    
                    try:
                        normalized = date_str.replace('/', '-').replace('.', '-')
                        norm_format = date_format.replace('/', '-').replace('.', '-')
                        parsed = datetime.strptime(normalized, norm_format)
                        
                        if datetime(1990, 1, 1) <= parsed <= datetime.now() + timedelta(days=730):
                            dates_found.append({
                                'date': parsed,
                                'position': position,
                                'raw': date_str
                            })
                    except ValueError:
                        continue
            except re.error:
                continue
        
        # Usuń duplikaty
        unique = []
        for d in dates_found:
            if not any(d['date'] == u['date'] and abs(d['position'] - u['position']) < 5 for u in unique):
                unique.append(d)
        
        return sorted(unique, key=lambda x: x['position'])
    
    def _find_date_by_keywords(self, text: str, all_dates: List[Dict], 
                                keywords: List[str], search_range: int) -> Optional[datetime]:
        """Znajduje datę przy słowach kluczowych"""
        text_upper = text.upper()
        
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword.upper()), text_upper):
                kw_pos = match.start()
                
                # Szukaj dat w pobliżu
                nearby = [d for d in all_dates if kw_pos <= d['position'] <= kw_pos + search_range]
                
                if not nearby:
                    nearby = [d for d in all_dates if abs(d['position'] - kw_pos) <= search_range]
                
                if nearby:
                    nearby.sort(key=lambda x: abs(x['position'] - kw_pos))
                    return nearby[0]['date']
        
        return None


class TaxIdExtractor:
    """Ekstrakcja NIP/CUI na podstawie YAML"""
    
    def __init__(self, config: Dict, language: str):
        self.config = config.get('tax_id', {})
        self.patterns = self.config.get('patterns', [])
        self.validation = self.config.get('validation', {})
        self.language = language
    
    def find_all(self, text: str) -> List[str]:
        """Znajduje wszystkie identyfikatory podatkowe"""
        tax_ids = []
        
        for pattern_str in self.patterns:
            try:
                matches = re.finditer(pattern_str, text, re.IGNORECASE)
                for match in matches:
                    raw = match.group(1) if match.lastindex else match.group(0)
                    clean = re.sub(r'\D', '', raw)
                    
                    if self._validate(clean):
                        if clean not in tax_ids:
                            tax_ids.append(clean)
                            logger.debug(f"Znaleziono NIP: {raw} -> {clean}")
            except re.error:
                continue
        
        return tax_ids
    
    def _validate(self, tax_id: str) -> bool:
        """Waliduje identyfikator podatkowy"""
        val_type = self.validation.get('type', '')
        
        if val_type == 'nip_pl':
            return len(tax_id) == 10 and ValidationUtils.validate_nip_pl(tax_id)
        elif val_type == 'cui_ro':
            return 2 <= len(tax_id) <= 10 and ValidationUtils.validate_cui_ro(tax_id)
        elif val_type == 'vat_de':
            return len(tax_id) == 9
        else:
            min_len = self.validation.get('min_length', 8)
            max_len = self.validation.get('max_length', 12)
            return min_len <= len(tax_id) <= max_len


class PartyExtractor:
    """Ekstrakcja danych stron na podstawie YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('parties', {})
        self.seller_config = self.config.get('seller', {})
        self.buyer_config = self.config.get('buyer', {})
    
    def get_seller_keywords(self) -> List[str]:
        return self.seller_config.get('keywords', ['SPRZEDAWCA', 'DOSTAWCA'])
    
    def get_buyer_keywords(self) -> List[str]:
        return self.buyer_config.get('keywords', ['NABYWCA', 'KUPUJĄCY'])
    
    def get_context_range(self, party: str) -> int:
        if party == 'seller':
            return self.seller_config.get('context_range', 300)
        return self.buyer_config.get('context_range', 300)


class AmountExtractor:
    """Ekstrakcja kwot na podstawie YAML"""
    
    def __init__(self, config: Dict, language: str):
        self.config = config.get('amounts', {})
        self.decimal_sep = self.config.get('decimal_separator', ',')
        self.thousand_sep = self.config.get('thousand_separator', ' ')
        self.gross_config = self.config.get('total_gross', {})
        self.net_config = self.config.get('total_net', {})
        self.vat_config = self.config.get('total_vat', {})
        self.language = language
    
    def extract_gross(self, text: str) -> Optional[Decimal]:
        return self._extract_by_keywords(text, self.gross_config.get('keywords', []))
    
    def extract_net(self, text: str) -> Optional[Decimal]:
        return self._extract_by_keywords(text, self.net_config.get('keywords', []))
    
    def extract_vat(self, text: str) -> Optional[Decimal]:
        return self._extract_by_keywords(text, self.vat_config.get('keywords', []))
    
    def get_default_vat_rate(self) -> int:
        return self.net_config.get('default_vat_rate', 23)
    
    def _extract_by_keywords(self, text: str, keywords: List[str]) -> Optional[Decimal]:
        """Ekstraktuje kwotę przy słowach kluczowych"""
        text_upper = text.upper()
        
        for keyword in keywords:
            pos = text_upper.find(keyword.upper())
            if pos != -1:
                end_pos = min(pos + len(keyword) + 50, len(text))
                nearby = text[pos + len(keyword):end_pos]
                nearby = nearby.strip()
                if nearby.startswith(':'):
                    nearby = nearby[1:].strip()
                
                # Parsuj kwotę
                amount = MoneyUtils.parse_amount(nearby.split('\n')[0], self.language)
                if amount:
                    return amount
        
        return None


class PaymentExtractor:
    """Ekstrakcja informacji o płatności na podstawie YAML"""
    
    def __init__(self, config: Dict):
        self.config = config.get('payment', {})
        self.methods = self.config.get('methods', {})
        self.statuses = self.config.get('status', {})
        self.default_method = self.config.get('default_method', 'przelew')
        self.default_status = self.config.get('default_status', 'nieopłacona')
    
    def detect_method(self, text: str) -> str:
        """Wykrywa metodę płatności"""
        text_upper = text.upper()
        
        for method, cfg in self.methods.items():
            keywords = cfg.get('keywords', [])
            for kw in keywords:
                if kw.upper() in text_upper:
                    return method
        
        return self.default_method
    
    def detect_status(self, text: str) -> str:
        """Wykrywa status płatności"""
        text_upper = text.upper()
        
        for status, cfg in self.statuses.items():
            keywords = cfg.get('keywords', [])
            for kw in keywords:
                if kw.upper() in text_upper:
                    return status
        
        return self.default_status


# ============================================
# BASE PARSER
# ============================================

class BaseParser:
    """Bazowa klasa parsera"""
    
    def __init__(self, text: str, language: str = 'Polski'):
        self.text = text.replace('\\', '/')
        self.lines = [l.strip() for l in self.text.split('\n') if l.strip()]
        self.language = language
        self.lang_config = get_language_config(language)
        self.yaml_config = YAMLConfigLoader.get_config(language)
        self.errors = []
        self.warnings = []
    
    def parse(self) -> ParsedInvoice:
        raise NotImplementedError
    
    def _find_by_keyword(self, keywords: List[str], max_distance: int = 50) -> Optional[str]:
        """Znajdź wartość po słowie kluczowym"""
        text_upper = self.text.upper()
        
        for keyword in keywords:
            pos = text_upper.find(keyword.upper())
            if pos != -1:
                end_pos = min(pos + len(keyword) + max_distance, len(self.text))
                nearby = self.text[pos + len(keyword):end_pos].strip()
                if nearby.startswith(':'):
                    nearby = nearby[1:].strip()
                lines = nearby.split('\n')
                if lines:
                    return lines[0].strip()
        
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


# ============================================
# SMART INVOICE PARSER (YAML-DRIVEN)
# ============================================

class SmartInvoiceParser(BaseParser):
    """Inteligentny parser kierowany konfiguracją YAML"""
    
    def __init__(self, text: str, language: str = 'Polski', user_tax_id: str = None):
        super().__init__(text, language)
        self.user_tax_id = user_tax_id
        
        # Inicjalizacja ekstraktorów z YAML
        self.currency_detector = CurrencyDetector(self.yaml_config)
        self.invoice_number_extractor = InvoiceNumberExtractor(self.yaml_config)
        self.invoice_type_detector = InvoiceTypeDetector(self.yaml_config)
        self.document_type_detector = DocumentTypeDetector(self.yaml_config)
        self.date_extractor = DateExtractor(self.yaml_config)
        self.tax_id_extractor = TaxIdExtractor(self.yaml_config, language)
        self.party_extractor = PartyExtractor(self.yaml_config)
        self.amount_extractor = AmountExtractor(self.yaml_config, language)
        self.payment_extractor = PaymentExtractor(self.yaml_config)
    
    def parse(self) -> ParsedInvoice:
        """Główna metoda parsowania"""
        
        # Typ dokumentu
        document_type, _ = self.document_type_detector.detect(self.text)
        
        # Numer faktury
        invoice_id, invoice_series = self.invoice_number_extractor.extract(self.text)
        
        # Typ faktury
        invoice_type = self.invoice_type_detector.detect(self.text)
        
        # Daty
        dates = self.date_extractor.extract_all(self.text)
        
        # Waluta
        currency, currency_confidence = self.currency_detector.detect(self.text)
        
        # Utwórz obiekt faktury
        invoice = ParsedInvoice(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            issue_date=dates['issue'],
            sale_date=dates['sale'],
            due_date=dates['due'],
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
        
        # Ekstraktuj dane stron
        self._extract_parties(invoice)
        
        # Ekstraktuj pozycje
        self._extract_items(invoice)
        
        # Ekstraktuj podsumowanie
        self._extract_summary(invoice)
        
        # Ekstraktuj płatność
        self._extract_payment_info(invoice)
        
        # Walidacja
        self._validate_and_mark(invoice)
        
        # Ostrzeżenia
        if currency_confidence < 0.5:
            self.warnings.append(f"Niska pewność waluty ({currency}): {currency_confidence:.0%}")
        
        invoice.parsing_errors = self.errors.copy()
        invoice.parsing_warnings = self.warnings.copy()
        
        return invoice
    
    def _extract_parties(self, invoice: ParsedInvoice):
        """Ekstraktuje dane stron transakcji"""
        tax_ids = self.tax_id_extractor.find_all(self.text)
        logger.info(f"Znalezione NIP-y: {tax_ids}")
        
        seller_keywords = self.party_extractor.get_seller_keywords()
        buyer_keywords = self.party_extractor.get_buyer_keywords()
        
        seller_pos = self._find_keyword_position(seller_keywords)
        buyer_pos = self._find_keyword_position(buyer_keywords)
        
        logger.debug(f"Pozycje: SPRZEDAWCA={seller_pos}, NABYWCA={buyer_pos}")
        
        # Przypisz NIP-y na podstawie odległości
        supplier_tax = None
        buyer_tax = None
        
        user_nip_clean = None
        if self.user_tax_id:
            user_nip_clean = re.sub(r'\D', '', self.user_tax_id)
        
        nip_distances = []
        for tax_id in tax_ids:
            positions = [m.start() for m in re.finditer(re.escape(tax_id), self.text)]
            for pos in positions:
                dist_seller = abs(pos - seller_pos) if seller_pos != -1 else 9999
                dist_buyer = abs(pos - buyer_pos) if buyer_pos != -1 else 9999
                nip_distances.append({
                    'nip': tax_id,
                    'position': pos,
                    'dist_seller': dist_seller,
                    'dist_buyer': dist_buyer,
                    'closer_to': 'seller' if dist_seller < dist_buyer else 'buyer'
                })
        
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
            supplier_tax = tax_ids[0]
        if not buyer_tax and tax_ids:
            buyer_tax = tax_ids[1] if len(tax_ids) > 1 else tax_ids[0]
        
        # Override jeśli znamy NIP użytkownika
        if user_nip_clean and user_nip_clean in tax_ids:
            user_distances = [x for x in nip_distances if x['nip'] == user_nip_clean]
            if user_distances:
                if user_distances[0]['closer_to'] == 'buyer':
                    buyer_tax = user_nip_clean
                    invoice.belongs_to_user = True
                    others = [x for x in tax_ids if x != user_nip_clean]
                    if others:
                        supplier_tax = others[0]
                else:
                    supplier_tax = user_nip_clean
                    invoice.belongs_to_user = False
                    others = [x for x in tax_ids if x != user_nip_clean]
                    if others:
                        buyer_tax = others[0]
        
        invoice.supplier_tax_id = supplier_tax or 'Nie znaleziono'
        invoice.buyer_tax_id = buyer_tax or 'Nie znaleziono'
        
        logger.info(f"Dostawca NIP: {invoice.supplier_tax_id}, Nabywca NIP: {invoice.buyer_tax_id}")
        
        # Nazwy firm
        invoice.supplier_name = self._extract_company_name(seller_keywords)
        invoice.buyer_name = self._extract_company_name(buyer_keywords)
        
        # Adresy
        invoice.supplier_address = self._extract_address_near_tax_id(supplier_tax) or 'Nie znaleziono'
        invoice.buyer_address = self._extract_address_near_tax_id(buyer_tax) or 'Nie znaleziono'
        
        # Konta bankowe
        invoice.supplier_accounts = BankAccountUtils.extract_bank_accounts(self.text)
    
    def _find_keyword_position(self, keywords: List[str]) -> int:
        """Znajduje pozycję słowa kluczowego"""
        text_upper = self.text.upper()
        min_pos = -1
        for keyword in keywords:
            pos = text_upper.find(keyword.upper())
            if pos != -1 and (min_pos == -1 or pos < min_pos):
                min_pos = pos
        return min_pos
    
    def _extract_company_name(self, keywords: List[str]) -> str:
        """Ekstraktuje nazwę firmy"""
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
        
        nearby = self.text[max(0, tax_pos - 200):min(len(self.text), tax_pos + 200)]
        
        address_config = self.yaml_config.get('address', {})
        patterns = address_config.get('patterns', [])
        
        for pattern in patterns:
            match = re.search(pattern, nearby, re.I)
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
            vat_rate = self.amount_extractor.get_default_vat_rate()
            invoice.total_net = total / Decimal(str(1 + vat_rate / 100))
            invoice.total_vat = total - invoice.total_net
    
    def _find_table_section(self) -> Optional[str]:
        """Znajduje sekcję z tabelą"""
        line_items_config = self.yaml_config.get('line_items', {})
        start_keywords = line_items_config.get('table_start', {}).get('keywords', [])
        end_keywords = line_items_config.get('table_end', {}).get('keywords', [])
        
        start_idx = -1
        end_idx = -1
        
        for i, line in enumerate(self.lines):
            line_upper = line.upper()
            
            if sum(1 for kw in start_keywords if kw.upper() in line_upper) >= 2:
                start_idx = i + 1
            
            if start_idx != -1 and any(kw.upper() in line_upper for kw in end_keywords):
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
        
        for line in section.split('\n'):
            if not line.strip():
                continue
            
            numbers = TextUtils.extract_numbers(line)
            if numbers:
                item = {
                    'description': re.sub(r'[\d\.,]+', '', line).strip(),
                    'quantity': int(numbers[0]) if numbers[0] < 1000 else 1,
                    'unit_price': 0,
                    'total': numbers[-1] if numbers else 0
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
        
        line_items_config = self.yaml_config.get('line_items', {})
        end_keywords = line_items_config.get('table_end', {}).get('keywords', [])
        
        for line in self.lines:
            if any(kw.upper() in line.upper() for kw in end_keywords):
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
        gross = self.amount_extractor.extract_gross(self.text)
        net = self.amount_extractor.extract_net(self.text)
        vat = self.amount_extractor.extract_vat(self.text)
        
        # Obliczenia fallback
        if gross and not net and not vat:
            vat_rate = self.amount_extractor.get_default_vat_rate()
            net = gross / Decimal(str(1 + vat_rate / 100))
            vat = gross - net
        elif net and vat and not gross:
            gross = net + vat
        elif gross and net and not vat:
            vat = gross - net
        
        invoice.total_gross = gross or Decimal('0')
        invoice.total_net = net or Decimal('0')
        invoice.total_vat = vat or Decimal('0')
    
    def _extract_payment_info(self, invoice: ParsedInvoice):
        """Ekstraktuje informacje o płatności"""
        invoice.payment_method = self.payment_extractor.detect_method(self.text)
        invoice.payment_status = self.payment_extractor.detect_status(self.text)
        
        if invoice.payment_status == 'opłacona':
            invoice.paid_amount = invoice.total_gross
        elif invoice.payment_status == 'częściowo_opłacona':
            # Szukaj kwoty zaliczki
            advance_keywords = ['ZALICZKA', 'ADVANCE', 'AVANS', 'ANZAHLUNG']
            advance = self._extract_amount_near_keyword(advance_keywords)
            if advance:
                invoice.paid_amount = advance
    
    def _validate_and_mark(self, invoice: ParsedInvoice):
        """Walidacja faktury"""
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
        
        result = validator.validate(invoice_dict)
        
        invoice.confidence = result.confidence
        invoice.is_verified = result.is_valid
        
        self.errors.extend(result.errors)
        self.warnings.extend(result.warnings)
