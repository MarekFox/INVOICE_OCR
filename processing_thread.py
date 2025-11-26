"""
FAKTURA BOT v5.0 - Processing Threads
=====================================
Wielowątkowe przetwarzanie dokumentów
"""

import os
import time
import traceback
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
import logging

from pdf2image import convert_from_path
from PIL import Image

from config import CONFIG, POPPLER_PATH
from language_config import LanguageDetector, get_language_config
from ocr_engines import HybridOCREngine, OCRResult
from invoice_separator import AdvancedSeparator, InvoiceBoundary
from parsers import SmartInvoiceParser, ParsedInvoice
from validators import InvoiceValidator, ComparisonValidator
from excel_generator import ExcelReportGenerator
from utils import FileUtils

logger = logging.getLogger(__name__)

@dataclass
class ProcessingTask:
    """Zadanie przetwarzania"""
    file_path: str
    task_id: str
    priority: int = 0
    options: Dict = None
    
@dataclass
class ProcessingResult:
    """Wynik przetwarzania"""
    task_id: str
    success: bool
    invoices: List[ParsedInvoice]
    excel_path: Optional[str]
    processing_time: float
    errors: List[str]
    statistics: Dict

class BatchProcessingThread(QThread):
    """Wątek do przetwarzania wsadowego wielu plików"""
    
    # Sygnały
    started = pyqtSignal(str)  # task_id
    progress = pyqtSignal(str, int, str)  # task_id, percent, message
    file_completed = pyqtSignal(str, ProcessingResult)  # task_id, result
    invoice_found = pyqtSignal(str, ParsedInvoice)  # task_id, invoice
    error_occurred = pyqtSignal(str, str)  # task_id, error_message
    all_completed = pyqtSignal(list)  # List[ProcessingResult]
    
    def __init__(self, tasks: List[ProcessingTask], settings: Dict):
        super().__init__()
        self.tasks = sorted(tasks, key=lambda x: x.priority, reverse=True)
        self.settings = settings
        self.results = []
        self._stop_requested = False
        self._pause_requested = False
        self._mutex = QMutex()
        
    def run(self):
        """Główna pętla przetwarzania"""
        logger.info(f"Rozpoczęto przetwarzanie {len(self.tasks)} plików")
        start_time = time.time()
        
        for task in self.tasks:
            if self._stop_requested:
                logger.info("Przerwano przetwarzanie")
                break
                
            while self._pause_requested:
                time.sleep(0.1)
                
            try:
                self.started.emit(task.task_id)
                result = self._process_single_file(task)
                self.results.append(result)
                self.file_completed.emit(task.task_id, result)
                
            except Exception as e:
                logger.error(f"Błąd przetwarzania {task.file_path}: {e}")
                error_result = ProcessingResult(
                    task_id=task.task_id,
                    success=False,
                    invoices=[],
                    excel_path=None,
                    processing_time=0,
                    errors=[str(e)],
                    statistics={}
                )
                self.results.append(error_result)
                self.error_occurred.emit(task.task_id, str(e))
                
        total_time = time.time() - start_time
        logger.info(f"Zakończono przetwarzanie w {total_time:.2f}s")
        self.all_completed.emit(self.results)
        
    def _process_single_file(self, task: ProcessingTask) -> ProcessingResult:
        """Przetwarza pojedynczy plik PDF"""
        file_start = time.time()
        errors = []
        invoices = []
        excel_path = None
        statistics = {}
        
        try:
            # 1. Konwersja PDF na obrazy
            self.progress.emit(task.task_id, 10, "Konwersja PDF...")
            images = self._convert_pdf_to_images(task.file_path)
            statistics['total_pages'] = len(images)
            
            # 2. OCR wszystkich stron
            self.progress.emit(task.task_id, 20, "Rozpoznawanie tekstu (OCR)...")
            ocr_results = self._perform_ocr(images, task)
            
            # 3. Separacja na faktury
            self.progress.emit(task.task_id, 40, "Wykrywanie granic faktur...")
            boundaries = self._separate_invoices(ocr_results, task)
            statistics['invoices_detected'] = len(boundaries)
            
            # 4. Parsowanie każdej faktury
            self.progress.emit(task.task_id, 60, "Parsowanie danych...")
            for i, boundary in enumerate(boundaries):
                invoice_text = self._merge_boundary_text(ocr_results, boundary)
                parsed = self._parse_invoice(invoice_text, boundary, task)
                
                if parsed:
                    invoices.append(parsed)
                    self.invoice_found.emit(task.task_id, parsed)
                    
                progress = 60 + int((i / len(boundaries)) * 30)
                self.progress.emit(
                    task.task_id, 
                    progress, 
                    f"Parsowanie faktury {i+1}/{len(boundaries)}"
                )
                
            # 5. Walidacja i oznaczanie
            self.progress.emit(task.task_id, 90, "Walidacja danych...")
            self._validate_invoices(invoices, task)
            
            # 6. Wykrywanie duplikatów
            duplicates = ComparisonValidator.find_duplicates(
                [self._invoice_to_dict(inv) for inv in invoices]
            )
            if duplicates:
                statistics['duplicates_found'] = len(duplicates)
                for i, j in duplicates:
                    invoices[i].is_duplicate = True
                    invoices[j].is_duplicate = True
                    
            # 7. Generowanie Excel
            if task.options.get('generate_excel', True):
                self.progress.emit(task.task_id, 95, "Generowanie raportu Excel...")
                excel_path = self._generate_excel(invoices, task)
                
            # Statystyki końcowe
            statistics.update({
                'invoices_parsed': len(invoices),
                'invoices_valid': sum(1 for inv in invoices if inv.is_verified),
                'invoices_with_errors': sum(1 for inv in invoices if inv.parsing_errors),
                'total_amount': sum(float(inv.total_gross) for inv in invoices),
                'processing_time': time.time() - file_start
            })
            
            self.progress.emit(task.task_id, 100, "Zakończono!")
            
            return ProcessingResult(
                task_id=task.task_id,
                success=True,
                invoices=invoices,
                excel_path=excel_path,
                processing_time=time.time() - file_start,
                errors=errors,
                statistics=statistics
            )
            
        except Exception as e:
            logger.error(f"Krytyczny błąd w _process_single_file: {e}")
            logger.error(traceback.format_exc())
            raise
            
    def _convert_pdf_to_images(self, pdf_path: str) -> List[Image.Image]:
        """Konwertuje PDF na obrazy"""
        try:
            images = convert_from_path(
                pdf_path,
                dpi=CONFIG.ocr.dpi,
                poppler_path=POPPLER_PATH
            )
            logger.info(f"Skonwertowano {len(images)} stron z {pdf_path}")
            return images
            
        except Exception as e:
            logger.error(f"Błąd konwersji PDF: {e}")
            raise
            
    def _perform_ocr(self, images: List[Image.Image], task: ProcessingTask) -> List[OCRResult]:
        """Wykonuje OCR na wszystkich obrazach - Z TIMEOUTEM"""
        results = []
        
        # Wykryj język jeśli auto
        language = task.options.get('language', 'Polski')
        if language == 'Auto':
            logger.info("🔍 Wykrywanie języka...")
            engine = HybridOCREngine('Polski')
            first_result = engine.extract_text(images[0], strategy='fast')
            language = LanguageDetector.detect(first_result.text)
            logger.info(f"✅ Wykryto język: {language}")
            
        # OCR wszystkich stron
        use_paddle = task.options.get('use_paddleocr', False)
        strategy = 'accurate' if use_paddle else 'fast'
        
        logger.info(f"🔧 Rozpoczynam OCR: silnik={'PaddleOCR' if use_paddle else 'Tesseract'}, strategia={strategy}")
        
        engine = HybridOCREngine(language)
        
        for i, image in enumerate(images):
            logger.info(f"📄 OCR strony {i+1}/{len(images)}...")
            
            try:
                # ===================== TIMEOUT NA OCR =====================
                import threading
                
                result_container = [None]
                error_container = [None]
                
                def ocr_worker():
                    """Worker thread dla OCR"""
                    try:
                        result_container[0] = engine.extract_text(image, strategy=strategy)
                        logger.info(f"✅ OCR strony {i+1} zakończony ({len(result_container[0].text)} znaków)")
                    except Exception as e:
                        error_container[0] = e
                        logger.error(f"❌ Błąd OCR w workerze: {e}")
                
                # Uruchom OCR w osobnym wątku z timeoutem
                ocr_thread = threading.Thread(target=ocr_worker, daemon=True)
                ocr_thread.start()
                
                # Czekaj max 60 sekund
                ocr_thread.join(timeout=60.0)
                
                if ocr_thread.is_alive():
                    # Timeout!
                    logger.error(f"⏱️ TIMEOUT OCR strony {i+1} (>60s)")
                    results.append(OCRResult(
                        text="[TIMEOUT - OCR przekroczył 60 sekund]",
                        confidence=0,
                        language=language,
                        engine="timeout",
                        processing_time=60.0,
                        word_boxes=[]
                    ))
                elif error_container[0]:
                    # Błąd w workerze
                    raise error_container[0]
                elif result_container[0]:
                    # Sukces
                    results.append(result_container[0])
                else:
                    # Nieznany stan
                    logger.warning(f"⚠️ OCR zwrócił None dla strony {i+1}")
                    results.append(OCRResult(
                        text="",
                        confidence=0,
                        language=language,
                        engine="unknown_error",
                        processing_time=0,
                        word_boxes=[]
                    ))
                # ==========================================================
                    
                progress = 20 + int((i / len(images)) * 20)
                self.progress.emit(
                    task.task_id,
                    progress,
                    f"OCR {i+1}/{len(images)}"
                )
                
            except Exception as e:
                logger.error(f"❌ Błąd OCR strony {i+1}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                results.append(OCRResult(
                    text=f"[BŁĄD OCR: {str(e)}]",
                    confidence=0,
                    language=language,
                    engine="error",
                    processing_time=0,
                    word_boxes=[]
                ))
                
        logger.info(f"✅ OCR zakończony: {len(results)} stron przetworzonych")
        return results

    def _separate_invoices(self, ocr_results: List[OCRResult], task: ProcessingTask) -> List[InvoiceBoundary]:
        """Rozdziela dokument na pojedyncze faktury"""
        if not task.options.get('auto_separate', True):
            # Traktuj cały dokument jako jedną fakturę
            return [InvoiceBoundary(
                start_page=1,
                end_page=len(ocr_results),
                confidence=1.0,
                invoice_type='SINGLE'
            )]
            
        # Użyj separatora
        language = task.options.get('language', 'Polski')
        separator = AdvancedSeparator(language, use_ml=False)
        
        pages_text = [result.text for result in ocr_results]
        boundaries = separator.separate(pages_text)
        
        return boundaries
        
    def _merge_boundary_text(self, ocr_results: List[OCRResult], boundary: InvoiceBoundary) -> str:
        """Łączy tekst z granic faktury"""
        start_idx = boundary.start_page - 1
        end_idx = boundary.end_page
        
        texts = []
        for i in range(start_idx, min(end_idx, len(ocr_results))):
            if ocr_results[i].text:
                texts.append(ocr_results[i].text)
                
        return '\n\n--- NOWA STRONA ---\n\n'.join(texts)
        
    def _parse_invoice(self, text: str, boundary: InvoiceBoundary, task: ProcessingTask) -> Optional[ParsedInvoice]:
        """Parsuje pojedynczą fakturę - Z OBSŁUGĄ BŁĘDÓW"""
        try:
            language = task.options.get('language', 'Polski')
            user_tax_id = task.options.get('user_tax_id', '')
            
            logger.info(f"🔍 Rozpoczynam parsowanie (język: {language}, NIP użytkownika: {user_tax_id})")
            
            parser = SmartInvoiceParser(text, language, user_tax_id)
            invoice = parser.parse()
            
            # Dodaj informacje o zakresie stron
            invoice.page_range = (boundary.start_page, boundary.end_page)
            
            logger.info(f"✅ Sparsowano: {invoice.invoice_id}")
            return invoice
            
        except Exception as e:
            logger.error(f"❌ Błąd parsowania faktury: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Nie zwracaj None - zwróć częściowo wypełnioną fakturę
            from datetime import datetime
            from decimal import Decimal
            
            error_invoice = ParsedInvoice(
                invoice_id=f"ERROR_{boundary.start_page}",
                invoice_type="BŁĄD",
                issue_date=datetime.now(),
                sale_date=datetime.now(),
                due_date=datetime.now(),
                supplier_name="Błąd parsowania",
                supplier_tax_id="Brak",
                supplier_address="Brak",
                supplier_accounts=[],
                buyer_name="Brak",
                buyer_tax_id="Brak",
                buyer_address="Brak",
                currency="PLN",
                language=language,
                raw_text=text[:500]  # Pierwsze 500 znaków
            )
            
            error_invoice.parsing_errors.append(f"Krytyczny błąd parsowania: {str(e)}")
            return error_invoice
            
    def _validate_invoices(self, invoices: List[ParsedInvoice], task: ProcessingTask):
        """Waliduje wszystkie faktury"""
        language = task.options.get('language', 'Polski')
        validator = InvoiceValidator(language)
        
        for invoice in invoices:
            invoice_dict = self._invoice_to_dict(invoice)
            result = validator.validate(invoice_dict)
            
            invoice.is_verified = result.is_valid
            invoice.confidence = result.confidence
            invoice.parsing_errors.extend(result.errors)
            invoice.parsing_warnings.extend(result.warnings)
            
    def _invoice_to_dict(self, invoice: ParsedInvoice) -> Dict:
        """Konwertuje ParsedInvoice na słownik dla walidatora"""
        return {
            'invoice_id': invoice.invoice_id,
            'supplier': {
                'name': invoice.supplier_name,
                'tax_id': invoice.supplier_tax_id,
                'address': invoice.supplier_address,
                'bank_accounts': invoice.supplier_accounts
            },
            'buyer': {
                'name': invoice.buyer_name,
                'tax_id': invoice.buyer_tax_id,
                'address': invoice.buyer_address
            },
            'dates': {
                'issue_date': invoice.issue_date.strftime('%Y-%m-%d'),
                'sale_date': invoice.sale_date.strftime('%Y-%m-%d'),
                'due_date': invoice.due_date.strftime('%Y-%m-%d'),
                'payment_term_days': (invoice.due_date - invoice.issue_date).days
            },
            'line_items': invoice.line_items,
            'summary': {
                'total_net': float(invoice.total_net),
                'total_vat': float(invoice.total_vat),
                'total_gross': float(invoice.total_gross)
            }
        }
        
    def _generate_excel(self, invoices: List[ParsedInvoice], task: ProcessingTask) -> str:
        """Generuje raport Excel"""
        try:
            # Nazwa pliku wyjściowego
            base_name = Path(task.file_path).stem
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            excel_name = f"{base_name}_raport_{timestamp}.xlsx"
            excel_path = str(Path(task.file_path).parent / excel_name)
            
            # Generuj raport
            generator = ExcelReportGenerator(excel_path)
            options = {
                'include_charts': task.options.get('excel_charts', True),
                'include_pivot': task.options.get('excel_pivot', False),
                'include_validation': True
            }
            generator.generate(invoices, options)
            
            return excel_path
            
        except Exception as e:
            logger.error(f"Błąd generowania Excel: {e}")
            return None
            
    def stop(self):
        """Zatrzymuje przetwarzanie"""
        with QMutexLocker(self._mutex):
            self._stop_requested = True
            
    def pause(self):
        """Wstrzymuje przetwarzanie"""
        with QMutexLocker(self._mutex):
            self._pause_requested = True
            
    def resume(self):
        """Wznawia przetwarzanie"""
        with QMutexLocker(self._mutex):
            self._pause_requested = False

class QuickAnalysisThread(QThread):
    """Szybka analiza pojedynczego pliku"""
    
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        
    def run(self):
        """Wykonuje szybką analizę"""
        try:
            # Konwertuj tylko pierwszą stronę
            images = convert_from_path(
                self.file_path,
                dpi=150,  # Niższa rozdzielczość dla szybkości
                poppler_path=CONFIG.POPPLER_PATH,
                first_page=1,
                last_page=1
            )
            
            if not images:
                self.error.emit("Nie można otworzyć pliku PDF")
                return
                
            # Szybki OCR pierwszej strony
            engine = HybridOCREngine('Polski')
            result = engine.extract_text(images[0], strategy='fast')
            
            # Wykryj język
            detected_language = LanguageDetector.detect(result.text)
            
            # Szybkie parsowanie
            parser = SmartInvoiceParser(result.text, detected_language)
            invoice = parser.parse()
            
            # Przygotuj wyniki
            analysis = {
                'invoice_number': invoice.invoice_id,
                'invoice_type': invoice.invoice_type,
                'supplier': invoice.supplier_name,
                'buyer': invoice.buyer_name,
                'date': invoice.issue_date.strftime('%Y-%m-%d'),
                'amount': float(invoice.total_gross),
                'currency': invoice.currency,
                'language': detected_language,
                'confidence': invoice.confidence,
                'page_count': self._count_pages()
            }
            
            self.result_ready.emit(analysis)
            
        except Exception as e:
            logger.error(f"Błąd szybkiej analizy: {e}")
            self.error.emit(str(e))
            
    def _count_pages(self) -> int:
        """Liczy strony w PDF"""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(self.file_path)
            return len(reader.pages)
        except:
            return 0

class BackgroundValidator(QThread):
    """Walidator działający w tle"""
    
    validation_completed = pyqtSignal(str, dict)  # invoice_id, validation_result
    
    def __init__(self, invoices: List[ParsedInvoice]):
        super().__init__()
        self.invoices = invoices
        
    def run(self):
        """Wykonuje walidację w tle"""
        for invoice in self.invoices:
            try:
                # Walidacja podstawowa
                validator = InvoiceValidator(invoice.language)
                invoice_dict = self._invoice_to_dict(invoice)
                result = validator.validate(invoice_dict)
                
                # Opcjonalna weryfikacja online (NIP w GUS, etc.)
                if CONFIG.validation.external_api_validation:
                    self._verify_online(invoice)
                    
                # Emituj wynik
                self.validation_completed.emit(
                    invoice.invoice_id,
                    {
                        'is_valid': result.is_valid,
                        'confidence': result.confidence,
                        'errors': result.errors,
                        'warnings': result.warnings
                    }
                )
                
            except Exception as e:
                logger.error(f"Błąd walidacji {invoice.invoice_id}: {e}")
                
    def _invoice_to_dict(self, invoice: ParsedInvoice) -> Dict:
        """Konwertuje fakturę na słownik"""
        # Implementacja jak w BatchProcessingThread
        pass
        
    def _verify_online(self, invoice: ParsedInvoice):
        """Weryfikacja online (GUS, ANAF, etc.)"""
        from utils import CompanyDataAPI
        
        # Weryfikuj NIP dostawcy
        if invoice.language == 'Polski' and invoice.supplier_tax_id:
            result = CompanyDataAPI.verify_nip_gus(invoice.supplier_tax_id)
            if result and not result['valid']:
                invoice.parsing_warnings.append(f"NIP {invoice.supplier_tax_id} nie znaleziony w GUS")
                
        elif invoice.language == 'Rumuński' and invoice.supplier_tax_id:
            result = CompanyDataAPI.verify_cui_anaf(invoice.supplier_tax_id)
            if result and not result['valid']:
                invoice.parsing_warnings.append(f"CUI {invoice.supplier_tax_id} nie znaleziony w ANAF")