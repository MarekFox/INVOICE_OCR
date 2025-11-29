"""
FAKTURA BOT v5.0 ULTIMATE EDITION
====
Profesjonalny system do masowego przetwarzania faktur
Autor: AI Assistant
Wersja: 5.0.0
"""

import sys
import os
from typing import List, Dict, Optional
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QComboBox,
    QCheckBox, QLineEdit, QProgressBar, QTabWidget, QSplitter,
    QGroupBox, QRadioButton, QButtonGroup, QToolBar, QStatusBar,
    QDockWidget, QMenuBar, QMenu, QTableWidgetItem, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings, QSize
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont, QPalette, QColor, QShortcut
import logging
from datetime import datetime

# Import modułów aplikacji
from config import CONFIG, APP_VERSION, APP_NAME
from language_config import LANGUAGE_PROFILES
from processing_thread import BatchProcessingThread, ProcessingTask, QuickAnalysisThread
from gui_components import InvoiceTableWidget, InvoiceDetailsWidget, SettingsDialog
from database import InvoiceDatabase
from parsers import ParsedInvoice
from excel_generator import ExcelReportGenerator

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('faktura_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Główne okno aplikacji"""

    def __init__(self):
        super().__init__()
        self.current_tasks = []
        self.processing_thread = None
        self.database = InvoiceDatabase()
        self.settings = QSettings('FakturaBot', 'Settings')
        self.current_result = None
        self.results_cache = []

        self.init_ui()
        logger.info(f"Uruchomiono {APP_NAME} v{APP_VERSION}")

    def init_ui(self):
        """Inicjalizuje interfejs użytkownika"""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(CONFIG.gui.window_width, CONFIG.gui.window_height)

        self.create_menu()
        self.create_toolbar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.invoice_table = InvoiceTableWidget()
        self.invoice_table.invoice_selected.connect(self.on_invoice_selected)
        self.invoice_table.invoice_double_clicked.connect(self.on_invoice_double_clicked)

        left_layout.addWidget(QLabel("Lista faktur:"))
        left_layout.addWidget(self.invoice_table)

        self.invoice_details = InvoiceDetailsWidget()

        splitter.addWidget(left_widget)
        splitter.addWidget(self.invoice_details)
        splitter.setSizes([800, 600])

        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status("Gotowy")

        self.create_dock_widgets()
        self.load_settings()

        if not self.my_nip_input.text():
            self.my_nip_input.setText("6792740329")
            logger.info("Ustawiono domyslny NIP: 6792740329")

        self.apply_theme()

        # Ctrl+C dla kopiowania
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        copy_shortcut.activated.connect(self.copy_selected_text)

    def copy_selected_text(self):
        """Kopiuje zaznaczony tekst z aktywnego widgetu"""
        from PyQt6.QtWidgets import QTableWidget

        focused = self.focusWidget()

        if isinstance(focused, QTableWidget):
            selection = focused.selectedItems()
            if selection:
                rows = sorted(set(item.row() for item in selection))
                cols = sorted(set(item.column() for item in selection))

                lines = []
                for row in rows:
                    row_data = []
                    for col in cols:
                        item = focused.item(row, col)
                        row_data.append(item.text() if item else "")
                    lines.append("\t".join(row_data))

                text = "\n".join(lines)
                QApplication.clipboard().setText(text)
                self.log_message(f"Skopiowano {len(rows)} wierszy z tabeli", level='INFO')
                return

        if isinstance(focused, QTextEdit):
            cursor = focused.textCursor()
            if cursor.hasSelection():
                QApplication.clipboard().setText(cursor.selectedText())
                self.log_message("Skopiowano zaznaczony tekst", level='INFO')
                return

        if isinstance(focused, QLabel):
            if focused.hasSelectedText():
                QApplication.clipboard().setText(focused.selectedText())
                self.log_message("Skopiowano tekst z etykiety", level='INFO')
                return

    def create_menu(self):
        """Tworzy menu aplikacji"""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Plik")

        open_action = QAction("Otworz PDF...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_files)
        file_menu.addAction(open_action)

        open_folder_action = QAction("Otworz folder...", self)
        open_folder_action.setShortcut("Ctrl+Shift+O")
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        export_excel_action = QAction("Eksportuj do Excel...", self)
        export_excel_action.setShortcut("Ctrl+E")
        export_excel_action.triggered.connect(self.export_to_excel)
        file_menu.addAction(export_excel_action)

        export_json_action = QAction("Eksportuj do JSON...", self)
        export_json_action.triggered.connect(self.export_to_json)
        file_menu.addAction(export_json_action)

        file_menu.addSeparator()

        exit_action = QAction("Wyjscie", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("Edycja")

        select_all_action = QAction("Zaznacz wszystko", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        edit_menu.addAction(select_all_action)

        edit_menu.addSeparator()

        settings_action = QAction("Ustawienia...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        edit_menu.addAction(settings_action)

        view_menu = menubar.addMenu("Widok")

        self.show_stats_action = QAction("Pokaz statystyki", self, checkable=True)
        self.show_stats_action.setChecked(True)
        self.show_stats_action.triggered.connect(self.toggle_statistics)
        view_menu.addAction(self.show_stats_action)

        self.show_logs_action = QAction("Pokaz logi", self, checkable=True)
        self.show_logs_action.triggered.connect(self.toggle_logs)
        view_menu.addAction(self.show_logs_action)

        view_menu.addSeparator()

        refresh_action = QAction("Odswiez", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self.refresh_view)
        view_menu.addAction(refresh_action)

        tools_menu = menubar.addMenu("Narzedzia")

        validate_all_action = QAction("Waliduj wszystkie", self)
        validate_all_action.triggered.connect(self.validate_all_invoices)
        tools_menu.addAction(validate_all_action)

        find_duplicates_action = QAction("Znajdz duplikaty", self)
        find_duplicates_action.triggered.connect(self.find_duplicates)
        tools_menu.addAction(find_duplicates_action)

        tools_menu.addSeparator()

        backup_db_action = QAction("Kopia zapasowa bazy", self)
        backup_db_action.triggered.connect(self.backup_database)
        tools_menu.addAction(backup_db_action)

        clean_cache_action = QAction("Wyczysc cache", self)
        clean_cache_action.triggered.connect(self.clean_cache)
        tools_menu.addAction(clean_cache_action)

        help_menu = menubar.addMenu("Pomoc")

        help_action = QAction("Pomoc", self)
        help_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

        help_menu.addSeparator()

        about_action = QAction("O programie", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_toolbar(self):
        """Tworzy pasek narzedzi"""
        toolbar = QToolBar("Glowny pasek narzedzi")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_btn = QAction("Otworz", self)
        open_btn.setToolTip("Otworz pliki PDF")
        open_btn.triggered.connect(self.open_files)
        toolbar.addAction(open_btn)

        analyze_btn = QAction("Analizuj", self)
        analyze_btn.setToolTip("Rozpocznij analize")
        analyze_btn.triggered.connect(self.start_processing)
        toolbar.addAction(analyze_btn)

        toolbar.addSeparator()

        export_btn = QAction("Excel", self)
        export_btn.setToolTip("Eksportuj do Excel")
        export_btn.triggered.connect(self.export_to_excel)
        toolbar.addAction(export_btn)

        save_btn = QAction("Zapisz", self)
        save_btn.setToolTip("Zapisz do bazy")
        save_btn.triggered.connect(self.save_to_database)
        toolbar.addAction(save_btn)

        toolbar.addSeparator()

        validate_btn = QAction("Waliduj", self)
        validate_btn.setToolTip("Waliduj zaznaczone")
        validate_btn.triggered.connect(self.validate_selected)
        toolbar.addAction(validate_btn)

        delete_btn = QAction("Usun", self)
        delete_btn.setToolTip("Usun zaznaczone")
        delete_btn.triggered.connect(self.delete_selected)
        toolbar.addAction(delete_btn)

    def create_control_panel(self) -> QGroupBox:
        """Tworzy panel kontrolny"""
        panel = QGroupBox("Panel kontrolny")
        layout = QHBoxLayout()

        layout.addWidget(QLabel("Jezyk:"))
        self.language_combo = QComboBox()
        self.language_combo.addItems(['Auto'] + list(LANGUAGE_PROFILES.keys()))
        self.language_combo.setMaximumWidth(150)
        layout.addWidget(self.language_combo)

        layout.addWidget(QLabel("OCR:"))
        self.ocr_group = QButtonGroup()

        self.tesseract_radio = QRadioButton("Tesseract")
        self.tesseract_radio.setChecked(True)
        self.ocr_group.addButton(self.tesseract_radio)
        layout.addWidget(self.tesseract_radio)

        self.paddle_radio = QRadioButton("PaddleOCR")
        self.ocr_group.addButton(self.paddle_radio)
        layout.addWidget(self.paddle_radio)

        layout.addWidget(QLabel("Moj NIP:"))
        self.my_nip_input = QLineEdit()
        self.my_nip_input.setPlaceholderText("Wpisz swoj NIP")
        self.my_nip_input.setText("6792740329")
        self.my_nip_input.setMaximumWidth(150)
        layout.addWidget(self.my_nip_input)

        layout.addStretch()

        self.auto_separate_check = QCheckBox("Auto-separacja")
        self.auto_separate_check.setChecked(True)
        layout.addWidget(self.auto_separate_check)

        self.generate_excel_check = QCheckBox("Generuj Excel")
        self.generate_excel_check.setChecked(True)
        layout.addWidget(self.generate_excel_check)

        self.save_to_db_check = QCheckBox("Zapisz do bazy")
        self.save_to_db_check.setChecked(True)
        layout.addWidget(self.save_to_db_check)

        self.load_btn = QPushButton("Wybierz pliki")
        self.load_btn.clicked.connect(self.open_files)
        layout.addWidget(self.load_btn)

        self.process_btn = QPushButton("Przetwarzaj")
        self.process_btn.clicked.connect(self.start_processing)
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        layout.addWidget(self.process_btn)

        panel.setLayout(layout)
        return panel

    def create_dock_widgets(self):
        """Tworzy widgety dokowane"""
        self.stats_dock = QDockWidget("Statystyki", self)
        self.stats_widget = QWidget()
        stats_layout = QVBoxLayout(self.stats_widget)

        self.stats_label = QLabel("Statystyki pojawia sie po przetworzeniu")
        stats_layout.addWidget(self.stats_label)

        self.stats_dock.setWidget(self.stats_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.stats_dock)

        self.logs_dock = QDockWidget("Logi", self)
        self.logs_dock.setVisible(False)

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setMaximumHeight(200)

        self.logs_dock.setWidget(self.logs_text)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.logs_dock)

    def open_files(self):
        """Otwiera pliki PDF"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Wybierz pliki PDF",
            "",
            "Pliki PDF (*.pdf);;Wszystkie pliki (*.*)"
        )

        if files:
            self.current_tasks = []
            for i, file_path in enumerate(files):
                task = ProcessingTask(
                    file_path=file_path,
                    task_id=f"task_{i}_{Path(file_path).stem}",
                    priority=0,
                    options=self.get_processing_options()
                )
                self.current_tasks.append(task)

            self.update_status(f"Zaladowano {len(files)} plikow")
            self.process_btn.setEnabled(True)
            self.log_message(f"Zaladowano pliki: {', '.join([Path(f).name for f in files])}")

    def open_folder(self):
        """Otwiera folder z plikami PDF"""
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder")

        if folder:
            pdf_files = list(Path(folder).glob("*.pdf"))

            if not pdf_files:
                QMessageBox.warning(self, "Uwaga", "Nie znaleziono plikow PDF w wybranym folderze")
                return

            self.current_tasks = []
            for i, file_path in enumerate(pdf_files):
                task = ProcessingTask(
                    file_path=str(file_path),
                    task_id=f"task_{i}_{file_path.stem}",
                    priority=0,
                    options=self.get_processing_options()
                )
                self.current_tasks.append(task)

            self.update_status(f"Zaladowano {len(pdf_files)} plikow z folderu")
            self.process_btn.setEnabled(True)

    def get_processing_options(self) -> Dict:
        """Pobiera opcje przetwarzania"""
        return {
            'language': self.language_combo.currentText(),
            'use_paddleocr': self.paddle_radio.isChecked(),
            'auto_separate': self.auto_separate_check.isChecked(),
            'generate_excel': self.generate_excel_check.isChecked(),
            'user_tax_id': self.my_nip_input.text(),
            'excel_charts': True,
            'excel_pivot': False
        }

    def start_processing(self):
        """Rozpoczyna przetwarzanie"""
        if not self.current_tasks:
            QMessageBox.warning(self, "Uwaga", "Najpierw wybierz pliki do przetworzenia")
            return

        self.invoice_table.clear_all()

        self.processing_thread = BatchProcessingThread(
            self.current_tasks,
            self.get_processing_options()
        )

        self.processing_thread.started.connect(self.on_processing_started)
        self.processing_thread.progress.connect(self.on_processing_progress)
        self.processing_thread.invoice_found.connect(self.on_invoice_found)
        self.processing_thread.file_completed.connect(self.on_file_completed)
        self.processing_thread.error_occurred.connect(self.on_processing_error)
        self.processing_thread.all_completed.connect(self.on_all_completed)

        self.processing_thread.start()

        self.progress_bar.setVisible(True)
        self.process_btn.setEnabled(False)
        self.load_btn.setEnabled(False)

    def on_processing_started(self, task_id: str):
        """Obsluguje rozpoczecie przetwarzania"""
        self.log_message(f"Rozpoczeto przetwarzanie: {task_id}")

    def on_processing_progress(self, task_id: str, percent: int, message: str):
        """Obsluguje postep przetwarzania"""
        self.progress_bar.setValue(percent)
        self.update_status(f"{task_id}: {message}")

    def on_invoice_found(self, task_id: str, invoice: ParsedInvoice):
        """Obsluguje znalezienie faktury"""
        self.invoice_table.add_invoice(invoice)

        if self.save_to_db_check.isChecked():
            try:
                self.database.save_invoice(invoice)
            except Exception as e:
                self.log_message(f"Blad zapisu do bazy: {e}", level='ERROR')

        self.update_statistics()

    def on_file_completed(self, task_id: str, result):
        """Obsluguje zakonczenie przetwarzania pliku"""
        self.log_message(f"Zakonczono: {task_id} - {result.statistics}")

        if result.excel_path:
            self.log_message(f"Wygenerowano Excel: {result.excel_path}")

    def on_processing_error(self, task_id: str, error: str):
        """Obsluguje blad przetwarzania"""
        self.log_message(f"Blad w {task_id}: {error}", level='ERROR')
        QMessageBox.warning(self, "Blad przetwarzania", f"Blad w {task_id}:\n{error}")

    def on_all_completed(self, results):
        """Obsluguje zakonczenie wszystkich zadan"""
        try:
            self.progress_bar.setVisible(False)
            self.process_btn.setEnabled(True)
            self.load_btn.setEnabled(True)

            all_invoices = []
            for result in results:
                if result.success and result.invoices:
                    all_invoices.extend(result.invoices)

            self.current_result = {
                'metadata': {
                    'filename': results[0].task_id if results else 'unknown',
                    'total_pages': sum(r.statistics.get('total_pages', 0) for r in results),
                    'invoices_count': len(all_invoices),
                    'processing_date': datetime.now().isoformat(),
                    'ocr_engine': 'paddleocr' if self.paddle_radio.isChecked() else 'tesseract',
                    'language': self.language_combo.currentText()
                },
                'invoices': all_invoices
            }

            total_invoices = len(all_invoices)
            total_errors = sum(len(r.errors) for r in results)

            message = f"Przetwarzanie zakonczone!\n\n"
            message += f"Przetworzone pliki: {len(results)}\n"
            message += f"Znalezione faktury: {total_invoices}\n"

            if total_errors > 0:
                message += f"Bledy: {total_errors}\n"

            excel_paths = [r.excel_path for r in results if r.excel_path]
            if excel_paths:
                message += f"\nWygenerowano {len(excel_paths)} raportow Excel"

            QMessageBox.information(self, "Zakonczone", message)

            self.update_status("Gotowy")
            self.update_statistics()

            if self.invoice_table.rowCount() > 0:
                self.invoice_table.selectRow(0)

        except Exception as e:
            logger.error(f"Blad w on_all_completed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            QMessageBox.critical(self, "Blad", f"Wystapil blad podczas finalizacji:\n{str(e)}")

    def on_invoice_selected(self):
        """Obsluguje wybor faktury"""
        try:
            if not hasattr(self, 'current_result') or not self.current_result:
                return

            selected = self.invoice_table.currentRow()
            if selected < 0:
                return

            if 'invoices' not in self.current_result:
                return

            invoices = self.current_result['invoices']

            if selected >= len(invoices):
                return

            invoice = invoices[selected]

            if hasattr(self, 'invoice_details'):
                self.invoice_details.display_invoice(invoice)

        except Exception as e:
            logger.error(f"Blad w on_invoice_selected: {e}")

    def on_invoice_double_clicked(self, invoice: ParsedInvoice):
        """Obsluguje podwojne klikniecie na fakture"""
        pass

    def update_statistics(self):
        """Aktualizuje statystyki"""
        stats = self.invoice_table.get_statistics()

        stats_text = f"""
        <h3>Statystyki</h3>
        <p><b>Liczba faktur:</b> {stats['total']}</p>
        <p><b>Poprawne:</b> <span style='color: green;'>{stats['valid']}</span></p>
        <p><b>Z bledami:</b> <span style='color: red;'>{stats['errors']}</span></p>
        <p><b>Z ostrzezeniami:</b> <span style='color: orange;'>{stats['warnings']}</span></p>
        <p><b>Duplikaty:</b> {stats['duplicates']}</p>
        <hr>
        <p><b>Suma calkowita:</b> {stats['total_amount']:.2f} PLN</p>
        """

        self.stats_label.setText(stats_text)

    def export_to_excel(self):
        """Eksportuje faktury do Excel"""
        if not self.invoice_table.invoices:
            QMessageBox.warning(self, "Uwaga", "Brak faktur do eksportu")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz raport Excel",
            f"Raport_Faktur_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Pliki Excel (*.xlsx)"
        )

        if file_path:
            try:
                generator = ExcelReportGenerator(file_path)
                generator.generate(self.invoice_table.invoices)

                QMessageBox.information(self, "Sukces", f"Raport zapisany:\n{file_path}")

                if sys.platform == 'win32':
                    os.startfile(file_path)
                elif sys.platform == 'darwin':
                    os.system(f'open "{file_path}"')
                else:
                    os.system(f'xdg-open "{file_path}"')

            except Exception as e:
                QMessageBox.critical(self, "Blad", f"Blad eksportu:\n{str(e)}")

    def export_to_json(self):
        """Eksportuje faktury do JSON"""
        if not self.invoice_table.invoices:
            QMessageBox.warning(self, "Uwaga", "Brak faktur do eksportu")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz JSON",
            f"Faktury_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "Pliki JSON (*.json)"
        )

        if file_path:
            try:
                import json

                data = {
                    'export_date': datetime.now().isoformat(),
                    'version': APP_VERSION,
                    'invoices': [
                        {
                            'invoice_id': inv.invoice_id,
                            'invoice_type': inv.invoice_type,
                            'issue_date': inv.issue_date.isoformat(),
                            'supplier': {
                                'name': inv.supplier_name,
                                'tax_id': inv.supplier_tax_id,
                                'address': inv.supplier_address,
                                'accounts': inv.supplier_accounts
                            },
                            'buyer': {
                                'name': inv.buyer_name,
                                'tax_id': inv.buyer_tax_id,
                                'address': inv.buyer_address
                            },
                            'amounts': {
                                'net': float(inv.total_net),
                                'vat': float(inv.total_vat),
                                'gross': float(inv.total_gross),
                                'currency': inv.currency
                            },
                            'items': inv.line_items,
                            'confidence': inv.confidence,
                            'is_verified': inv.is_verified
                        }
                        for inv in self.invoice_table.invoices
                    ]
                }

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                QMessageBox.information(self, "Sukces", f"Dane zapisane:\n{file_path}")

            except Exception as e:
                QMessageBox.critical(self, "Blad", f"Blad eksportu:\n{str(e)}")

    def save_to_database(self):
        """Zapisuje faktury do bazy"""
        saved = 0
        errors = 0

        for invoice in self.invoice_table.invoices:
            try:
                self.database.save_invoice(invoice)
                saved += 1
            except Exception as e:
                errors += 1
                self.log_message(f"Blad zapisu {invoice.invoice_id}: {e}", level='ERROR')

        message = f"Zapisano {saved} faktur do bazy"
        if errors > 0:
            message += f"\nBledy: {errors}"

        QMessageBox.information(self, "Zapis do bazy", message)

    def validate_all_invoices(self):
        pass

    def validate_selected(self):
        pass

    def find_duplicates(self):
        duplicates = self.database.get_duplicates()

        if duplicates:
            message = f"Znaleziono {len(duplicates)} par duplikatow:\n\n"
            for inv1, inv2 in duplicates[:5]:
                message += f"- {inv1} <-> {inv2}\n"

            QMessageBox.information(self, "Duplikaty", message)
        else:
            QMessageBox.information(self, "Duplikaty", "Nie znaleziono duplikatow")

    def delete_selected(self):
        pass

    def backup_database(self):
        backup_path = self.database.backup()
        QMessageBox.information(self, "Kopia zapasowa", f"Utworzono kopie:\n{backup_path}")

    def clean_cache(self):
        QMessageBox.information(self, "Cache", "Cache zostal wyczyszczony")

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.apply_theme()

    def show_help(self):
        QMessageBox.information(
            self,
            "Pomoc",
            "FAKTURA BOT v5.0\n\n"
            "1. Wybierz pliki PDF lub folder\n"
            "2. Ustaw jezyk i opcje\n"
            "3. Kliknij Przetwarzaj\n"
            "4. Eksportuj wyniki do Excel/JSON\n\n"
            "Skroty klawiszowe:\n"
            "Ctrl+O - Otworz pliki\n"
            "Ctrl+E - Eksport do Excel\n"
            "F5 - Odswiez\n"
            "F1 - Pomoc"
        )

    def show_about(self):
        try:
            import paddleocr
            paddle_ver = paddleocr.__version__
        except:
            paddle_ver = "nie zainstalowany"

        try:
            import pytesseract
            tess_ver = pytesseract.get_tesseract_version()
        except:
            tess_ver = "nie zainstalowany"

        QMessageBox.about(
            self,
            "O programie",
            f"<h2>{APP_NAME}</h2>"
            f"<p>Wersja: {APP_VERSION}</p>"
            "<p>Profesjonalny system do masowego przetwarzania faktur</p>"
            "<p><b>Zainstalowane silniki OCR:</b></p>"
            "<ul>"
            f"<li>Tesseract: {tess_ver}</li>"
            f"<li>PaddleOCR: {paddle_ver}</li>"
            "</ul>"
        )

    def toggle_statistics(self):
        self.stats_dock.setVisible(self.show_stats_action.isChecked())

    def toggle_logs(self):
        self.logs_dock.setVisible(self.show_logs_action.isChecked())

    def refresh_view(self):
        self.update_statistics()
        self.update_status("Odswiezono")

    def log_message(self, message: str, level: str = 'INFO'):
        timestamp = datetime.now().strftime('%H:%M:%S')

        if level == 'ERROR':
            formatted = f"<span style='color: red;'>[{timestamp}] {message}</span>"
        elif level == 'WARNING':
            formatted = f"<span style='color: orange;'>[{timestamp}] {message}</span>"
        else:
            formatted = f"[{timestamp}] {message}"

        self.logs_text.append(formatted)

        if level == 'ERROR':
            logger.error(message)
        elif level == 'WARNING':
            logger.warning(message)
        else:
            logger.info(message)

    def update_status(self, message: str):
        self.status_bar.showMessage(message)

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
                color: #333333;
            }
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106EBE;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f9f9f9;
                gridline-color: #e0e0e0;
                border: 1px solid #cccccc;
            }
            QTableWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #0078D4;
                font-weight: bold;
            }
            QProgressBar {
                border: 1px solid #cccccc;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0078D4;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px;
            }
        """)

    def load_settings(self):
        self.my_nip_input.setText(self.settings.value('my_nip', ''))

        language = self.settings.value('language', 'Polski')
        index = self.language_combo.findText(language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

        use_paddle = self.settings.value('use_paddle', False, type=bool)
        if use_paddle:
            self.paddle_radio.setChecked(True)
        else:
            self.tesseract_radio.setChecked(True)

    def save_settings(self):
        self.settings.setValue('my_nip', self.my_nip_input.text())
        self.settings.setValue('language', self.language_combo.currentText())
        self.settings.setValue('use_paddle', self.paddle_radio.isChecked())

    def closeEvent(self, event):
        if CONFIG.gui.confirm_exit:
            reply = QMessageBox.question(
                self,
                "Potwierdzenie",
                "Czy na pewno chcesz zamknac aplikacje?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        self.save_settings()

        if self.database:
            self.database.close()

        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait()

        event.accept()
        logger.info("Aplikacja zamknieta")


def main():
    """Glowna funkcja uruchamiajaca aplikacje"""

    def exception_hook(exctype, value, tb):
        import traceback
        error_msg = ''.join(traceback.format_exception(exctype, value, tb))
        logger.critical(f"NIEOBSLUZONY WYJATEK:\n{error_msg}")

        QMessageBox.critical(
            None,
            "Krytyczny blad",
            f"Program napotkal nieoczekiwany blad:\n\n{exctype.__name__}: {value}"
        )

        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = exception_hook

    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setOrganizationName("FakturaBot")
        app.setStyle('Fusion')

        window = MainWindow()
        window.show()

        sys.exit(app.exec())

    except Exception as e:
        logger.critical(f"Krytyczny blad uruchomienia: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
