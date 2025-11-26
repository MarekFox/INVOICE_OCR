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

## 🚀 Instalacja i Uruchomienie

Aby uruchomić projekt lokalnie, postępuj zgodnie z poniższymi instrukcjami.

### Wymagania wstępne

1.  Zainstalowany [Python](https://www.python.org/).
2.  Zainstalowany silnik [Tesseract-OCR](https://github.com/tesseract-ocr/tesseract) w systemie (i dodany do zmiennej środowiskowej PATH).

### Krok 1: Klonowanie repozytorium

Pobierz kod źródłowy i przełącz się na branch testowy:

```bash
git clone https://github.com/MarekFox/INVOICE_OCR.git
cd INVOICE_OCR
git checkout TESTING
```

### Krok 2: Konfiguracja środowiska

Zaleca się użycie wirtualnego środowiska:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate   # Windows
```

### Krok 3: Instalacja zależności

Zainstaluj wymagane biblioteki z pliku `requirements.txt`:

```bash
pip install -r requirements.txt

Utwórz plik secrets_config.py z następującą zawartością:
# Ścieżki do zewnętrznych narzędzi
```bash
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Program Files\poppler\bin"

## 💻 Użycie

Aby uruchomić program i przetworzyć przykładową fakturę:

```bash
python main.py --input "sciezka/do/faktury.pdf"
```

Wyniki zostaną wyświetlone w konsoli lub zapisane w folderze `/output`.

## 🧪 Branch: TESTING

Ta gałąź (`TESTING`) służy do rozwoju i testowania eksperymentalnych funkcji. Kod tutaj zawarty może być niestabilny. Główne cele tej gałęzi to:

1.  Testowanie nowych metod binaryzacji obrazu.
2.  Poprawa wyrażeń regularnych (Regex) dla niestandardowych formatów faktur.
3.  Unit testy dla modułów parsujących.

## 🤝 Autor

**MarekFox**
Link do repozytorium: [https://github.com/MarekFox/INVOICE\_OCR](https://www.google.com/url?sa=E&source=gmail&q=https://github.com/MarekFox/INVOICE_OCR)
