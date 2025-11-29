"""
FAKTURA BOT v5.0 - Template Loader
====================================
Ładowanie, walidacja i zarządzanie szablonami YAML
"""

import os
import yaml
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TemplateField:
    """Definicja pojedynczego pola w szablonie"""
    name: str
    parser: str  # regex, date, money, context_extraction, keyword_detection, static, bank_accounts, address_extraction
    patterns: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    group: int = 1
    required: bool = False
    validator: Optional[str] = None  # nip, cui, iban, email
    fallback: Optional[str] = None
    context_keywords: List[str] = field(default_factory=list)
    context_range: int = 200
    search_range: int = 150
    formats: List[str] = field(default_factory=list)  # Dla dat
    decimal_separator: str = ","
    thousand_separator: str = " "
    currency: str = "PLN"
    multiple: bool = False
    mapping: Dict[str, str] = field(default_factory=dict)
    default: Optional[str] = None
    extraction_strategy: str = "next_line"
    value: Optional[str] = None  # Dla parser: static


@dataclass
class TemplateLines:
    """Konfiguracja ekstrakcji pozycji faktury"""
    enabled: bool = True
    start_patterns: List[str] = field(default_factory=list)
    end_patterns: List[str] = field(default_factory=list)
    line_pattern: str = ""
    line_fields: List[Dict] = field(default_factory=list)
    alternative_patterns: List[Dict] = field(default_factory=list)
    skip_patterns: List[str] = field(default_factory=list)


@dataclass
class TemplateOptions:
    """Opcje przetwarzania szablonu"""
    remove_whitespace: bool = True
    lowercase_keywords: bool = False
    remove_accents: bool = False
    date_tolerance_days: int = 365
    amount_tolerance: float = 0.02
    tax_id_assignment_strategy: str = "context_proximity"
    validate_iban: bool = True
    debug_mode: bool = False


@dataclass
class InvoiceTemplate:
    """Kompletny szablon faktury"""
    # Identyfikacja
    issuer: str
    description: str = ""
    language: str = "Polski"
    priority: int = 50  # 1-100, wyższy = ważniejszy

    # Dopasowanie
    keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)

    # Pola do ekstrakcji
    fields: Dict[str, TemplateField] = field(default_factory=dict)

    # Pozycje faktury
    lines: Optional[TemplateLines] = None

    # Opcje
    options: TemplateOptions = field(default_factory=TemplateOptions)

    # Metadane
    file_path: str = ""
    version: str = "1.0"
    author: str = "System"
    created: str = ""
    last_modified: str = ""

    # Cache skompilowanych regex
    _compiled_patterns: Dict[str, List[re.Pattern]] = field(default_factory=dict, repr=False)

    def compile_patterns(self):
        """Kompiluje wszystkie wzorce regex dla wydajności"""
        for field_name, field_def in self.fields.items():
            if field_def.patterns:
                self._compiled_patterns[field_name] = [
                    re.compile(p, re.IGNORECASE | re.MULTILINE) 
                    for p in field_def.patterns
                ]

        # Kompiluj wzorce dla linii
        if self.lines:
            if self.lines.start_patterns:
                self._compiled_patterns['_lines_start'] = [
                    re.compile(p, re.IGNORECASE) for p in self.lines.start_patterns
                ]
            if self.lines.end_patterns:
                self._compiled_patterns['_lines_end'] = [
                    re.compile(p, re.IGNORECASE) for p in self.lines.end_patterns
                ]
            if self.lines.line_pattern:
                self._compiled_patterns['_line_main'] = [
                    re.compile(self.lines.line_pattern, re.IGNORECASE)
                ]


class TemplateValidationError(Exception):
    """Błąd walidacji szablonu"""
    pass


class TemplateLoader:
    """Ładuje i zarządza szablonami YAML"""

    # Wymagane pola w szablonie
    REQUIRED_ROOT_FIELDS = ['issuer', 'fields']
    REQUIRED_INVOICE_FIELDS = ['invoice_id', 'supplier_tax_id', 'buyer_tax_id', 'total_gross']

    # Dozwolone typy parserów
    VALID_PARSERS = [
        'regex', 'date', 'money', 'context_extraction', 
        'keyword_detection', 'static', 'bank_accounts', 
        'address_extraction'
    ]

    # Dozwolone walidatory
    VALID_VALIDATORS = ['nip', 'cui', 'iban', 'email', 'phone', 'vat_de']

    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.templates: Dict[str, InvoiceTemplate] = {}
        self.load_errors: List[Tuple[str, str]] = []

    def load_all_templates(self) -> int:
        """
        Ładuje wszystkie szablony z katalogu.
        Zwraca liczbę załadowanych szablonów.
        """
        self.templates.clear()
        self.load_errors.clear()
        loaded_count = 0

        if not self.templates_dir.exists():
            logger.warning(f"Katalog szablonów nie istnieje: {self.templates_dir}")
            return 0

        # Szukaj plików YAML rekurencyjnie
        yaml_files = list(self.templates_dir.rglob("*.yml")) + list(self.templates_dir.rglob("*.yaml"))

        for yaml_path in yaml_files:
            try:
                template = self.load_template(yaml_path)
                if template:
                    # Użyj ścieżki względnej jako klucza
                    rel_path = yaml_path.relative_to(self.templates_dir)
                    key = str(rel_path).replace(os.sep, "/")
                    self.templates[key] = template
                    loaded_count += 1
                    logger.info(f"✅ Załadowano szablon: {key} ({template.issuer})")
            except Exception as e:
                self.load_errors.append((str(yaml_path), str(e)))
                logger.error(f"❌ Błąd ładowania {yaml_path}: {e}")

        logger.info(f"📊 Załadowano {loaded_count} szablonów, {len(self.load_errors)} błędów")
        return loaded_count

    def load_template(self, file_path: Path) -> Optional[InvoiceTemplate]:
        """Ładuje pojedynczy szablon z pliku YAML"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            raise TemplateValidationError("Pusty plik YAML")

        # Walidacja podstawowa
        self._validate_root_structure(data, file_path)

        # Parsuj pola
        fields = self._parse_fields(data.get('fields', {}))

        # Parsuj konfigurację linii
        lines = self._parse_lines(data.get('lines', {}))

        # Parsuj opcje
        options = self._parse_options(data.get('options', {}))

        # Metadane
        metadata = data.get('metadata', {})

        # Utwórz obiekt szablonu
        template = InvoiceTemplate(
            issuer=data['issuer'],
            description=data.get('description', ''),
            language=data.get('language', 'Polski'),
            priority=data.get('priority', 50),
            keywords=data.get('keywords', []),
            exclude_keywords=data.get('exclude_keywords', []),
            fields=fields,
            lines=lines,
            options=options,
            file_path=str(file_path),
            version=metadata.get('version', '1.0'),
            author=metadata.get('author', 'Unknown'),
            created=metadata.get('created', ''),
            last_modified=metadata.get('last_modified', datetime.now().strftime('%Y-%m-%d'))
        )

        # Kompiluj wzorce regex
        template.compile_patterns()

        return template

    def _validate_root_structure(self, data: Dict, file_path: Path):
        """Waliduje główną strukturę szablonu"""
        for field in self.REQUIRED_ROOT_FIELDS:
            if field not in data:
                raise TemplateValidationError(
                    f"Brak wymaganego pola '{field}' w {file_path}"
                )

        # Sprawdź czy są wymagane pola faktury
        fields = data.get('fields', {})
        for req_field in self.REQUIRED_INVOICE_FIELDS:
            if req_field not in fields:
                logger.warning(
                    f"⚠️ Szablon {file_path} nie definiuje pola '{req_field}'"
                )

    def _parse_fields(self, fields_data: Dict) -> Dict[str, TemplateField]:
        """Parsuje definicje pól"""
        fields = {}

        for field_name, field_def in fields_data.items():
            if not isinstance(field_def, dict):
                continue

            parser = field_def.get('parser', 'regex')
            if parser not in self.VALID_PARSERS:
                logger.warning(f"Nieznany parser '{parser}' dla pola '{field_name}'")
                parser = 'regex'

            validator = field_def.get('validator')
            if validator and validator not in self.VALID_VALIDATORS:
                logger.warning(f"Nieznany walidator '{validator}' dla pola '{field_name}'")
                validator = None

            fields[field_name] = TemplateField(
                name=field_name,
                parser=parser,
                patterns=field_def.get('patterns', []),
                keywords=field_def.get('keywords', []),
                group=field_def.get('group', 1),
                required=field_def.get('required', False),
                validator=validator,
                fallback=field_def.get('fallback'),
                context_keywords=field_def.get('context_keywords', []),
                context_range=field_def.get('context_range', 200),
                search_range=field_def.get('search_range', 150),
                formats=field_def.get('formats', []),
                decimal_separator=field_def.get('decimal_separator', ','),
                thousand_separator=field_def.get('thousand_separator', ' '),
                currency=field_def.get('currency', 'PLN'),
                multiple=field_def.get('multiple', False),
                mapping=field_def.get('mapping', {}),
                default=field_def.get('default'),
                extraction_strategy=field_def.get('extraction_strategy', 'next_line'),
                value=field_def.get('value')
            )

        return fields

    def _parse_lines(self, lines_data: Dict) -> Optional[TemplateLines]:
        """Parsuje konfigurację pozycji faktury"""
        if not lines_data or not lines_data.get('enabled', True):
            return None

        start_data = lines_data.get('start', {})
        end_data = lines_data.get('end', {})
        skip_data = lines_data.get('skip_lines', {})

        return TemplateLines(
            enabled=lines_data.get('enabled', True),
            start_patterns=start_data.get('patterns', []) if isinstance(start_data, dict) else [],
            end_patterns=end_data.get('patterns', []) if isinstance(end_data, dict) else [],
            line_pattern=lines_data.get('line_pattern', ''),
            line_fields=lines_data.get('line_fields', []),
            alternative_patterns=lines_data.get('alternative_patterns', []),
            skip_patterns=skip_data.get('patterns', []) if isinstance(skip_data, dict) else []
        )

    def _parse_options(self, options_data: Dict) -> TemplateOptions:
        """Parsuje opcje przetwarzania"""
        return TemplateOptions(
            remove_whitespace=options_data.get('remove_whitespace', True),
            lowercase_keywords=options_data.get('lowercase_keywords', False),
            remove_accents=options_data.get('remove_accents', False),
            date_tolerance_days=options_data.get('date_tolerance_days', 365),
            amount_tolerance=options_data.get('amount_tolerance', 0.02),
            tax_id_assignment_strategy=options_data.get('tax_id_assignment_strategy', 'context_proximity'),
            validate_iban=options_data.get('validate_iban', True),
            debug_mode=options_data.get('debug_mode', False)
        )

    def get_templates_by_language(self, language: str) -> List[InvoiceTemplate]:
        """Zwraca szablony dla danego języka, posortowane wg priorytetu"""
        templates = [t for t in self.templates.values() if t.language == language]
        return sorted(templates, key=lambda t: t.priority, reverse=True)

    def get_template_by_issuer(self, issuer: str) -> Optional[InvoiceTemplate]:
        """Szuka szablonu po nazwie wystawcy"""
        for template in self.templates.values():
            if template.issuer.lower() == issuer.lower():
                return template
        return None

    def get_all_templates(self) -> List[InvoiceTemplate]:
        """Zwraca wszystkie szablony posortowane wg priorytetu"""
        return sorted(self.templates.values(), key=lambda t: t.priority, reverse=True)

    def reload_template(self, template_key: str) -> bool:
        """Przeładowuje pojedynczy szablon"""
        if template_key not in self.templates:
            return False

        file_path = Path(self.templates[template_key].file_path)
        try:
            template = self.load_template(file_path)
            if template:
                self.templates[template_key] = template
                return True
        except Exception as e:
            logger.error(f"Błąd przeładowania szablonu {template_key}: {e}")

        return False

    def save_template(self, template: InvoiceTemplate, file_path: Optional[Path] = None) -> bool:
        """Zapisuje szablon do pliku YAML"""
        if file_path is None:
            file_path = Path(template.file_path)

        # Konwertuj do słownika
        data = self._template_to_dict(template)

        try:
            # Upewnij się, że katalog istnieje
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            logger.info(f"✅ Zapisano szablon: {file_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Błąd zapisu szablonu: {e}")
            return False

    def _template_to_dict(self, template: InvoiceTemplate) -> Dict:
        """Konwertuje szablon do słownika (do zapisu YAML)"""
        data = {
            'issuer': template.issuer,
            'description': template.description,
            'language': template.language,
            'priority': template.priority,
            'keywords': template.keywords,
            'exclude_keywords': template.exclude_keywords,
            'fields': {},
            'options': {
                'remove_whitespace': template.options.remove_whitespace,
                'lowercase_keywords': template.options.lowercase_keywords,
                'remove_accents': template.options.remove_accents,
                'date_tolerance_days': template.options.date_tolerance_days,
                'amount_tolerance': template.options.amount_tolerance,
                'tax_id_assignment_strategy': template.options.tax_id_assignment_strategy,
                'validate_iban': template.options.validate_iban,
                'debug_mode': template.options.debug_mode
            },
            'metadata': {
                'author': template.author,
                'version': template.version,
                'created': template.created,
                'last_modified': datetime.now().strftime('%Y-%m-%d')
            }
        }

        # Konwertuj pola
        for field_name, field_def in template.fields.items():
            field_dict = {'parser': field_def.parser}

            if field_def.patterns:
                field_dict['patterns'] = field_def.patterns
            if field_def.keywords:
                field_dict['keywords'] = field_def.keywords
            if field_def.group != 1:
                field_dict['group'] = field_def.group
            if field_def.required:
                field_dict['required'] = True
            if field_def.validator:
                field_dict['validator'] = field_def.validator
            if field_def.fallback:
                field_dict['fallback'] = field_def.fallback
            if field_def.context_keywords:
                field_dict['context_keywords'] = field_def.context_keywords
            if field_def.context_range != 200:
                field_dict['context_range'] = field_def.context_range
            if field_def.formats:
                field_dict['formats'] = field_def.formats
            if field_def.mapping:
                field_dict['mapping'] = field_def.mapping
            if field_def.default:
                field_dict['default'] = field_def.default
            if field_def.value:
                field_dict['value'] = field_def.value

            data['fields'][field_name] = field_dict

        # Konwertuj linie
        if template.lines and template.lines.enabled:
            data['lines'] = {
                'enabled': True,
                'start': {'patterns': template.lines.start_patterns},
                'end': {'patterns': template.lines.end_patterns},
                'line_pattern': template.lines.line_pattern,
                'line_fields': template.lines.line_fields,
                'skip_lines': {'patterns': template.lines.skip_patterns}
            }

        return data


# Singleton dla globalnego dostępu
_global_loader: Optional[TemplateLoader] = None

def get_template_loader(templates_dir: str = "templates") -> TemplateLoader:
    """Zwraca globalną instancję loadera szablonów"""
    global _global_loader
    if _global_loader is None:
        _global_loader = TemplateLoader(templates_dir)
        _global_loader.load_all_templates()
    return _global_loader

def reload_templates(templates_dir: str = "templates") -> int:
    """Przeładowuje wszystkie szablony"""
    global _global_loader
    _global_loader = TemplateLoader(templates_dir)
    return _global_loader.load_all_templates()
