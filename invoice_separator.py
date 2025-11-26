"""
FAKTURA BOT v5.0 - Invoice Separator
=====================================
Inteligentne rozdzielanie wielostronicowych PDF na pojedyncze faktury
"""

import re
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import logging

from language_config import LANGUAGE_PROFILES

logger = logging.getLogger(__name__)

@dataclass
class InvoiceBoundary:
    """Granice pojedynczej faktury w dokumencie"""
    start_page: int
    end_page: int
    confidence: float
    invoice_type: str
    detected_number: Optional[str] = None
    detected_supplier: Optional[str] = None

class InvoiceSeparator:
    """Zaawansowany separator faktur w dokumentach wielostronicowych"""
    
    # Uniwersalne nagłówki faktur
    INVOICE_HEADERS = [
        r'FAKTURA\s+(?:VAT\s+)?(?:NR\.?|Nr\.?)?',
        r'INVOICE\s+(?:NO\.?|#)?',
        r'RECHNUNG\s+(?:NR\.?)?',
        r'FACTURĂ\s+(?:NR\.?)?',
        r'FACTURA\s+(?:NÚM\.?)?',
        r'NOTA\s+(?:KSIĘGOWA|KORYGUJĄCA)?',
        r'CREDIT\s+NOTE',
        r'PROFORMA',
        r'ZALICZK'
    ]
    
    # Słowa kluczowe początku faktury
    START_KEYWORDS = {
        'pl': ['SPRZEDAWCA', 'DOSTAWCA', 'WYSTAWCA', 'NABYWCA'],
        'en': ['SELLER', 'SUPPLIER', 'BUYER', 'BILL TO'],
        'de': ['VERKÄUFER', 'LIEFERANT', 'KÄUFER'],
        'ro': ['FURNIZOR', 'VÂNZĂTOR', 'CUMPĂRĂTOR']
    }
    
    # Słowa kluczowe końca faktury
    END_KEYWORDS = {
        'pl': ['RAZEM DO ZAPŁATY', 'SŁOWNIE', 'PODPIS', 'PIECZĄTKA'],
        'en': ['TOTAL DUE', 'IN WORDS', 'SIGNATURE', 'STAMP'],
        'de': ['GESAMTBETRAG', 'IN WORTEN', 'UNTERSCHRIFT'],
        'ro': ['TOTAL DE PLATĂ', 'ÎN LITERE', 'SEMNĂTURĂ']
    }
    
    def __init__(self, language: str = 'Polski'):
        self.language = language
        self.lang_code = self._get_lang_code(language)
        
    def _get_lang_code(self, language: str) -> str:
        """Mapowanie języka na kod"""
        lang_map = {
            'Polski': 'pl',
            'Angielski': 'en',
            'Niemiecki': 'de',
            'Rumuński': 'ro'
        }
        return lang_map.get(language, 'pl')
    
    def separate(self, pages_text: List[str]) -> List[InvoiceBoundary]:
        """
        Główna metoda rozdzielająca dokument na faktury
        
        Args:
            pages_text: Lista z tekstem każdej strony
            
        Returns:
            Lista granic faktur
        """
        if not pages_text:
            return []
            
        if len(pages_text) == 1:
            # Pojedyncza strona - jedna faktura
            return [InvoiceBoundary(
                start_page=1,
                end_page=1,
                confidence=1.0,
                invoice_type='SINGLE'
            )]
            
        # Analiza struktury dokumentu
        page_analysis = self._analyze_pages(pages_text)
        
        # Wykrywanie granic
        boundaries = self._detect_boundaries(page_analysis)
        
        # Weryfikacja i korekta
        boundaries = self._verify_boundaries(boundaries, pages_text)
        
        logger.info(f"Wykryto {len(boundaries)} faktur w dokumencie")
        
        return boundaries
    
    def _analyze_pages(self, pages_text: List[str]) -> List[Dict]:
        """Analizuje każdą stronę pod kątem cech charakterystycznych"""
        analysis = []
        
        for i, page_text in enumerate(pages_text):
            page_info = {
                'page_num': i + 1,
                'is_invoice_start': False,
                'is_invoice_end': False,
                'has_header': False,
                'has_summary': False,
                'has_items': False,
                'has_signatures': False,
                'invoice_number': None,
                'supplier_name': None,
                'total_amount': None,
                'confidence': 0.0,
                'features': []
            }
            
            # Sprawdź nagłówek faktury
            for header_pattern in self.INVOICE_HEADERS:
                if re.search(header_pattern, page_text, re.IGNORECASE):
                    page_info['has_header'] = True
                    page_info['features'].append('header')
                    
                    # Spróbuj wyciągnąć numer faktury
                    match = re.search(header_pattern + r'\s*([A-Z0-9/\-\.]+)', page_text, re.I)
                    if match:
                        page_info['invoice_number'] = match.group(1)
                    break
            
            # Sprawdź słowa kluczowe początku
            start_keywords = self.START_KEYWORDS.get(self.lang_code, self.START_KEYWORDS['pl'])
            start_count = sum(1 for kw in start_keywords if kw in page_text.upper())
            if start_count >= 2:
                page_info['is_invoice_start'] = True
                page_info['features'].append('start_keywords')
            
            # Sprawdź słowa kluczowe końca
            end_keywords = self.END_KEYWORDS.get(self.lang_code, self.END_KEYWORDS['pl'])
            end_count = sum(1 for kw in end_keywords if kw in page_text.upper())
            if end_count >= 2:
                page_info['is_invoice_end'] = True
                page_info['features'].append('end_keywords')
            
            # Sprawdź obecność tabel z pozycjami
            if self._has_item_table(page_text):
                page_info['has_items'] = True
                page_info['features'].append('items_table')
            
            # Sprawdź podsumowanie finansowe
            if self._has_financial_summary(page_text):
                page_info['has_summary'] = True
                page_info['features'].append('summary')
                
                # Spróbuj wyciągnąć kwotę całkowitą
                amount_match = re.search(r'(?:RAZEM|TOTAL|SUMA)[:\s]+([0-9\s,\.]+)', page_text, re.I)
                if amount_match:
                    page_info['total_amount'] = amount_match.group(1)
            
            # Sprawdź podpisy
            if re.search(r'PODPIS|SIGNATURE|UNTERSCHRIFT', page_text, re.I):
                page_info['has_signatures'] = True
                page_info['features'].append('signatures')
            
            # Oblicz poziom pewności
            page_info['confidence'] = self._calculate_page_confidence(page_info)
            
            analysis.append(page_info)
            
        return analysis
    
    def _has_item_table(self, text: str) -> bool:
        """Sprawdza czy strona zawiera tabelę z pozycjami"""
        table_indicators = [
            r'L\.?\s*P\.?',  # Lp.
            r'(?:NAZWA|OPIS|DESCRIPTION)',
            r'(?:ILOŚĆ|QTY|QUANTITY)',
            r'(?:CENA|PRICE)',
            r'(?:WARTOŚĆ|VALUE|AMOUNT)',
            r'(?:NETTO|NET)',
            r'(?:VAT|TAX)',
            r'(?:BRUTTO|GROSS)'
        ]
        
        indicator_count = sum(1 for ind in table_indicators if re.search(ind, text, re.I))
        
        # Sprawdź też czy są liczby w formacie cen
        price_pattern = r'\d+[,\.]\d{2}'
        price_count = len(re.findall(price_pattern, text))
        
        return indicator_count >= 3 or price_count >= 5
    
    def _has_financial_summary(self, text: str) -> bool:
        """Sprawdza czy strona zawiera podsumowanie finansowe"""
        summary_patterns = [
            r'(?:SUMA|RAZEM|TOTAL|GESAMT)\s*:?\s*\d',
            r'(?:DO\s+ZAPŁATY|AMOUNT\s+DUE|ZU\s+ZAHLEN)',
            r'(?:NETTO|NET)\s*:?\s*\d+',
            r'(?:BRUTTO|GROSS)\s*:?\s*\d+',
            r'VAT\s*:?\s*\d+[,\.]\d{2}'
        ]
        
        for pattern in summary_patterns:
            if re.search(pattern, text, re.I):
                return True
                
        return False
    
    def _calculate_page_confidence(self, page_info: Dict) -> float:
        """Oblicza poziom pewności że strona jest częścią faktury"""
        confidence = 0.0
        
        # Wagi dla różnych cech
        weights = {
            'header': 0.3,
            'start_keywords': 0.2,
            'end_keywords': 0.15,
            'items_table': 0.15,
            'summary': 0.15,
            'signatures': 0.05
        }
        
        for feature in page_info['features']:
            confidence += weights.get(feature, 0)
            
        # Bonus za numer faktury
        if page_info['invoice_number']:
            confidence += 0.1
            
        # Bonus za kwotę
        if page_info['total_amount']:
            confidence += 0.05
            
        return min(1.0, confidence)
    
    def _detect_boundaries(self, page_analysis: List[Dict]) -> List[InvoiceBoundary]:
        """Wykrywa granice faktur na podstawie analizy stron"""
        boundaries = []
        current_start = None
        current_invoice_num = None
        
        for i, page in enumerate(page_analysis):
            # Początek nowej faktury
            if page['has_header'] or (page['is_invoice_start'] and page['confidence'] > 0.5):
                # Jeśli mamy otwartą fakturę, zamknij ją
                if current_start is not None:
                    boundaries.append(InvoiceBoundary(
                        start_page=current_start + 1,  # +1 bo indeksowanie od 1
                        end_page=i,  # i bo poprzednia strona
                        confidence=0.8,
                        invoice_type='MULTI_PAGE',
                        detected_number=current_invoice_num
                    ))
                
                # Rozpocznij nową fakturę
                current_start = i
                current_invoice_num = page['invoice_number']
                
            # Koniec faktury
            elif page['is_invoice_end'] or page['has_signatures']:
                if current_start is not None:
                    boundaries.append(InvoiceBoundary(
                        start_page=current_start + 1,
                        end_page=i + 1,
                        confidence=0.9,
                        invoice_type='STANDARD',
                        detected_number=current_invoice_num
                    ))
                    current_start = None
                    current_invoice_num = None
        
        # Zamknij ostatnią fakturę jeśli jest otwarta
        if current_start is not None:
            boundaries.append(InvoiceBoundary(
                start_page=current_start + 1,
                end_page=len(page_analysis),
                confidence=0.7,
                invoice_type='INCOMPLETE',
                detected_number=current_invoice_num
            ))
        
        # Jeśli nie wykryto granic, traktuj cały dokument jako jedną fakturę
        if not boundaries:
            boundaries = [InvoiceBoundary(
                start_page=1,
                end_page=len(page_analysis),
                confidence=0.5,
                invoice_type='UNKNOWN'
            )]
            
        return boundaries
    
    def _verify_boundaries(self, boundaries: List[InvoiceBoundary], pages_text: List[str]) -> List[InvoiceBoundary]:
        """Weryfikuje i koryguje wykryte granice"""
        verified = []
        
        for boundary in boundaries:
            # Sprawdź minimalną długość faktury
            page_count = boundary.end_page - boundary.start_page + 1
            
            if page_count < 1:
                logger.warning(f"Nieprawidłowa granica: {boundary}")
                continue
                
            # Sprawdź czy faktury nie zachodzą na siebie
            for other in verified:
                if (boundary.start_page <= other.end_page and 
                    boundary.end_page >= other.start_page):
                    logger.warning(f"Nachodzące faktury: {boundary} i {other}")
                    # Połącz je w jedną
                    other.end_page = max(other.end_page, boundary.end_page)
                    other.confidence *= 0.9  # Zmniejsz pewność
                    break
            else:
                verified.append(boundary)
        
        return verified
    
    def merge_pages(self, pages_text: List[str], boundary: InvoiceBoundary) -> str:
        """Łączy strony należące do jednej faktury"""
        start_idx = boundary.start_page - 1  # Konwersja na indeks 0-based
        end_idx = boundary.end_page
        
        if start_idx < 0 or end_idx > len(pages_text):
            logger.error(f"Nieprawidłowe granice: {boundary}")
            return ""
            
        invoice_pages = pages_text[start_idx:end_idx]
        return '\n\n--- NOWA STRONA ---\n\n'.join(invoice_pages)
    
    def create_summary(self, boundaries: List[InvoiceBoundary]) -> Dict:
        """Tworzy podsumowanie rozdzielania"""
        return {
            'total_invoices': len(boundaries),
            'boundaries': [
                {
                    'invoice': i + 1,
                    'pages': f"{b.start_page}-{b.end_page}",
                    'type': b.invoice_type,
                    'confidence': f"{b.confidence:.1%}",
                    'number': b.detected_number or 'Nieznany'
                }
                for i, b in enumerate(boundaries)
            ],
            'warnings': self._check_for_issues(boundaries)
        }
    
    def _check_for_issues(self, boundaries: List[InvoiceBoundary]) -> List[str]:
        """Sprawdza potencjalne problemy"""
        warnings = []
        
        # Sprawdź faktury o niskiej pewności
        low_confidence = [b for b in boundaries if b.confidence < 0.6]
        if low_confidence:
            warnings.append(f"Wykryto {len(low_confidence)} faktur z niską pewnością (<60%)")
        
        # Sprawdź niekompletne faktury
        incomplete = [b for b in boundaries if b.invoice_type == 'INCOMPLETE']
        if incomplete:
            warnings.append(f"Wykryto {len(incomplete)} potencjalnie niekompletnych faktur")
        
        # Sprawdź duplikaty numerów
        numbers = [b.detected_number for b in boundaries if b.detected_number]
        if len(numbers) != len(set(numbers)):
            warnings.append("Wykryto duplikaty numerów faktur")
            
        return warnings

class AdvancedSeparator(InvoiceSeparator):
    """Rozszerzony separator z uczeniem maszynowym"""
    
    def __init__(self, language: str = 'Polski', use_ml: bool = False):
        super().__init__(language)
        self.use_ml = use_ml
        self.ml_model = None
        
        if use_ml:
            self._load_ml_model()
    
    def _load_ml_model(self):
        """Ładuje model ML do rozpoznawania granic (placeholder)"""
        # Tu można zaimplementować rzeczywisty model ML
        # np. używając sklearn, tensorflow lub pytorch
        pass
    
    def separate_with_ml(self, pages_text: List[str]) -> List[InvoiceBoundary]:
        """Separacja z wykorzystaniem ML"""
        if not self.ml_model:
            return self.separate(pages_text)
            
        # Ekstrakcja cech dla modelu
        features = self._extract_ml_features(pages_text)
        
        # Predykcja granic
        predictions = self.ml_model.predict(features)
        
        # Konwersja predykcji na boundaries
        boundaries = self._predictions_to_boundaries(predictions)
        
        return boundaries
    
    def _extract_ml_features(self, pages_text: List[str]) -> List[List[float]]:
        """Ekstraktuje cechy numeryczne dla modelu ML"""
        features = []
        
        for page in pages_text:
            page_features = [
                len(page),  # Długość tekstu
                page.count('\n'),  # Liczba linii
                len(re.findall(r'\d+', page)),  # Liczba liczb
                len(re.findall(r'[A-Z]{2,}', page)),  # Liczba słów CAPS
                # ... więcej cech
            ]
            features.append(page_features)
            
        return features
    
    def _predictions_to_boundaries(self, predictions) -> List[InvoiceBoundary]:
        """Konwertuje predykcje ML na granice faktur"""
        # Implementacja zależy od formatu predykcji modelu
        boundaries = []
        # ...
        return boundaries