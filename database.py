"""
FAKTURA BOT v5.0 - Database Module
===================================
Opcjonalna baza danych do przechowywania faktur
"""

import sqlite3
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal
import logging

from parsers import ParsedInvoice
from config import CONFIG, DEFAULT_PATHS

logger = logging.getLogger(__name__)

class InvoiceDatabase:
    """Baza danych SQLite dla faktur"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_dir = DEFAULT_PATHS['data_dir']
            db_dir = Path(db_dir)
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / 'invoices.db')
            
        self.db_path = db_path
        self.conn = None
        self.init_database()
        
    def init_database(self):
        """Inicjalizuje strukturę bazy danych"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Włącz foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")
        
        # Tabela faktur
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT UNIQUE NOT NULL,
                invoice_type TEXT,
                issue_date DATE,
                sale_date DATE,
                due_date DATE,
                supplier_name TEXT,
                supplier_tax_id TEXT,
                supplier_address TEXT,
                supplier_accounts TEXT,  -- JSON array
                buyer_name TEXT,
                buyer_tax_id TEXT,
                buyer_address TEXT,
                total_net REAL,
                total_vat REAL,
                total_gross REAL,
                currency TEXT,
                payment_method TEXT,
                payment_status TEXT,
                paid_amount REAL DEFAULT 0,
                language TEXT,
                confidence REAL,
                is_verified BOOLEAN DEFAULT 0,
                is_duplicate BOOLEAN DEFAULT 0,
                belongs_to_user BOOLEAN DEFAULT 0,
                page_range TEXT,  -- JSON array [start, end]
                file_path TEXT,
                file_hash TEXT,
                raw_text TEXT,
                parsing_errors TEXT,  -- JSON array
                parsing_warnings TEXT,  -- JSON array
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_by TEXT,
                notes TEXT
            )
        """)
        
        # Tabela pozycji faktur
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT NOT NULL,
                position INTEGER,
                description TEXT,
                quantity REAL,
                unit_price REAL,
                net_amount REAL,
                vat_rate REAL,
                vat_amount REAL,
                gross_amount REAL,
                FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE
            )
        """)
        
        # Tabela załączników
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT NOT NULL,
                file_name TEXT,
                file_type TEXT,
                file_size INTEGER,
                file_data BLOB,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE
            )
        """)
        
        # Tabela historii zmian
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT,
                action TEXT,  -- CREATE, UPDATE, DELETE, VERIFY
                user TEXT,
                changes TEXT,  -- JSON
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela ustawień użytkownika
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indeksy dla wydajności
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoices(issue_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_supplier_tax ON invoices(supplier_tax_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_buyer_tax ON invoices(buyer_tax_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_invoice_status ON invoices(payment_status)")
        
        self.conn.commit()
        
    def save_invoice(self, invoice: ParsedInvoice, file_path: str = None, file_hash: str = None) -> int:
        """Zapisuje fakturę do bazy"""
        try:
            cursor = self.conn.cursor()
            
            # Sprawdź czy faktura już istnieje
            existing = cursor.execute(
                "SELECT id FROM invoices WHERE invoice_id = ?",
                (invoice.invoice_id,)
            ).fetchone()
            
            if existing:
                # Aktualizuj istniejącą
                invoice_db_id = self.update_invoice(invoice)
                self._log_action(invoice.invoice_id, 'UPDATE')
            else:
                # Wstaw nową fakturę
                cursor.execute("""
                    INSERT INTO invoices (
                        invoice_id, invoice_type, issue_date, sale_date, due_date,
                        supplier_name, supplier_tax_id, supplier_address, supplier_accounts,
                        buyer_name, buyer_tax_id, buyer_address,
                        total_net, total_vat, total_gross, currency,
                        payment_method, payment_status, paid_amount,
                        language, confidence, is_verified, is_duplicate, belongs_to_user,
                        page_range, file_path, file_hash, raw_text,
                        parsing_errors, parsing_warnings, processed_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    invoice.invoice_id,
                    invoice.invoice_type,
                    invoice.issue_date.isoformat(),
                    invoice.sale_date.isoformat(),
                    invoice.due_date.isoformat(),
                    invoice.supplier_name,
                    invoice.supplier_tax_id,
                    invoice.supplier_address,
                    json.dumps(invoice.supplier_accounts),
                    invoice.buyer_name,
                    invoice.buyer_tax_id,
                    invoice.buyer_address,
                    float(invoice.total_net),
                    float(invoice.total_vat),
                    float(invoice.total_gross),
                    invoice.currency,
                    invoice.payment_method,
                    invoice.payment_status,
                    float(invoice.paid_amount),
                    invoice.language,
                    invoice.confidence,
                    invoice.is_verified,
                    invoice.is_duplicate,
                    invoice.belongs_to_user,
                    json.dumps(invoice.page_range),
                    file_path,
                    file_hash,
                    invoice.raw_text,
                    json.dumps(invoice.parsing_errors),
                    json.dumps(invoice.parsing_warnings),
                    'SYSTEM'
                ))
                
                invoice_db_id = cursor.lastrowid
                
                # Zapisz pozycje faktury
                for i, item in enumerate(invoice.line_items):
                    self._save_invoice_item(invoice.invoice_id, i + 1, item)
                    
                self._log_action(invoice.invoice_id, 'CREATE')
                
            self.conn.commit()
            logger.info(f"Zapisano fakturę {invoice.invoice_id} (ID: {invoice_db_id})")
            return invoice_db_id
            
        except Exception as e:
            logger.error(f"Błąd zapisu faktury: {e}")
            self.conn.rollback()
            raise
            
    def update_invoice(self, invoice: ParsedInvoice) -> int:
        """Aktualizuje istniejącą fakturę"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            UPDATE invoices SET
                invoice_type = ?, issue_date = ?, sale_date = ?, due_date = ?,
                supplier_name = ?, supplier_tax_id = ?, supplier_address = ?, supplier_accounts = ?,
                buyer_name = ?, buyer_tax_id = ?, buyer_address = ?,
                total_net = ?, total_vat = ?, total_gross = ?, currency = ?,
                payment_method = ?, payment_status = ?, paid_amount = ?,
                language = ?, confidence = ?, is_verified = ?, is_duplicate = ?,
                belongs_to_user = ?, parsing_errors = ?, parsing_warnings = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = ?
        """, (
            invoice.invoice_type,
            invoice.issue_date.isoformat(),
            invoice.sale_date.isoformat(),
            invoice.due_date.isoformat(),
            invoice.supplier_name,
            invoice.supplier_tax_id,
            invoice.supplier_address,
            json.dumps(invoice.supplier_accounts),
            invoice.buyer_name,
            invoice.buyer_tax_id,
            invoice.buyer_address,
            float(invoice.total_net),
            float(invoice.total_vat),
            float(invoice.total_gross),
            invoice.currency,
            invoice.payment_method,
            invoice.payment_status,
            float(invoice.paid_amount),
            invoice.language,
            invoice.confidence,
            invoice.is_verified,
            invoice.is_duplicate,
            invoice.belongs_to_user,
            json.dumps(invoice.parsing_errors),
            json.dumps(invoice.parsing_warnings),
            invoice.invoice_id
        ))
        
        # Usuń stare pozycje i dodaj nowe
        cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice.invoice_id,))
        for i, item in enumerate(invoice.line_items):
            self._save_invoice_item(invoice.invoice_id, i + 1, item)
            
        return cursor.lastrowid
        
    def _save_invoice_item(self, invoice_id: str, position: int, item: Dict):
        """Zapisuje pozycję faktury"""
        cursor = self.conn.cursor()
        
        # Oblicz kwoty jeśli brakuje
        quantity = item.get('quantity', 1)
        unit_price = item.get('unit_price', 0)
        total = item.get('total', quantity * unit_price)
        
        # Zakładamy 23% VAT jeśli nie podano
        vat_rate = item.get('vat_rate', 23)
        net_amount = total / (1 + vat_rate / 100)
        vat_amount = total - net_amount
        
        cursor.execute("""
            INSERT INTO invoice_items (
                invoice_id, position, description, quantity, unit_price,
                net_amount, vat_rate, vat_amount, gross_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            position,
            item.get('description', ''),
            quantity,
            unit_price,
            net_amount,
            vat_rate,
            vat_amount,
            total
        ))
        
    def get_invoice(self, invoice_id: str) -> Optional[Dict]:
        """Pobiera fakturę z bazy"""
        cursor = self.conn.cursor()
        
        # Pobierz fakturę
        invoice = cursor.execute(
            "SELECT * FROM invoices WHERE invoice_id = ?",
            (invoice_id,)
        ).fetchone()
        
        if not invoice:
            return None
            
        # Pobierz pozycje
        items = cursor.execute(
            "SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY position",
            (invoice_id,)
        ).fetchall()
        
        # Konwertuj do słownika
        result = dict(invoice)
        
        # Parsuj JSON pola
        result['supplier_accounts'] = json.loads(result['supplier_accounts'])
        result['page_range'] = json.loads(result['page_range'])
        result['parsing_errors'] = json.loads(result['parsing_errors'])
        result['parsing_warnings'] = json.loads(result['parsing_warnings'])
        
        # Dodaj pozycje
        result['items'] = [dict(item) for item in items]
        
        return result
        
    def search_invoices(self, criteria: Dict) -> List[Dict]:
        """Wyszukuje faktury według kryteriów"""
        query = "SELECT * FROM invoices WHERE 1=1"
        params = []
        
        # Buduj zapytanie dynamicznie
        if criteria.get('invoice_id'):
            query += " AND invoice_id LIKE ?"
            params.append(f"%{criteria['invoice_id']}%")
            
        if criteria.get('supplier_name'):
            query += " AND supplier_name LIKE ?"
            params.append(f"%{criteria['supplier_name']}%")
            
        if criteria.get('supplier_tax_id'):
            query += " AND supplier_tax_id = ?"
            params.append(criteria['supplier_tax_id'])
            
        if criteria.get('buyer_tax_id'):
            query += " AND buyer_tax_id = ?"
            params.append(criteria['buyer_tax_id'])
            
        if criteria.get('date_from'):
            query += " AND issue_date >= ?"
            params.append(criteria['date_from'])
            
        if criteria.get('date_to'):
            query += " AND issue_date <= ?"
            params.append(criteria['date_to'])
            
        if criteria.get('min_amount'):
            query += " AND total_gross >= ?"
            params.append(criteria['min_amount'])
            
        if criteria.get('max_amount'):
            query += " AND total_gross <= ?"
            params.append(criteria['max_amount'])
            
        if criteria.get('payment_status'):
            query += " AND payment_status = ?"
            params.append(criteria['payment_status'])
            
        if criteria.get('is_verified') is not None:
            query += " AND is_verified = ?"
            params.append(criteria['is_verified'])
            
        # Sortowanie
        order_by = criteria.get('order_by', 'issue_date')
        order_dir = criteria.get('order_dir', 'DESC')
        query += f" ORDER BY {order_by} {order_dir}"
        
        # Limit
        if criteria.get('limit'):
            query += " LIMIT ?"
            params.append(criteria['limit'])
            
        cursor = self.conn.cursor()
        results = cursor.execute(query, params).fetchall()
        
        invoices = []
        for row in results:
            invoice = dict(row)
            # Parsuj JSON pola
            invoice['supplier_accounts'] = json.loads(invoice['supplier_accounts'])
            invoice['page_range'] = json.loads(invoice['page_range'])
            invoice['parsing_errors'] = json.loads(invoice['parsing_errors'])
            invoice['parsing_warnings'] = json.loads(invoice['parsing_warnings'])
            invoices.append(invoice)
            
        return invoices
        
    def get_statistics(self, date_from: str = None, date_to: str = None) -> Dict:
        """Oblicza statystyki"""
        cursor = self.conn.cursor()
        
        where_clause = ""
        params = []
        
        if date_from:
            where_clause += " AND issue_date >= ?"
            params.append(date_from)
        if date_to:
            where_clause += " AND issue_date <= ?"
            params.append(date_to)
            
        # Statystyki ogólne
        stats = cursor.execute(f"""
            SELECT 
                COUNT(*) as total_count,
                SUM(total_net) as total_net,
                SUM(total_vat) as total_vat,
                SUM(total_gross) as total_gross,
                AVG(total_gross) as avg_gross,
                MIN(total_gross) as min_gross,
                MAX(total_gross) as max_gross,
                COUNT(DISTINCT supplier_tax_id) as unique_suppliers,
                COUNT(DISTINCT buyer_tax_id) as unique_buyers,
                SUM(is_verified) as verified_count,
                SUM(is_duplicate) as duplicate_count
            FROM invoices
            WHERE 1=1 {where_clause}
        """, params).fetchone()
        
        # Top dostawcy
        top_suppliers = cursor.execute(f"""
            SELECT 
                supplier_name,
                supplier_tax_id,
                COUNT(*) as invoice_count,
                SUM(total_gross) as total_amount
            FROM invoices
            WHERE 1=1 {where_clause}
            GROUP BY supplier_tax_id
            ORDER BY total_amount DESC
            LIMIT 10
        """, params).fetchall()
        
        # Podsumowanie miesięczne
        monthly = cursor.execute(f"""
            SELECT 
                strftime('%Y-%m', issue_date) as month,
                COUNT(*) as invoice_count,
                SUM(total_gross) as total_amount
            FROM invoices
            WHERE 1=1 {where_clause}
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """, params).fetchall()
        
        return {
            'general': dict(stats),
            'top_suppliers': [dict(row) for row in top_suppliers],
            'monthly': [dict(row) for row in monthly]
        }
        
    def delete_invoice(self, invoice_id: str):
        """Usuwa fakturę z bazy"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM invoices WHERE invoice_id = ?", (invoice_id,))
        self.conn.commit()
        self._log_action(invoice_id, 'DELETE')
        
    def mark_as_paid(self, invoice_id: str, amount: float = None):
        """Oznacza fakturę jako opłaconą"""
        cursor = self.conn.cursor()
        
        if amount is None:
            # Pobierz pełną kwotę
            amount = cursor.execute(
                "SELECT total_gross FROM invoices WHERE invoice_id = ?",
                (invoice_id,)
            ).fetchone()[0]
            
        cursor.execute("""
            UPDATE invoices 
            SET payment_status = 'opłacona', 
                paid_amount = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = ?
        """, (amount, invoice_id))
        
        self.conn.commit()
        self._log_action(invoice_id, 'PAYMENT', {'amount': amount})
        
    def verify_invoice(self, invoice_id: str, verified: bool = True):
        """Oznacza fakturę jako zweryfikowaną"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE invoices 
            SET is_verified = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = ?
        """, (verified, invoice_id))
        
        self.conn.commit()
        self._log_action(invoice_id, 'VERIFY', {'verified': verified})
        
    def add_attachment(self, invoice_id: str, file_path: str):
        """Dodaje załącznik do faktury"""
        import os
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
            
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO attachments (invoice_id, file_name, file_type, file_size, file_data)
            VALUES (?, ?, ?, ?, ?)
        """, (invoice_id, file_name, 'application/pdf', file_size, file_data))
        
        self.conn.commit()
        
    def get_duplicates(self) -> List[Tuple[str, str]]:
        """Znajduje duplikaty faktur"""
        cursor = self.conn.cursor()
        
        duplicates = cursor.execute("""
            SELECT a.invoice_id, b.invoice_id
            FROM invoices a
            JOIN invoices b ON a.supplier_tax_id = b.supplier_tax_id
                AND a.issue_date = b.issue_date
                AND a.total_gross = b.total_gross
                AND a.invoice_id < b.invoice_id
        """).fetchall()
        
        return duplicates
        
    def _log_action(self, invoice_id: str, action: str, changes: Dict = None):
        """Loguje akcję w audit log"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO audit_log (invoice_id, action, user, changes)
            VALUES (?, ?, ?, ?)
        """, (
            invoice_id,
            action,
            'SYSTEM',
            json.dumps(changes) if changes else None
        ))
        
    def backup(self, backup_path: str = None):
        """Tworzy kopię zapasową bazy"""
        import shutil
        
        if backup_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{self.db_path}.backup_{timestamp}"
            
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Utworzono kopię zapasową: {backup_path}")
        return backup_path
        
    def close(self):
        """Zamyka połączenie z bazą"""
        if self.conn:
            self.conn.close()

class CacheManager:
    """Manager pamięci podręcznej dla wydajności"""
    
    def __init__(self):
        self._cache = {}
        self._cache_time = {}
        self._max_age = 300  # 5 minut
        
    def get(self, key: str) -> Optional[Any]:
        """Pobiera wartość z cache"""
        if key in self._cache:
            # Sprawdź wiek
            age = (datetime.now() - self._cache_time[key]).total_seconds()
            if age < self._max_age:
                return self._cache[key]
            else:
                # Usuń przeterminowane
                del self._cache[key]
                del self._cache_time[key]
        return None
        
    def set(self, key: str, value: Any):
        """Zapisuje wartość w cache"""
        self._cache[key] = value
        self._cache_time[key] = datetime.now()
        
    def clear(self):
        """Czyści cache"""
        self._cache.clear()
        self._cache_time.clear()