"""
FAKTURA BOT v5.0 ULTIMATE - Configuration Module
====
Centralna konfiguracja aplikacji
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import json

# Wersja aplikacji
APP_VERSION = "5.0.0"
APP_NAME = "FAKTURA BOT ULTIMATE"
APP_DESCRIPTION = "Profesjonalny system do masowego przetwarzania faktur"

# Tryb debugowania
DEBUG_MODE = True

# ==== DODANE: Sprawdzenie dostępności PaddleOCR ====
PADDLEOCR_AVAILABLE = False
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    print("✅ PaddleOCR dostępny")
except ImportError:
    print("⚠️ PaddleOCR niedostępny - tylko Tesseract będzie używany")
# ====

# Ścieżki domyślne
DEFAULT_PATHS = {
    'tesseract': r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    'poppler': r'C:\Program Files\poppler-24.02.0\Library\bin',
    'data_dir': Path.home() / '.faktura-bot' / 'data',
    'logs_dir': Path.home() / '.faktura-bot' / 'logs',
    'templates_dir': Path.home() / '.faktura-bot' / 'templates',
    # ==== NOWE: Ścieżki dla szablonów YAML ====
    'yaml_templates_dir': Path(__file__).parent / 'templates',
    'user_templates_dir': Path(__file__).parent / 'templates' / 'custom',
    'templates_backup_dir': Path(__file__).parent / 'templates_backup',
}

# Import lokalnej konfiguracji
try:
    from secrets_config import TESSERACT_CMD, POPPLER_PATH
    DATABASE_URL = None
except ImportError:
    TESSERACT_CMD = DEFAULT_PATHS['tesseract']
    POPPLER_PATH = DEFAULT_PATHS['poppler']
    DATABASE_URL = None
    print("⚠️ Używam domyślnych ścieżek. Utwórz 'secrets_config.py' dla własnych ustawień.")

# Ustawienia OCR
@dataclass
class OCRSettings:
    """Konfiguracja silników OCR"""
    dpi: int = 300
    timeout: int = 60
    use_gpu: bool = False
    paddle_precision: str = 'fp32'  # fp32, fp16, int8
    tesseract_psm: int = 1  # Page segmentation mode
    tesseract_oem: int = 3  # OCR Engine mode

# Ustawienia parsowania
@dataclass
class ParsingSettings:
    """Konfiguracja parserów"""
    fuzzy_matching: bool = True
    min_confidence: float = 0.85
    max_errors: int = 5
    smart_table_detection: bool = True
    auto_rotation: bool = True
    remove_watermarks: bool = False

# Ustawienia walidacji
@dataclass
class ValidationSettings:
    """Konfiguracja walidatorów"""
    validate_nip: bool = True
    validate_iban: bool = True
    validate_dates: bool = True
    validate_amounts: bool = True
    cross_validate: bool = True
    external_api_validation: bool = False  # np. GUS API dla NIP


# ==== NOWE: Ustawienia szablonów YAML ====
@dataclass
class TemplateSettings:
    """Konfiguracja systemu szablonów YAML"""
    # Katalogi
    templates_dir: str = "templates"
    user_templates_dir: str = "templates/custom"
    backup_dir: str = "templates_backup"

    # Zachowanie
    auto_load_templates: bool = True
    default_template_fallback: bool = True
    cache_enabled: bool = True
    cache_size: int = 100

    # Dopasowanie szablonów
    min_match_score: float = 20.0  # Minimalny score do użycia szablonu
    prefer_specific_templates: bool = True  # Preferuj szablony specyficzne nad ogólne

    # Logowanie
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    log_template_matching: bool = False  # Loguj szczegóły dopasowania

    # Edytor GUI
    editor_font_size: int = 10
    editor_theme: str = "default"  # default, dark, light
    syntax_highlighting: bool = True
    auto_save_interval: int = 300  # sekundy (0 = wyłączone)

    # Walidacja szablonów
    validate_on_load: bool = True
    strict_validation: bool = False  # Odrzuć szablony z ostrzeżeniami

    # Backup
    auto_backup: bool = True
    max_backups: int = 10
# ====


# Ustawienia Excel
@dataclass 
class ExcelSettings:
    """Konfiguracja generatora Excel"""
    template_path: Optional[str] = None
    include_charts: bool = True
    include_pivot: bool = True
    color_coding: bool = True
    auto_formulas: bool = True
    protect_sheets: bool = False
    password: Optional[str] = None

# Ustawienia GUI
@dataclass
class GUISettings:
    """Konfiguracja interfejsu"""
    theme: str = 'modern_dark'  # modern_dark, classic, enterprise_blue
    window_width: int = 1600
    window_height: int = 900
    auto_save: bool = True
    confirm_exit: bool = True
    show_tooltips: bool = True
    # ==== NOWE: Ustawienia edytora szablonów ====
    template_editor_width: int = 1400
    template_editor_height: int = 900
    show_template_editor_in_menu: bool = True

# Główna klasa konfiguracji
class AppConfig:
    """Centralna konfiguracja aplikacji"""

    def __init__(self):
        self.ocr = OCRSettings()
        self.parsing = ParsingSettings()
        self.validation = ValidationSettings()
        self.templates = TemplateSettings()  # NOWE
        self.excel = ExcelSettings()
        self.gui = GUISettings()
        self._load_user_config()
        self._ensure_directories()

    def _ensure_directories(self):
        """Tworzy wymagane katalogi jeśli nie istnieją"""
        dirs_to_create = [
            DEFAULT_PATHS['data_dir'],
            DEFAULT_PATHS['logs_dir'],
            DEFAULT_PATHS['yaml_templates_dir'],
            DEFAULT_PATHS['user_templates_dir'],
            DEFAULT_PATHS['templates_backup_dir'],
        ]
        for dir_path in dirs_to_create:
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"⚠️ Nie można utworzyć katalogu {dir_path}: {e}")

    def _load_user_config(self):
        """Ładuje konfigurację użytkownika z pliku JSON"""
        config_file = DEFAULT_PATHS['data_dir'] / 'config.json'
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                self._apply_user_config(user_config)
            except Exception as e:
                print(f"⚠️ Błąd wczytywania konfiguracji użytkownika: {e}")

    def _apply_user_config(self, config: Dict[str, Any]):
        """Aplikuje ustawienia użytkownika"""
        for section, settings in config.items():
            if hasattr(self, section):
                section_obj = getattr(self, section)
                for key, value in settings.items():
                    if hasattr(section_obj, key):
                        setattr(section_obj, key, value)

    def save_user_config(self):
        """Zapisuje bieżącą konfigurację"""
        DEFAULT_PATHS['data_dir'].mkdir(parents=True, exist_ok=True)
        config_file = DEFAULT_PATHS['data_dir'] / 'config.json'

        config = {
            'ocr': self.ocr.__dict__,
            'parsing': self.parsing.__dict__,
            'validation': self.validation.__dict__,
            'templates': self.templates.__dict__,  # NOWE
            'excel': self.excel.__dict__,
            'gui': self.gui.__dict__
        }

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def get_theme_colors(self) -> Dict[str, str]:
        """Zwraca kolory dla wybranego motywu"""
        themes = {
            'modern_dark': {
                'bg': '#1e1e1e',
                'fg': '#ffffff',
                'accent': '#007ACC',
                'success': '#4CAF50',
                'warning': '#FFC107',
                'error': '#F44336'
            },
            'classic': {
                'bg': '#f0f0f0',
                'fg': '#000000',
                'accent': '#0078D7',
                'success': '#107C10',
                'warning': '#F7630C',
                'error': '#D13438'
            },
            'enterprise_blue': {
                'bg': '#002050',
                'fg': '#ffffff',
                'accent': '#0078D4',
                'success': '#107C10',
                'warning': '#FFB900',
                'error': '#D83B01'
            }
        }
        return themes.get(self.gui.theme, themes['modern_dark'])

    # ==== NOWE: Metody pomocnicze dla szablonów ====
    def get_templates_dir(self) -> Path:
        """Zwraca ścieżkę do katalogu szablonów"""
        return Path(self.templates.templates_dir)

    def get_user_templates_dir(self) -> Path:
        """Zwraca ścieżkę do katalogu szablonów użytkownika"""
        return Path(self.templates.user_templates_dir)

    def get_template_backup_dir(self) -> Path:
        """Zwraca ścieżkę do katalogu backupów szablonów"""
        return Path(self.templates.backup_dir)

    def is_template_caching_enabled(self) -> bool:
        """Sprawdza czy cache szablonów jest włączony"""
        return self.templates.cache_enabled

    def get_template_log_level(self) -> str:
        """Zwraca poziom logowania dla szablonów"""
        return self.templates.log_level
    # ====

# Singleton konfiguracji
CONFIG = AppConfig()

# Eksportowane stałe
SUPPORTED_LANGUAGES = ['Polski', 'Niemiecki', 'Rumuński', 'Angielski', 'Austriacki']
SUPPORTED_FORMATS = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff']
MAX_FILE_SIZE_MB = 100
BATCH_PROCESSING_LIMIT = 100

# ==== NOWE: Stałe dla systemu szablonów ====
TEMPLATE_FILE_EXTENSIONS = ['.yml', '.yaml']
DEFAULT_TEMPLATE_PRIORITY = 50
MAX_TEMPLATE_PRIORITY = 100
MIN_TEMPLATE_PRIORITY = 1

# Mapowanie języków na kody ISO
LANGUAGE_CODES = {
    'Polski': 'pl',
    'Niemiecki': 'de', 
    'Rumuński': 'ro',
    'Angielski': 'en'
}

# Domyślne stawki VAT dla krajów
DEFAULT_VAT_RATES = {
    'pl': [0, 5, 8, 23],
    'de': [0, 7, 19],
    'ro': [0, 5, 9, 19],
    'en': [0, 5, 20]  # UK
}

# Waluty dla krajów
COUNTRY_CURRENCIES = {
    'pl': 'PLN',
    'de': 'EUR',
    'ro': 'RON',
    'en': 'GBP'
}
# ====


# ==== NOWE: Funkcje pomocnicze ====
def get_templates_path() -> Path:
    """Zwraca absolutną ścieżkę do katalogu szablonów"""
    templates_dir = CONFIG.get_templates_dir()
    if templates_dir.is_absolute():
        return templates_dir
    return Path(__file__).parent / templates_dir


def get_default_vat_rates(language: str) -> list:
    """Zwraca domyślne stawki VAT dla języka/kraju"""
    code = LANGUAGE_CODES.get(language, 'pl')
    return DEFAULT_VAT_RATES.get(code, [0, 23])


def get_currency_for_language(language: str) -> str:
    """Zwraca domyślną walutę dla języka/kraju"""
    code = LANGUAGE_CODES.get(language, 'pl')
    return COUNTRY_CURRENCIES.get(code, 'PLN')


def setup_template_logging():
    """Konfiguruje logowanie dla systemu szablonów"""
    import logging

    log_level = getattr(logging, CONFIG.templates.log_level.upper(), logging.INFO)

    # Logger dla szablonów
    template_logger = logging.getLogger('template_engine')
    template_logger.setLevel(log_level)

    # Handler do konsoli
    if not template_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        handler.setFormatter(formatter)
        template_logger.addHandler(handler)

    return template_logger
# ====


# Inicjalizacja logowania przy imporcie
if CONFIG.templates.auto_load_templates:
    try:
        setup_template_logging()
    except Exception as e:
        print(f"⚠️ Błąd inicjalizacji logowania szablonów: {e}")
