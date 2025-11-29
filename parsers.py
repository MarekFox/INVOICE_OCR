"""
FAKTURA BOT v5.0 - Invoice Parsers (Wrapper)
=============================================
Uproszczony wrapper dla kompatybilności wstecznej.
Cała logika parsowania przeniesiona do template_engine.py
"""

import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Tuple

# Import nowego silnika szablonów
from template_engine import TemplateEngine, ParsedInvoice as TemplateInvoice

logger = logging.getLogger(__name__)


# Re-export ParsedInvoice dla kompatybilności
@dataclass
class ParsedInvoice:
    """
    Struktura sparsowanej faktury.
    Wrapper dla kompatybilności z istniejącym kodem.
    """
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

    # Nowe pole - informacja o użytym szablonie
    template_used: str = ""


class BaseParser:
    """
    Bazowa klasa parsera - zachowana dla kompatybilności.
    Teraz deleguje do TemplateEngine.
    """

    def __init__(self, text: str, language: str = 'Polski'):
        self.text = text
        self.lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.language = language
        self.errors = []
        self.warnings = []

    def parse(self) -> ParsedInvoice:
        """Główna metoda parsowania - deleguje do TemplateEngine"""
        raise NotImplementedError("Użyj SmartInvoiceParser")


class SmartInvoiceParser(BaseParser):
    """
    Inteligentny parser faktur.

    UWAGA: Ta klasa jest teraz wrapperem dla TemplateEngine.
    Cała logika parsowania oparta jest na szablonach YAML.
    """

    def __init__(self, text: str, language: str = 'Polski', 
                 user_tax_id: str = None, templates_dir: str = 'templates'):
        super().__init__(text, language)
        self.user_tax_id = user_tax_id
        self.templates_dir = templates_dir
        self._engine = None

    @property
    def engine(self) -> TemplateEngine:
        """Lazy loading silnika szablonów"""
        if self._engine is None:
            self._engine = TemplateEngine(self.templates_dir)
        return self._engine

    def parse(self) -> ParsedInvoice:
        """
        Parsowanie z użyciem systemu szablonów YAML.

        Returns:
            ParsedInvoice z wyekstraktowanymi danymi
        """
        logger.info(f"🚀 SmartInvoiceParser: Rozpoczynam parsowanie ({self.language})")

        # Deleguj do TemplateEngine
        template_result = self.engine.parse(
            text=self.text,
            language=self.language,
            user_tax_id=self.user_tax_id
        )

        # Konwertuj wynik do ParsedInvoice (dla kompatybilności)
        invoice = self._convert_to_parsed_invoice(template_result)

        logger.info(f"✅ Parsowanie zakończone. Szablon: {template_result.template_used}")

        return invoice

    def _convert_to_parsed_invoice(self, result: TemplateInvoice) -> ParsedInvoice:
        """Konwertuje wynik z TemplateEngine do ParsedInvoice"""
        return ParsedInvoice(
            invoice_id=result.invoice_id,
            invoice_type=result.invoice_type,
            issue_date=result.issue_date,
            sale_date=result.sale_date,
            due_date=result.due_date,

            supplier_name=result.supplier_name,
            supplier_tax_id=result.supplier_tax_id,
            supplier_address=result.supplier_address,
            supplier_accounts=result.supplier_accounts,
            supplier_email=result.supplier_email,
            supplier_phone=result.supplier_phone,

            buyer_name=result.buyer_name,
            buyer_tax_id=result.buyer_tax_id,
            buyer_address=result.buyer_address,
            buyer_email=result.buyer_email,
            buyer_phone=result.buyer_phone,

            currency=result.currency,
            language=result.language,
            raw_text=result.raw_text,

            line_items=result.line_items,

            total_net=result.total_net,
            total_vat=result.total_vat,
            total_gross=result.total_gross,
            vat_breakdown=result.vat_breakdown,

            payment_method=result.payment_method,
            payment_status=result.payment_status,
            paid_amount=result.paid_amount,

            confidence=result.confidence,
            parsing_errors=result.parsing_errors,
            parsing_warnings=result.parsing_warnings,
            page_range=result.page_range,

            is_correction=result.is_correction,
            is_proforma=result.is_proforma,
            is_duplicate=result.is_duplicate,
            is_verified=result.is_verified,
            belongs_to_user=result.belongs_to_user,

            template_used=result.template_used
        )

    def set_template(self, template_path: str):
        """
        Wymusza użycie konkretnego szablonu.

        Args:
            template_path: Ścieżka do pliku YAML szablonu
        """
        from template_loader import TemplateLoader
        loader = TemplateLoader(self.templates_dir)
        template = loader.load_template(template_path)

        if template:
            # Parsuj z wymuszonym szablonem
            self._forced_template = template

    def get_available_templates(self) -> List[str]:
        """Zwraca listę dostępnych szablonów"""
        return list(self.engine.loader.templates.keys())

    def get_template_info(self, template_key: str) -> Optional[Dict]:
        """Zwraca informacje o szablonie"""
        template = self.engine.loader.templates.get(template_key)
        if template:
            return {
                'issuer': template.issuer,
                'description': template.description,
                'language': template.language,
                'priority': template.priority,
                'fields': list(template.fields.keys()),
                'file_path': template.file_path
            }
        return None


# Alias dla kompatybilności z istniejącym kodem
InvoiceParser = SmartInvoiceParser


def parse_invoice_text(text: str, language: str = 'Polski', 
                       user_tax_id: str = None) -> ParsedInvoice:
    """
    Funkcja pomocnicza do parsowania tekstu faktury.

    Args:
        text: Tekst OCR faktury
        language: Język dokumentu
        user_tax_id: NIP użytkownika

    Returns:
        ParsedInvoice z danymi
    """
    parser = SmartInvoiceParser(text, language, user_tax_id)
    return parser.parse()
