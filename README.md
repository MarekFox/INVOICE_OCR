# 📄 FAKTURA BOT v5.0 ULTIMATE

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![OCR Engine](https://img.shields.io/badge/OCR-Tesseract%20%2B%20PaddleOCR-orange)

> Zaawansowany system automatycznej ekstrakcji danych z faktur oparty na technologii OCR z wielojęzycznym interfejsem użytkownika.

## 📋 Spis treści

- [Opis projektu](#-opis-projektu)
- [Kluczowe funkcjonalności](#-kluczowe-funkcjonalności)
- [Architektura systemu](#-architektura-systemu)
- [Wymagania systemowe](#-wymagania-systemowe)
- [Instalacja](#-instalacja)
- [Konfiguracja](#-konfiguracja)
- [Użycie](#-użycie)
- [Struktura projektu](#-struktura-projektu)
- [Technologie](#-technologie)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [Licencja](#-licencja)
- [Kontakt](#-kontakt)

## 🎯 Opis projektu

**FAKTURA BOT v5.0 ULTIMATE** to kompleksowa aplikacja desktopowa zaprojektowana do automatyzacji procesu przetwarzania faktur biznesowych. System wykorzystuje zaawansowane techniki optycznego rozpoznawania znaków (OCR) w połączeniu z algorytmami przetwarzania języka naturalnego, aby ekstrahować kluczowe dane z dokumentów fakturowych w różnych formatach i językach.

Aplikacja została stworzona z myślą o firmach i działach księgowych, które potrzebują efektywnego narzędzia do digitalizacji i zarządzania dużą ilością faktur papierowych i elektronicznych.

### 🎯 Dla kogo?

- 📊 Działy księgowe i finansowe
- 🏢 Małe i średnie przedsiębiorstwa
- 💼 Biura rachunkowe
- 🔄 Firmy zajmujące się digitalizacją dokumentów

## ✨ Kluczowe funkcjonalności

### 🔍 Hybrydowe rozpoznawanie OCR
- **Podwójny silnik OCR**: Połączenie Tesseract i PaddleOCR dla maksymalnej dokładności
- **Adaptacyjne przetwarzanie**: Automatyczny wybór optymalnego silnika OCR na podstawie jakości dokumentu
- **Preprocessing obrazu**: Zaawansowane algorytmy wstępnej obróbki dla lepszych wyników OCR

### 🌍 Obsługa wielojęzyczna
Pełna obsługa faktur w językach:
- 🇵🇱 Polski
- 🇷🇴 Rumuński
- 🇬🇧 Angielski
- 🇩🇪 Niemiecki

### 📄 Inteligentna separacja dokumentów
- Automatyczne wykrywanie i rozdzielanie wielu faktur z jednego pliku PDF
- Identyfikacja granic dokumentów
- Zachowanie jakości i metadanych oryginalnych plików

### 📊 Generowanie raportów Excel
- Eksport danych do profesjonalnie sformatowanych arkuszy Excel
- Wbudowane wykresy i dashboardy analityczne
- Możliwość dostosowania formatów eksportu

### ✅ Zaawansowana walidacja danych
- **Weryfikacja NIP**: Sprawdzanie poprawności numerów identyfikacji podatkowej
- **Kontrola sum**: Walidacja kwot i obliczeń matematycznych
- **Weryfikacja dat**: Kontrola formatów i logiczności dat
- **Kontrola IBAN**: Walidacja numerów kont bankowych

### 🔄 Detekcja duplikatów
- Inteligentny system wykrywania powtarzających się faktur
- Porównywanie metadanych i treści dokumentów
- Zapobieganie podwójnemu księgowaniu

### 🖥️ Nowoczesny interfejs graficzny
- Intuicyjny GUI oparty na PyQt6
- Responsywny design
- Podgląd przetwarzanych dokumentów w czasie rzeczywistym
- Wielowątkowe przetwarzanie z paskiem postępu

## 🏗️ Architektura systemu

```
┌─────────────────────────────────────────────────────────────┐
│                    FAKTURA BOT v5.0                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐   ┌──────────────┐  │
│  │   GUI Layer  │───▶│ Processing   │──▶│  Export      │  │
│  │   (PyQt6)    │    │   Engine     │   │  (Excel)     │  │
│  └──────────────┘    └──────────────┘   └──────────────┘  │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────┐    ┌──────────────┐   ┌──────────────┐  │
│  │  Document    │    │  OCR Engines │   │  Validators  │  │
│  │  Separator   │    │  Tesseract + │   │  & Database  │  │
│  │             │    │  PaddleOCR   │   │              │  │
│  └──────────────┘    └──────────────┘   └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 💻 Wymagania systemowe

### Minimalne wymagania sprzętowe
- **Procesor**: Intel Core i3 lub równoważny (2.0 GHz+)
- **RAM**: 4 GB
- **Dysk**: 500 MB wolnego miejsca
- **System operacyjny**: Windows 10/11, Linux (Ubuntu 20.04+), macOS 10.15+

### Zalecane wymagania sprzętowe
- **Procesor**: Intel Core i5/i7 lub równoważny (3.0 GHz+)
- **RAM**: 8 GB lub więcej
- **Dysk**: 2 GB wolnego miejsca (SSD zalecany)

### Wymagane oprogramowanie
- **Python**: 3.8 lub nowszy
- **Tesseract OCR**: 4.0 lub nowszy
- **Poppler**: Do konwersji PDF (tylko Windows)

## 🚀 Instalacja

### Krok 1: Sklonuj repozytorium

```bash
git clone https://github.com/MarekFox/INVOICE_OCR.git
cd INVOICE_OCR
```

### Krok 2: Utwórz środowisko wirtualne (zalecane)

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Krok 3: Zainstaluj zależności Python

```bash
pip install -r requirements.txt
```

### Krok 4: Zainstaluj Tesseract OCR

**Windows:**
1. Pobierz instalator z [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
2. Uruchom instalator i zapamiętaj ścieżkę instalacji
3. Dodaj Tesseract do zmiennej środowiskowej PATH

**macOS:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install tesseract-ocr
sudo apt install tesseract-ocr-pol  # Polskie pakiety językowe
```

### Krok 5: Zainstaluj Poppler (tylko Windows)

1. Pobierz Poppler z oficjalnej strony
2. Rozpakuj do wybranego katalogu (np. `C:\Program Files\poppler`)
3. Zanotuj ścieżkę do folderu `bin`

## ⚙️ Konfiguracja

### Utwórz plik konfiguracyjny

Stwórz plik `secrets_config.py` w głównym katalogu projektu:

```python
# secrets_config.py

# Ścieżka do silnika Tesseract OCR
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Ścieżka do Poppler (tylko Windows)
POPPLER_PATH = r"C:\Program Files\poppler\bin"

# Opcjonalne ustawienia zaawansowane
OCR_CONFIDENCE_THRESHOLD = 60  # Minimalny próg pewności OCR (0-100)
MAX_PROCESSING_THREADS = 4      # Liczba wątków przetwarzania
AUTO_BACKUP = True              # Automatyczne tworzenie kopii zapasowych
```

### Dostosowanie ustawień językowych

W pliku `language_config.py` możesz dostosować:
- Preferowane języki OCR
- Wzorce wyrażeń regularnych dla różnych języków
- Formaty dat i walut specyficzne dla regionu

## 📖 Użycie

### Uruchomienie aplikacji z GUI

```bash
python main.py
```

### Tryb wsadowy (batch processing)

Przetwarzanie pojedynczego pliku:
```bash
python main.py --input "faktury/faktura_001.pdf"
```

Przetwarzanie całego folderu:
```bash
python main.py --input-dir "faktury/" --output-dir "wyniki/"
```

### Zaawansowane opcje wiersza poleceń

```bash
python main.py \
  --input "faktury/faktura.pdf" \
  --output "wyniki/" \
  --language "pol+eng" \
  --ocr-engine "hybrid" \
  --export-format "excel" \
  --validate-nip \
  --detect-duplicates
```

#### Dostępne parametry:
- `--input`: Ścieżka do pliku PDF z fakturą
- `--input-dir`: Katalog z wieloma fakturami
- `--output`: Katalog wyjściowy dla wyników
- `--language`: Języki OCR (pol, eng, ger, ron)
- `--ocr-engine`: Silnik OCR (tesseract, paddle, hybrid)
- `--export-format`: Format eksportu (excel, csv, json)
- `--validate-nip`: Włącz walidację numerów NIP
- `--detect-duplicates`: Wykrywaj duplikaty faktur
- `--no-gui`: Uruchom bez interfejsu graficznego

### Przykłady użycia

**Przykład 1: Podstawowe przetwarzanie**
```bash
python main.py --input "faktura_vat.pdf"
```

**Przykład 2: Przetwarzanie z walidacją**
```bash
python main.py --input "faktura_vat.pdf" --validate-nip --detect-duplicates
```

**Przykład 3: Przetwarzanie wsadowe z eksportem do CSV**
```bash
python main.py --input-dir "faktury_2024/" --export-format "csv"
```

## 📁 Struktura projektu

```
faktura-bot-v5/
│
├── 📄 main.py                    # Punkt wejścia aplikacji, główna logika GUI
├── 📄 config.py                  # Plik konfiguracyjny z ustawieniami globalnymi
├── 📄 secrets_config.py          # Konfiguracja wrażliwa (nie w repo)
├── 📄 requirements.txt           # Zależności Python
│
├── 📂 core/                      # Moduły główne
│   ├── 📄 ocr_engines.py         # Implementacje silników OCR
│   ├── 📄 parsers.py             # Parsery faktur dla różnych języków
│   ├── 📄 invoice_separator.py  # Logika separacji wielostronicowych PDF
│   ├── 📄 validators.py          # Walidatory danych (NIP, IBAN, kwoty)
│   └── 📄 database.py            # Warstwa dostępu do danych
│
├── 📂 gui/                       # Komponenty interfejsu
│   ├── 📄 gui_components.py      # Widgety i komponenty Qt
│   ├── 📄 processing_thread.py   # Wątki dla operacji w tle
│   └── 📄 styles.qss             # Style CSS dla GUI
│
├── 📂 export/                    # Moduły eksportu
│   ├── 📄 excel_generator.py     # Generator raportów Excel
│   ├── 📄 csv_exporter.py        # Eksport do CSV
│   └── 📄 json_exporter.py       # Eksport do JSON
│
├── 📂 utils/                     # Narzędzia pomocnicze
│   ├── 📄 utils.py               # Funkcje uniwersalne
│   ├── 📄 image_processing.py    # Preprocessing obrazów
│   └── 📄 language_config.py     # Konfiguracja językowa
│
├── 📂 tests/                     # Testy jednostkowe
│   ├── 📄 test_ocr.py
│   ├── 📄 test_parsers.py
│   └── 📄 test_validators.py
│
├── 📂 docs/                      # Dokumentacja
│   ├── 📄 API.md                 # Dokumentacja API
│   ├── 📄 USER_GUIDE.md          # Przewodnik użytkownika
│   └── 📄 DEVELOPER_GUIDE.md     # Przewodnik dla deweloperów
│
├── 📂 data/                      # Dane i zasoby
│   ├── 📂 samples/               # Przykładowe faktury testowe
│   ├── 📂 templates/             # Szablony raportów
│   └── 📂 models/                # Modele ML (jeśli używane)
│
└── 📄 README.md                  # Ten plik
```

## 🔧 Technologie

### Języki programowania
- **Python 3.8+**: Główny język implementacji

### Biblioteki główne
- **PyQt6**: Biblioteka GUI dla interfejsu użytkownika
- **Tesseract OCR**: Silnik rozpoznawania tekstu open-source
- **PaddleOCR**: Zaawansowany silnik OCR oparty na deep learning
- **pdf2image**: Konwersja PDF do obrazów
- **Pillow (PIL)**: Przetwarzanie i manipulacja obrazami
- **pytesseract**: Wrapper Pythona dla Tesseract
- **openpyxl**: Praca z plikami Excel
- **pandas**: Analiza i manipulacja danych
- **numpy**: Operacje numeryczne i macierzowe

### Biblioteki pomocnicze
- **opencv-python**: Zaawansowane przetwarzanie obrazów
- **python-dateutil**: Parsowanie i formatowanie dat
- **regex**: Wyrażenia regularne dla ekstrakcji danych
- **hashlib**: Generowanie sum kontrolnych dla duplikatów

### Narzędzia deweloperskie
- **pytest**: Framework testowy
- **black**: Formatowanie kodu
- **flake8**: Linter dla Pythona
- **mypy**: Sprawdzanie typów statycznych

## 🗺️ Roadmap

### ✅ Ukończone
- [x] Podstawowy silnik OCR z Tesseract
- [x] Interfejs GUI w PyQt6
- [x] Obsługa wielojęzyczna
- [x] Eksport do Excel
- [x] Walidacja NIP
- [x] Wykrywanie duplikatów

### 🚧 W trakcie implementacji
- [ ] Integracja z PaddleOCR dla lepszej dokładności
- [ ] API REST dla integracji z innymi systemami
- [ ] Wsparcie dla faktur elektronicznych (e-faktur)

### 🔮 Planowane funkcjonalności
- [ ] Machine Learning dla klasyfikacji typów faktur
- [ ] Automatyczna kategoryzacja wydatków
- [ ] Integracja z systemami księgowymi (SAP, Symfonia)
- [ ] Aplikacja webowa
- [ ] Aplikacja mobilna (Android/iOS)
- [ ] Rozpoznawanie tabel i pozycji faktur
- [ ] OCR dla odręcznych notatek
- [ ] Wersja SaaS z panelem administracyjnym
- [ ] Obsługa faktur z kodami QR/kodami kreskowymi
- [ ] Automatyczne wysyłanie raportów e-mail

## 🤝 Contributing

Wkład w rozwój projektu jest mile widziany! Jeśli chcesz przyczynić się do rozwoju FAKTURA BOT:

### Jak zgłosić błąd?

1. Sprawdź, czy błąd nie został już zgłoszony w [Issues](https://github.com/MarekFox/INVOICE_OCR/issues)
2. Utwórz nowy Issue z szczegółowym opisem:
   - Kroki do reprodukcji
   - Oczekiwane zachowanie
   - Rzeczywiste zachowanie
   - Wersja systemu i Pythona
   - Logi błędów (jeśli dostępne)

### Jak zaproponować nową funkcjonalność?

1. Otwórz Issue z tagiem "enhancement"
2. Opisz szczegółowo proponowaną funkcjonalność
3. Wyjaśnij, dlaczego byłaby przydatna
4. Dołącz przykłady użycia (opcjonalnie)

### Proces zgłaszania zmian (Pull Request)

1. **Fork** repozytorium
2. Utwórz nowy branch dla swojej funkcjonalności:
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. Wprowadź zmiany i commituj z opisowymi wiadomościami:
   ```bash
   git commit -m "Add: Implementacja nowej funkcji X"
   ```
4. Push do swojego forka:
   ```bash
   git push origin feature/AmazingFeature
   ```
5. Otwórz Pull Request z opisem zmian

### Wytyczne dla kontrybutorów

- Kod powinien być zgodny ze standardem PEP 8
- Dodaj testy jednostkowe dla nowych funkcjonalności
- Aktualizuj dokumentację dla wprowadzonych zmian
- Używaj znaczących nazw zmiennych i funkcji
- Komentuj skomplikowany kod
- Testuj zmiany przed zgłoszeniem PR

## 📜 Licencja

Ten projekt jest dostępny na licencji **MIT License**.

```
MIT License

Copyright (c) 2024 MarekFox

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Zobacz [LICENSE](LICENSE) dla pełnej treści licencji.

## 📞 Kontakt

**Autor**: MarekFox

- 🐙 GitHub: [@MarekFox](https://github.com/MarekFox)
- 📧 Email: [Skontaktuj się przez GitHub](https://github.com/MarekFox)
- 🔗 Repozytorium: [https://github.com/MarekFox/INVOICE_OCR](https://github.com/MarekFox/INVOICE_OCR)

### Wsparcie

Jeśli masz pytania lub potrzebujesz pomocy:

1. Przeczytaj [dokumentację](docs/)
2. Sprawdź [FAQ](docs/FAQ.md)
3. Wyszukaj w [Issues](https://github.com/MarekFox/INVOICE_OCR/issues)
4. Zadaj pytanie tworząc nowy Issue

---

## 🙏 Podziękowania

Dziękujemy wszystkim kontrybutorsom, którzy przyczynili się do rozwoju tego projektu!

Projekt wykorzystuje następujące technologie open-source:
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- [pdf2image](https://github.com/Belval/pdf2image)

---

<div align="center">

**⭐ Jeśli ten projekt Ci pomógł, zostaw gwiazdkę! ⭐**

Made with ❤️ by [MarekFox](https://github.com/MarekFox)

[⬆ Powrót na górę](#-faktura-bot-v50-ultimate)

</div>