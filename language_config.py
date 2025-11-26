"""
FAKTURA BOT v5.0 - Language Configuration
==========================================
Definicje językowe, słowa kluczowe, formaty
"""

from typing import Dict, List, Pattern
import re
from dataclasses import dataclass

@dataclass
class LanguageProfile:
    """Profil językowy z wszystkimi ustawieniami"""
    code: str
    tesseract_lang: str
    paddle_lang: str
    decimal_separator: str
    thousand_separator: str
    currency_symbol: str
    date_formats: List[str]
    keywords: Dict[str, List[str]]
    patterns: Dict[str, List[Pattern]]
    
# Definicje językowe
LANGUAGE_PROFILES = {
    'Polski': LanguageProfile(
        code='pl',
        tesseract_lang='pol',
        paddle_lang='pl',
        decimal_separator=',',
        thousand_separator=' ',
        currency_symbol='zł',
        date_formats=['%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'],
        keywords={
            'invoice_header': ['FAKTURA', 'FAKTURA VAT', 'FAKTURA PROFORMA', 'NOTA'],
            'seller': ['SPRZEDAWCA', 'SPRZEDAJĄCY', 'DOSTAWCA', 'WYSTAWCA', 'USŁUGODAWCA'],
            'buyer': ['NABYWCA', 'KUPUJĄCY', 'ODBIORCA', 'PŁATNIK', 'ZAMAWIAJĄCY'],
            'nip': ['NIP', 'REGON', 'KRS'],
            'payment': ['ZAPŁATA', 'TERMIN PŁATNOŚCI', 'DO ZAPŁATY', 'FORMA PŁATNOŚCI'],
            'bank': ['BANK', 'KONTO', 'RACHUNEK', 'IBAN', 'SWIFT'],
            'summary': ['SUMA', 'RAZEM', 'DO ZAPŁATY', 'WARTOŚĆ', 'OGÓŁEM'],
            'items': ['LP', 'NAZWA', 'ILOŚĆ', 'CENA', 'WARTOŚĆ', 'NETTO', 'VAT', 'BRUTTO'],
            'dates': ['DATA WYSTAWIENIA', 'DATA SPRZEDAŻY', 'TERMIN PŁATNOŚCI'],
            'signature': ['PODPIS', 'PIECZĄTKA', 'WYSTAWIŁ', 'ODEBRAŁ']
        },
        patterns={
            'invoice_number': [
                re.compile(r'(?:Faktura|FV|FA)[:\s]*(?:nr\.?|Nr\.?)?\s*([A-Z0-9][A-Z0-9/\-\._]+)', re.I),
                re.compile(r'Nr\s+faktury[:\s]*([A-Z0-9][A-Z0-9/\-\._]+)', re.I),
                re.compile(r'([0-9]{1,10}/[0-9]{1,2}/[0-9]{4})', re.I)
            ],
            'nip': [
                re.compile(r'NIP[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2})', re.I),
                re.compile(r'NIP[:\s]*(\d{10})', re.I),
                re.compile(r'(?:PL\s?)?(\d{10})(?!\d)', re.I)
            ],
            'amount': [
                re.compile(r'(\d{1,3}(?:\s\d{3})*(?:,\d{2})?)\s*(?:zł|PLN|ZŁ)', re.I),
                re.compile(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:zł|PLN|ZŁ)', re.I)
            ],
            'bank_account': [
                re.compile(r'(?:PL\s?)?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}'),
                re.compile(r'(?<!\d)\d{26}(?!\d)')
            ]
        }
    ),
    
    'Niemiecki': LanguageProfile(
        code='de',
        tesseract_lang='deu',
        paddle_lang='german',
        decimal_separator=',',
        thousand_separator='.',
        currency_symbol='€',
        date_formats=['%d.%m.%Y', '%Y-%m-%d'],
        keywords={
            'invoice_header': ['RECHNUNG', 'QUITTUNG', 'BELEG', 'FAKTURA'],
            'seller': ['VERKÄUFER', 'LIEFERANT', 'ANBIETER', 'LEISTUNGSERBRINGER'],
            'buyer': ['KÄUFER', 'KUNDE', 'EMPFÄNGER', 'AUFTRAGGEBER'],
            'nip': ['UST-IDNR', 'STEUERNUMMER', 'HANDELSREGISTER'],
            'payment': ['ZAHLUNG', 'ZAHLUNGSBEDINGUNGEN', 'FÄLLIGKEIT', 'ZAHLBAR'],
            'bank': ['BANK', 'IBAN', 'BIC', 'SWIFT', 'KONTONUMMER'],
            'summary': ['GESAMT', 'SUMME', 'TOTAL', 'BETRAG', 'ENDBETRAG'],
            'items': ['POS', 'BEZEICHNUNG', 'MENGE', 'PREIS', 'BETRAG', 'NETTO', 'MWST', 'BRUTTO'],
            'dates': ['RECHNUNGSDATUM', 'LIEFERDATUM', 'ZAHLUNGSZIEL'],
            'signature': ['UNTERSCHRIFT', 'STEMPEL', 'AUSGESTELLT']
        },
        patterns={
            'invoice_number': [
                re.compile(r'Rechnungs?[-\s]?(?:nr|nummer)[:\s]*([A-Z0-9][A-Z0-9/\-\.]+)', re.I),
                re.compile(r'(?:RNr|R\-Nr)[:\s]*([A-Z0-9][A-Z0-9/\-\.]+)', re.I)
            ],
            'nip': [
                re.compile(r'(?:UST[-\s]?ID[-\s]?Nr|USt[-\s]?IdNr)[:\s]*(DE\s?\d{9})', re.I),
                re.compile(r'Steuernummer[:\s]*(\d{2,3}/\d{3}/\d{5})', re.I)
            ],
            'amount': [
                re.compile(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|EUR)', re.I)
            ],
            'bank_account': [
                re.compile(r'(?:DE\s?)?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}')
            ]
        }
    ),
    
    'Rumuński': LanguageProfile(
        code='ro',
        tesseract_lang='ron',
        paddle_lang='ro',
        decimal_separator=',',
        thousand_separator='.',
        currency_symbol='lei',
        date_formats=['%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d'],
        keywords={
            'invoice_header': ['FACTURĂ', 'FACTURA', 'CHITANȚĂ', 'BON'],
            'seller': ['FURNIZOR', 'VÂNZĂTOR', 'PRESTATOR', 'EMITENT'],
            'buyer': ['CUMPĂRĂTOR', 'CLIENT', 'BENEFICIAR', 'DESTINATAR'],
            'nip': ['CUI', 'CIF', 'COD FISCAL', 'REG.COM'],
            'payment': ['PLATĂ', 'TERMEN PLATĂ', 'SCADENȚĂ', 'MODALITATE PLATĂ'],
            'bank': ['BANCA', 'CONT', 'IBAN', 'BIC', 'SWIFT'],
            'summary': ['TOTAL', 'SUMA', 'VALOARE', 'TOTAL GENERAL', 'DE PLATĂ'],
            'items': ['NR', 'DENUMIRE', 'CANTITATE', 'PREȚ', 'VALOARE', 'TVA'],
            'dates': ['DATA EMITERII', 'DATA LIVRĂRII', 'DATA SCADENȚEI'],
            'signature': ['SEMNĂTURĂ', 'ȘTAMPILĂ', 'EMIS DE', 'PRIMIT DE']
        },
        patterns={
            'invoice_number': [
                re.compile(r'(?:Factur[aă]|Seria)[:\s]*([A-Z]+\s*[0-9]+)', re.I),
                re.compile(r'Nr\.\s*([0-9]+)', re.I)
            ],
            'nip': [
                re.compile(r'(?:CUI|CIF|C\.U\.I)[:\s]*(RO\s?\d{2,10})', re.I),
                re.compile(r'(?:CUI|CIF)[:\s]*(\d{2,10})', re.I)
            ],
            'amount': [
                re.compile(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:lei|RON|LEI)', re.I)
            ],
            'bank_account': [
                re.compile(r'(?:RO\s?)?\d{2}\s?[A-Z]{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}')
            ]
        }
    ),
    
    'Angielski': LanguageProfile(
        code='en',
        tesseract_lang='eng',
        paddle_lang='en',
        decimal_separator='.',
        thousand_separator=',',
        currency_symbol='$',
        date_formats=['%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d'],
        keywords={
            'invoice_header': ['INVOICE', 'BILL', 'RECEIPT', 'STATEMENT'],
            'seller': ['SELLER', 'VENDOR', 'SUPPLIER', 'FROM', 'BILLER'],
            'buyer': ['BUYER', 'CUSTOMER', 'BILL TO', 'TO', 'PURCHASER'],
            'nip': ['VAT', 'TAX ID', 'EIN', 'GST', 'COMPANY REG'],
            'payment': ['PAYMENT', 'DUE DATE', 'PAYMENT TERMS', 'PAY BY'],
            'bank': ['BANK', 'ACCOUNT', 'IBAN', 'SWIFT', 'ROUTING'],
            'summary': ['TOTAL', 'GRAND TOTAL', 'AMOUNT DUE', 'BALANCE', 'SUBTOTAL'],
            'items': ['NO', 'DESCRIPTION', 'QTY', 'PRICE', 'AMOUNT', 'TAX', 'GROSS'],
            'dates': ['INVOICE DATE', 'DELIVERY DATE', 'DUE DATE'],
            'signature': ['SIGNATURE', 'AUTHORIZED BY', 'ISSUED BY', 'RECEIVED BY']
        },
        patterns={
            'invoice_number': [
                re.compile(r'Invoice\s*(?:No|#)[:\s]*([A-Z0-9][A-Z0-9/\-\.]+)', re.I),
                re.compile(r'INV[-\s]?([0-9]+)', re.I)
            ],
            'nip': [
                re.compile(r'(?:VAT|Tax\s*ID)[:\s]*([A-Z]{2}\s?\d+)', re.I),
                re.compile(r'EIN[:\s]*(\d{2}-\d{7})', re.I)
            ],
            'amount': [
                re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:\$|USD|GBP|EUR)', re.I)
            ],
            'bank_account': [
                re.compile(r'[A-Z]{2}\d{2}\s?[A-Z0-9]{4}\s?\d{4}\s?\d{4}\s?\d{4}(?:\s?\d{0,4})?')
            ]
        }
    )
}

class LanguageDetector:
    """Automatyczna detekcja języka dokumentu"""
    
    @staticmethod
    def detect(text: str) -> str:
        """Wykrywa język na podstawie słów kluczowych"""
        scores = {}
        
        for lang_name, profile in LANGUAGE_PROFILES.items():
            score = 0
            text_upper = text.upper()
            
            # Sprawdź słowa kluczowe
            for keyword_list in profile.keywords.values():
                for keyword in keyword_list:
                    if keyword.upper() in text_upper:
                        score += 1
                        
            # Sprawdź wzorce
            for pattern_list in profile.patterns.values():
                for pattern in pattern_list:
                    if pattern.search(text):
                        score += 2
                        
            scores[lang_name] = score
            
        # Zwróć język z najwyższym wynikiem
        if scores:
            best_lang = max(scores, key=scores.get)
            if scores[best_lang] > 0:
                return best_lang
                
        return 'Polski'  # Domyślnie

def get_language_config(language: str) -> LanguageProfile:
    """Pobiera konfigurację dla danego języka"""
    return LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES['Polski'])