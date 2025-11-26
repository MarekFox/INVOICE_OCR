"""
FAKTURA BOT v5.0 - Invoice Parsers
===================================
Zaawansowane parsery do ekstrakcji danych z faktur
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

# Reszta kodu klasy BaseParser pozostaje bez zmian
class BaseParser:
    """Bazowa klasa parsera"""
    
    def __init__(self, text: str, language: str = 'Polski'):
        self.text = text
        self.lines = [l.strip() for l in text.split('\n') if l.strip()]
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

class SmartInvoiceParser(BaseParser):
    """Inteligentny parser z uczeniem maszynowym kontekstu"""
    
    def __init__(self, text: str, language: str = 'Polski', user_tax_id: str = None):
        super().__init__(text, language)
        self.user_tax_id = user_tax_id
        
    def parse(self) -> ParsedInvoice:
        """Parsowanie z inteligentną detekcją"""
        
        # Najpierw zbierz wszystkie dane
        invoice_id = self._extract_invoice_number()
        invoice_type = self._detect_invoice_type()
        
        # Daty
        dates = self._extract_all_dates()
        issue_date = dates.get('issue', datetime.now())
        sale_date = dates.get('sale', issue_date)
        due_date = dates.get('due', issue_date)
        
        # Utwórz obiekt z WSZYSTKIMI wymaganymi polami
        invoice = ParsedInvoice(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            issue_date=issue_date,
            sale_date=sale_date,
            due_date=due_date,
            supplier_name='Nie znaleziono',  # Wartość domyślna
            supplier_tax_id='Brak',
            supplier_address='Nie znaleziono',
            supplier_accounts=[],
            buyer_name='Nie znaleziono',
            buyer_tax_id='Brak',
            buyer_address='Nie znaleziono',
            currency='PLN',
            language=self.language,
            raw_text=self.text
        )
        
        # Teraz ekstraktuj resztę danych i zaktualizuj obiekt
        self._extract_parties(invoice)
        self._extract_items(invoice)
        self._extract_summary(invoice)
        self._extract_payment_info(invoice)
        
        # Walidacja i oznaczanie
        self._validate_and_mark(invoice)
        
        invoice.parsing_errors = self.errors.copy()
        invoice.parsing_warnings = self.warnings.copy()
        
        return invoice
    
    def _extract_all_dates(self) -> Dict[str, datetime]:
        """Ekstraktuje daty z faktury - ULEPSZONA WERSJA z kontekstem"""
        
        # ===================== KROK 1: Znajdź wszystkie daty w dokumencie =====================
        all_dates_found = []  # Lista słowników z datą, pozycją, surowym stringiem
        
        # Rozszerzone patterny dla różnych formatów dat
        date_patterns = [
            (r'(\d{2}\.\d{2}\.\d{4})', '%d.%m.%Y'),           # 18.11.2025
            (r'(\d{2}-\d{2}-\d{4})', '%d-%m-%Y'),             # 18-11-2025
            (r'(\d{2}/\d{2}/\d{4})', '%d/%m/%Y'),             # 18/11/2025
            (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),             # 2025-11-20
            (r'(\d{4}\.\d{2}\.\d{2})', '%Y.%m.%d'),           # 2025.11.20
            (r'(\d{1,2}\.\d{1,2}\.\d{4})', '%d.%m.%Y'),       # 1.11.2025
        ]
        
        for pattern_str, date_format in date_patterns:
            pattern = re.compile(pattern_str)
            matches = pattern.finditer(self.text)
            
            for match in matches:
                date_str = match.group(1)
                position = match.start()
                
                try:
                    # Normalizuj separator
                    normalized = date_str.replace('/', '-').replace('.', '-').replace(' ', '-')
                    parsed_date = datetime.strptime(
                        normalized, 
                        date_format.replace('.', '-').replace('/', '-').replace(' ', '-')
                    )
                    
                    # Walidacja - rozsądny zakres dat
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
        
        # ===================== KROK 2: Słowa kluczowe dla typów dat =====================
        
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
        
        # ===================== KROK 3: Szukaj dat przy frazach =====================
        
        def find_date_near_keywords(keywords: list, search_range: int = 150) -> Optional[datetime]:
            """Szuka daty w pobliżu słów kluczowych"""
            for keyword in keywords:
                keyword_upper = keyword.upper()
                
                # Znajdź wystąpienia frazy
                for match in re.finditer(re.escape(keyword_upper), self.text.upper()):
                    keyword_pos = match.start()
                    
                    # Szukaj dat w okolicy (głównie PO frazie)
                    nearby_dates = [
                        d for d in all_dates_found
                        if keyword_pos <= d['position'] <= keyword_pos + search_range
                    ]
                    
                    # Jeśli nie ma po, szukaj przed (±range)
                    if not nearby_dates:
                        nearby_dates = [
                            d for d in all_dates_found
                            if abs(d['position'] - keyword_pos) <= search_range
                        ]
                    
                    if nearby_dates:
                        # Najbliższa data
                        nearby_dates.sort(key=lambda x: abs(x['position'] - keyword_pos))
                        found = nearby_dates[0]
                        
                        logger.info(f"✅ '{keyword}' → {found['raw']} (odl: {abs(found['position'] - keyword_pos)})")
                        return found['date']
            
            return None
        
        # Znajdź każdy typ daty
        issue_date = find_date_near_keywords(issue_keywords)
        sale_date = find_date_near_keywords(sale_keywords)
        due_date = find_date_near_keywords(due_keywords)
        
        # ===================== KROK 4: Fallback logika =====================
        
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
        
        # ===================== KROK 5: Walidacja logiczna =====================
        
        # Jeśli brak daty wystawienia, ustaw dzisiaj
        if not issue_date:
            issue_date = datetime.now()
        
        # Data sprzedaży nie powinna być dużo późniejsza niż wystawienia
        if sale_date and issue_date and sale_date > issue_date + timedelta(days=60):
            logger.warning(f"⚠️ Data sprzedaży podejrzanie późna - korekta")
            sale_date = issue_date
        
        # Termin nie może być przed wystawieniem
        if due_date and issue_date and due_date < issue_date:
            logger.warning(f"⚠️ Termin przed wystawieniem - korekta")
            due_date = issue_date + timedelta(days=14)
        
        # ===================== ZWRÓĆ WYNIK =====================
        
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
        """Wyciąga numer faktury"""
        patterns = self.lang_config.patterns.get('invoice_number', [])
        
        invoice_id = self._find_pattern(patterns)
        if invoice_id:
            return invoice_id
            
        # Fallback - szukaj słów kluczowych
        keywords = ['Faktura nr', 'Invoice no', 'Rechnung Nr', 'Factura nr']
        for keyword in keywords:
            value = self._find_by_keyword([keyword])
            if value:
                # Wyciągnij pierwszą sekwencję alfanumeryczną
                match = re.search(r'([A-Z0-9][A-Z0-9/\-\._ ]+)', value, re.I)
                if match:
                    return match.group(1).strip()
                    
        self.errors.append("Nie znaleziono numeru faktury")
        return "UNKNOWN"
    
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
        
        # ===================== ULEPSZONA LOGIKA PRZYPISYWANIA =====================
        supplier_tax = None
        buyer_tax = None
        
        # Jeśli mamy własny NIP, najpierw sprawdź który NIP to my
        user_nip_clean = None
        if self.user_tax_id:
            user_nip_clean = re.sub(r'\D', '', self.user_tax_id)
            logger.info(f"👤 Mój NIP: {user_nip_clean}")
        
        # Metoda 1: Przypisz na podstawie odległości od słów kluczowych
        nip_distances = []
        
        for tax_id in tax_ids:
            # Znajdź wszystkie wystąpienia tego NIP-u w tekście
            positions = [m.start() for m in re.finditer(tax_id, self.text)]
            
            for pos in positions:
                dist_to_seller = abs(pos - seller_pos) if seller_pos != -1 else 999999
                dist_to_buyer = abs(pos - buyer_pos) if buyer_pos != -1 else 999999
                
                nip_distances.append({
                    'nip': tax_id,
                    'position': pos,
                    'dist_seller': dist_to_seller,
                    'dist_buyer': dist_to_buyer,
                    'closer_to': 'seller' if dist_to_seller < dist_to_buyer else 'buyer'
                })
        
        # Sortuj według odległości
        for item in nip_distances:
            logger.info(f"  NIP {item['nip']}: pos={item['position']}, "
                    f"do_sprzedawcy={item['dist_seller']}, "
                    f"do_nabywcy={item['dist_buyer']}, "
                    f"bliżej: {item['closer_to']}")
        
        # Przypisz NIP-y
        if nip_distances:
            # Znajdź NIP najbliższy SPRZEDAWCY
            seller_candidates = [x for x in nip_distances if x['closer_to'] == 'seller']
            if seller_candidates:
                seller_candidates.sort(key=lambda x: x['dist_seller'])
                supplier_tax = seller_candidates[0]['nip']
            
            # Znajdź NIP najbliższy NABYWCY
            buyer_candidates = [x for x in nip_distances if x['closer_to'] == 'buyer']
            if buyer_candidates:
                buyer_candidates.sort(key=lambda x: x['dist_buyer'])
                buyer_tax = buyer_candidates[0]['nip']
            
            # Jeśli nie znaleziono przez odległość, użyj kolejności
            if not supplier_tax and tax_ids:
                supplier_tax = tax_ids[0] if len(tax_ids) > 0 else None
            
            if not buyer_tax and tax_ids:
                buyer_tax = tax_ids[1] if len(tax_ids) > 1 else tax_ids[0]
        
        # Metoda 2: Override jeśli znamy NIP użytkownika
        if user_nip_clean and user_nip_clean in tax_ids:
            logger.info(f"✅ Znaleziono mój NIP w dokumencie!")
            
            # Sprawdź czy jestem bliżej NABYWCY czy SPRZEDAWCY
            user_distances = [x for x in nip_distances if x['nip'] == user_nip_clean]
            
            if user_distances:
                if user_distances[0]['closer_to'] == 'buyer':
                    buyer_tax = user_nip_clean
                    invoice.belongs_to_user = True
                    # Sprzedawcą jest inny NIP
                    others = [x for x in tax_ids if x != user_nip_clean]
                    if others:
                        supplier_tax = others[0]
                    logger.info("👤 Jestem NABYWCĄ")
                else:
                    supplier_tax = user_nip_clean
                    invoice.belongs_to_user = False
                    # Nabywcą jest inny NIP
                    others = [x for x in tax_ids if x != user_nip_clean]
                    if others:
                        buyer_tax = others[0]
                    logger.info("🏢 Jestem SPRZEDAWCĄ")
        # ==========================================================================
        
        # Przypisz wartości
        invoice.supplier_tax_id = supplier_tax or 'Nie znaleziono'
        invoice.buyer_tax_id = buyer_tax or 'Nie znaleziono'
        
        logger.info(f"✅ PRZYPISANE - Dostawca NIP: {invoice.supplier_tax_id}, Nabywca NIP: {invoice.buyer_tax_id}")
        
        # Ekstraktuj nazwy firm
        invoice.supplier_name = self._extract_company_name_near_keyword(seller_keywords)
        invoice.buyer_name = self._extract_company_name_near_keyword(buyer_keywords)
        
        # Ekstraktuj adresy
        invoice.supplier_address = self._extract_address_near_tax_id(supplier_tax) or 'Nie znaleziono'
        invoice.buyer_address = self._extract_address_near_tax_id(buyer_tax) or 'Nie znaleziono'
        
        # Ekstraktuj konta bankowe
        invoice.supplier_accounts = BankAccountUtils.extract_bank_accounts(self.text)
    
    def _find_all_tax_ids(self) -> List[str]:
        """Znajduje wszystkie numery identyfikacji podatkowej - ULEPSZONA WERSJA"""
        tax_ids = []
        
        # ===================== ROZSZERZONE PATTERNY DLA NIP =====================
        # Pattern 1: NIP z myślnikami (XXX-XXX-XX-XX)
        # Pattern 2: NIP z myślnikami (XXX-XX-XX-XXX) - alternatywny format
        # Pattern 3: NIP z kropkami (XXX.XXX.XX.XX)
        # Pattern 4: NIP ze spacjami (XXX XXX XX XX)
        # Pattern 5: NIP ciągły (10 cyfr)
        # Pattern 6: Prefix PL + NIP
        
        patterns = [
            r'NIP[:\.\s-]*(\d{3}[-\s]\d{3}[-\s]\d{2}[-\s]\d{2})',  # 753-001-14-46
            r'NIP[:\.\s-]*(\d{3}[-\s]\d{2}[-\s]\d{2}[-\s]\d{3})',  # 753-00-14-146 (alt)
            r'NIP[:\.\s-]*(\d{3}\.\d{3}\.\d{2}\.\d{2})',          # 753.001.14.46
            r'NIP[:\.\s-]*(\d{3}\s\d{3}\s\d{2}\s\d{2})',          # 753 001 14 46
            r'NIP[:\.\s-]*(\d{10})',                              # 7530011446
            r'(?:PL[-\s]?)(\d{10})',                              # PL7530011446
            r'(?<!\d)(\d{3}[-\s]\d{3}[-\s]\d{2}[-\s]\d{2})(?!\d)', # bez słowa NIP
            r'(?<!\d)(\d{10})(?!\d)'                              # 10 cyfr gdziekolwiek
        ]
        # =========================================================================
        
        found_raw = []  # Lista krotek (raw_text, clean_nip, position)
        
        for pattern in patterns:
            matches = re.finditer(pattern, self.text, re.IGNORECASE)
            for match in matches:
                raw_nip = match.group(1) if match.lastindex else match.group(0)
                clean = re.sub(r'\D', '', raw_nip)
                position = match.start()
                
                # Walidacja w zależności od kraju
                is_valid = False
                
                if self.language == 'Polski':
                    if len(clean) == 10:
                        is_valid = ValidationUtils.validate_nip_pl(clean)
                elif self.language == 'Rumuński':
                    if 2 <= len(clean) <= 10:
                        is_valid = ValidationUtils.validate_cui_ro(clean)
                else:
                    # Podstawowa walidacja długości
                    if 8 <= len(clean) <= 12:
                        is_valid = True
                
                if is_valid and clean not in [x[1] for x in found_raw]:
                    found_raw.append((raw_nip, clean, position))
                    logger.info(f"🔍 Znaleziono NIP: {raw_nip} → {clean} (pozycja: {position})")
        
        # Zwróć tylko unikalne NIP-y (czyste, bez duplikatów)
        unique_nips = list(dict.fromkeys([x[1] for x in found_raw]))
        
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
                    # Sprawdź czy nazwa jest w tej samej linii
                    parts = line.split(':')
                    if len(parts) > 1:
                        name = parts[1].strip()
                        if len(name) > 3:
                            return name
                            
                    # Sprawdź następną linię
                    if i + 1 < len(self.lines):
                        next_line = self.lines[i + 1].strip()
                        # Sprawdź czy to nazwa firmy (nie NIP, nie adres)
                        if (not re.search(r'\d{2}-\d{3}', next_line) and  # kod pocztowy
                            not re.search(r'NIP|CUI|VAT', next_line, re.I) and
                            len(next_line) > 3):
                            return next_line
                            
        return 'Nie znaleziono'
    
    def _extract_address_near_tax_id(self, tax_id: str) -> Optional[str]:
        """Ekstraktuje adres w pobliżu NIP"""
        if not tax_id or tax_id == 'Nie znaleziono':
            return None
            
        # Znajdź pozycję NIP w tekście
        tax_pos = self.text.find(tax_id)
        if tax_pos == -1:
            return None
            
        # Szukaj kodu pocztowego w pobliżu
        nearby_text = self.text[max(0, tax_pos - 200):min(len(self.text), tax_pos + 200)]
        
        # Pattern dla adresu (kod pocztowy + miasto)
        patterns = [
            r'(\d{2}-\d{3}\s+[A-ZĄŻŹĆŃŁÓĘŚ][a-zążźćńłóęś]+(?:\s+[A-ZĄŻŹĆŃŁÓĘŚ][a-zążźćńłóęś]+)*)',
            r'([A-Z][a-z]+\s+\d{5})',  # Format amerykański
            r'(\d{4}\s+[A-Z][a-z]+)',  # Format szwajcarski
        ]
        
        for pattern in patterns:
            match = re.search(pattern, nearby_text, re.I)
            if match:
                return match.group(1)
                
        return None
    
    def _extract_items(self, invoice: ParsedInvoice):
        """Ekstraktuje pozycje faktury"""
        items = []
        
        # Strategia 1: Szukaj sekcji z tabelą
        table_section = self._find_table_section()
        if table_section:
            items = self._parse_table_section(table_section)
            
        # Strategia 2: Inteligentne wykrywanie pozycji
        if not items:
            items = self._smart_item_detection()
            
        invoice.line_items = items
        
        # Oblicz sumy jeśli nie ma w dokumencie
        if items and invoice.total_gross == 0:
            total = sum(Decimal(str(item.get('total', 0))) for item in items)
            invoice.total_gross = total
            invoice.total_net = total / Decimal('1.23')  # Założenie 23% VAT
            invoice.total_vat = total - invoice.total_net
            
    def _find_table_section(self) -> Optional[str]:
        """Znajduje sekcję z tabelą pozycji"""
        # Szukaj nagłówków tabeli
        table_keywords = ['LP', 'NAZWA', 'ILOŚĆ', 'CENA', 'WARTOŚĆ', 'DESCRIPTION', 'QTY', 'PRICE']
        
        start_idx = -1
        end_idx = -1
        
        for i, line in enumerate(self.lines):
            line_upper = line.upper()
            
            # Sprawdź czy to nagłówek tabeli
            if sum(1 for kw in table_keywords if kw in line_upper) >= 2:
                start_idx = i + 1
                
            # Sprawdź czy to koniec tabeli
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
                
            # Wyciągnij liczby z linii
            numbers = TextUtils.extract_numbers(line)
            
            if numbers:
                # Heurystyka: pierwsza liczba to ilość, ostatnia to wartość
                item = {
                    'description': re.sub(r'[\d\.,]+', '', line).strip(),
                    'quantity': int(numbers[0]) if numbers[0] < 1000 else 1,
                    'unit_price': 0,
                    'total': numbers[-1] if len(numbers) > 0 else 0
                }
                
                # Oblicz cenę jednostkową
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
            # Przerwij na podsumowaniu
            if any(kw in line.upper() for kw in ['SUMA', 'RAZEM', 'TOTAL', 'DO ZAPŁATY']):
                break
                
            # Wyciągnij liczby
            numbers = TextUtils.extract_numbers(line)
            
            if numbers:
                collecting_numbers.extend(numbers)
            else:
                # Jeśli nie ma liczb, to może być opis
                clean_line = line.strip()
                if len(clean_line) > 5 and not any(kw in clean_line.upper() for kw in ['NIP', 'REGON', 'BANK']):
                    # Zakończ poprzedni item jeśli istnieje
                    if current_item and collecting_numbers:
                        current_item['total'] = max(collecting_numbers) if collecting_numbers else 0
                        current_item['quantity'] = 1
                        current_item['unit_price'] = current_item['total']
                        items.append(current_item)
                        
                    # Rozpocznij nowy item
                    current_item = {'description': clean_line}
                    collecting_numbers = []
                    
        # Dodaj ostatni item
        if current_item and collecting_numbers:
            current_item['total'] = max(collecting_numbers)
            current_item['quantity'] = 1
            current_item['unit_price'] = current_item['total']
            items.append(current_item)
            
        return items
        
    def _extract_summary(self, invoice: ParsedInvoice):
        """Ekstraktuje podsumowanie finansowe"""
        # Szukaj kwot przy słowach kluczowych
        keywords_gross = ['DO ZAPŁATY', 'RAZEM', 'TOTAL', 'SUMA', 'BRUTTO']
        keywords_net = ['NETTO', 'NET', 'PODSTAWA']
        keywords_vat = ['VAT', 'TAX', 'PODATEK']
        
        gross = self._extract_amount_near_keyword(keywords_gross)
        net = self._extract_amount_near_keyword(keywords_net)
        vat = self._extract_amount_near_keyword(keywords_vat)
        
        # Jeśli brakuje niektórych wartości, oblicz
        if gross and not net and not vat:
            # Zakładając 23% VAT
            net = gross / Decimal('1.23')
            vat = gross - net
        elif net and vat and not gross:
            gross = net + vat
        elif gross and net and not vat:
            vat = gross - net
            
        invoice.total_gross = gross or Decimal('0')
        invoice.total_net = net or Decimal('0')
        invoice.total_vat = vat or Decimal('0')
        
        # Wykryj walutę
        currency_match = re.search(r'(PLN|EUR|USD|GBP|RON|CZK)', self.text, re.I)
        if currency_match:
            invoice.currency = currency_match.group(1).upper()
            
    def _extract_payment_info(self, invoice: ParsedInvoice):
        """Ekstraktuje informacje o płatności"""
        # Metoda płatności
        if re.search(r'PRZELEW|TRANSFER|PRZELEWEM', self.text, re.I):
            invoice.payment_method = 'przelew'
        elif re.search(r'GOTÓWK|CASH|HOTOVOST', self.text, re.I):
            invoice.payment_method = 'gotówka'
        elif re.search(r'KART|CARD', self.text, re.I):
            invoice.payment_method = 'karta'
            
        # Status płatności
        if re.search(r'ZAPŁACON|OPŁACON|PAID|SETTLED', self.text, re.I):
            invoice.payment_status = 'opłacona'
            invoice.paid_amount = invoice.total_gross
        elif re.search(r'ZALICZK|ADVANCE|DEPOSIT', self.text, re.I):
            invoice.payment_status = 'częściowo opłacona'
            # Szukaj kwoty zaliczki
            advance_amount = self._extract_amount_near_keyword(['ZALICZKA', 'ADVANCE'])
            if advance_amount:
                invoice.paid_amount = advance_amount
                
    def _validate_and_mark(self, invoice: ParsedInvoice):
        """Walidacja i oznaczanie faktur"""
        validator = InvoiceValidator(self.language)
        
        # Konwersja do formatu słownikowego dla walidatora
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
        
        # Dodaj błędy i ostrzeżenia
        self.errors.extend(validation_result.errors)
        self.warnings.extend(validation_result.warnings)