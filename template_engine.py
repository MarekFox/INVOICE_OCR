"""
FAKTURA BOT v5.0 - Template Engine
===================================
Główny silnik parsowania faktur na podstawie szablonów YAML
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from template_loader import InvoiceTemplate, TemplateField, TemplateLoader, get_template_loader
from utils import TextUtils, MoneyUtils, DateUtils, ValidationUtils, BankAccountUtils
from language_config import get_language_config

logger = logging.getLogger(__name__)


@dataclass
class ParsedInvoice:
    """Wynik parsowania faktury"""
    # Pola WYMAGANE (bez wartości domyślnych) - muszą być PIERWSZE
    invoice_number: str
    invoice_date: str
    seller_name: str
    seller_nip: str
    buyer_name: str
    buyer_nip: str
    net_amount: float
    vat_amount: float
    gross_amount: float

    # Pola OPCJONALNE (z wartościami domyślnymi) - muszą być PO wymaganych
    due_date: str = ""
    seller_address: str = ""
    buyer_address: str = ""
    bank_account: str = ""
    currency: str = "PLN"
    payment_method: str = ""
    items: list = None
    raw_text: str = ""
    confidence: float = 0.0
    template_used: str = ""
    warnings: list = None

    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.warnings is None:
            self.warnings = []


class TemplateEngine:
    """
    Główny silnik parsowania faktur na podstawie szablonów YAML.
    Zastępuje hardcoded logikę w SmartInvoiceParser.
    """

    def __init__(self, templates_dir: str = "templates"):
        self.loader = get_template_loader(templates_dir)
        self.current_template: Optional[InvoiceTemplate] = None
        self.text = ""
        self.lines: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.extracted_values: Dict[str, Any] = {}
        self.user_tax_id: Optional[str] = None

    def parse(self, text: str, language: str = "Polski", 
              user_tax_id: Optional[str] = None,
              template: Optional[InvoiceTemplate] = None) -> ParsedInvoice:
        """
        Główna metoda parsowania faktury.

        Args:
            text: Tekst OCR faktury
            language: Język dokumentu
            user_tax_id: NIP użytkownika (do oznaczania własnych faktur)
            template: Konkretny szablon (opcjonalnie, jeśli None - auto-detekcja)

        Returns:
            ParsedInvoice z wyekstraktowanymi danymi
        """
        # Reset stanu
        self.text = text
        self.lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.errors.clear()
        self.warnings.clear()
        self.extracted_values.clear()
        self.user_tax_id = user_tax_id

        # Znajdź lub użyj dostarczonego szablonu
        if template:
            self.current_template = template
        else:
            self.current_template = self._find_best_template(language)

        if not self.current_template:
            logger.warning("Nie znaleziono pasującego szablonu, używam domyślnego")
            self.current_template = self._get_default_template(language)

        logger.info(f"🔧 Używam szablonu: {self.current_template.issuer}")

        # Ekstraktuj wszystkie pola
        self._extract_all_fields()

        # Buduj obiekt ParsedInvoice
        invoice = self._build_invoice(language)

        # Post-processing
        self._post_process(invoice)

        # Walidacja
        self._validate_invoice(invoice)

        return invoice

    def _find_best_template(self, language: str) -> Optional[InvoiceTemplate]:
        """Znajduje najlepiej pasujący szablon dla tekstu"""
        from template_matcher import TemplateMatcher
        matcher = TemplateMatcher(self.loader)
        return matcher.find_best_match(self.text, language)

    def _get_default_template(self, language: str) -> InvoiceTemplate:
        """Zwraca domyślny szablon dla języka"""
        templates = self.loader.get_templates_by_language(language)

        # Szukaj szablonu z 'generic' w nazwie
        for t in templates:
            if 'generic' in t.file_path.lower() or 'default' in t.file_path.lower():
                return t

        # Zwróć pierwszy dostępny lub utwórz minimalny
        if templates:
            return templates[0]

        # Fallback - minimalny szablon
        return self._create_minimal_template(language)

    def _create_minimal_template(self, language: str) -> InvoiceTemplate:
        """Tworzy minimalny szablon dla języka"""
        from template_loader import TemplateField, TemplateOptions

        lang_config = get_language_config(language)

        fields = {
            'invoice_id': TemplateField(
                name='invoice_id',
                parser='regex',
                patterns=[p.pattern for p in lang_config.patterns.get('invoice_number', [])],
                required=True
            ),
            'supplier_tax_id': TemplateField(
                name='supplier_tax_id',
                parser='regex',
                patterns=[p.pattern for p in lang_config.patterns.get('nip', [])],
                validator='nip' if language == 'Polski' else None
            ),
            'buyer_tax_id': TemplateField(
                name='buyer_tax_id',
                parser='regex',
                patterns=[p.pattern for p in lang_config.patterns.get('nip', [])]
            ),
            'total_gross': TemplateField(
                name='total_gross',
                parser='money',
                patterns=[p.pattern for p in lang_config.patterns.get('amount', [])],
                keywords=lang_config.keywords.get('summary', [])
            )
        }

        return InvoiceTemplate(
            issuer=f"Default {language}",
            language=language,
            priority=1,
            keywords=lang_config.keywords.get('invoice_header', []),
            fields=fields,
            options=TemplateOptions()
        )

    def _extract_all_fields(self):
        """Ekstraktuje wszystkie pola zdefiniowane w szablonie"""
        for field_name, field_def in self.current_template.fields.items():
            try:
                value = self._extract_field(field_name, field_def)
                self.extracted_values[field_name] = value

                if field_def.required and value is None:
                    self.errors.append(f"Nie znaleziono wymaganego pola: {field_name}")

            except Exception as e:
                logger.error(f"Błąd ekstrakcji pola {field_name}: {e}")
                self.extracted_values[field_name] = None
                if field_def.required:
                    self.errors.append(f"Błąd ekstrakcji pola {field_name}: {e}")

    def _extract_field(self, field_name: str, field_def: TemplateField) -> Any:
        """Ekstraktuje pojedyncze pole według definicji"""
        parser_method = getattr(self, f"_parse_{field_def.parser}", None)

        if parser_method is None:
            logger.warning(f"Nieznany parser: {field_def.parser}")
            return None

        value = parser_method(field_def)

        # Walidacja
        if value and field_def.validator:
            if not self._validate_value(value, field_def.validator):
                self.warnings.append(f"Nieprawidłowa wartość {field_name}: {value}")
                # Nie zwracaj None - może być częściowo poprawna

        # Fallback
        if value is None and field_def.fallback:
            value = self._apply_fallback(field_def.fallback, field_name)

        return value

    # ==================== PARSERY ====================

    def _parse_regex(self, field_def: TemplateField) -> Optional[str]:
        """Parser regex - szuka wzorca w tekście"""
        search_text = self.text

        # Ogranicz obszar szukania jeśli są context_keywords
        if field_def.context_keywords:
            search_text = self._get_context_text(
                field_def.context_keywords, 
                field_def.context_range
            )

        # Użyj skompilowanych wzorców jeśli dostępne
        patterns = self.current_template._compiled_patterns.get(
            field_def.name,
            [re.compile(p, re.IGNORECASE) for p in field_def.patterns]
        )

        for pattern in patterns:
            match = pattern.search(search_text)
            if match:
                try:
                    return match.group(field_def.group)
                except IndexError:
                    return match.group(0)

        return None

    def _parse_date(self, field_def: TemplateField) -> Optional[datetime]:
        """Parser dat - szuka daty w pobliżu słów kluczowych"""
        # Najpierw szukaj przy słowach kluczowych
        if field_def.keywords:
            for keyword in field_def.keywords:
                date = self._find_date_near_keyword(keyword, field_def)
                if date:
                    return date

        # Fallback - szukaj wzorców w całym tekście
        for pattern_str in field_def.patterns:
            pattern = re.compile(pattern_str)
            matches = pattern.findall(self.text)

            for match in matches:
                for fmt in field_def.formats:
                    try:
                        date_str = match if isinstance(match, str) else match[0]
                        normalized = date_str.replace('/', '-').replace('.', '-')
                        norm_fmt = fmt.replace('/', '-').replace('.', '-')
                        dt = datetime.strptime(normalized, norm_fmt)

                        # Waliduj zakres
                        if datetime(1990, 1, 1) <= dt <= datetime.now() + timedelta(days=730):
                            return dt
                    except ValueError:
                        continue

        return None

    def _find_date_near_keyword(self, keyword: str, field_def: TemplateField) -> Optional[datetime]:
        """Szuka daty w pobliżu słowa kluczowego"""
        keyword_pos = self.text.upper().find(keyword.upper())

        if keyword_pos == -1:
            return None

        # Tekst wokół słowa kluczowego
        start = max(0, keyword_pos - 50)
        end = min(len(self.text), keyword_pos + field_def.search_range)
        nearby_text = self.text[start:end]

        # Szukaj dat
        for pattern_str in field_def.patterns:
            pattern = re.compile(pattern_str)
            match = pattern.search(nearby_text)

            if match:
                date_str = match.group(0)
                for fmt in field_def.formats:
                    try:
                        normalized = date_str.replace('/', '-').replace('.', '-')
                        norm_fmt = fmt.replace('/', '-').replace('.', '-')
                        return datetime.strptime(normalized, norm_fmt)
                    except ValueError:
                        continue

        return None

    def _parse_money(self, field_def: TemplateField) -> Optional[Decimal]:
        """Parser kwot pieniężnych"""
        # Szukaj przy słowach kluczowych
        if field_def.keywords:
            for keyword in field_def.keywords:
                amount = self._find_amount_near_keyword(keyword, field_def)
                if amount:
                    return amount

        # Szukaj wzorców
        for pattern_str in field_def.patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            match = pattern.search(self.text)

            if match:
                amount_str = match.group(1) if match.lastindex else match.group(0)
                return self._parse_amount_string(amount_str, field_def)

        return None

    def _find_amount_near_keyword(self, keyword: str, field_def: TemplateField) -> Optional[Decimal]:
        """Szuka kwoty w pobliżu słowa kluczowego"""
        keyword_pos = self.text.upper().find(keyword.upper())

        if keyword_pos == -1:
            return None

        # Tekst po słowie kluczowym
        end = min(len(self.text), keyword_pos + len(keyword) + 100)
        nearby_text = self.text[keyword_pos:end]

        for pattern_str in field_def.patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            match = pattern.search(nearby_text)

            if match:
                amount_str = match.group(1) if match.lastindex else match.group(0)
                return self._parse_amount_string(amount_str, field_def)

        return None

    def _parse_amount_string(self, amount_str: str, field_def: TemplateField) -> Optional[Decimal]:
        """Parsuje string kwoty do Decimal"""
        # Usuń walutę i białe znaki
        clean = re.sub(r'[A-Z]{3}|zł|PLN|€|EUR|\$|USD|lei|RON', '', amount_str, flags=re.I)
        clean = clean.strip()

        # Normalizuj separatory
        thousand_sep = field_def.thousand_separator
        decimal_sep = field_def.decimal_separator

        if thousand_sep == ' ':
            clean = clean.replace(' ', '')
        elif thousand_sep == '.':
            clean = clean.replace('.', '')
        elif thousand_sep == ',':
            # Tylko jeśli jest więcej niż jeden przecinek
            if clean.count(',') > 1:
                clean = clean.replace(',', '')

        # Zamień separator dziesiętny na kropkę
        if decimal_sep == ',':
            clean = clean.replace(',', '.')

        try:
            return Decimal(clean).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except:
            return None

    def _parse_context_extraction(self, field_def: TemplateField) -> Optional[str]:
        """Parser kontekstowy - wyciąga tekst w pobliżu słów kluczowych"""
        for keyword in field_def.keywords:
            for i, line in enumerate(self.lines):
                if keyword.upper() in line.upper():
                    # Strategia: next_line
                    if field_def.extraction_strategy == 'next_line':
                        if i + 1 < len(self.lines):
                            next_line = self.lines[i + 1].strip()
                            # Sprawdź czy to nie NIP/adres
                            if not re.search(r'NIP|CUI|\d{2}-\d{3}', next_line, re.I):
                                if len(next_line) > 3:
                                    return next_line

                    # Strategia: same_line (po dwukropku)
                    elif field_def.extraction_strategy == 'same_line':
                        if ':' in line:
                            value = line.split(':', 1)[1].strip()
                            if len(value) > 2:
                                return value

        return field_def.fallback if field_def.fallback == 'NOT_FOUND' else None

    def _parse_keyword_detection(self, field_def: TemplateField) -> str:
        """Parser detekcji słów kluczowych - mapuje na wartości"""
        text_upper = self.text.upper()

        for keyword, value in field_def.mapping.items():
            if keyword.upper() in text_upper:
                return value

        return field_def.default or ""

    def _parse_static(self, field_def: TemplateField) -> Any:
        """Parser statyczny - zwraca stałą wartość"""
        return field_def.value

    def _parse_bank_accounts(self, field_def: TemplateField) -> List[str]:
        """Parser kont bankowych"""
        accounts = []

        for pattern_str in field_def.patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            matches = pattern.findall(self.text)

            for match in matches:
                account = match if isinstance(match, str) else match[0]
                formatted = BankAccountUtils.format_iban(account)

                # Waliduj jeśli włączona walidacja
                if field_def.validator == 'iban':
                    if ValidationUtils.validate_iban(formatted.replace(' ', '')):
                        if formatted not in accounts:
                            accounts.append(formatted)
                else:
                    if formatted not in accounts:
                        accounts.append(formatted)

        return accounts

    def _parse_address_extraction(self, field_def: TemplateField) -> Optional[str]:
        """Parser adresów"""
        search_text = self.text

        if field_def.context_keywords:
            search_text = self._get_context_text(
                field_def.context_keywords,
                field_def.context_range
            )

        for pattern_str in field_def.patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            match = pattern.search(search_text)
            if match:
                return match.group(1) if match.lastindex else match.group(0)

        return None

    # ==================== POMOCNICZE ====================

    def _get_context_text(self, keywords: List[str], range_chars: int) -> str:
        """Zwraca tekst w pobliżu słów kluczowych"""
        contexts = []

        for keyword in keywords:
            pos = self.text.upper().find(keyword.upper())
            if pos != -1:
                start = max(0, pos - 50)
                end = min(len(self.text), pos + range_chars)
                contexts.append(self.text[start:end])

        return ' '.join(contexts) if contexts else self.text

    def _validate_value(self, value: Any, validator: str) -> bool:
        """Waliduje wartość"""
        if validator == 'nip':
            clean = re.sub(r'\D', '', str(value))
            return ValidationUtils.validate_nip_pl(clean)
        elif validator == 'cui':
            clean = re.sub(r'\D', '', str(value))
            return ValidationUtils.validate_cui_ro(clean)
        elif validator == 'iban':
            return ValidationUtils.validate_iban(str(value).replace(' ', ''))
        elif validator == 'email':
            return ValidationUtils.validate_email(str(value))

        return True

    def _apply_fallback(self, fallback: str, field_name: str) -> Any:
        """Stosuje wartość fallback"""
        if fallback == 'NOT_FOUND':
            return 'Nie znaleziono'

        elif fallback == 'use_issue_date':
            return self.extracted_values.get('issue_date')

        elif fallback.startswith('add_days:'):
            days = int(fallback.split(':')[1])
            issue_date = self.extracted_values.get('issue_date')
            if issue_date:
                return issue_date + timedelta(days=days)

        elif fallback.startswith('calculate_from_gross:'):
            vat_rate = int(fallback.split(':')[1])
            gross = self.extracted_values.get('total_gross')
            if gross:
                return gross / Decimal(f'1.{vat_rate}')

        elif fallback == 'calculate_difference':
            gross = self.extracted_values.get('total_gross', Decimal('0'))
            net = self.extracted_values.get('total_net', Decimal('0'))
            return gross - net

        return None

    def _build_invoice(self, language: str) -> ParsedInvoice:
        """Buduje obiekt ParsedInvoice z wyekstraktowanych wartości"""
        now = datetime.now()

        return ParsedInvoice(
            # Identyfikacja
            invoice_id=self.extracted_values.get('invoice_id') or 'UNKNOWN',
            invoice_type=self.extracted_values.get('invoice_type') or 'VAT',

            # Daty
            issue_date=self.extracted_values.get('issue_date') or now,
            sale_date=self.extracted_values.get('sale_date') or self.extracted_values.get('issue_date') or now,
            due_date=self.extracted_values.get('due_date') or (self.extracted_values.get('issue_date') or now) + timedelta(days=14),

            # Dostawca
            supplier_name=self.extracted_values.get('supplier_name') or 'Nie znaleziono',
            supplier_tax_id=self.extracted_values.get('supplier_tax_id') or 'Brak',
            supplier_address=self.extracted_values.get('supplier_address') or 'Nie znaleziono',
            supplier_accounts=self.extracted_values.get('supplier_accounts') or [],
            supplier_email=self.extracted_values.get('supplier_email'),
            supplier_phone=self.extracted_values.get('supplier_phone'),

            # Nabywca
            buyer_name=self.extracted_values.get('buyer_name') or 'Nie znaleziono',
            buyer_tax_id=self.extracted_values.get('buyer_tax_id') or 'Brak',
            buyer_address=self.extracted_values.get('buyer_address') or 'Nie znaleziono',
            buyer_email=self.extracted_values.get('buyer_email'),
            buyer_phone=self.extracted_values.get('buyer_phone'),

            # Finanse
            total_net=self.extracted_values.get('total_net') or Decimal('0'),
            total_vat=self.extracted_values.get('total_vat') or Decimal('0'),
            total_gross=self.extracted_values.get('total_gross') or Decimal('0'),
            currency=self.extracted_values.get('currency') or 'PLN',

            # Pozycje
            line_items=self._extract_line_items(),

            # Płatność
            payment_method=self.extracted_values.get('payment_method') or 'przelew',

            # Metadane
            language=language,
            raw_text=self.text,
            template_used=self.current_template.issuer if self.current_template else "",
            parsing_errors=self.errors.copy(),
            parsing_warnings=self.warnings.copy()
        )

    def _extract_line_items(self) -> List[Dict]:
        """Ekstraktuje pozycje faktury"""
        if not self.current_template.lines or not self.current_template.lines.enabled:
            return []

        lines_config = self.current_template.lines
        items = []

        # Znajdź sekcję tabeli
        in_table = False
        table_lines = []

        for line in self.lines:
            # Sprawdź początek tabeli
            if not in_table:
                for pattern in self.current_template._compiled_patterns.get('_lines_start', []):
                    if pattern.search(line):
                        in_table = True
                        break

            # Sprawdź koniec tabeli
            if in_table:
                for pattern in self.current_template._compiled_patterns.get('_lines_end', []):
                    if pattern.search(line):
                        in_table = False
                        break

                if in_table:
                    # Sprawdź czy linia do pominięcia
                    skip = False
                    for skip_pattern in lines_config.skip_patterns:
                        if re.search(skip_pattern, line, re.I):
                            skip = True
                            break

                    if not skip:
                        table_lines.append(line)

        # Parsuj linie tabeli
        main_patterns = self.current_template._compiled_patterns.get('_line_main', [])

        for line in table_lines:
            for pattern in main_patterns:
                match = pattern.match(line)
                if match:
                    item = {}
                    for field_info in lines_config.line_fields:
                        try:
                            value = match.group(field_info['group'])
                            field_type = field_info.get('type', 'string')

                            if field_type == 'int':
                                item[field_info['name']] = int(value)
                            elif field_type == 'decimal':
                                item[field_info['name']] = float(value.replace(',', '.'))
                            else:
                                item[field_info['name']] = value
                        except (IndexError, ValueError):
                            continue

                    if item:
                        items.append(item)
                    break

        return items

    def _post_process(self, invoice: ParsedInvoice):
        """Post-processing faktury"""
        # Oznacz typ faktury
        if invoice.invoice_type == 'KOREKTA':
            invoice.is_correction = True
        elif invoice.invoice_type == 'PROFORMA':
            invoice.is_proforma = True

        # Oblicz brakujące kwoty
        if invoice.total_gross and not invoice.total_net:
            invoice.total_net = invoice.total_gross / Decimal('1.23')
            invoice.total_vat = invoice.total_gross - invoice.total_net

        # Oznacz własność faktury
        if self.user_tax_id:
            user_nip_clean = re.sub(r'\D', '', self.user_tax_id)
            buyer_nip_clean = re.sub(r'\D', '', invoice.buyer_tax_id)
            supplier_nip_clean = re.sub(r'\D', '', invoice.supplier_tax_id)

            if user_nip_clean == buyer_nip_clean:
                invoice.belongs_to_user = True
            elif user_nip_clean == supplier_nip_clean:
                invoice.belongs_to_user = False  # Wystawiona przez użytkownika

    def _validate_invoice(self, invoice: ParsedInvoice):
        """Walidacja końcowa"""
        from validators import InvoiceValidator

        validator = InvoiceValidator(invoice.language)

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
                'due_date': invoice.due_date.strftime('%Y-%m-%d')
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
        invoice.parsing_errors.extend(result.errors)
        invoice.parsing_warnings.extend(result.warnings)


# Funkcja pomocnicza dla kompatybilności wstecznej
def parse_invoice(text: str, language: str = "Polski", 
                  user_tax_id: Optional[str] = None,
                  templates_dir: str = "templates") -> ParsedInvoice:
    """
    Wrapper funkcji dla łatwego użycia.
    Zastępuje SmartInvoiceParser.parse()
    """
    engine = TemplateEngine(templates_dir)
    return engine.parse(text, language, user_tax_id)
