# FAKTURA BOT v5.0 - System Szablonów YAML

## Instalacja

1. Skopiuj nowe pliki do katalogu projektu:
   - `template_loader.py`
   - `template_engine.py`  
   - `template_matcher.py`
   - `template_editor_gui.py`
   - `parsers.py` (zastępuje stary plik)

2. Skopiuj katalog `templates/` do katalogu projektu

3. Dodaj zależności do `requirements.txt`:
   ```
   PyYAML>=6.0
   ```

4. Zaktualizuj `config.py` według `config_additions.txt`

## Struktura katalogów

```
templates/
├── default/          # Szablony domyślne
│   ├── pl_generic.yml
│   ├── de_generic.yml
│   ├── ro_generic.yml
│   └── en_generic.yml
├── pl/               # Polskie szablony specyficzne
│   └── orange_polska.yml
├── de/               # Niemieckie szablony
├── ro/               # Rumuńskie szablony
└── custom/           # Szablony użytkownika
```

## Użycie

### Parsowanie faktury (bez zmian w API)
```python
from parsers import SmartInvoiceParser

parser = SmartInvoiceParser(text, "Polski", user_nip)
invoice = parser.parse()
```

### Edytor szablonów GUI
```python
from template_editor_gui import run_editor
run_editor("templates")
```

### Bezpośrednie użycie silnika szablonów
```python
from template_engine import TemplateEngine

engine = TemplateEngine("templates")
invoice = engine.parse(text, "Polski")
```

## Tworzenie własnych szablonów

Zobacz `docs/template_guide.md` dla pełnej dokumentacji.

## Licencja

MIT License
