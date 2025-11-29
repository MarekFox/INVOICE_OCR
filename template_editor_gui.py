"""
FAKTURA BOT v5.0 - Template Editor GUI
=======================================
Edytor szablonów YAML z interfejsem graficznym PyQt6
"""

import sys
import os
import yaml
import re
from pathlib import Path
from typing import Optional, Dict, List, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTabWidget, QTextEdit,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton, QLabel,
    QGroupBox, QFormLayout, QScrollArea, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QInputDialog,
    QPlainTextEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction

from template_loader import TemplateLoader, InvoiceTemplate, TemplateField


class YAMLSyntaxHighlighter(QSyntaxHighlighter):
    """Podświetlanie składni YAML"""

    def __init__(self, document):
        super().__init__(document)

        # Formaty
        self.key_format = QTextCharFormat()
        self.key_format.setForeground(QColor("#0066cc"))
        self.key_format.setFontWeight(QFont.Weight.Bold)

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#008800"))

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#cc6600"))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#888888"))
        self.comment_format.setFontItalic(True)

        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#cc0066"))

        # Wzorce
        self.rules = [
            (r'^[\s]*[a-zA-Z_][a-zA-Z0-9_]*:', self.key_format),
            (r'"[^"]*"', self.string_format),
            (r"'[^']*'", self.string_format),
            (r'\b\d+\.?\d*\b', self.number_format),
            (r'#.*$', self.comment_format),
            (r'\b(true|false|null|yes|no)\b', self.keyword_format),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text, re.MULTILINE):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class FieldEditorWidget(QWidget):
    """Widget do edycji pojedynczego pola szablonu"""

    field_changed = pyqtSignal(str, dict)

    PARSER_TYPES = [
        'regex', 'date', 'money', 'context_extraction',
        'keyword_detection', 'static', 'bank_accounts', 'address_extraction'
    ]

    VALIDATORS = ['', 'nip', 'cui', 'iban', 'email', 'phone', 'vat_de']

    def __init__(self, field_name: str = "", field_data: Dict = None, parent=None):
        super().__init__(parent)
        self.field_name = field_name
        self.field_data = field_data or {}
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Nazwa pola
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nazwa pola:"))
        self.name_edit = QLineEdit(self.field_name)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # Typ parsera
        parser_layout = QHBoxLayout()
        parser_layout.addWidget(QLabel("Parser:"))
        self.parser_combo = QComboBox()
        self.parser_combo.addItems(self.PARSER_TYPES)
        self.parser_combo.currentTextChanged.connect(self._on_parser_changed)
        parser_layout.addWidget(self.parser_combo)
        layout.addLayout(parser_layout)

        # Opcje
        options_group = QGroupBox("Opcje")
        options_layout = QFormLayout(options_group)

        self.required_check = QCheckBox()
        options_layout.addRow("Wymagane:", self.required_check)

        self.validator_combo = QComboBox()
        self.validator_combo.addItems(self.VALIDATORS)
        options_layout.addRow("Walidator:", self.validator_combo)

        self.group_spin = QSpinBox()
        self.group_spin.setRange(0, 10)
        self.group_spin.setValue(1)
        options_layout.addRow("Grupa regex:", self.group_spin)

        self.context_range_spin = QSpinBox()
        self.context_range_spin.setRange(50, 1000)
        self.context_range_spin.setValue(200)
        options_layout.addRow("Zakres kontekstu:", self.context_range_spin)

        layout.addWidget(options_group)

        # Wzorce (patterns)
        patterns_group = QGroupBox("Wzorce regex")
        patterns_layout = QVBoxLayout(patterns_group)

        self.patterns_edit = QPlainTextEdit()
        self.patterns_edit.setPlaceholderText("Jeden wzorzec na linię...")
        self.patterns_edit.setMaximumHeight(100)
        patterns_layout.addWidget(self.patterns_edit)

        layout.addWidget(patterns_group)

        # Słowa kluczowe
        keywords_group = QGroupBox("Słowa kluczowe")
        keywords_layout = QVBoxLayout(keywords_group)

        self.keywords_edit = QPlainTextEdit()
        self.keywords_edit.setPlaceholderText("Jedno słowo kluczowe na linię...")
        self.keywords_edit.setMaximumHeight(80)
        keywords_layout.addWidget(self.keywords_edit)

        layout.addWidget(keywords_group)

        # Fallback
        fallback_layout = QHBoxLayout()
        fallback_layout.addWidget(QLabel("Fallback:"))
        self.fallback_edit = QLineEdit()
        self.fallback_edit.setPlaceholderText("np. NOT_FOUND, use_issue_date, add_days:14")
        fallback_layout.addWidget(self.fallback_edit)
        layout.addLayout(fallback_layout)

        # Formaty dat (widoczne tylko dla parser=date)
        self.date_formats_group = QGroupBox("Formaty dat")
        date_layout = QVBoxLayout(self.date_formats_group)
        self.date_formats_edit = QPlainTextEdit()
        self.date_formats_edit.setPlaceholderText("%d.%m.%Y\n%d-%m-%Y\n%Y-%m-%d")
        self.date_formats_edit.setMaximumHeight(80)
        date_layout.addWidget(self.date_formats_edit)
        layout.addWidget(self.date_formats_group)

        # Mapowanie (widoczne tylko dla parser=keyword_detection)
        self.mapping_group = QGroupBox("Mapowanie słów kluczowych")
        mapping_layout = QVBoxLayout(self.mapping_group)
        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["Słowo kluczowe", "Wartość"])
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        self.mapping_table.setMaximumHeight(120)
        mapping_layout.addWidget(self.mapping_table)

        mapping_buttons = QHBoxLayout()
        add_mapping_btn = QPushButton("Dodaj")
        add_mapping_btn.clicked.connect(self._add_mapping_row)
        remove_mapping_btn = QPushButton("Usuń")
        remove_mapping_btn.clicked.connect(self._remove_mapping_row)
        mapping_buttons.addWidget(add_mapping_btn)
        mapping_buttons.addWidget(remove_mapping_btn)
        mapping_buttons.addStretch()
        mapping_layout.addLayout(mapping_buttons)

        layout.addWidget(self.mapping_group)

        # Wartość statyczna (widoczne tylko dla parser=static)
        self.static_group = QGroupBox("Wartość statyczna")
        static_layout = QHBoxLayout(self.static_group)
        self.static_value_edit = QLineEdit()
        static_layout.addWidget(self.static_value_edit)
        layout.addWidget(self.static_group)

        layout.addStretch()

        # Początkowo ukryj specjalne grupy
        self._on_parser_changed(self.parser_combo.currentText())

    def _on_parser_changed(self, parser: str):
        """Pokazuje/ukrywa opcje w zależności od typu parsera"""
        self.date_formats_group.setVisible(parser == 'date')
        self.mapping_group.setVisible(parser == 'keyword_detection')
        self.static_group.setVisible(parser == 'static')
        self.patterns_edit.parentWidget().setVisible(parser in ['regex', 'date', 'money', 'bank_accounts', 'address_extraction'])

    def _add_mapping_row(self):
        row = self.mapping_table.rowCount()
        self.mapping_table.insertRow(row)
        self.mapping_table.setItem(row, 0, QTableWidgetItem(""))
        self.mapping_table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_mapping_row(self):
        row = self.mapping_table.currentRow()
        if row >= 0:
            self.mapping_table.removeRow(row)

    def _load_data(self):
        """Ładuje dane pola do widgetów"""
        if not self.field_data:
            return

        self.parser_combo.setCurrentText(self.field_data.get('parser', 'regex'))
        self.required_check.setChecked(self.field_data.get('required', False))
        self.validator_combo.setCurrentText(self.field_data.get('validator', ''))
        self.group_spin.setValue(self.field_data.get('group', 1))
        self.context_range_spin.setValue(self.field_data.get('context_range', 200))

        patterns = self.field_data.get('patterns', [])
        self.patterns_edit.setPlainText('\n'.join(patterns))

        keywords = self.field_data.get('keywords', [])
        self.keywords_edit.setPlainText('\n'.join(keywords))

        self.fallback_edit.setText(self.field_data.get('fallback', ''))

        formats = self.field_data.get('formats', [])
        self.date_formats_edit.setPlainText('\n'.join(formats))

        mapping = self.field_data.get('mapping', {})
        for key, value in mapping.items():
            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            self.mapping_table.setItem(row, 0, QTableWidgetItem(key))
            self.mapping_table.setItem(row, 1, QTableWidgetItem(value))

        self.static_value_edit.setText(self.field_data.get('value', ''))

    def get_data(self) -> Dict:
        """Zwraca dane pola jako słownik"""
        data = {
            'parser': self.parser_combo.currentText(),
        }

        if self.required_check.isChecked():
            data['required'] = True

        if self.validator_combo.currentText():
            data['validator'] = self.validator_combo.currentText()

        if self.group_spin.value() != 1:
            data['group'] = self.group_spin.value()

        if self.context_range_spin.value() != 200:
            data['context_range'] = self.context_range_spin.value()

        patterns = [p.strip() for p in self.patterns_edit.toPlainText().split('\n') if p.strip()]
        if patterns:
            data['patterns'] = patterns

        keywords = [k.strip() for k in self.keywords_edit.toPlainText().split('\n') if k.strip()]
        if keywords:
            data['keywords'] = keywords

        if self.fallback_edit.text():
            data['fallback'] = self.fallback_edit.text()

        if self.parser_combo.currentText() == 'date':
            formats = [f.strip() for f in self.date_formats_edit.toPlainText().split('\n') if f.strip()]
            if formats:
                data['formats'] = formats

        if self.parser_combo.currentText() == 'keyword_detection':
            mapping = {}
            for row in range(self.mapping_table.rowCount()):
                key_item = self.mapping_table.item(row, 0)
                value_item = self.mapping_table.item(row, 1)
                if key_item and value_item and key_item.text():
                    mapping[key_item.text()] = value_item.text()
            if mapping:
                data['mapping'] = mapping

        if self.parser_combo.currentText() == 'static':
            data['value'] = self.static_value_edit.text()

        return data


class TemplateEditorWindow(QMainWindow):
    """Główne okno edytora szablonów"""

    def __init__(self, templates_dir: str = "templates"):
        super().__init__()
        self.templates_dir = Path(templates_dir)
        self.loader = TemplateLoader(templates_dir)
        self.current_template: Optional[InvoiceTemplate] = None
        self.current_file: Optional[Path] = None
        self.modified = False

        self._setup_ui()
        self._setup_menu()
        self._load_templates()

    def _setup_ui(self):
        self.setWindowTitle("FAKTURA BOT - Edytor Szablonów")
        self.setGeometry(100, 100, 1400, 900)

        # Główny widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Panel lewy - lista szablonów
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        left_layout.addWidget(QLabel("Szablony:"))

        self.templates_tree = QTreeWidget()
        self.templates_tree.setHeaderLabel("Szablony")
        self.templates_tree.itemClicked.connect(self._on_template_selected)
        left_layout.addWidget(self.templates_tree)

        # Przyciski
        btn_layout = QHBoxLayout()
        new_btn = QPushButton("Nowy")
        new_btn.clicked.connect(self._new_template)
        btn_layout.addWidget(new_btn)

        refresh_btn = QPushButton("Odśwież")
        refresh_btn.clicked.connect(self._load_templates)
        btn_layout.addWidget(refresh_btn)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_panel)

        # Panel środkowy - edycja
        middle_panel = QWidget()
        middle_layout = QVBoxLayout(middle_panel)

        # Zakładki
        self.tabs = QTabWidget()

        # Zakładka: Ogólne
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)

        self.issuer_edit = QLineEdit()
        general_layout.addRow("Wystawca:", self.issuer_edit)

        self.description_edit = QLineEdit()
        general_layout.addRow("Opis:", self.description_edit)

        self.language_combo = QComboBox()
        self.language_combo.addItems(['Polski', 'Niemiecki', 'Rumuński', 'Angielski'])
        general_layout.addRow("Język:", self.language_combo)

        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 100)
        self.priority_spin.setValue(50)
        general_layout.addRow("Priorytet:", self.priority_spin)

        self.keywords_edit = QPlainTextEdit()
        self.keywords_edit.setMaximumHeight(100)
        self.keywords_edit.setPlaceholderText("Słowa kluczowe do dopasowania (jedno na linię)")
        general_layout.addRow("Słowa kluczowe:", self.keywords_edit)

        self.exclude_edit = QPlainTextEdit()
        self.exclude_edit.setMaximumHeight(80)
        self.exclude_edit.setPlaceholderText("Słowa wykluczające (jedno na linię)")
        general_layout.addRow("Wykluczenia:", self.exclude_edit)

        self.tabs.addTab(general_tab, "Ogólne")

        # Zakładka: Pola
        fields_tab = QWidget()
        fields_layout = QHBoxLayout(fields_tab)

        # Lista pól
        fields_left = QWidget()
        fields_left_layout = QVBoxLayout(fields_left)
        fields_left_layout.addWidget(QLabel("Pola:"))

        self.fields_list = QListWidget()
        self.fields_list.itemClicked.connect(self._on_field_selected)
        fields_left_layout.addWidget(self.fields_list)

        fields_btn_layout = QHBoxLayout()
        add_field_btn = QPushButton("Dodaj")
        add_field_btn.clicked.connect(self._add_field)
        fields_btn_layout.addWidget(add_field_btn)

        remove_field_btn = QPushButton("Usuń")
        remove_field_btn.clicked.connect(self._remove_field)
        fields_btn_layout.addWidget(remove_field_btn)
        fields_left_layout.addLayout(fields_btn_layout)

        fields_layout.addWidget(fields_left)

        # Edytor pola
        self.field_editor_scroll = QScrollArea()
        self.field_editor_scroll.setWidgetResizable(True)
        self.field_editor = FieldEditorWidget()
        self.field_editor_scroll.setWidget(self.field_editor)
        fields_layout.addWidget(self.field_editor_scroll, stretch=2)

        self.tabs.addTab(fields_tab, "Pola")

        # Zakładka: Pozycje (lines)
        lines_tab = QWidget()
        lines_layout = QFormLayout(lines_tab)

        self.lines_enabled = QCheckBox("Włączone")
        lines_layout.addRow("Ekstrakcja pozycji:", self.lines_enabled)

        self.lines_start_edit = QPlainTextEdit()
        self.lines_start_edit.setMaximumHeight(80)
        self.lines_start_edit.setPlaceholderText("Wzorce początku tabeli (regex)")
        lines_layout.addRow("Początek tabeli:", self.lines_start_edit)

        self.lines_end_edit = QPlainTextEdit()
        self.lines_end_edit.setMaximumHeight(80)
        self.lines_end_edit.setPlaceholderText("Wzorce końca tabeli (regex)")
        lines_layout.addRow("Koniec tabeli:", self.lines_end_edit)

        self.line_pattern_edit = QLineEdit()
        self.line_pattern_edit.setPlaceholderText("Główny wzorzec linii (regex z grupami)")
        lines_layout.addRow("Wzorzec linii:", self.line_pattern_edit)

        self.tabs.addTab(lines_tab, "Pozycje")

        # Zakładka: YAML (surowy kod)
        yaml_tab = QWidget()
        yaml_layout = QVBoxLayout(yaml_tab)

        self.yaml_edit = QPlainTextEdit()
        self.yaml_edit.setFont(QFont("Consolas", 10))
        self.highlighter = YAMLSyntaxHighlighter(self.yaml_edit.document())
        yaml_layout.addWidget(self.yaml_edit)

        yaml_btn_layout = QHBoxLayout()
        apply_yaml_btn = QPushButton("Zastosuj YAML")
        apply_yaml_btn.clicked.connect(self._apply_yaml)
        yaml_btn_layout.addWidget(apply_yaml_btn)
        yaml_btn_layout.addStretch()
        yaml_layout.addLayout(yaml_btn_layout)

        self.tabs.addTab(yaml_tab, "YAML")

        middle_layout.addWidget(self.tabs)

        # Przyciski zapisu
        save_layout = QHBoxLayout()

        save_btn = QPushButton("Zapisz")
        save_btn.clicked.connect(self._save_template)
        save_layout.addWidget(save_btn)

        save_as_btn = QPushButton("Zapisz jako...")
        save_as_btn.clicked.connect(self._save_template_as)
        save_layout.addWidget(save_as_btn)

        test_btn = QPushButton("Testuj szablon")
        test_btn.clicked.connect(self._test_template)
        save_layout.addWidget(test_btn)

        save_layout.addStretch()
        middle_layout.addLayout(save_layout)

        splitter.addWidget(middle_panel)

        # Panel prawy - podgląd/test
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Test/Podgląd:"))

        self.test_input = QPlainTextEdit()
        self.test_input.setPlaceholderText("Wklej tekst faktury do testowania...")
        right_layout.addWidget(self.test_input)

        test_run_btn = QPushButton("Uruchom test")
        test_run_btn.clicked.connect(self._run_test)
        right_layout.addWidget(test_run_btn)

        self.test_output = QPlainTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setPlaceholderText("Wyniki testu pojawią się tutaj...")
        right_layout.addWidget(self.test_output)

        splitter.addWidget(right_panel)

        # Proporcje
        splitter.setSizes([250, 700, 450])

    def _setup_menu(self):
        menubar = self.menuBar()

        # Menu Plik
        file_menu = menubar.addMenu("Plik")

        new_action = QAction("Nowy szablon", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_template)
        file_menu.addAction(new_action)

        open_action = QAction("Otwórz...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_template)
        file_menu.addAction(open_action)

        save_action = QAction("Zapisz", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_template)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        exit_action = QAction("Zamknij", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Menu Edycja
        edit_menu = menubar.addMenu("Edycja")

        add_field_action = QAction("Dodaj pole", self)
        add_field_action.triggered.connect(self._add_field)
        edit_menu.addAction(add_field_action)

        # Menu Pomoc
        help_menu = menubar.addMenu("Pomoc")

        docs_action = QAction("Dokumentacja", self)
        docs_action.triggered.connect(self._show_docs)
        help_menu.addAction(docs_action)

    def _load_templates(self):
        """Ładuje listę szablonów do drzewa"""
        self.templates_tree.clear()
        self.loader.load_all_templates()

        # Grupuj wg katalogów
        groups: Dict[str, QTreeWidgetItem] = {}

        for key, template in self.loader.templates.items():
            parts = key.split('/')

            if len(parts) > 1:
                group_name = parts[0]
                if group_name not in groups:
                    group_item = QTreeWidgetItem([group_name])
                    group_item.setExpanded(True)
                    self.templates_tree.addTopLevelItem(group_item)
                    groups[group_name] = group_item

                item = QTreeWidgetItem([parts[-1]])
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                groups[group_name].addChild(item)
            else:
                item = QTreeWidgetItem([key])
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                self.templates_tree.addTopLevelItem(item)

    def _on_template_selected(self, item: QTreeWidgetItem, column: int):
        """Obsługa wyboru szablonu"""
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            return

        template = self.loader.templates.get(key)
        if template:
            self.current_template = template
            self.current_file = Path(template.file_path)
            self._display_template(template)

    def _display_template(self, template: InvoiceTemplate):
        """Wyświetla szablon w edytorze"""
        # Ogólne
        self.issuer_edit.setText(template.issuer)
        self.description_edit.setText(template.description)
        self.language_combo.setCurrentText(template.language)
        self.priority_spin.setValue(template.priority)
        self.keywords_edit.setPlainText('\n'.join(template.keywords))
        self.exclude_edit.setPlainText('\n'.join(template.exclude_keywords))

        # Pola
        self.fields_list.clear()
        for field_name in template.fields.keys():
            self.fields_list.addItem(field_name)

        # Pozycje
        if template.lines:
            self.lines_enabled.setChecked(template.lines.enabled)
            self.lines_start_edit.setPlainText('\n'.join(template.lines.start_patterns))
            self.lines_end_edit.setPlainText('\n'.join(template.lines.end_patterns))
            self.line_pattern_edit.setText(template.lines.line_pattern)
        else:
            self.lines_enabled.setChecked(False)
            self.lines_start_edit.clear()
            self.lines_end_edit.clear()
            self.line_pattern_edit.clear()

        # YAML
        yaml_content = self._template_to_yaml(template)
        self.yaml_edit.setPlainText(yaml_content)

    def _template_to_yaml(self, template: InvoiceTemplate) -> str:
        """Konwertuje szablon do YAML"""
        data = self.loader._template_to_dict(template)
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _on_field_selected(self, item: QListWidgetItem):
        """Obsługa wyboru pola"""
        field_name = item.text()
        if self.current_template and field_name in self.current_template.fields:
            field = self.current_template.fields[field_name]
            field_data = {
                'parser': field.parser,
                'patterns': field.patterns,
                'keywords': field.keywords,
                'group': field.group,
                'required': field.required,
                'validator': field.validator,
                'fallback': field.fallback,
                'context_range': field.context_range,
                'formats': field.formats,
                'mapping': field.mapping,
                'value': field.value
            }

            # Usuń stary edytor i utwórz nowy
            self.field_editor = FieldEditorWidget(field_name, field_data)
            self.field_editor_scroll.setWidget(self.field_editor)

    def _add_field(self):
        """Dodaje nowe pole"""
        name, ok = QInputDialog.getText(self, "Nowe pole", "Nazwa pola:")
        if ok and name:
            self.fields_list.addItem(name)
            self.modified = True

    def _remove_field(self):
        """Usuwa wybrane pole"""
        item = self.fields_list.currentItem()
        if item:
            row = self.fields_list.row(item)
            self.fields_list.takeItem(row)
            self.modified = True

    def _new_template(self):
        """Tworzy nowy szablon"""
        self.current_template = None
        self.current_file = None

        self.issuer_edit.clear()
        self.description_edit.clear()
        self.language_combo.setCurrentText('Polski')
        self.priority_spin.setValue(50)
        self.keywords_edit.clear()
        self.exclude_edit.clear()
        self.fields_list.clear()
        self.lines_enabled.setChecked(False)
        self.yaml_edit.clear()

        self.modified = True

    def _open_template(self):
        """Otwiera szablon z pliku"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Otwórz szablon", str(self.templates_dir),
            "YAML Files (*.yml *.yaml)"
        )

        if file_path:
            try:
                template = self.loader.load_template(Path(file_path))
                if template:
                    self.current_template = template
                    self.current_file = Path(file_path)
                    self._display_template(template)
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie można otworzyć pliku:\n{e}")

    def _save_template(self):
        """Zapisuje szablon"""
        if not self.current_file:
            self._save_template_as()
            return

        self._do_save(self.current_file)

    def _save_template_as(self):
        """Zapisuje szablon jako nowy plik"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz szablon", str(self.templates_dir),
            "YAML Files (*.yml)"
        )

        if file_path:
            if not file_path.endswith('.yml'):
                file_path += '.yml'
            self._do_save(Path(file_path))

    def _do_save(self, file_path: Path):
        """Wykonuje zapis szablonu"""
        try:
            # Zbierz dane z formularza
            data = {
                'issuer': self.issuer_edit.text(),
                'description': self.description_edit.text(),
                'language': self.language_combo.currentText(),
                'priority': self.priority_spin.value(),
                'keywords': [k.strip() for k in self.keywords_edit.toPlainText().split('\n') if k.strip()],
                'exclude_keywords': [k.strip() for k in self.exclude_edit.toPlainText().split('\n') if k.strip()],
                'fields': {},
                'options': {},
                'metadata': {
                    'author': 'User',
                    'version': '1.0'
                }
            }

            # Zbierz pola
            for i in range(self.fields_list.count()):
                field_name = self.fields_list.item(i).text()
                if self.current_template and field_name in self.current_template.fields:
                    field = self.current_template.fields[field_name]
                    data['fields'][field_name] = {
                        'parser': field.parser,
                        'patterns': field.patterns,
                        'keywords': field.keywords,
                        'required': field.required
                    }
                    if field.validator:
                        data['fields'][field_name]['validator'] = field.validator

            # Pozycje
            if self.lines_enabled.isChecked():
                data['lines'] = {
                    'enabled': True,
                    'start': {'patterns': [p.strip() for p in self.lines_start_edit.toPlainText().split('\n') if p.strip()]},
                    'end': {'patterns': [p.strip() for p in self.lines_end_edit.toPlainText().split('\n') if p.strip()]},
                    'line_pattern': self.line_pattern_edit.text()
                }

            # Zapisz
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            self.current_file = file_path
            self.modified = False

            QMessageBox.information(self, "Sukces", f"Szablon zapisany:\n{file_path}")

            # Odśwież listę
            self._load_templates()

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie można zapisać:\n{e}")

    def _apply_yaml(self):
        """Stosuje zmiany z edytora YAML"""
        try:
            yaml_text = self.yaml_edit.toPlainText()
            data = yaml.safe_load(yaml_text)

            # Załaduj jako szablon
            # Zapisz tymczasowo i przeładuj
            temp_path = self.templates_dir / "_temp_preview.yml"
            with open(temp_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            template = self.loader.load_template(temp_path)
            if template:
                self.current_template = template
                self._display_template(template)
                QMessageBox.information(self, "Sukces", "YAML zastosowany pomyślnie")

            # Usuń tymczasowy
            temp_path.unlink(missing_ok=True)

        except Exception as e:
            QMessageBox.critical(self, "Błąd YAML", f"Nieprawidłowy YAML:\n{e}")

    def _test_template(self):
        """Testuje szablon"""
        self.tabs.setCurrentIndex(3)  # Przejdź do zakładki YAML/Test
        self.test_input.setFocus()

    def _run_test(self):
        """Uruchamia test szablonu na wprowadzonym tekście"""
        text = self.test_input.toPlainText()
        if not text:
            QMessageBox.warning(self, "Uwaga", "Wklej tekst faktury do przetestowania")
            return

        if not self.current_template:
            QMessageBox.warning(self, "Uwaga", "Najpierw wybierz lub utwórz szablon")
            return

        try:
            from template_engine import TemplateEngine

            engine = TemplateEngine(str(self.templates_dir))
            result = engine.parse(text, self.current_template.language, template=self.current_template)

            # Formatuj wynik
            output = []
            output.append("=" * 50)
            output.append("WYNIK PARSOWANIA")
            output.append("=" * 50)
            output.append(f"Szablon: {result.template_used}")
            output.append(f"Confidence: {result.confidence:.2%}")
            output.append("")
            output.append("--- DANE PODSTAWOWE ---")
            output.append(f"Nr faktury: {result.invoice_id}")
            output.append(f"Typ: {result.invoice_type}")
            output.append(f"Data wystawienia: {result.issue_date.strftime('%d.%m.%Y')}")
            output.append(f"Termin płatności: {result.due_date.strftime('%d.%m.%Y')}")
            output.append("")
            output.append("--- DOSTAWCA ---")
            output.append(f"Nazwa: {result.supplier_name}")
            output.append(f"NIP: {result.supplier_tax_id}")
            output.append(f"Adres: {result.supplier_address}")
            output.append("")
            output.append("--- NABYWCA ---")
            output.append(f"Nazwa: {result.buyer_name}")
            output.append(f"NIP: {result.buyer_tax_id}")
            output.append("")
            output.append("--- KWOTY ---")
            output.append(f"Netto: {result.total_net}")
            output.append(f"VAT: {result.total_vat}")
            output.append(f"Brutto: {result.total_gross} {result.currency}")

            if result.parsing_errors:
                output.append("")
                output.append("--- BŁĘDY ---")
                for err in result.parsing_errors:
                    output.append(f"❌ {err}")

            if result.parsing_warnings:
                output.append("")
                output.append("--- OSTRZEŻENIA ---")
                for warn in result.parsing_warnings:
                    output.append(f"⚠️ {warn}")

            self.test_output.setPlainText('\n'.join(output))

        except Exception as e:
            self.test_output.setPlainText(f"BŁĄD TESTOWANIA:\n{e}")

    def _show_docs(self):
        """Pokazuje dokumentację"""
        docs = """
DOKUMENTACJA EDYTORA SZABLONÓW
==============================

TYPY PARSERÓW:
- regex: Szuka wzorca regex w tekście
- date: Specjalizowany parser dat
- money: Parser kwot pieniężnych  
- context_extraction: Wyciąga tekst w pobliżu słów kluczowych
- keyword_detection: Mapuje słowa kluczowe na wartości
- static: Stała wartość
- bank_accounts: Parser numerów kont bankowych
- address_extraction: Parser adresów

WALIDATORY:
- nip: Polski NIP
- cui: Rumuński CUI
- iban: Numer konta IBAN
- email: Adres email

FALLBACK:
- NOT_FOUND: Zwraca "Nie znaleziono"
- use_issue_date: Używa daty wystawienia
- add_days:N: Dodaje N dni do daty wystawienia
- calculate_from_gross:N: Oblicza z brutto przy stawce N%
- calculate_difference: gross - net
        """
        QMessageBox.information(self, "Dokumentacja", docs)


def run_editor(templates_dir: str = "templates"):
    """Uruchamia edytor szablonów"""
    app = QApplication(sys.argv)

    # Styl
    app.setStyle('Fusion')

    window = TemplateEditorWindow(templates_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_editor()
