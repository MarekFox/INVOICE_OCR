"""
FAKTURA BOT v5.0 - Business Validators
=======================================
Zaawansowana walidacja logiki biznesowej
"""
import re
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
import logging
from dataclasses import dataclass

from utils import ValidationUtils, MoneyUtils, DateUtils

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Wynik walidacji"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]
    confidence: float

class InvoiceValidator:
    """Kompleksowy walidator faktur"""
    
    def __init__(self, language: str = 'Polski'):
        self.language = language
        self.errors = []
        self.warnings = []
        self.suggestions = []
        
    def validate(self, invoice_data: Dict) -> ValidationResult:
        """Przeprowadza pełną walidację faktury"""
        self.errors.clear()
        self.warnings.clear()
        self.suggestions.clear()
        
        # Walidacje podstawowe
        self._validate_required_fields(invoice_data)
        self._validate_invoice_number(invoice_data.get('invoice_id', ''))
        self._validate_parties(invoice_data)
        self._validate_dates(invoice_data)
        self._validate_amounts(invoice_data)
        self._validate_items(invoice_data.get('line_items', []))
        
        # Walidacje krzyżowe
        self._cross_validate_amounts(invoice_data)
        self._validate_tax_rates(invoice_data)
        
        # Walidacje logiczne
        self._validate_business_logic(invoice_data)
        
        # Oblicz poziom pewności
        confidence = self._calculate_confidence()
        
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
            suggestions=self.suggestions.copy(),
            confidence=confidence
        )
    
    def _validate_required_fields(self, data: Dict):
        """Sprawdza obecność wymaganych pól"""
        required = ['invoice_id', 'supplier', 'buyer', 'dates', 'summary']
        
        for field in required:
            if field not in data or not data[field]:
                self.errors.append(f"Brak wymaganego pola: {field}")
    
    def _validate_invoice_number(self, invoice_id: str):
        """Walidacja numeru faktury"""
        if not invoice_id or invoice_id == "UNKNOWN" or invoice_id == "BRAK":
            self.errors.append("Brak numeru faktury")
        elif len(invoice_id) < 3:
            self.warnings.append("Podejrzanie krótki numer faktury")
        elif not re.search(r'\d', invoice_id):
            self.warnings.append("Numer faktury nie zawiera cyfr")
            
        # Sprawdź format typowy dla kraju
        if self.language == 'Polski':
            # Format: XXX/MM/YYYY lub XXX/YYYY/MM
            if not re.match(r'.+/\d{1,2}/\d{4}', invoice_id):
                self.suggestions.append("Typowy format: NR/MM/YYYY")
    
    def _validate_parties(self, data: Dict):
        """Walidacja stron transakcji"""
        supplier = data.get('supplier', {})
        buyer = data.get('buyer', {})
        
        # Walidacja dostawcy
        if not supplier.get('name') or supplier['name'] == 'Nie znaleziono':
            self.errors.append("Brak nazwy dostawcy")
            
        supplier_nip = supplier.get('tax_id', '')
        if supplier_nip and supplier_nip != 'Brak':
            if self.language == 'Polski':
                if not ValidationUtils.validate_nip_pl(supplier_nip):
                    self.errors.append(f"Nieprawidłowy NIP dostawcy: {supplier_nip}")
            elif self.language == 'Rumuński':
                if not ValidationUtils.validate_cui_ro(supplier_nip):
                    self.errors.append(f"Nieprawidłowy CUI dostawcy: {supplier_nip}")
        else:
            self.warnings.append("Brak NIP/CUI dostawcy")
            
        # Walidacja nabywcy
        if not buyer.get('name') or buyer['name'] == 'Nie znaleziono':
            self.errors.append("Brak nazwy nabywcy")
            
        buyer_nip = buyer.get('tax_id', '')
        if buyer_nip and buyer_nip != 'Brak':
            if self.language == 'Polski':
                if not ValidationUtils.validate_nip_pl(buyer_nip):
                    self.warnings.append(f"Nieprawidłowy NIP nabywcy: {buyer_nip}")
                    
        # Sprawdź konto bankowe
        accounts = supplier.get('bank_accounts', [])
        if accounts and accounts[0] != 'Nie znaleziono':
            for account in accounts:
                clean_account = account.replace(' ', '')
                if not ValidationUtils.validate_iban(clean_account):
                    self.warnings.append(f"Nieprawidłowy IBAN: {account}")
    
    def _validate_dates(self, data: Dict):
        """Walidacja dat"""
        dates = data.get('dates', {})
        
        try:
            issue_date = datetime.strptime(dates.get('issue_date', ''), '%Y-%m-%d')
            due_date = datetime.strptime(dates.get('due_date', ''), '%Y-%m-%d')
            
            # Sprawdź logikę dat
            if issue_date > datetime.now():
                self.warnings.append("Data wystawienia w przyszłości")
                
            if due_date < issue_date:
                self.errors.append("Termin płatności przed datą wystawienia")
                
            # Sprawdź rozsądny termin płatności
            days_diff = (due_date - issue_date).days
            if days_diff > 90:
                self.warnings.append(f"Bardzo długi termin płatności: {days_diff} dni")
            elif days_diff < 0:
                self.errors.append("Ujemny termin płatności")
                
        except (ValueError, TypeError):
            self.errors.append("Nieprawidłowy format dat")
    
    def _validate_amounts(self, data: Dict):
        """Walidacja kwot"""
        summary = data.get('summary', {})
        
        net = Decimal(str(summary.get('total_net', 0)))
        vat = Decimal(str(summary.get('total_vat', 0)))
        gross = Decimal(str(summary.get('total_gross', 0)))
        
        if net < 0 or vat < 0 or gross < 0:
            self.errors.append("Ujemne kwoty na fakturze")
            
        if gross == 0:
            self.errors.append("Brak kwoty brutto")
            
        # Sprawdź czy kwoty się zgadzają
        calculated_gross = net + vat
        if abs(calculated_gross - gross) > Decimal('0.02'):  # 2 grosze tolerancji
            self.errors.append(
                f"Niezgodność kwot: {net} + {vat} = {calculated_gross}, "
                f"ale brutto = {gross}"
            )
            
        # Sprawdź stawkę VAT
        if net > 0:
            vat_rate = (vat / net * 100).quantize(Decimal('0.01'))
            standard_rates = [Decimal('0'), Decimal('5'), Decimal('8'), 
                            Decimal('19'), Decimal('23')]  # Polskie stawki
            
            if self.language == 'Polski':
                if not any(abs(vat_rate - rate) < Decimal('0.5') for rate in standard_rates):
                    self.warnings.append(f"Niestandardowa stawka VAT: {vat_rate}%")
    
    def _validate_items(self, items: List[Dict]):
        """Walidacja pozycji faktury"""
        if not items:
            self.warnings.append("Brak pozycji na fakturze")
            return
            
        for i, item in enumerate(items, 1):
            # Sprawdź wymagane pola
            if not item.get('description'):
                self.warnings.append(f"Pozycja {i}: brak opisu")
                
            qty = item.get('quantity', 0)
            if qty <= 0:
                self.warnings.append(f"Pozycja {i}: nieprawidłowa ilość")
                
            price = item.get('unit_price', 0)
            if price < 0:
                self.errors.append(f"Pozycja {i}: ujemna cena")
                
            total = item.get('total', 0)
            if total < 0:
                self.errors.append(f"Pozycja {i}: ujemna wartość")
                
            # Sprawdź matematykę
            calculated = Decimal(str(qty)) * Decimal(str(price))
            if abs(calculated - Decimal(str(total))) > Decimal('0.02'):
                self.warnings.append(
                    f"Pozycja {i}: niezgodność obliczeń "
                    f"({qty} × {price} = {calculated}, podano {total})"
                )
    
    def _cross_validate_amounts(self, data: Dict):
        """Krzyżowa walidacja sum"""
        items = data.get('line_items', [])
        summary = data.get('summary', {})
        
        if items:
            # Sumuj pozycje
            items_total = sum(Decimal(str(item.get('total', 0))) for item in items)
            invoice_gross = Decimal(str(summary.get('total_gross', 0)))
            
            if abs(items_total - invoice_gross) > Decimal('0.05'):
                self.warnings.append(
                    f"Suma pozycji ({items_total}) różni się od sumy faktury ({invoice_gross})"
                )
    
    def _validate_tax_rates(self, data: Dict):
        """Walidacja stawek podatkowych"""
        breakdown = data.get('summary', {}).get('breakdown', [])
        
        for rate_info in breakdown:
            rate = Decimal(str(rate_info.get('rate', 0)))
            
            # Sprawdź standardowe stawki dla kraju
            if self.language == 'Polski':
                valid_rates = [0, 5, 8, 23]
                if rate not in valid_rates:
                    self.warnings.append(f"Niestandardowa stawka VAT: {rate}%")
                    
            elif self.language == 'Niemiecki':
                valid_rates = [0, 7, 19]
                if rate not in valid_rates:
                    self.warnings.append(f"Niestandardowa stawka MwSt: {rate}%")
    
    def _validate_business_logic(self, data: Dict):
        """Walidacja logiki biznesowej"""
        # Sprawdź duplikację NIP (nabywca = sprzedawca)
        supplier_nip = data.get('supplier', {}).get('tax_id', '')
        buyer_nip = data.get('buyer', {}).get('tax_id', '')
        
        if supplier_nip and buyer_nip and supplier_nip == buyer_nip:
            self.errors.append("Nabywca i sprzedawca mają ten sam NIP")
            
        # Sprawdź rozsądność kwot
        gross = Decimal(str(data.get('summary', {}).get('total_gross', 0)))
        if gross > 1000000:
            self.warnings.append("Bardzo wysoka kwota faktury (>1M)")
        
        # Sprawdź minimalną wartość
        if 0 < gross < Decimal('0.01'):
            self.warnings.append("Podejrzanie niska kwota faktury")
    
    def _calculate_confidence(self) -> float:
        """Oblicza poziom pewności walidacji"""
        # Bazowa pewność
        confidence = 1.0
        
        # Zmniejsz za błędy
        confidence -= len(self.errors) * 0.15
        
        # Zmniejsz za ostrzeżenia
        confidence -= len(self.warnings) * 0.05
        
        # Ogranicz do zakresu 0-1
        return max(0.0, min(1.0, confidence))

class ComparisonValidator:
    """Walidator porównawczy (do sprawdzania duplikatów)"""
    
    @staticmethod
    def find_duplicates(invoices: List[Dict]) -> List[Tuple[int, int]]:
        """Znajduje potencjalne duplikaty faktur"""
        duplicates = []
        
        for i in range(len(invoices)):
            for j in range(i + 1, len(invoices)):
                if ComparisonValidator._are_duplicates(invoices[i], invoices[j]):
                    duplicates.append((i, j))
                    
        return duplicates
    
    @staticmethod
    def _are_duplicates(inv1: Dict, inv2: Dict) -> bool:
        """Sprawdza czy dwie faktury to duplikaty"""
        # Sprawdź numer faktury
        if inv1.get('invoice_id') == inv2.get('invoice_id'):
            return True
            
        # Sprawdź kombinację: dostawca + data + kwota
        same_supplier = (
            inv1.get('supplier', {}).get('tax_id') == 
            inv2.get('supplier', {}).get('tax_id')
        )
        same_date = (
            inv1.get('dates', {}).get('issue_date') == 
            inv2.get('dates', {}).get('issue_date')
        )
        same_amount = (
            abs(
                Decimal(str(inv1.get('summary', {}).get('total_gross', 0))) -
                Decimal(str(inv2.get('summary', {}).get('total_gross', 0)))
            ) < Decimal('0.01')
        )
        
        if same_supplier and same_date and same_amount:
            return True
            
        return False

class TaxCalculator:
    """Kalkulator podatkowy"""
    
    @staticmethod
    def calculate_vat_summary(items: List[Dict]) -> Dict[str, Decimal]:
        """Oblicza podsumowanie VAT"""
        vat_groups = {}
        
        for item in items:
            rate = item.get('vat_rate', 23)
            net = Decimal(str(item.get('net_amount', 0)))
            
            if rate not in vat_groups:
                vat_groups[rate] = {
                    'net': Decimal('0'),
                    'vat': Decimal('0'),
                    'gross': Decimal('0')
                }
                
            vat = MoneyUtils.calculate_vat(net, Decimal(str(rate)))
            vat_groups[rate]['net'] += net
            vat_groups[rate]['vat'] += vat['vat']
            vat_groups[rate]['gross'] += vat['gross']
            
        return vat_groups
    
    @staticmethod
    def calculate_reverse_charge(net_amount: Decimal, country: str) -> Dict:
        """Oblicza odwrotne obciążenie"""
        # Zasady dla różnych krajów UE
        if country in ['DE', 'FR', 'IT', 'ES']:
            return {
                'applicable': True,
                'net': net_amount,
                'vat': Decimal('0'),
                'gross': net_amount,
                'note': 'Odwrotne obciążenie - art. 17 ust. 1 pkt 4'
            }
        return {
            'applicable': False,
            'net': net_amount,
            'vat': MoneyUtils.calculate_vat(net_amount, Decimal('23'))['vat'],
            'gross': net_amount + MoneyUtils.calculate_vat(net_amount, Decimal('23'))['vat']
        }