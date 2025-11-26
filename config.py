"""
FAKTURA BOT v5.0 ULTIMATE - Configuration Module
=================================================
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

# ===================== DODANE: Sprawdzenie dostępności PaddleOCR =====================
PADDLEOCR_AVAILABLE = False
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    print("✅ PaddleOCR dostępny")
except ImportError:
    print("⚠️ PaddleOCR niedostępny - tylko Tesseract będzie używany")
# ====================================================================================

# Ścieżki domyślne
DEFAULT_PATHS = {
    'tesseract': r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    'poppler': r'C:\Program Files\poppler-24.02.0\Library\bin',
    'data_dir': Path.home() / '.faktura-bot' / 'data',
    'logs_dir': Path.home() / '.faktura-bot' / 'logs',
    'templates_dir': Path.home() / '.faktura-bot' / 'templates'
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
    
# Główna klasa konfiguracji
class AppConfig:
    """Centralna konfiguracja aplikacji"""
    
    def __init__(self):
        self.ocr = OCRSettings()
        self.parsing = ParsingSettings()
        self.validation = ValidationSettings()
        self.excel = ExcelSettings()
        self.gui = GUISettings()
        self._load_user_config()
        
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

# Singleton konfiguracji
CONFIG = AppConfig()

# Eksportowane stałe
SUPPORTED_LANGUAGES = ['Polski', 'Niemiecki', 'Rumuński', 'Angielski']
SUPPORTED_FORMATS = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff']
MAX_FILE_SIZE_MB = 100
BATCH_PROCESSING_LIMIT = 100