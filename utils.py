"""
FAKTURA BOT v5.0 - Utility Functions
=====================================
Funkcje pomocnicze, walidatory, formattery
"""

import re
import hashlib
import requests
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

class TextUtils:
    """Narzędzia do przetwarzania tekstu"""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Czyści tekst z artefaktów OCR"""
        # Usuń wielokrotne spacje
        text = re.sub(r'\s+', ' ', text)
        # Usuń dziwne znaki
        text = re.sub(r'[←→↑↓■□▪▫◆◇○●]', '', text)
        # Popraw częste błędy OCR
        replacements = {
            'l': '1', 'O': '0', 'S': '5', 'Z': '2',  # Tylko w kontekście liczb
            '|': 'I', '!': '1', '@': 'a', '#': 'H'
        }
        # Inteligentna zamiana tylko w liczbach
        for old, new in replacements.items():
            text = re.sub(rf'(?<=\d){re.escape(old)}(?=\d)', new, text)
        return text.strip()
    
    @staticmethod
    def extract_numbers(text: str) -> List[float]:
        """Wydobywa wszystkie liczby z tekstu"""
        # Ignoruj daty
        text_no_dates = re.sub(r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}', '', text)
        
        numbers = []
        # Pattern dla różnych formatów liczb
        patterns = [
            r'(\d{1,3}(?:\s\d{3})*(?:,\d{2})?)',  # 1 234,56
            r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',  # 1.234,56
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # 1,234.56
            r'(\d+(?:[.,]\d+)?)'                    # Proste liczby
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_no_dates)
            for match in matches:
                try:
                    # Normalizacja do formatu z kropką
                    clean = match.replace(' ', '')
                    # Heurystyka: ostatni separator to dziesiętny
                    if ',' in clean and '.' in clean:
                        if clean.rfind(',') > clean.rfind('.'):
                            clean = clean.replace('.', '').replace(',', '.')
                        else:
                            clean = clean.replace(',', '')
                    elif ',' in clean:
                        # Sprawdź czy to separator tysięcy czy dziesiętny
                        parts = clean.split(',')
                        if len(parts) == 2 and len(parts[1]) == 2:
                            clean = clean.replace(',', '.')
                        else:
                            clean = clean.replace(',', '')
                    
                    num = float(clean)
                    if num > 0 and num < 10000000:  # Rozsądny zakres
                        numbers.append(num)
                except:
                    continue
                    
        return list(set(numbers))  # Usuń duplikaty

class MoneyUtils:
    """Operacje na kwotach pieniężnych"""
    
    @staticmethod
    def parse_amount(text: str, language: str = 'Polski') -> Optional[Decimal]:
        """Parsuje kwotę z uwzględnieniem języka"""
        from language_config import get_language_config
        
        config = get_language_config(language)
        
        # Usuń symbol waluty
        text = re.sub(r'[A-Z]{3}|zł|PLN|€|EUR|\$|USD|lei|RON', '', text, flags=re.I)
        
        # Znajdź liczbę
        pattern = r'(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)'
        match = re.search(pattern, text)
        
        if not match:
            return None
            
        num_str = match.group(1)
        
        # Normalizacja zgodnie z językiem
        if config.thousand_separator == ' ':
            num_str = num_str.replace(' ', '')
        elif config.thousand_separator == '.':
            num_str = num_str.replace('.', '')
        elif config.thousand_separator == ',':
            # Tylko jeśli nie jest to separator dziesiętny
            if num_str.count(',') > 1:
                num_str = num_str.replace(',', '')
                
        # Zamień separator dziesiętny na kropkę
        if config.decimal_separator == ',':
            num_str = num_str.replace(',', '.')
            
        try:
            return Decimal(num_str)
        except:
            return None
    
    @staticmethod
    def calculate_vat(net: Decimal, vat_rate: Decimal) -> Dict[str, Decimal]:
        """Oblicza kwoty VAT"""
        vat_amount = (net * vat_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        gross = net + vat_amount
        
        return {
            'net': net,
            'vat': vat_amount,
            'gross': gross,
            'rate': vat_rate
        }
    
    @staticmethod
    def format_amount(amount: Decimal, language: str = 'Polski') -> str:
        """Formatuje kwotę zgodnie z językiem"""
        from language_config import get_language_config
        
        config = get_language_config(language)
        
        # Formatuj z dwoma miejscami po przecinku
        formatted = f"{amount:.2f}"
        
        # Podziel na części
        parts = formatted.split('.')
        integer_part = parts[0]
        decimal_part = parts[1] if len(parts) > 1 else '00'
        
        # Dodaj separatory tysięcy
        if len(integer_part) > 3:
            integer_formatted = ''
            for i, digit in enumerate(reversed(integer_part)):
                if i > 0 and i % 3 == 0:
                    integer_formatted = config.thousand_separator + integer_formatted
                integer_formatted = digit + integer_formatted
            integer_part = integer_formatted
            
        # Złóż z powrotem
        return f"{integer_part}{config.decimal_separator}{decimal_part} {config.currency_symbol}"

class DateUtils:
    """Operacje na datach"""

    @staticmethod
    def format_date_output(date: datetime) -> str:
        """
        ZAWSZE zwraca datę w formacie dd.mm.rrrr
        
        Args:
            date: Obiekt datetime
            
        Returns:
            String w formacie dd.mm.rrrr (np. "18.11.2025")
        """
        if date is None:
            return "Brak daty"
        
        try:
            return date.strftime('%d.%m.%Y')
        except:
            return "Nieprawidłowa data"
    
    @staticmethod
    def parse_date(text: str, language: str = 'Polski') -> Optional[datetime]:
        """Parsuje datę z uwzględnieniem formatu językowego"""
        from language_config import get_language_config
        
        config = get_language_config(language)
        
        # Znajdź potencjalne daty - rozszerzona lista formatów
        date_patterns = [
            (r'(\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{4})', ['%d.%m.%Y', '%d-%m-%Y', '%d/%m/%Y']),
            (r'(\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2})', ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d']),
            (r'(\d{1,2}\s+\d{1,2}\s+\d{4})', ['%d %m %Y']),
        ]
        
        for pattern, formats in date_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Normalizuj separator
                normalized = match.replace('/', '-').replace('.', '-').replace(' ', '-')
                
                for date_format in formats:
                    try:
                        # Normalizuj format
                        norm_format = date_format.replace('/', '-').replace('.', '-').replace(' ', '-')
                        dt = datetime.strptime(normalized, norm_format)
                        
                        # Waliduj rozsądny zakres
                        if datetime(1990, 1, 1) <= dt <= datetime.now() + timedelta(days=365):
                            return dt
                    except:
                        continue
                        
        return None
    
    @staticmethod
    def calculate_due_date(issue_date: datetime, payment_days: int) -> datetime:
        """Oblicza termin płatności"""
        return issue_date + timedelta(days=payment_days)
    
    @staticmethod
    def format_date(date: datetime, language: str = 'Polski') -> str:
        """Formatuje datę zgodnie z językiem"""
        from language_config import get_language_config
        
        config = get_language_config(language)
        
        # Użyj pierwszego formatu z listy
        if config.date_formats:
            return date.strftime(config.date_formats[0])
        return date.strftime('%Y-%m-%d')

class ValidationUtils:
    """Walidatory danych"""
    
    @staticmethod
    def validate_nip_pl(nip: str) -> bool:
        """Walidacja polskiego NIP"""
        clean = re.sub(r'\D', '', nip)
        
        if len(clean) != 10:
            return False
            
        weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
        
        try:
            checksum = sum(int(clean[i]) * weights[i] for i in range(9)) % 11
            return checksum == int(clean[9])
        except:
            return False
    
    @staticmethod
    def validate_cui_ro(cui: str) -> bool:
        """Walidacja rumuńskiego CUI"""
        clean = re.sub(r'\D', '', cui)
        
        if not (2 <= len(clean) <= 10):
            return False
            
        # Dla CUI używamy algorytmu modulo 11
        if len(clean) >= 2:
            test_key = '753217532'
            
            if len(clean) <= len(test_key):
                control_sum = 0
                for i in range(len(clean) - 1):
                    control_sum += int(clean[i]) * int(test_key[i])
                    
                control_digit = control_sum * 10 % 11
                if control_digit == 10:
                    control_digit = 0
                    
                return control_digit == int(clean[-1])
                
        return True  # Uproszczona walidacja dla krótkich CUI
    
    @staticmethod
    def validate_iban(iban: str) -> bool:
        """Walidacja IBAN"""
        # Usuń spacje i znormalizuj
        iban = re.sub(r'\s', '', iban.upper())
        
        # Sprawdź format
        if not re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]+$', iban):
            return False
            
        # Sprawdź długość dla kraju
        country_lengths = {
            'PL': 28, 'DE': 22, 'RO': 24, 'GB': 22,
            'FR': 27, 'ES': 24, 'IT': 27, 'NL': 18
        }
        
        country = iban[:2]
        if country in country_lengths:
            if len(iban) != country_lengths[country]:
                return False
                
        # Algorytm mod 97
        rearranged = iban[4:] + iban[:4]
        numeric = ''
        
        for char in rearranged:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - 55)
                
        try:
            return int(numeric) % 97 == 1
        except:
            return False
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Walidacja adresu email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str, country: str = 'PL') -> bool:
        """Walidacja numeru telefonu"""
        clean = re.sub(r'\D', '', phone)
        
        # Długości dla różnych krajów
        lengths = {
            'PL': [9, 11],  # 9 cyfr lub z kierunkowym
            'DE': [10, 11, 12],
            'RO': [10],
            'GB': [10, 11],
            'US': [10]
        }
        
        expected = lengths.get(country, [9, 10, 11, 12])
        return len(clean) in expected

class BankAccountUtils:
    """Narzędzia do pracy z rachunkami bankowymi"""
    
    @staticmethod
    def format_iban(account: str) -> str:
        """Formatuje numer konta do formatu IBAN"""
        # Usuń wszystkie spacje i znaki
        clean = re.sub(r'[^A-Z0-9]', '', account.upper())
        
        # Jeśli to polski NRB bez PL, dodaj
        if len(clean) == 26 and clean.isdigit():
            clean = 'PL' + clean
            
        # Podziel na grupy po 4 znaki
        if len(clean) >= 15:  # Minimalny rozsądny IBAN
            groups = []
            for i in range(0, len(clean), 4):
                groups.append(clean[i:i+4])
            return ' '.join(groups)
            
        return account
    
    @staticmethod
    def extract_bank_accounts(text: str) -> List[str]:
        """Wydobywa numery kont z tekstu"""
        accounts = []
        
        # Różne formaty IBAN
        patterns = [
            r'[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,8}',  # IBAN z spacjami
            r'[A-Z]{2}\d{26}',  # IBAN ciągły
            r'\d{26}',  # Polski NRB
            r'\d{2}(?:\s?\d{4}){6}'  # NRB ze spacjami
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                formatted = BankAccountUtils.format_iban(match)
                if ValidationUtils.validate_iban(formatted.replace(' ', '')):
                    if formatted not in accounts:
                        accounts.append(formatted)
                        
        return accounts
    
    @staticmethod
    def get_bank_from_iban(iban: str) -> str:
        """Rozpoznaje bank po numerze konta"""
        # Słownik rozpoznawania banków (pierwsze 8 cyfr po PL)
        polish_banks = {
            '10901014': 'Santander Bank Polska',
            '10901304': 'Santander Consumer Bank',
            '10201026': 'PKO BP',
            '11401010': 'mBank',
            '10501012': 'ING Bank Śląski',
            '24901044': 'Alior Bank',
            '10301016': 'Citi Handlowy',
            '10901694': 'BNP Paribas',
            '11602202': 'Bank Millennium',
            '10601076': 'BPS',
            '14701012': 'Eurobank',
            '10801014': 'Bank Pekao SA'
        }
        
        clean = re.sub(r'[^0-9]', '', iban)
        if len(clean) >= 8:
            bank_code = clean[2:10] if clean.startswith('PL') else clean[:8]
            return polish_banks.get(bank_code, 'Nieznany bank')
        return 'Nieznany bank'

class CompanyDataAPI:
    """API do weryfikacji danych firm"""
    
    @staticmethod
    def verify_nip_gus(nip: str) -> Optional[Dict[str, Any]]:
        """Weryfikacja NIP w bazie GUS (wymaga klucza API)"""
        # To jest przykład - wymaga prawdziwego API GUS
        try:
            # Tutaj normalnie byłoby wywołanie API
            # response = requests.get(f"https://api.gus.gov.pl/nip/{nip}")
            # return response.json()
            
            # Mockowane dane dla przykładu
            if ValidationUtils.validate_nip_pl(nip):
                return {
                    'valid': True,
                    'company_name': 'Przykładowa Firma Sp. z o.o.',
                    'address': 'ul. Przykładowa 1, 00-001 Warszawa'
                }
        except Exception as e:
            logger.error(f"Błąd weryfikacji NIP: {e}")
            
        return None
    
    @staticmethod
    def verify_cui_anaf(cui: str) -> Optional[Dict[str, Any]]:
        """Weryfikacja CUI w bazie ANAF (Rumunia)"""
        # API ANAF jest publiczne
        try:
            url = f"https://webservicesp.anaf.ro/PlatitorTvaRest/api/v6/ws/tva"
            data = [{"cui": int(re.sub(r'\D', '', cui)), "data": datetime.now().strftime("%Y-%m-%d")}]
            
            response = requests.post(url, json=data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get('found') and len(result.get('found', [])) > 0:
                    company = result['found'][0]
                    return {
                        'valid': True,
                        'company_name': company.get('denumire', ''),
                        'address': company.get('adresa', '')
                    }
        except Exception as e:
            logger.error(f"Błąd weryfikacji CUI: {e}")
            
        return None

class FileUtils:
    """Narzędzia do pracy z plikami"""
    
    @staticmethod
    def get_file_hash(filepath: str) -> str:
        """Oblicza hash SHA256 pliku"""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Czyści nazwę pliku z niedozwolonych znaków"""
        # Usuń niedozwolone znaki
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
            
        # Ogranicz długość
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) == 2:
            name, ext = name_parts
            if len(name) > 200:
                name = name[:200]
            filename = f"{name}.{ext}"
        elif len(filename) > 200:
            filename = filename[:200]
            
        return filename
    
    @staticmethod
    def create_backup(filepath: str) -> str:
        """Tworzy kopię zapasową pliku"""
        import shutil
        from pathlib import Path
        
        backup_dir = Path(filepath).parent / 'backup'
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{Path(filepath).stem}_{timestamp}{Path(filepath).suffix}"
        backup_path = backup_dir / backup_name
        
        shutil.copy2(filepath, backup_path)
        return str(backup_path)