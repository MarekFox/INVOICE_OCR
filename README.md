# 🧾 FAKTURA BOT v5.0 ULTIMATE

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-orange.svg)](https://www.riverbankcomputing.com/software/pyqt/)

## 📋 Opis projektu

**FAKTURA BOT v5.0 ULTIMATE** to kompleksowa aplikacja desktopowa w Pythonie (PyQt6) służąca do optycznego rozpoznawania znaków (OCR) i ekstrakcji danych z faktur.

Aplikacja automatycznie przetwarza pliki PDF zawierające faktury, rozpoznaje tekst za pomocą zaawansowanych silników OCR, a następnie ekstrahuje kluczowe dane biznesowe do formatu Excel.

---

## ✨ Główne funkcje

- 🔍 **Hybrydowy OCR** - Tesseract + PaddleOCR dla maksymalnej dokładności
- 🌍 **Wielojęzyczność** - obsługa faktur polskich, rumuńskich, angielskich i niemieckich
- 📄 **Automatyczna separacja** - rozdzielanie wielu faktur z jednego PDF
- 📊 **Eksport do Excel** - generowanie raportów z wykresami
- ✅ **Walidacja danych** - weryfikacja NIP, kwot, dat
- 🔄 **Wykrywanie duplikatów** - identyfikacja powtórzonych faktur
- 🖥️ **Nowoczesny interfejs** - GUI w PyQt6

---

## 🏗️ Struktura projektu

faktura-bot-v5/
│
├── 📄 main.py # Główna aplikacja i GUI
├── 📄 config.py # Konfiguracja i stałe
├── 📄 utils.py # Funkcje pomocnicze
├── 📄 ocr_engines.py # Silniki OCR (Tesseract, PaddleOCR)
├── 📄 parsers.py # Parsery faktur
├── 📄 invoice_separator.py # Moduł rozdzielania PDF
├── 📄 excel_generator.py # Generator raportów Excel
├── 📄 database.py # Przechowywanie danych
├── 📄 gui_components.py # Komponenty GUI
├── 📄 processing_thread.py # Wątki przetwarzania
├── 📄 validators.py # Walidatory biznesowe
├── 📄 language_config.py # Konfiguracja językowa
└── 📄 requirements.txt # Zależności


---

## 🚀 Instalacja

### Wymagania wstępne

- Python 3.10 lub nowszy
- Tesseract OCR zainstalowany w systemie
- Poppler (do konwersji PDF)

### Kroki instalacji

1. **Sklonuj repozytorium:**
   git clone https://github.com/MarekFox/invoice-ocr.git
   cd invoice-ocr


2. Utwórz środowisko wirtualne:
python -m venv venv
venv\Scripts\activate  # Windows
# lub
source venv/bin/activate  # Linux/Mac

3. Zainstaluj zależności:
pip install -r requirements.txt

4. Utwórz plik konfiguracyjny:
cp secrets_config.example.py secrets_config.py
# Edytuj secrets_config.py i ustaw ścieżki do Tesseract i Poppler


5. Uruchom aplikację:
python main.py

Utwórz plik secrets_config.py z następującą zawartością:
# Ścieżki do zewnętrznych narzędzi
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Program Files\poppler\bin"





