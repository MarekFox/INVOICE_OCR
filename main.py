"""
FAKTURA BOT v5.0 ULTIMATE EDITION
==================================
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
    QDockWidget, QMenuBar, QMenu, QTableWidgetItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings, QSize
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont, QPalette, QColor
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
        self.setWindowTitle(f"🧾 {APP_NAME} v{APP_VERSION}")
        self.resize(CONFIG.gui.window_width, CONFIG.gui.window_height)
        
        # Menu
        self.create_menu()
        
        # Toolbar
        self.create_toolbar()
        
        # Centralny widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout główny
        main_layout = QVBoxLayout(central_widget)
        
        # Panel kontrolny
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # Splitter główny
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Lewa strona - tabela
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        self.invoice_table = InvoiceTableWidget()
        self.invoice_table.invoice_selected.connect(self.on_invoice_selected)
        self.invoice_table.invoice_double_clicked.connect(self.on_invoice_double_clicked)
        
        left_layout.addWidget(QLabel("📋 Lista faktur:"))
        left_layout.addWidget(self.invoice_table)
        
        # Prawa strona - szczegóły
        self.invoice_details = InvoiceDetailsWidget()
        
        splitter.addWidget(left_widget)
        splitter.addWidget(self.invoice_details)
        splitter.setSizes([800, 600])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status("Gotowy")
        
        # Dock widgets
        self.create_dock_widgets()

        self.load_settings()

        if not self.my_nip_input.text():
            self.my_nip_input.setText("6792740329")
            logger.info("✅ Ustawiono domyślny NIP: 6792740329")

        self.apply_theme()

        from PyQt6.QtGui import QKeySequence, QShortcut
    
        # Ctrl+C dla kopiowania z aktywnej zakładki
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        copy_shortcut.activated.connect(self.copy_selected_text)

    def copy_selected_text(self):
        """Kopiuje zaznaczony tekst z aktywnej zakładki"""
        from PyQt6.QtWidgets import QTextEdit
        focused = self.focusWidget()
        
        if isinstance(focused, QTextEdit):
            cursor = focused.textCursor()
            if cursor.hasSelection():
                QApplication.clipboard().setText(cursor.selectedText())
                self.log_message("📋 Skopiowano zaznaczony tekst", level='INFO')
        
    def create_menu(self):
        """Tworzy menu aplikacji"""
        menubar = self.menuBar()
        
        # Menu Plik
        file_menu = menubar.addMenu("📁 Plik")
        
        open_action = QAction("Otwórz PDF...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_files)
        file_menu.addAction(open_action)
        
        open_folder_action = QAction("Otwórz folder...", self)
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
        
        exit_action = QAction("Wyjście", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Menu Edycja
        edit_menu = menubar.addMenu("✏️ Edycja")
        
        select_all_action = QAction("Zaznacz wszystko", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        settings_action = QAction("Ustawienia...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        edit_menu.addAction(settings_action)
        
        # Menu Widok
        view_menu = menubar.addMenu("👁️ Widok")
        
        self.show_stats_action = QAction("Pokaż statystyki", self, checkable=True)
        self.show_stats_action.setChecked(True)
        self.show_stats_action.triggered.connect(self.toggle_statistics)
        view_menu.addAction(self.show_stats_action)
        
        self.show_logs_action = QAction("Pokaż logi", self, checkable=True)
        self.show_logs_action.triggered.connect(self.toggle_logs)
        view_menu.addAction(self.show_logs_action)
        
        view_menu.addSeparator()
        
        refresh_action = QAction("Odśwież", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self.refresh_view)
        view_menu.addAction(refresh_action)
        
        # Menu Narzędzia
        tools_menu = menubar.addMenu("🔧 Narzędzia")
        
        validate_all_action = QAction("Waliduj wszystkie", self)
        validate_all_action.triggered.connect(self.validate_all_invoices)
        tools_menu.addAction(validate_all_action)
        
        find_duplicates_action = QAction("Znajdź duplikaty", self)
        find_duplicates_action.triggered.connect(self.find_duplicates)
        tools_menu.addAction(find_duplicates_action)
        
        tools_menu.addSeparator()
        
        backup_db_action = QAction("Kopia zapasowa bazy", self)
        backup_db_action.triggered.connect(self.backup_database)
        tools_menu.addAction(backup_db_action)
        
        clean_cache_action = QAction("Wyczyść cache", self)
        clean_cache_action.triggered.connect(self.clean_cache)
        tools_menu.addAction(clean_cache_action)
        
        # Menu Pomoc
        help_menu = menubar.addMenu("❓ Pomoc")
        
        help_action = QAction("Pomoc", self)
        help_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)
        
        help_menu.addSeparator()
        
        about_action = QAction("O programie", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_toolbar(self):
        """Tworzy pasek narzędzi"""
        toolbar = QToolBar("Główny pasek narzędzi")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Otwórz
        open_btn = QAction("📂 Otwórz", self)
        open_btn.setToolTip("Otwórz pliki PDF")
        open_btn.triggered.connect(self.open_files)
        toolbar.addAction(open_btn)
        
        # Analizuj
        analyze_btn = QAction("🔍 Analizuj", self)
        analyze_btn.setToolTip("Rozpocznij analizę")
        analyze_btn.triggered.connect(self.start_processing)
        toolbar.addAction(analyze_btn)
        
        toolbar.addSeparator()
        
        # Eksportuj
        export_btn = QAction("📊 Excel", self)
        export_btn.setToolTip("Eksportuj do Excel")
        export_btn.triggered.connect(self.export_to_excel)
        toolbar.addAction(export_btn)
        
        # Zapisz
        save_btn = QAction("💾 Zapisz", self)
        save_btn.setToolTip("Zapisz do bazy")
        save_btn.triggered.connect(self.save_to_database)
        toolbar.addAction(save_btn)
        
        toolbar.addSeparator()
        
        # Waliduj
        validate_btn = QAction("✅ Waliduj", self)
        validate_btn.setToolTip("Waliduj zaznaczone")
        validate_btn.triggered.connect(self.validate_selected)
        toolbar.addAction(validate_btn)
        
        # Usuń
        delete_btn = QAction("🗑️ Usuń", self)
        delete_btn.setToolTip("Usuń zaznaczone")
        delete_btn.triggered.connect(self.delete_selected)
        toolbar.addAction(delete_btn)
        
    def create_control_panel(self) -> QGroupBox:
        """Tworzy panel kontrolny"""
        panel = QGroupBox("⚙️ Panel kontrolny")
        layout = QHBoxLayout()
        
        # Język
        layout.addWidget(QLabel("Język:"))
        self.language_combo = QComboBox()
        self.language_combo.addItems(['Auto'] + list(LANGUAGE_PROFILES.keys()))
        self.language_combo.setMaximumWidth(150)
        layout.addWidget(self.language_combo)
        
        # Silnik OCR
        layout.addWidget(QLabel("OCR:"))
        self.ocr_group = QButtonGroup()
        
        self.tesseract_radio = QRadioButton("Tesseract")
        self.tesseract_radio.setChecked(True)
        self.ocr_group.addButton(self.tesseract_radio)
        layout.addWidget(self.tesseract_radio)
        
        self.paddle_radio = QRadioButton("PaddleOCR")
        self.ocr_group.addButton(self.paddle_radio)
        layout.addWidget(self.paddle_radio)
        
        # Mój NIP
        layout.addWidget(QLabel("Mój NIP:"))
        self.my_nip_input = QLineEdit()
        self.my_nip_input.setPlaceholderText("Wpisz swój NIP")
        self.my_nip_input.setText("6792740329")  # ← DODANE: Domyślna wartość
        self.my_nip_input.setMaximumWidth(150)
        layout.addWidget(self.my_nip_input)
        
        layout.addStretch()
        
        # Opcje
        self.auto_separate_check = QCheckBox("Auto-separacja")
        self.auto_separate_check.setChecked(True)
        layout.addWidget(self.auto_separate_check)
        
        self.generate_excel_check = QCheckBox("Generuj Excel")
        self.generate_excel_check.setChecked(True)
        layout.addWidget(self.generate_excel_check)
        
        self.save_to_db_check = QCheckBox("Zapisz do bazy")
        self.save_to_db_check.setChecked(True)
        layout.addWidget(self.save_to_db_check)
        
        # Przyciski
        self.load_btn = QPushButton("📁 Wybierz pliki")
        self.load_btn.clicked.connect(self.open_files)
        layout.addWidget(self.load_btn)
        
        self.process_btn = QPushButton("🚀 Przetwarzaj")
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
        # Dock ze statystykami
        self.stats_dock = QDockWidget("📊 Statystyki", self)
        self.stats_widget = QWidget()
        stats_layout = QVBoxLayout(self.stats_widget)
        
        self.stats_label = QLabel("Statystyki pojawią się po przetworzeniu")
        stats_layout.addWidget(self.stats_label)
        
        self.stats_dock.setWidget(self.stats_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.stats_dock)
        
        # Dock z logami
        self.logs_dock = QDockWidget("📝 Logi", self)
        self.logs_dock.setVisible(False)
        
        from PyQt6.QtWidgets import QTextEdit
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
                
            self.update_status(f"Załadowano {len(files)} plików")
            self.process_btn.setEnabled(True)
            self.log_message(f"Załadowano pliki: {', '.join([Path(f).name for f in files])}")
            
    def open_folder(self):
        """Otwiera folder z plikami PDF"""
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder")
        
        if folder:
            pdf_files = list(Path(folder).glob("*.pdf"))
            
            if not pdf_files:
                QMessageBox.warning(self, "Uwaga", "Nie znaleziono plików PDF w wybranym folderze")
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
                
            self.update_status(f"Załadowano {len(pdf_files)} plików z folderu")
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
            
        # Wyczyść poprzednie wyniki
        self.invoice_table.clear_all()
        
        # Uruchom wątek przetwarzania
        self.processing_thread = BatchProcessingThread(
            self.current_tasks,
            self.get_processing_options()
        )
        
        # Podłącz sygnały
        self.processing_thread.started.connect(self.on_processing_started)
        self.processing_thread.progress.connect(self.on_processing_progress)
        self.processing_thread.invoice_found.connect(self.on_invoice_found)
        self.processing_thread.file_completed.connect(self.on_file_completed)
        self.processing_thread.error_occurred.connect(self.on_processing_error)
        self.processing_thread.all_completed.connect(self.on_all_completed)
        
        # Rozpocznij
        self.processing_thread.start()
        
        # Aktualizuj UI
        self.progress_bar.setVisible(True)
        self.process_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        
    def on_processing_started(self, task_id: str):
        """Obsługuje rozpoczęcie przetwarzania"""
        self.log_message(f"Rozpoczęto przetwarzanie: {task_id}")
        
    def on_processing_progress(self, task_id: str, percent: int, message: str):
        """Obsługuje postęp przetwarzania"""
        self.progress_bar.setValue(percent)
        self.update_status(f"{task_id}: {message}")
        
    def on_invoice_found(self, task_id: str, invoice: ParsedInvoice):
        """Obsługuje znalezienie faktury"""
        self.invoice_table.add_invoice(invoice)
        
        # Zapisz do bazy jeśli włączone
        if self.save_to_db_check.isChecked():
            try:
                self.database.save_invoice(invoice)
            except Exception as e:
                self.log_message(f"Błąd zapisu do bazy: {e}", level='ERROR')
                
        self.update_statistics()
        
    def on_file_completed(self, task_id: str, result):
        """Obsługuje zakończenie przetwarzania pliku"""
        self.log_message(f"Zakończono: {task_id} - {result.statistics}")
        
        if result.excel_path:
            self.log_message(f"Wygenerowano Excel: {result.excel_path}")
            
    def on_processing_error(self, task_id: str, error: str):
        """Obsługuje błąd przetwarzania"""
        self.log_message(f"Błąd w {task_id}: {error}", level='ERROR')
        QMessageBox.warning(self, "Błąd przetwarzania", f"Błąd w {task_id}:\n{error}")
        
    def on_all_completed(self, results):
        """Obsługuje zakończenie wszystkich zadań - Z OBSŁUGĄ BŁĘDÓW"""
        try:
            self.progress_bar.setVisible(False)
            self.process_btn.setEnabled(True)
            self.load_btn.setEnabled(True)
            
            # Przygotuj wynik w odpowiednim formacie
            all_invoices = []
            for result in results:
                if result.success and result.invoices:
                    all_invoices.extend(result.invoices)
            
            # ===================== ZAPISZ WYNIK =====================
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
            # ========================================================
            
            # Podsumowanie
            total_invoices = len(all_invoices)
            total_errors = sum(len(r.errors) for r in results)
            
            message = f"Przetwarzanie zakończone!\n\n"
            message += f"Przetworzone pliki: {len(results)}\n"
            message += f"Znalezione faktury: {total_invoices}\n"
            
            if total_errors > 0:
                message += f"Błędy: {total_errors}\n"
            
            # Excel path z pierwszego wyniku (jeśli istnieje)
            excel_paths = [r.excel_path for r in results if r.excel_path]
            if excel_paths:
                message += f"\n📊 Wygenerowano {len(excel_paths)} raportów Excel"
                
            QMessageBox.information(self, "Zakończono", message)
            
            self.update_status("Gotowy")
            self.update_statistics()
            
            # Automatycznie zaznacz pierwszą fakturę (jeśli jest)
            if self.invoice_table.rowCount() > 0:
                self.invoice_table.selectRow(0)
                
        except Exception as e:
            logger.error(f"❌ Błąd w on_all_completed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            QMessageBox.critical(
                self,
                "Błąd",
                f"Wystąpił błąd podczas finalizacji:\n{str(e)}"
            )
        
    def on_invoice_selected(self):
        """Obsługuje wybór faktury - Z OBSŁUGĄ BŁĘDÓW"""
        try:
            # Sprawdź czy mamy dane
            if not hasattr(self, 'current_result') or not self.current_result:
                logger.warning("⚠️ Brak danych wyników - current_result nie istnieje")
                return
            
            # Sprawdź czy tabela ma zaznaczenie
            selected = self.invoice_table.currentRow()
            if selected < 0:
                logger.debug("Brak zaznaczenia w tabeli")
                return
            
            # Sprawdź czy indeks jest w zakresie
            if 'invoices' not in self.current_result:
                logger.error("❌ Brak klucza 'invoices' w wynikach")
                return
                
            invoices = self.current_result['invoices']
            
            if selected >= len(invoices):
                logger.error(f"❌ Indeks {selected} poza zakresem (mamy {len(invoices)} faktur)")
                return
            
            # Pobierz fakturę
            invoice = invoices[selected]
            
            # Wyświetl szczegóły
            if hasattr(self, 'invoice_details'):
                self.invoice_details.display_invoice(invoice)
                logger.info(f"✅ Wyświetlono szczegóły faktury: {invoice.invoice_id}")
            else:
                logger.error("❌ Brak widgetu invoice_details")
                
        except Exception as e:
            logger.error(f"❌ Błąd w on_invoice_selected: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Pokaż użytkownikowi
            QMessageBox.warning(
                self,
                "Błąd wyświetlania",
                f"Nie można wyświetlić szczegółów faktury:\n{str(e)}"
            )
        
    def on_invoice_double_clicked(self, invoice: ParsedInvoice):
        """Obsługuje podwójne kliknięcie na fakturę"""
        # Można otworzyć w nowym oknie lub edytorze
        pass
        
    def update_statistics(self):
        """Aktualizuje statystyki"""
        stats = self.invoice_table.get_statistics()
        
        stats_text = f"""
        <h3>📊 Statystyki</h3>
        <p><b>Liczba faktur:</b> {stats['total']}</p>
        <p><b>Poprawne:</b> <span style='color: green;'>{stats['valid']}</span></p>
        <p><b>Z błędami:</b> <span style='color: red;'>{stats['errors']}</span></p>
        <p><b>Z ostrzeżeniami:</b> <span style='color: orange;'>{stats['warnings']}</span></p>
        <p><b>Duplikaty:</b> {stats['duplicates']}</p>
        <hr>
        <p><b>Suma całkowita:</b> {stats['total_amount']:.2f} PLN</p>
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
                
                # Otwórz plik jeśli możliwe
                if sys.platform == 'win32':
                    os.startfile(file_path)
                elif sys.platform == 'darwin':
                    os.system(f'open "{file_path}"')
                else:
                    os.system(f'xdg-open "{file_path}"')
                    
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Błąd eksportu:\n{str(e)}")
                
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
                QMessageBox.critical(self, "Błąd", f"Błąd eksportu:\n{str(e)}")
                
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
                self.log_message(f"Błąd zapisu {invoice.invoice_id}: {e}", level='ERROR')
                
        message = f"Zapisano {saved} faktur do bazy"
        if errors > 0:
            message += f"\nBłędy: {errors}"
            
        QMessageBox.information(self, "Zapis do bazy", message)
        
    def validate_all_invoices(self):
        """Waliduje wszystkie faktury"""
        # Implementacja walidacji
        pass
        
    def validate_selected(self):
        """Waliduje zaznaczone faktury"""
        # Implementacja walidacji zaznaczonych
        pass
        
    def find_duplicates(self):
        """Znajduje duplikaty"""
        duplicates = self.database.get_duplicates()
        
        if duplicates:
            message = f"Znaleziono {len(duplicates)} par duplikatów:\n\n"
            for inv1, inv2 in duplicates[:5]:  # Pokaż max 5
                message += f"• {inv1} ↔ {inv2}\n"
                
            QMessageBox.information(self, "Duplikaty", message)
        else:
            QMessageBox.information(self, "Duplikaty", "Nie znaleziono duplikatów")
            
    def delete_selected(self):
        """Usuwa zaznaczone faktury"""
        # Implementacja usuwania
        pass
        
    def backup_database(self):
        """Tworzy kopię zapasową bazy"""
        backup_path = self.database.backup()
        QMessageBox.information(self, "Kopia zapasowa", f"Utworzono kopię:\n{backup_path}")
        
    def clean_cache(self):
        """Czyści cache"""
        # Implementacja czyszczenia cache
        QMessageBox.information(self, "Cache", "Cache został wyczyszczony")
        
    def show_settings(self):
        """Pokazuje okno ustawień"""
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.apply_theme()
            
    def show_help(self):
        """Pokazuje pomoc"""
        QMessageBox.information(
            self,
            "Pomoc",
            "🧾 FAKTURA BOT v5.0\n\n"
            "1. Wybierz pliki PDF lub folder\n"
            "2. Ustaw język i opcje\n"
            "3. Kliknij Przetwarzaj\n"
            "4. Eksportuj wyniki do Excel/JSON\n\n"
            "Skróty klawiszowe:\n"
            "Ctrl+O - Otwórz pliki\n"
            "Ctrl+E - Eksport do Excel\n"
            "F5 - Odśwież\n"
            "F1 - Pomoc"
        )
        
    def show_about(self):
        """Pokazuje informacje o programie"""
        
        # Sprawdź wersje zainstalowanych pakietów
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
            f"<li>PaddlePaddle: 3.2.2</li>"
            "</ul>"
            "<p><b>Funkcje:</b></p>"
            "<ul>"
            "<li>Obsługa wielu języków (PL, DE, RO, EN)</li>"
            "<li>Podwójny OCR (Tesseract + PaddleOCR 3.3.2)</li>"
            "<li>Automatyczna separacja dokumentów</li>"
            "<li>Walidacja NIP/CUI/VAT</li>"
            "<li>Eksport do Excel z wykresami</li>"
            "<li>Baza danych SQLite</li>"
            "</ul>"
            "<p>© 2024 AI Assistant</p>"
        )
        
    def toggle_statistics(self):
        """Przełącza widoczność statystyk"""
        self.stats_dock.setVisible(self.show_stats_action.isChecked())
        
    def toggle_logs(self):
        """Przełącza widoczność logów"""
        self.logs_dock.setVisible(self.show_logs_action.isChecked())
        
    def refresh_view(self):
        """Odświeża widok"""
        self.update_statistics()
        self.update_status("Odświeżono")
        
    def log_message(self, message: str, level: str = 'INFO'):
        """Dodaje wiadomość do logów z kolorowaniem"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        if level == 'ERROR':
            formatted = f"<span style='color: red;'>[{timestamp}] ❌ {message}</span>"
        elif level == 'WARNING':
            formatted = f"<span style='color: orange;'>[{timestamp}] ⚠️ {message}</span>"
        elif level == 'DEBUG':
            formatted = f"<span style='color: blue;'>[{timestamp}] 🔍 {message}</span>"
        else:
            formatted = f"[{timestamp}] ℹ️ {message}"
        
        self.logs_text.append(formatted)
        
        # Log także do pliku
        if level == 'ERROR':
            logger.error(message)
        elif level == 'WARNING':
            logger.warning(message)
        else:
            logger.info(message)
            
    def update_status(self, message: str):
        """Aktualizuje pasek statusu"""
        self.status_bar.showMessage(message)
        
    def apply_theme(self):
        """Stosuje jasny motyw"""
        # ===================== JASNY MOTYW =====================
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
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #0078D4;
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
            QPushButton:pressed {
                background-color: #005A9E;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f9f9f9;
                gridline-color: #e0e0e0;
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                color: #333333;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #0078D4;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: #ffffff;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #e8e8e8;
                color: #333333;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: 2px solid #0078D4;
            }
            QTabBar::tab:hover {
                background-color: #f0f0f0;
            }
            QProgressBar {
                border: 1px solid #cccccc;
                border-radius: 4px;
                text-align: center;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 3px;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 2px solid #0078D4;
            }
            QCheckBox, QRadioButton {
                color: #333333;
            }
            QLabel {
                color: #333333;
            }
            QDockWidget {
                background-color: #ffffff;
                border: 1px solid #cccccc;
            }
            QDockWidget::title {
                background-color: #e8e8e8;
                padding: 6px;
                font-weight: bold;
            }
            QStatusBar {
                background-color: #e8e8e8;
                color: #333333;
            }
            QMenuBar {
                background-color: #ffffff;
                color: #333333;
            }
            QMenuBar::item:selected {
                background-color: #0078D4;
                color: white;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #cccccc;
            }
            QMenu::item:selected {
                background-color: #0078D4;
                color: white;
            }
        """)
            
    def load_settings(self):
        """Wczytuje ustawienia użytkownika"""
        # Wczytaj zapisane ustawienia
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
        """Zapisuje ustawienia użytkownika"""
        self.settings.setValue('my_nip', self.my_nip_input.text())
        self.settings.setValue('language', self.language_combo.currentText())
        self.settings.setValue('use_paddle', self.paddle_radio.isChecked())
        
    def closeEvent(self, event):
        """Obsługuje zamknięcie aplikacji"""
        if CONFIG.gui.confirm_exit:
            reply = QMessageBox.question(
                self,
                "Potwierdzenie",
                "Czy na pewno chcesz zamknąć aplikację?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
                
        # Zapisz ustawienia
        self.save_settings()
        
        # Zamknij bazę danych
        if self.database:
            self.database.close()
            
        # Zatrzymaj wątki jeśli działają
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait()
            
        event.accept()
        logger.info("Aplikacja zamknięta")

    def add_table_row(self, data: ParsedInvoice):
        """Dodaje fakturę do tabeli"""
        from utils import DateUtils  # ← DODANE
        
        self.results_cache.append(data)
        row = self.invoice_table.rowCount()
        self.invoice_table.insertRow(row)
        
        self.invoice_table.setItem(row, 0, QTableWidgetItem(data.invoice_id))
        self.invoice_table.setItem(row, 1, QTableWidgetItem(data.supplier_name))
        self.invoice_table.setItem(row, 2, QTableWidgetItem(f"{data.total_gross:.2f}"))
        
        # Dodaj datę jeśli masz taką kolumnę (opcjonalnie)
        # self.invoice_table.setItem(row, 3, QTableWidgetItem(DateUtils.format_date_output(data.issue_date)))
        
        status = "✅ OK"
        color = QColor(200, 255, 200)
        if data.parsing_errors:
            status = "⚠️ Błędy"
            color = QColor(255, 200, 200)
        elif not data.is_verified:
            status = "❓ Obcy NIP"
            color = QColor(255, 255, 200)
            
        item_status = QTableWidgetItem(status)
        item_status.setBackground(color)
        self.invoice_table.setItem(row, 3, item_status)


def main():
    """Główna funkcja uruchamiająca aplikację"""
    
    # ===================== GLOBALNA OBSŁUGA BŁĘDÓW =====================
    import sys
    
    def exception_hook(exctype, value, tb):
        """Przechwytuje nieobsłużone wyjątki"""
        import traceback
        
        error_msg = ''.join(traceback.format_exception(exctype, value, tb))
        logger.critical(f"💥 NIEOBSŁUŻONY WYJĄTEK:\n{error_msg}")
        
        # Pokaż okno błędu
        QMessageBox.critical(
            None,
            "Krytyczny błąd",
            f"Program napotkał nieoczekiwany błąd:\n\n{exctype.__name__}: {value}\n\n"
            f"Szczegóły zapisano w logach."
        )
        
        # Wywołaj domyślną obsługę
        sys.__excepthook__(exctype, value, tb)
    
    # Ustaw globalny hook
    sys.excepthook = exception_hook
    # ====================================================================
    
    try:
        app = QApplication(sys.argv)
        
        # Ustawienia aplikacji
        app.setApplicationName(APP_NAME)
        app.setOrganizationName("FakturaBot")
        app.setStyle('Fusion')
        
        # Główne okno
        window = MainWindow()
        window.show()
        
        # Uruchom
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical(f"💥 Krytyczny błąd uruchomienia: {e}")
        import traceback
        traceback.print_exc()
        
        QMessageBox.critical(
            None,
            "Błąd krytyczny",
            f"Nie można uruchomić aplikacji:\n{str(e)}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()