# 🧾 FAKTURA BOT v5.0 ULTIMATE

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-orange.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![OCR](https://img.shields.io/badge/OCR-Tesseract%20%2B%20PaddleOCR-red.svg)](https://github.com/tesseract-ocr/tesseract)

> Zaawansowany system automatycznej ekstrakcji danych z faktur oparty na technologii OCR z elastycznym systemem szablonów YAML.

---

## 📋 Spis treści

- [Opis projektu](#-opis-projektu)
- [Kluczowe funkcjonalności](#-kluczowe-funkcjonalności)
- [Architektura systemu](#-architektura-systemu)
- [Wymagania systemowe](#-wymagania-systemowe)
- [Instalacja](#-instalacja)
- [Konfiguracja](#-konfiguracja)
- [Użycie](#-użycie)
- [System szablonów YAML](#-system-szablonów-yaml)
- [Struktura projektu](#-struktura-projektu)
- [Technologie](#-technologie)
- [Branch TESTING2](#-branch-testing2)
- [Contributing](#-contributing)
- [Licencja](#-licencja)
- [Kontakt](#-kontakt)

---

## 🎯 Opis projektu

**FAKTURA BOT v5.0 ULTIMATE** to kompleksowa aplikacja desktopowa zaprojektowana do automatyzacji procesu przetwarzania faktur biznesowych. System wykorzystuje zaawansowane techniki optycznego rozpoznawania znaków (OCR) w połączeniu z **elastycznym systemem szablonów YAML** (wzorowanym na invoice2data), aby ekstrahować kluczowe dane z dokumentów fakturowych w różnych formatach i językach.

### 🎯 Dla kogo?

- 📊 Działy księgowe i finansowe
- 🏢 Małe i średnie przedsiębiorstwa
- 💼 Biura rachunkowe
- 🔄 Firmy zajmujące się digitalizacją dokumentów

---

## ✨ Kluczowe funkcjonalności

### 🔍 Hybrydowe rozpoznawanie OCR
- **Podwójny silnik OCR**: Tesseract + PaddleOCR dla maksymalnej dokładności
- **Adaptacyjne przetwarzanie**: Wybór silnika OCR w GUI
- **Preprocessing obrazu**: Automatyczna konwersja PDF do obrazów

### 🌍 Obsługa wielojęzyczna
Pełna obsługa faktur w językach:
- 🇵🇱 Polski
- 🇷🇴 Rumuński
- 🇬🇧 Angielski
- 🇩🇪 Niemiecki

### 📝 System szablonów YAML (NOWOŚĆ w TESTING2)
- **Elastyczne parsowanie**: Definiowanie reguł ekstrakcji w plikach YAML
- **Szablony per dostawca**: Dedykowane szablony dla konkretnych firm (np. Orange Polska)
- **Szablony generyczne**: Uniwersalne szablony dla każdego języka
- **Edytor GUI**: Wbudowany edytor szablonów z podglądem na żywo
- **Hot-reload**: Automatyczne przeładowanie szablonów bez restartu

### 📄 Inteligentna separacja dokumentów
- Automatyczne wykrywanie i rozdzielanie wielu faktur z jednego pliku PDF
- Identyfikacja granic dokumentów
- Zachowanie jakości oryginalnych plików

### 📊 Generowanie raportów Excel
- Eksport danych do profesjonalnie sformatowanych arkuszy Excel
- Wbudowane wykresy i podsumowania
- Eksport do JSON

### ✅ Zaawansowana walidacja danych
- **Weryfikacja NIP**: Sprawdzanie poprawności numerów identyfikacji podatkowej (algorytm wagowy)
- **Kontrola IBAN**: Walidacja numerów kont bankowych
- **Weryfikacja dat**: Kontrola formatów i logiczności dat
- **Kontrola kwot**: Walidacja sum i obliczeń matematycznych

### 🔄 Detekcja duplikatów
- Inteligentny system wykrywania powtarzających się faktur
- Porównywanie metadanych i treści dokumentów
- Zapobieganie podwójnemu księgowaniu

### 🖥️ Nowoczesny interfejs graficzny
- Intuicyjny GUI oparty na PyQt6
- Jasny motyw (Light Theme)
- Podgląd przetwarzanych dokumentów w czasie rzeczywistym
- Wielowątkowe przetwarzanie z paskiem postępu
- Panel statystyk i logów

---

## 🏗️ Architektura systemu

```
┌─────────────────────────────────────────────────────────────────┐
│                    FAKTURA BOT v5.0 ULTIMATE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   GUI Layer  │───▶│  Processing  │───▶│   Export     │      │
│  │   (PyQt6)    │    │    Thread    │    │  (Excel/JSON)│      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                    │              │
│         ▼                   ▼                    ▼              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Document   │    │  OCR Engines │    │  Validators  │      │
│  │   Separator  │    │  Tesseract + │    │  (NIP, IBAN) │      │
│  │              │    │  PaddleOCR   │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              YAML Template Engine (NOWE)             │      │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐     │      │
│  │  │  Loader    │  │  Matcher   │  │  Parser    │     │      │
│  │  │            │  │            │  │            │     │      │
│  │  └────────────┘  └────────────┘  └────────────┘     │      │
│  └──────────────────────────────────────────────────────┘      │
│                             │                                   │
│                             ▼                                   │
│                    ┌──────────────┐                             │
│                    │   Database   │                             │
│                    │   (SQLite)   │                             │
│                    └──────────────┘                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 💻 Wymagania systemowe

### Minimalne wymagania
- **Procesor**: Intel Core i3 lub równoważny (2.0 GHz+)
- **RAM**: 4 GB
- **Dysk**: 500 MB wolnego miejsca
- **System**: Windows 10/11, Linux (Ubuntu 20.04+), macOS 10.15+

### Zalecane wymagania
- **Procesor**: Intel Core i5/i7 lub równoważny (3.0 GHz+)
- **RAM**: 8 GB lub więcej
- **Dysk**: 2 GB wolnego miejsca (SSD zalecany)
- **GPU**: NVIDIA z CUDA (opcjonalnie, dla PaddleOCR)

### Wymagane oprogramowanie
- **Python**: 3.10 lub nowszy
- **Tesseract OCR**: 4.0 lub nowszy
- **Poppler**: Do konwersji PDF (tylko Windows)

---

## 🚀 Instalacja

### Krok 1: Sklonuj repozytorium

```bash
git clone https://github.com/MarekFox/INVOICE_OCR.git
cd INVOICE_OCR
git checkout TESTING2
```

### Krok 2: Utwórz środowisko wirtualne

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
2. Uruchom instalator (domyślna ścieżka: `C:\Program Files\Tesseract-OCR`)
3. Podczas instalacji wybierz pakiety językowe: Polish, German, Romanian, English

**macOS:**
```bash
brew install tesseract
brew install tesseract-lang
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install tesseract-ocr
sudo apt install tesseract-ocr-pol tesseract-ocr-deu tesseract-ocr-ron
```

### Krok 5: Zainstaluj Poppler (tylko Windows)

1. Pobierz Poppler z [poppler releases](https://github.com/oschwartz10612/poppler-windows/releases)
2. Rozpakuj do `C:\Program Files\poppler-24.02.0`
3. Zanotuj ścieżkę do folderu `Library\bin`

---

## ⚙️ Konfiguracja

### Utwórz plik konfiguracyjny

Stwórz plik `secrets_config.py` w głównym katalogu projektu:

```python
# secrets_config.py

# Ścieżka do silnika Tesseract OCR
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Ścieżka do Poppler (tylko Windows)
POPPLER_PATH = r"C:\Program Files\poppler-24.02.0\Library\bin"
```

### Konfiguracja szablonów YAML

Szablony znajdują się w katalogu `templates/`:

```
templates/
├── default/           # Szablony generyczne
│   ├── pl_generic.yml
│   ├── en_generic.yml
│   ├── de_generic.yml
│   └── ro_generic.yml
├── pl/                # Szablony polskie (per dostawca)
│   └── orange_polska.yml
├── en/                # Szablony angielskie
│   └── generic.yml
├── de/                # Szablony niemieckie
├── ro/                # Szablony rumuńskie
└── custom/            # Szablony użytkownika
    └── .gitkeep
```

---

## 📖 Użycie

### Uruchomienie aplikacji

```bash
python main.py
```

### Podstawowy workflow

1. **Wybierz pliki** - Kliknij "📁 Wybierz pliki" lub użyj Ctrl+O
2. **Ustaw opcje**:
   - Wybierz język (Auto/Polski/Niemiecki/Rumuński/Angielski)
   - Wybierz silnik OCR (Tesseract lub PaddleOCR)
   - Wpisz swój NIP (do filtrowania faktur)
3. **Przetwarzaj** - Kliknij "🚀 Przetwarzaj"
4. **Eksportuj** - Zapisz wyniki do Excel (Ctrl+E) lub JSON

### Skróty klawiszowe

| Skrót | Akcja |
|-------|-------|
| `Ctrl+O` | Otwórz pliki PDF |
| `Ctrl+Shift+O` | Otwórz folder |
| `Ctrl+E` | Eksport do Excel |
| `Ctrl+,` | Ustawienia |
| `F5` | Odśwież widok |
| `F1` | Pomoc |
| `Ctrl+C` | Kopiuj zaznaczony tekst |

---

## 📝 System szablonów YAML

### Struktura szablonu

```yaml
# templates/pl/orange_polska.yml
template:
  name: "Orange Polska"
  version: "1.0"
  language: "pl"
  priority: 80

issuer:
  name: "Orange Polska"
  tax_id: "5260250995"
  keywords:
    - "Orange Polska"
    - "orange.pl"

fields:
  invoice_number:
    patterns:
      - "Numer faktury[:\s]+([A-Z0-9/-]+)"
      - "Nr faktury[:\s]+([A-Z0-9/-]+)"
    required: true

  invoice_date:
    patterns:
      - "Data wystawienia[:\s]+(\d{2}[./-]\d{2}[./-]\d{4})"
    required: true
    type: "date"
    format: "%d.%m.%Y"

  gross_amount:
    patterns:
      - "Do zapłaty[:\s]+([\d\s]+[,.]\d{2})"
      - "RAZEM[:\s]+([\d\s]+[,.]\d{2})"
    required: true
    type: "amount"

tables:
  line_items:
    start_pattern: "Lp\.?\s+Nazwa"
    end_pattern: "RAZEM|Suma"
    columns:
      - name: "lp"
        pattern: "(\d+)"
      - name: "description"
        pattern: "(.+?)\s+\d"
      - name: "amount"
        pattern: "([\d,]+\.\d{2})\s*$"
```

### Tworzenie własnych szablonów

1. Skopiuj istniejący szablon z `templates/default/`
2. Umieść w `templates/custom/` lub odpowiednim katalogu językowym
3. Dostosuj wzorce regex do formatu faktury
4. Przetestuj na przykładowych fakturach

### Edytor szablonów GUI

Uruchom edytor szablonów:
```bash
python template_editor_gui.py
```

Funkcje edytora:
- Podgląd struktury szablonu
- Testowanie wzorców regex
- Walidacja składni YAML
- Import/eksport szablonów

---

## 📁 Struktura projektu

```
INVOICE_OCR/
│
├── 📄 main.py                    # Główna aplikacja GUI (PyQt6)
├── 📄 config.py                  # Konfiguracja globalna + TemplateSettings
├── 📄 secrets_config.py          # Ścieżki lokalne (nie w repo)
├── 📄 ocr_engines.py             # Silniki OCR (Tesseract, PaddleOCR)
├── 📄 parsers.py                 # Parser faktur + integracja z szablonami
├── 📄 invoice_separator.py       # Separacja wielostronicowych PDF
├── 📄 validators.py              # Walidatory (NIP, IBAN, kwoty, daty)
├── 📄 database.py                # Baza danych SQLite
├── 📄 excel_generator.py         # Generator raportów Excel
├── 📄 gui_components.py          # Komponenty Qt (tabele, widgety)
├── 📄 processing_thread.py       # Wątki przetwarzania w tle
├── 📄 template_editor_gui.py     # Edytor szablonów YAML
├── 📄 template_engine.py         # Silnik parsowania szablonów
├── 📄 template_loader.py         # Ładowanie i cache szablonów
├── 📄 template_matcher.py        # Dopasowywanie faktur do szablonów
├── 📄 utils.py                   # Funkcje pomocnicze
├── 📄 language_config.py         # Profile językowe OCR
├── 📄 requirements.txt           # Zależności Python
├── 📄 requirements_full.txt      # Pełne zależności
├── 📄 README.md                  # Dokumentacja projektu
├── 📄 LICENSE.txt                # Licencja MIT
├── 📄 .gitignore                 # Ignorowane pliki Git
├── 📄 faktura_bot.log            # Logi aplikacji
│
├── 📂 templates/                 # Szablony YAML
│   ├── 📂 custom/                # Szablony użytkownika
│   │   └── .gitkeep
│   ├── 📂 default/               # Szablony generyczne
│   │   ├── de_generic.yml
│   │   ├── en_generic.yml
│   │   ├── pl_generic.yml
│   │   └── ro_generic.yml
│   ├── 📂 de/                    # Szablony niemieckie
│   ├── 📂 en/                    # Szablony angielskie
│   │   └── generic.yml
│   ├── 📂 pl/                    # Szablony polskie
│   │   └── orange_polska.yml
│   └── 📂 ro/                    # Szablony rumuńskie
│
├── 📂 templates_backup/          # Kopie zapasowe szablonów
├── 📂 docs/                      # Dokumentacja
└── 📂 venv/                      # Środowisko wirtualne (nie w repo)
```

---

## 🔧 Technologie

### Języki i frameworki
- **Python 3.10+** - Główny język implementacji
- **PyQt6** - Framework GUI

### Silniki OCR
- **Tesseract OCR 4.x/5.x** - Open-source OCR
- **PaddleOCR 2.x** - Deep learning OCR (opcjonalny)
- **PaddlePaddle 3.x** - Backend dla PaddleOCR

### Biblioteki główne
| Biblioteka | Wersja | Zastosowanie |
|------------|--------|--------------|
| PyQt6 | 6.x | Interfejs graficzny |
| pytesseract | 0.3.x | Wrapper Tesseract |
| paddleocr | 2.x | OCR deep learning |
| pdf2image | 1.x | Konwersja PDF→obrazy |
| Pillow | 10.x | Przetwarzanie obrazów |
| openpyxl | 3.x | Generowanie Excel |
| PyYAML | 6.x | Parsowanie szablonów |
| regex | 2023.x | Zaawansowane wyrażenia regularne |

---

## 🧪 Branch: TESTING2

Ta gałąź (`TESTING2`) zawiera **nowy system szablonów YAML** dla parsowania faktur. Główne zmiany:

### ✅ Zaimplementowane
- [x] System szablonów YAML (wzorowany na invoice2data)
- [x] Template Engine z obsługą regex
- [x] Template Loader z cache'owaniem
- [x] Template Matcher - automatyczne dopasowanie szablonu
- [x] Szablony generyczne dla PL/EN/DE/RO
- [x] Szablon dedykowany: Orange Polska
- [x] Integracja z istniejącym parserem
- [x] Rozszerzona konfiguracja (TemplateSettings)

### 🚧 W trakcie testów
- [ ] Edytor GUI szablonów
- [ ] Hot-reload szablonów
- [ ] Więcej szablonów dedykowanych

### 📋 Do zrobienia
- [ ] Unit testy dla template engine
- [ ] Dokumentacja API szablonów
- [ ] Wizard tworzenia szablonów

---

## 🤝 Contributing

Wkład w rozwój projektu jest mile widziany!

### Jak zgłosić błąd?

1. Sprawdź [Issues](https://github.com/MarekFox/INVOICE_OCR/issues)
2. Utwórz nowy Issue z opisem:
   - Kroki do reprodukcji
   - Oczekiwane vs rzeczywiste zachowanie
   - Wersja Python i systemu
   - Logi błędów (plik `faktura_bot.log`)

### Proces Pull Request

1. Fork repozytorium
2. Utwórz branch: `git checkout -b feature/NazwaFunkcji`
3. Commituj zmiany: `git commit -m "feat: Opis zmian"`
4. Push: `git push origin feature/NazwaFunkcji`
5. Otwórz Pull Request

### Wytyczne
- Kod zgodny z PEP 8
- Docstringi dla funkcji publicznych
- Testy dla nowych funkcjonalności

---

## 📜 Licencja

Ten projekt jest dostępny na licencji **MIT License**.

```
MIT License

Copyright (c) 2024 MarekFox

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software...
```

Zobacz [LICENSE](LICENSE) dla pełnej treści.

---

## 📞 Kontakt

**Autor**: MarekFox

- 🐙 GitHub: [@MarekFox](https://github.com/MarekFox)
- 🔗 Repozytorium: [https://github.com/MarekFox/INVOICE_OCR](https://github.com/MarekFox/INVOICE_OCR)

---

## 🙏 Podziękowania

Projekt wykorzystuje technologie open-source:
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- [invoice2data](https://github.com/invoice-x/invoice2data) - inspiracja dla systemu szablonów

---

<div align="center">

**⭐ Jeśli ten projekt Ci pomógł, zostaw gwiazdkę! ⭐**

Made with ❤️ by [MarekFox](https://github.com/MarekFox)

</div>
