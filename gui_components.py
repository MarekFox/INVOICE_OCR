"""
FAKTURA BOT v5.0 - GUI Components
====
Zaawansowane komponenty interfejsu użytkownika
UPDATED: Dodano document_type, ulepszone kopiowanie CTRL+C
"""

from typing import List, Dict, Optional, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QCheckBox, QLineEdit, QTextEdit,
    QProgressBar, QGroupBox, QSplitter, QTabWidget, QHeaderView,
    QMenu, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QSpinBox, QDoubleSpinBox, QDateEdit, QRadioButton, QButtonGroup,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QGraphicsView, QGraphicsScene, QToolBar, QStatusBar, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QDate, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QBrush, QPixmap, QPainter,
    QAction, QIcon, QKeySequence, QPen, QShortcut
)
from dataclasses import dataclass
import json

from config import CONFIG
from parsers import ParsedInvoice


# ==============================================================================
# HELPER: Tworzenie QLabel z możliwością kopiowania
# ==============================================================================

def create_selectable_label(text: str = "") -> QLabel:
    """Tworzy QLabel z możliwością zaznaczania i kopiowania tekstu (CTRL+C)"""
    label = QLabel(text)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | 
        Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    return label


# ==============================================================================
# KLASA: InvoiceTableWidget
# ==============================================================================

class InvoiceTableWidget(QTableWidget):
    """Zaawansowana tabela do wyświetlania faktur"""

    invoice_selected = pyqtSignal(ParsedInvoice)
    invoice_double_clicked = pyqtSignal(ParsedInvoice)

    def __init__(self):
        super().__init__()
        self.invoices = []
        self.setup_ui()

    def setup_ui(self):
        """Konfiguruje wygląd tabeli"""
        # Kolumny - DODANO "Dokument" (oryginał/kopia)
        columns = [
            "Status", "Nr Faktury", "Typ", "Dokument", "Data", "Dostawca", 
            "NIP", "Nabywca", "Netto", "VAT", "Brutto", 
            "Waluta", "Pewność", "Uwagi"
        ]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)

        # Wygląd
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSortingEnabled(True)

        # Szerokości kolumn
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 50)   # Status
        self.setColumnWidth(3, 80)   # Dokument (oryginał/kopia)

        # Menu kontekstowe
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # Sygnały
        self.itemSelectionChanged.connect(self.on_selection_changed)
        self.itemDoubleClicked.connect(self.on_item_double_clicked)

        # NOWE: Skrót CTRL+C do kopiowania zaznaczonych komórek
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.copy_shortcut.activated.connect(self.copy_selection_to_clipboard)

    def copy_selection_to_clipboard(self):
        """Kopiuje zaznaczone komórki do schowka"""
        selection = self.selectedItems()
        if not selection:
            return

        # Zbierz unikalne wiersze i kolumny
        rows = sorted(set(item.row() for item in selection))
        cols = sorted(set(item.column() for item in selection))

        # Zbuduj tekst do skopiowania
        lines = []
        for row in rows:
            row_data = []
            for col in cols:
                item = self.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))

        text = "\n".join(lines)

        # Skopiuj do schowka
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def add_invoice(self, invoice: ParsedInvoice):
        """Dodaje fakturę do tabeli"""
        self.invoices.append(invoice)
        row = self.rowCount()
        self.insertRow(row)

        # Status z ikoną
        status_item = QTableWidgetItem()
        if invoice.is_duplicate:
            status_item.setText("🔄")
            status_item.setToolTip("Duplikat")
        elif invoice.parsing_errors:
            status_item.setText("❌")
            status_item.setToolTip(f"{len(invoice.parsing_errors)} błędów")
        elif invoice.parsing_warnings:
            status_item.setText("⚠️")
            status_item.setToolTip(f"{len(invoice.parsing_warnings)} ostrzeżeń")
        else:
            status_item.setText("✅")
            status_item.setToolTip("OK")

        self.setItem(row, 0, status_item)

        # Nr faktury
        self.setItem(row, 1, QTableWidgetItem(invoice.invoice_id))

        # Typ faktury
        self.setItem(row, 2, QTableWidgetItem(invoice.invoice_type))

        # NOWE: Typ dokumentu (oryginał/kopia) z kolorowym tłem
        doc_type_item = QTableWidgetItem(invoice.document_type.upper())
        doc_type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if invoice.document_type == 'oryginał':
            doc_type_item.setBackground(QColor(200, 255, 200))  # Zielony
            doc_type_item.setToolTip("Dokument oryginalny")
        elif invoice.document_type == 'kopia':
            doc_type_item.setBackground(QColor(255, 255, 200))  # Żółty
            doc_type_item.setToolTip("Kopia dokumentu")
        elif invoice.document_type == 'duplikat':
            doc_type_item.setBackground(QColor(255, 220, 180))  # Pomarańczowy
            doc_type_item.setToolTip("Duplikat dokumentu")
        else:
            doc_type_item.setBackground(QColor(220, 220, 220))  # Szary
            doc_type_item.setToolTip("Typ dokumentu nieznany")

        self.setItem(row, 3, doc_type_item)

        # Data
        self.setItem(row, 4, QTableWidgetItem(invoice.issue_date.strftime('%Y-%m-%d')))

        # Dostawca
        self.setItem(row, 5, QTableWidgetItem(invoice.supplier_name[:30]))

        # NIP
        self.setItem(row, 6, QTableWidgetItem(invoice.supplier_tax_id))

        # Nabywca
        self.setItem(row, 7, QTableWidgetItem(invoice.buyer_name[:30]))

        # Kwoty - wyrównane do prawej (kolumny 8, 9, 10)
        for col, value in enumerate([invoice.total_net, invoice.total_vat, invoice.total_gross], 8):
            item = QTableWidgetItem(f"{value:.2f}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, col, item)

        # Waluta
        self.setItem(row, 11, QTableWidgetItem(invoice.currency))

        # Pewność z kolorem tła
        confidence_item = QTableWidgetItem(f"{invoice.confidence:.0%}")
        confidence_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if invoice.confidence >= 0.9:
            confidence_item.setBackground(QColor(200, 255, 200))
        elif invoice.confidence >= 0.7:
            confidence_item.setBackground(QColor(255, 255, 200))
        else:
            confidence_item.setBackground(QColor(255, 200, 200))

        self.setItem(row, 12, confidence_item)

        # Uwagi
        warnings_text = ', '.join(invoice.parsing_warnings[:2])
        self.setItem(row, 13, QTableWidgetItem(warnings_text))

    def show_context_menu(self, position):
        """Wyświetla menu kontekstowe"""
        menu = QMenu(self)

        # NOWE: Akcja kopiowania
        copy_action = QAction("📋 Kopiuj (Ctrl+C)", self)
        copy_action.triggered.connect(self.copy_selection_to_clipboard)
        menu.addAction(copy_action)

        menu.addSeparator()

        # Akcje
        view_action = QAction("🔍 Podgląd", self)
        view_action.triggered.connect(self.view_invoice)
        menu.addAction(view_action)

        edit_action = QAction("✏️ Edytuj", self)
        edit_action.triggered.connect(self.edit_invoice)
        menu.addAction(edit_action)

        menu.addSeparator()

        export_action = QAction("💾 Eksportuj", self)
        export_action.triggered.connect(self.export_invoice)
        menu.addAction(export_action)

        validate_action = QAction("✅ Weryfikuj", self)
        validate_action.triggered.connect(self.validate_invoice)
        menu.addAction(validate_action)

        menu.addSeparator()

        delete_action = QAction("🗑️ Usuń", self)
        delete_action.triggered.connect(self.delete_invoice)
        menu.addAction(delete_action)

        menu.exec(self.mapToGlobal(position))

    def on_selection_changed(self):
        """Obsługuje zmianę zaznaczenia"""
        selected_rows = set(item.row() for item in self.selectedItems())
        if selected_rows and len(selected_rows) == 1:
            row = list(selected_rows)[0]
            if 0 <= row < len(self.invoices):
                self.invoice_selected.emit(self.invoices[row])

    def on_item_double_clicked(self, item):
        """Obsługuje podwójne kliknięcie"""
        row = item.row()
        if 0 <= row < len(self.invoices):
            self.invoice_double_clicked.emit(self.invoices[row])

    def view_invoice(self):
        """Wyświetla szczegóły faktury"""
        pass

    def edit_invoice(self):
        """Edytuje fakturę"""
        pass

    def export_invoice(self):
        """Eksportuje fakturę"""
        pass

    def validate_invoice(self):
        """Weryfikuje fakturę"""
        pass

    def delete_invoice(self):
        """Usuwa fakturę"""
        selected_rows = set(item.row() for item in self.selectedItems())
        if selected_rows:
            reply = QMessageBox.question(
                self,
                "Potwierdzenie",
                f"Czy na pewno usunąć {len(selected_rows)} faktur?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                for row in sorted(selected_rows, reverse=True):
                    self.removeRow(row)
                    del self.invoices[row]

    def clear_all(self):
        """Czyści całą tabelę"""
        self.setRowCount(0)
        self.invoices.clear()

    def get_statistics(self) -> Dict:
        """Zwraca statystyki faktur"""
        total = len(self.invoices)
        valid = sum(1 for inv in self.invoices if inv.is_verified)
        errors = sum(1 for inv in self.invoices if inv.parsing_errors)
        warnings = sum(1 for inv in self.invoices if inv.parsing_warnings and not inv.parsing_errors)
        duplicates = sum(1 for inv in self.invoices if inv.is_duplicate)

        # NOWE: Statystyki typów dokumentów
        originals = sum(1 for inv in self.invoices if inv.document_type == 'oryginał')
        copies = sum(1 for inv in self.invoices if inv.document_type == 'kopia')

        total_amount = sum(float(inv.total_gross) for inv in self.invoices)

        return {
            'total': total,
            'valid': valid,
            'errors': errors,
            'warnings': warnings,
            'duplicates': duplicates,
            'originals': originals,
            'copies': copies,
            'total_amount': total_amount
        }


# ==============================================================================
# KLASA: InvoiceDetailsWidget
# ==============================================================================

class InvoiceDetailsWidget(QWidget):
    """Widget do wyświetlania szczegółów faktury"""

    def __init__(self):
        super().__init__()
        self.current_invoice = None
        self.setup_ui()

    def setup_ui(self):
        """Konfiguruje interfejs"""
        layout = QVBoxLayout()

        # Zakładki
        self.tabs = QTabWidget()

        # Zakładka: Przegląd
        self.overview_tab = self._create_overview_tab()
        self.tabs.addTab(self.overview_tab, "📊 Przegląd")

        # Zakładka: Pozycje
        self.items_tab = self._create_items_tab()
        self.tabs.addTab(self.items_tab, "📦 Pozycje")

        # Zakładka: Strony transakcji
        self.parties_tab = self._create_parties_tab()
        self.tabs.addTab(self.parties_tab, "👥 Strony")

        # Zakładka: Walidacja
        self.validation_tab = self._create_validation_tab()
        self.tabs.addTab(self.validation_tab, "✅ Walidacja")

        # Zakładka: Surowy OCR
        self.raw_tab = self._create_raw_tab()
        self.tabs.addTab(self.raw_tab, "📝 OCR")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def _create_overview_tab(self) -> QWidget:
        """Tworzy zakładkę przeglądu"""
        widget = QWidget()
        layout = QFormLayout()

        # Pola tylko do odczytu - z możliwością zaznaczania i kopiowania
        self.invoice_id_label = create_selectable_label()
        self.invoice_type_label = create_selectable_label()

        # NOWE: Typ dokumentu (oryginał/kopia)
        self.document_type_label = create_selectable_label()
        self.document_type_label.setStyleSheet("font-weight: bold; padding: 2px 6px;")

        # NOWE: Seria faktury (dla rumuńskich)
        self.invoice_series_label = create_selectable_label()

        self.issue_date_label = create_selectable_label()
        self.sale_date_label = create_selectable_label()
        self.due_date_label = create_selectable_label()
        self.total_net_label = create_selectable_label()
        self.total_vat_label = create_selectable_label()
        self.total_gross_label = create_selectable_label()
        self.currency_label = create_selectable_label()
        self.payment_method_label = create_selectable_label()
        self.payment_status_label = create_selectable_label()

        layout.addRow("Nr faktury:", self.invoice_id_label)
        layout.addRow("Seria:", self.invoice_series_label)  # NOWE
        layout.addRow("Typ:", self.invoice_type_label)
        layout.addRow("Dokument:", self.document_type_label)  # NOWE
        layout.addRow("Data wystawienia:", self.issue_date_label)
        layout.addRow("Data sprzedaży:", self.sale_date_label)  # NOWE
        layout.addRow("Termin płatności:", self.due_date_label)
        layout.addRow("Wartość netto:", self.total_net_label)
        layout.addRow("VAT:", self.total_vat_label)
        layout.addRow("Wartość brutto:", self.total_gross_label)
        layout.addRow("Waluta:", self.currency_label)
        layout.addRow("Metoda płatności:", self.payment_method_label)
        layout.addRow("Status płatności:", self.payment_status_label)

        widget.setLayout(layout)
        return widget

    def _create_items_tab(self) -> QWidget:
        """Tworzy zakładkę pozycji"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Tabela pozycji
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(
            ["LP", "Opis", "Ilość", "Cena jedn.", "Wartość"]
        )

        # NOWE: Skrót CTRL+C dla tabeli pozycji
        self.items_copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.items_table)
        self.items_copy_shortcut.activated.connect(lambda: self._copy_table_selection(self.items_table))

        layout.addWidget(self.items_table)
        widget.setLayout(layout)
        return widget

    def _copy_table_selection(self, table: QTableWidget):
        """Kopiuje zaznaczenie z tabeli do schowka"""
        selection = table.selectedItems()
        if not selection:
            return

        rows = sorted(set(item.row() for item in selection))
        cols = sorted(set(item.column() for item in selection))

        lines = []
        for row in rows:
            row_data = []
            for col in cols:
                item = table.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))

        text = "\n".join(lines)
        QApplication.clipboard().setText(text)

    def _create_parties_tab(self) -> QWidget:
        """Tworzy zakładkę stron transakcji"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Dostawca
        supplier_group = QGroupBox("Dostawca")
        supplier_layout = QFormLayout()

        self.supplier_name_label = create_selectable_label()
        self.supplier_name_label.setWordWrap(True)

        self.supplier_tax_label = create_selectable_label()

        self.supplier_address_label = create_selectable_label()
        self.supplier_address_label.setWordWrap(True)

        self.supplier_account_label = create_selectable_label()
        self.supplier_account_label.setWordWrap(True)

        supplier_layout.addRow("Nazwa:", self.supplier_name_label)
        supplier_layout.addRow("NIP/VAT:", self.supplier_tax_label)
        supplier_layout.addRow("Adres:", self.supplier_address_label)
        supplier_layout.addRow("Konto:", self.supplier_account_label)
        supplier_group.setLayout(supplier_layout)

        # Nabywca
        buyer_group = QGroupBox("Nabywca")
        buyer_layout = QFormLayout()

        self.buyer_name_label = create_selectable_label()
        self.buyer_name_label.setWordWrap(True)

        self.buyer_tax_label = create_selectable_label()

        self.buyer_address_label = create_selectable_label()
        self.buyer_address_label.setWordWrap(True)

        buyer_layout.addRow("Nazwa:", self.buyer_name_label)
        buyer_layout.addRow("NIP/VAT:", self.buyer_tax_label)
        buyer_layout.addRow("Adres:", self.buyer_address_label)
        buyer_group.setLayout(buyer_layout)

        layout.addWidget(supplier_group)
        layout.addWidget(buyer_group)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def _create_validation_tab(self) -> QWidget:
        """Tworzy zakładkę walidacji"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Status
        self.validation_status = QLabel()
        self.validation_status.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.validation_status)

        # Poziom pewności
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        layout.addWidget(QLabel("Poziom pewności:"))
        layout.addWidget(self.confidence_bar)

        # Błędy
        self.errors_list = QListWidget()
        layout.addWidget(QLabel("Błędy:"))
        layout.addWidget(self.errors_list)

        # Ostrzeżenia
        self.warnings_list = QListWidget()
        layout.addWidget(QLabel("Ostrzeżenia:"))
        layout.addWidget(self.warnings_list)

        widget.setLayout(layout)
        return widget

    def _create_raw_tab(self) -> QWidget:
        """Tworzy zakładkę surowego OCR"""
        widget = QWidget()
        layout = QVBoxLayout()

        # NOWE: Przycisk kopiowania całego tekstu OCR
        copy_btn = QPushButton("📋 Kopiuj cały tekst OCR")
        copy_btn.clicked.connect(self._copy_raw_text)
        layout.addWidget(copy_btn)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setFont(QFont("Consolas", 9))

        layout.addWidget(self.raw_text)
        widget.setLayout(layout)
        return widget

    def _copy_raw_text(self):
        """Kopiuje cały tekst OCR do schowka"""
        text = self.raw_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            # Opcjonalnie: pokaż komunikat
            # QMessageBox.information(self, "Skopiowano", "Tekst OCR skopiowany do schowka")

    def display_invoice(self, invoice: ParsedInvoice):
        """Wyświetla szczegóły faktury"""
        from utils import DateUtils

        self.current_invoice = invoice

        # ==== ZAKŁADKA: PRZEGLĄD ====
        self.invoice_id_label.setText(invoice.invoice_id)

        # NOWE: Seria faktury
        if invoice.invoice_series:
            self.invoice_series_label.setText(invoice.invoice_series)
            self.invoice_series_label.setVisible(True)
        else:
            self.invoice_series_label.setText("-")

        self.invoice_type_label.setText(invoice.invoice_type)

        # NOWE: Typ dokumentu z kolorowym tłem
        doc_type = invoice.document_type.upper()
        self.document_type_label.setText(doc_type)

        if invoice.document_type == 'oryginał':
            self.document_type_label.setStyleSheet(
                "font-weight: bold; padding: 2px 6px; background-color: #c8ffc8; border-radius: 3px;"
            )
        elif invoice.document_type == 'kopia':
            self.document_type_label.setStyleSheet(
                "font-weight: bold; padding: 2px 6px; background-color: #ffffc8; border-radius: 3px;"
            )
        elif invoice.document_type == 'duplikat':
            self.document_type_label.setStyleSheet(
                "font-weight: bold; padding: 2px 6px; background-color: #ffdcb4; border-radius: 3px;"
            )
        else:
            self.document_type_label.setStyleSheet(
                "font-weight: bold; padding: 2px 6px; background-color: #dcdcdc; border-radius: 3px;"
            )

        self.issue_date_label.setText(DateUtils.format_date_output(invoice.issue_date))
        self.sale_date_label.setText(DateUtils.format_date_output(invoice.sale_date))
        self.due_date_label.setText(DateUtils.format_date_output(invoice.due_date))
        self.total_net_label.setText(f"{invoice.total_net:.2f} {invoice.currency}")
        self.total_vat_label.setText(f"{invoice.total_vat:.2f} {invoice.currency}")
        self.total_gross_label.setText(f"{invoice.total_gross:.2f} {invoice.currency}")
        self.currency_label.setText(invoice.currency)
        self.payment_method_label.setText(invoice.payment_method)
        self.payment_status_label.setText(invoice.payment_status)

        # ==== ZAKŁADKA: POZYCJE ====
        self.items_table.setRowCount(0)
        for i, item in enumerate(invoice.line_items, 1):
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)

            self.items_table.setItem(row, 0, QTableWidgetItem(str(i)))
            self.items_table.setItem(row, 1, QTableWidgetItem(item.get('description', '')))
            self.items_table.setItem(row, 2, QTableWidgetItem(str(item.get('quantity', 0))))
            self.items_table.setItem(row, 3, QTableWidgetItem(f"{item.get('unit_price', 0):.2f}"))
            self.items_table.setItem(row, 4, QTableWidgetItem(f"{item.get('total', 0):.2f}"))

        # ==== ZAKŁADKA: STRONY ====
        self.supplier_name_label.setText(invoice.supplier_name)
        self.supplier_tax_label.setText(invoice.supplier_tax_id)
        self.supplier_address_label.setText(invoice.supplier_address)
        self.supplier_account_label.setText(
            invoice.supplier_accounts[0] if invoice.supplier_accounts else "Brak"
        )

        self.buyer_name_label.setText(invoice.buyer_name)
        self.buyer_tax_label.setText(invoice.buyer_tax_id)
        self.buyer_address_label.setText(invoice.buyer_address)

        # ==== ZAKŁADKA: WALIDACJA ====
        if invoice.is_verified:
            self.validation_status.setText("✅ Zweryfikowana")
            self.validation_status.setStyleSheet("color: green;")
        else:
            self.validation_status.setText("❌ Niezweryfikowana")
            self.validation_status.setStyleSheet("color: red;")

        self.confidence_bar.setValue(int(invoice.confidence * 100))

        self.errors_list.clear()
        for error in invoice.parsing_errors:
            self.errors_list.addItem(f"• {error}")

        self.warnings_list.clear()
        for warning in invoice.parsing_warnings:
            self.warnings_list.addItem(f"• {warning}")

        # ==== ZAKŁADKA: OCR ====
        self.raw_text.setText(invoice.raw_text)


# ==============================================================================
# KLASA: SettingsDialog
# ==============================================================================

class SettingsDialog(QDialog):
    """Dialog ustawień aplikacji"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Ustawienia")
        self.setModal(True)
        self.resize(600, 500)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Konfiguruje interfejs"""
        layout = QVBoxLayout()

        # Zakładki ustawień
        tabs = QTabWidget()

        # Zakładka: OCR
        ocr_tab = self._create_ocr_tab()
        tabs.addTab(ocr_tab, "OCR")

        # Zakładka: Parsowanie
        parsing_tab = self._create_parsing_tab()
        tabs.addTab(parsing_tab, "Parsowanie")

        # Zakładka: Walidacja
        validation_tab = self._create_validation_tab()
        tabs.addTab(validation_tab, "Walidacja")

        # Zakładka: Excel
        excel_tab = self._create_excel_tab()
        tabs.addTab(excel_tab, "Excel")

        # Zakładka: Interfejs
        ui_tab = self._create_ui_tab()
        tabs.addTab(ui_tab, "Interfejs")

        layout.addWidget(tabs)

        # Przyciski
        buttons_layout = QHBoxLayout()

        save_btn = QPushButton("💾 Zapisz")
        save_btn.clicked.connect(self.save_settings)

        cancel_btn = QPushButton("❌ Anuluj")
        cancel_btn.clicked.connect(self.reject)

        buttons_layout.addStretch()
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def _create_ocr_tab(self) -> QWidget:
        """Tworzy zakładkę ustawień OCR"""
        widget = QWidget()
        layout = QFormLayout()

        # DPI
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(150, 600)
        self.dpi_spin.setSingleStep(50)
        layout.addRow("DPI skanowania:", self.dpi_spin)

        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setSuffix(" s")
        layout.addRow("Timeout OCR:", self.timeout_spin)

        # GPU
        self.use_gpu_check = QCheckBox("Użyj GPU (jeśli dostępne)")
        layout.addRow(self.use_gpu_check)

        # PaddleOCR precision
        self.paddle_precision = QComboBox()
        self.paddle_precision.addItems(["fp32", "fp16", "int8"])
        layout.addRow("Precyzja PaddleOCR:", self.paddle_precision)

        widget.setLayout(layout)
        return widget

    def _create_parsing_tab(self) -> QWidget:
        """Tworzy zakładkę ustawień parsowania"""
        widget = QWidget()
        layout = QFormLayout()

        # Fuzzy matching
        self.fuzzy_check = QCheckBox("Dopasowanie rozmyte")
        layout.addRow(self.fuzzy_check)

        # Min confidence
        self.min_confidence = QDoubleSpinBox()
        self.min_confidence.setRange(0.0, 1.0)
        self.min_confidence.setSingleStep(0.05)
        layout.addRow("Min. pewność:", self.min_confidence)

        # Smart table detection
        self.smart_tables_check = QCheckBox("Inteligentna detekcja tabel")
        layout.addRow(self.smart_tables_check)

        # Auto rotation
        self.auto_rotation_check = QCheckBox("Automatyczna rotacja")
        layout.addRow(self.auto_rotation_check)

        # Remove watermarks
        self.remove_watermarks_check = QCheckBox("Usuń znaki wodne")
        layout.addRow(self.remove_watermarks_check)

        widget.setLayout(layout)
        return widget

    def _create_validation_tab(self) -> QWidget:
        """Tworzy zakładkę ustawień walidacji"""
        widget = QWidget()
        layout = QFormLayout()

        # Validate NIP
        self.validate_nip_check = QCheckBox("Waliduj NIP")
        layout.addRow(self.validate_nip_check)

        # Validate IBAN
        self.validate_iban_check = QCheckBox("Waliduj IBAN")
        layout.addRow(self.validate_iban_check)

        # Validate dates
        self.validate_dates_check = QCheckBox("Waliduj daty")
        layout.addRow(self.validate_dates_check)

        # Cross validate
        self.cross_validate_check = QCheckBox("Walidacja krzyżowa")
        layout.addRow(self.cross_validate_check)

        # External API
        self.external_api_check = QCheckBox("Weryfikacja online (GUS, ANAF)")
        layout.addRow(self.external_api_check)

        widget.setLayout(layout)
        return widget

    def _create_excel_tab(self) -> QWidget:
        """Tworzy zakładkę ustawień Excel"""
        widget = QWidget()
        layout = QFormLayout()

        # Include charts
        self.include_charts_check = QCheckBox("Dołącz wykresy")
        layout.addRow(self.include_charts_check)

        # Include pivot
        self.include_pivot_check = QCheckBox("Dołącz tabelę przestawną")
        layout.addRow(self.include_pivot_check)

        # Color coding
        self.color_coding_check = QCheckBox("Kolorowanie komórek")
        layout.addRow(self.color_coding_check)

        # Auto formulas
        self.auto_formulas_check = QCheckBox("Automatyczne formuły")
        layout.addRow(self.auto_formulas_check)

        widget.setLayout(layout)
        return widget

    def _create_ui_tab(self) -> QWidget:
        """Tworzy zakładkę ustawień interfejsu"""
        widget = QWidget()
        layout = QFormLayout()

        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["modern_dark", "classic", "enterprise_blue"])
        layout.addRow("Motyw:", self.theme_combo)

        # Auto save
        self.auto_save_check = QCheckBox("Automatyczny zapis")
        layout.addRow(self.auto_save_check)

        # Confirm exit
        self.confirm_exit_check = QCheckBox("Potwierdzaj wyjście")
        layout.addRow(self.confirm_exit_check)

        # Show tooltips
        self.show_tooltips_check = QCheckBox("Pokazuj podpowiedzi")
        layout.addRow(self.show_tooltips_check)

        widget.setLayout(layout)
        return widget

    def load_settings(self):
        """Wczytuje bieżące ustawienia"""
        # OCR
        self.dpi_spin.setValue(CONFIG.ocr.dpi)
        self.timeout_spin.setValue(CONFIG.ocr.timeout)
        self.use_gpu_check.setChecked(CONFIG.ocr.use_gpu)
        self.paddle_precision.setCurrentText(CONFIG.ocr.paddle_precision)

        # Parsowanie
        self.fuzzy_check.setChecked(CONFIG.parsing.fuzzy_matching)
        self.min_confidence.setValue(CONFIG.parsing.min_confidence)
        self.smart_tables_check.setChecked(CONFIG.parsing.smart_table_detection)
        self.auto_rotation_check.setChecked(CONFIG.parsing.auto_rotation)
        self.remove_watermarks_check.setChecked(CONFIG.parsing.remove_watermarks)

        # Walidacja
        self.validate_nip_check.setChecked(CONFIG.validation.validate_nip)
        self.validate_iban_check.setChecked(CONFIG.validation.validate_iban)
        self.validate_dates_check.setChecked(CONFIG.validation.validate_dates)
        self.cross_validate_check.setChecked(CONFIG.validation.cross_validate)
        self.external_api_check.setChecked(CONFIG.validation.external_api_validation)

        # Excel
        self.include_charts_check.setChecked(CONFIG.excel.include_charts)
        self.include_pivot_check.setChecked(CONFIG.excel.include_pivot)
        self.color_coding_check.setChecked(CONFIG.excel.color_coding)
        self.auto_formulas_check.setChecked(CONFIG.excel.auto_formulas)

        # UI
        self.theme_combo.setCurrentText(CONFIG.gui.theme)
        self.auto_save_check.setChecked(CONFIG.gui.auto_save)
        self.confirm_exit_check.setChecked(CONFIG.gui.confirm_exit)
        self.show_tooltips_check.setChecked(CONFIG.gui.show_tooltips)

    def save_settings(self):
        """Zapisuje ustawienia"""
        # OCR
        CONFIG.ocr.dpi = self.dpi_spin.value()
        CONFIG.ocr.timeout = self.timeout_spin.value()
        CONFIG.ocr.use_gpu = self.use_gpu_check.isChecked()
        CONFIG.ocr.paddle_precision = self.paddle_precision.currentText()

        # Parsowanie
        CONFIG.parsing.fuzzy_matching = self.fuzzy_check.isChecked()
        CONFIG.parsing.min_confidence = self.min_confidence.value()
        CONFIG.parsing.smart_table_detection = self.smart_tables_check.isChecked()
        CONFIG.parsing.auto_rotation = self.auto_rotation_check.isChecked()
        CONFIG.parsing.remove_watermarks = self.remove_watermarks_check.isChecked()

        # Walidacja
        CONFIG.validation.validate_nip = self.validate_nip_check.isChecked()
        CONFIG.validation.validate_iban = self.validate_iban_check.isChecked()
        CONFIG.validation.validate_dates = self.validate_dates_check.isChecked()
        CONFIG.validation.cross_validate = self.cross_validate_check.isChecked()
        CONFIG.validation.external_api_validation = self.external_api_check.isChecked()

        # Excel
        CONFIG.excel.include_charts = self.include_charts_check.isChecked()
        CONFIG.excel.include_pivot = self.include_pivot_check.isChecked()
        CONFIG.excel.color_coding = self.color_coding_check.isChecked()
        CONFIG.excel.auto_formulas = self.auto_formulas_check.isChecked()

        # UI
        CONFIG.gui.theme = self.theme_combo.currentText()
        CONFIG.gui.auto_save = self.auto_save_check.isChecked()
        CONFIG.gui.confirm_exit = self.confirm_exit_check.isChecked()
        CONFIG.gui.show_tooltips = self.show_tooltips_check.isChecked()

        # Zapisz do pliku
        CONFIG.save_user_config()

        QMessageBox.information(self, "Sukces", "Ustawienia zostały zapisane")
        self.accept()
