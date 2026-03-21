"""Source DB reader using fdb (Firebird direct connection) for high-speed extraction.

Reads AR transactions and master data from source SQL Account databases.
"""

import fdb
from dataclasses import dataclass, field
from typing import Optional
from config import EntityConfig
from logger import SyncLogger


@dataclass
class CustomerRecord:
    code: str = ""
    company_name: str = ""
    company_category: str = ""
    currency_code: str = ""
    attention: str = ""
    phone1: str = ""
    email: str = ""
    address1: str = ""
    address2: str = ""
    address3: str = ""
    address4: str = ""
    postcode: str = ""
    city: str = ""
    state: str = ""
    country: str = ""


@dataclass
class DocDetailRecord:
    seq: int = 0
    account: str = ""
    description: str = ""
    tax: str = ""
    tax_rate: str = ""
    tax_inclusive: str = "F"
    tax_amt: float = 0.0
    exempted_tax_rate: str = ""
    exempted_tax_amt: float = 0.0
    amount: float = 0.0


@dataclass
class ARDocRecord:
    """Represents an AR document (IV, DN, CN, CT, PM, CF)."""
    doc_type: str = ""     # IV, DN, CN, CT, PM, CF
    doc_no: str = ""
    doc_date: str = ""
    post_date: str = ""
    code: str = ""         # Customer code
    description: str = ""
    currency_code: str = ""
    currency_rate: float = 1.0
    amount: float = 0.0
    local_amount: float = 0.0
    cancelled: bool = False
    agent: str = ""
    details: list = field(default_factory=list)  # List of DocDetailRecord
    # For payments
    payment_method: str = ""
    cheque_no: str = ""
    # Knock-off info (for PM)
    knockoffs: list = field(default_factory=list)


@dataclass
class KnockOffRecord:
    doc_type: str = ""
    doc_no: str = ""
    ko_amt: float = 0.0
    local_ko_amt: float = 0.0
    actual_local_ko_amt: float = 0.0
    gain_loss: float = 0.0


@dataclass
class SYProfile:
    alias: str = ""
    company_name: str = ""


class SourceReader:
    """Reads data from a source SQL Account database via Firebird."""

    def __init__(self, entity: EntityConfig, logger: SyncLogger = None):
        self.entity = entity
        self.logger = logger
        self.conn = None

    def connect(self):
        self.conn = fdb.connect(
            host=self.entity.fb_host,
            database=self.entity.fb_path,
            user=self.entity.fb_user,
            password=self.entity.fb_password,
            charset="UTF8",
        )
        if self.logger:
            self.logger.info(f"Connected to source DB: {self.entity.fb_path}")

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    def read_profile(self) -> SYProfile:
        """Read SY_PROFILE for entity prefix and company info."""
        cur = self.conn.cursor()
        cur.execute("SELECT ALIAS, COMPANYNAME FROM SY_PROFILE")
        row = cur.fetchone()
        cur.close()
        if row:
            return SYProfile(alias=(row[0] or "").strip(), company_name=(row[1] or "").strip())
        return SYProfile()

    def read_customers(self) -> list:
        """Read all customers with billing branch details via JOIN."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                A.CODE, A.COMPANYNAME, A.COMPANYCATEGORY, A.CURRENCYCODE,
                B.ATTENTION, B.PHONE1, B.EMAIL,
                B.ADDRESS1, B.ADDRESS2, B.ADDRESS3, B.ADDRESS4,
                B.POSTCODE, B.CITY, B.STATE, B.COUNTRY
            FROM AR_CUSTOMER A
            INNER JOIN AR_CUSTOMERBRANCH B ON (A.CODE = B.CODE)
            WHERE (B.BRANCHTYPE = 'B')
            ORDER BY A.CODE
        """)
        customers = []
        for row in cur.fetchall():
            customers.append(CustomerRecord(
                code=(row[0] or "").strip(),
                company_name=(row[1] or "").strip(),
                company_category=(row[2] or "").strip(),
                currency_code=(row[3] or "").strip(),
                attention=(row[4] or "").strip(),
                phone1=(row[5] or "").strip(),
                email=(row[6] or "").strip(),
                address1=(row[7] or "").strip(),
                address2=(row[8] or "").strip(),
                address3=(row[9] or "").strip(),
                address4=(row[10] or "").strip(),
                postcode=(row[11] or "").strip(),
                city=(row[12] or "").strip(),
                state=(row[13] or "").strip(),
                country=(row[14] or "").strip(),
            ))
        cur.close()
        if self.logger:
            self.logger.info(f"Read {len(customers)} customers from source")
        return customers

    def read_currencies(self) -> list:
        """Read all currencies from source CURRENCY table."""
        cur = self.conn.cursor()
        cur.execute("SELECT CODE, DESCRIPTION, ISOCODE, SYMBOL FROM CURRENCY ORDER BY CODE")
        currencies = []
        for row in cur.fetchall():
            currencies.append({
                "code": (row[0] or "").strip(),
                "description": (row[1] or "").strip(),
                "isocode": (row[2] or "").strip(),
                "symbol": (row[3] or "").strip(),
            })
        cur.close()
        if self.logger:
            self.logger.info(f"Read {len(currencies)} currencies from source")
        return currencies

    def read_payment_methods(self) -> list:
        """Read payment methods with currency ISO codes from source DB.

        Includes home currency payment methods (----).
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT A.CODE, A.JOURNAL, A.CURRENCYCODE, B.ISOCODE
            FROM PMMETHOD A
            INNER JOIN CURRENCY B ON (A.CURRENCYCODE=B.CODE)
        """)
        methods = []
        for row in cur.fetchall():
            pm_code = (row[0] or "").strip()
            journal = (row[1] or "").strip()
            isocode = (row[3] or "").strip()
            currency_code = (row[2] or "").strip()
            if pm_code and isocode:
                methods.append({
                    "pm_code": pm_code,
                    "journal": journal,
                    "currency_code": currency_code,
                    "isocode": isocode,
                })
        cur.close()
        if self.logger:
            self.logger.info(f"Read {len(methods)} payment methods from source")
        return methods

    def count_documents(self, doc_type: str, date_from: str = None, date_to: str = None) -> int:
        """Count AR documents of a given type for preview/dry run."""
        table = self._doc_table(doc_type)
        if not table:
            return 0

        # Only count non-cancelled documents
        sql = f"SELECT COUNT(*) FROM {table} WHERE CANCELLED=FALSE"

        params = []
        if date_from:
            sql += " AND DOCDATE >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND DOCDATE <= ?"
            params.append(date_to)

        cur = self.conn.cursor()
        cur.execute(sql, params)
        count = cur.fetchone()[0]
        cur.close()
        return count

    def read_documents(self, doc_type: str, date_from: str = None,
                       date_to: str = None, last_synced: str = None) -> list:
        """Read AR documents of a specific type."""
        table = self._doc_table(doc_type)
        detail_table = self._detail_table(doc_type)
        if not table:
            return []

        if doc_type == "PM":
            return self._read_payments(date_from, date_to)

        if doc_type == "CF":
            return self._read_refunds(date_from, date_to)

        # Non-PM documents: IV, DN, CN, CT (only non-cancelled)
        sql = f"""
            SELECT DOCKEY, DOCNO, DOCDATE, POSTDATE, CODE,
                   DESCRIPTION, CURRENCYCODE, CURRENCYRATE,
                   DOCAMT, LOCALDOCAMT
            FROM {table}
            WHERE CANCELLED=FALSE
        """
        params = []

        if date_from:
            sql += " AND DOCDATE >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND DOCDATE <= ?"
            params.append(date_to)

        sql += " ORDER BY DOCDATE, DOCNO"

        cur = self.conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

        documents = []
        for row in rows:
            dockey = row[0]
            doc = ARDocRecord(
                doc_type=doc_type,
                doc_no=(row[1] or "").strip(),
                doc_date=str(row[2]) if row[2] else "",
                post_date=str(row[3]) if row[3] else "",
                code=(row[4] or "").strip(),
                description=(row[5] or "").strip(),
                currency_code=(row[6] or "").strip(),
                currency_rate=float(row[7] or 1),
                amount=float(row[8] or 0),
                local_amount=float(row[9] or 0),
            )

            # Read detail lines
            if detail_table:
                doc.details = self._read_details(dockey, detail_table)

            # Read knock-offs for CN and CT (both knock off IV/DN)
            if doc_type in ("CN", "CT"):
                doc.knockoffs = self._read_knockoffs(dockey, from_doc_type=doc_type)

            documents.append(doc)

        cur.close()
        if self.logger:
            self.logger.info(f"Read {len(documents)} {doc_type} documents from source")
        return documents

    def _read_payments(self, date_from: str = None, date_to: str = None) -> list:
        """Read AR_PM payments (only non-cancelled)."""
        sql = """
            SELECT DOCKEY, DOCNO, DOCDATE, CODE,
                   DESCRIPTION, CURRENCYCODE, CURRENCYRATE,
                   DOCAMT, LOCALDOCAMT,
                   PAYMENTMETHOD, CHEQUENUMBER
            FROM AR_PM
            WHERE CANCELLED=FALSE
        """
        params = []

        if date_from:
            sql += " AND DOCDATE >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND DOCDATE <= ?"
            params.append(date_to)

        sql += " ORDER BY DOCDATE, DOCNO"

        cur = self.conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

        documents = []
        for row in rows:
            dockey = row[0]
            doc = ARDocRecord(
                doc_type="PM",
                doc_no=(row[1] or "").strip(),
                doc_date=str(row[2]) if row[2] else "",
                code=(row[3] or "").strip(),
                description=(row[4] or "").strip(),
                currency_code=(row[5] or "").strip(),
                currency_rate=float(row[6] or 1),
                amount=float(row[7] or 0),
                local_amount=float(row[8] or 0),
                payment_method=(row[9] or "").strip(),
                cheque_no=(row[10] or "").strip(),
            )
            doc.knockoffs = self._read_knockoffs(dockey)
            documents.append(doc)

        cur.close()
        if self.logger:
            self.logger.info(f"Read {len(documents)} PM documents from source")
        return documents

    def _read_refunds(self, date_from: str = None, date_to: str = None) -> list:
        """Read AR_CF customer refunds (only non-cancelled)."""
        sql = """
            SELECT DOCKEY, DOCNO, DOCDATE, CODE,
                   DESCRIPTION, CURRENCYCODE, CURRENCYRATE,
                   DOCAMT, LOCALDOCAMT,
                   PAYMENTMETHOD, CHEQUENUMBER
            FROM AR_CF
            WHERE CANCELLED=FALSE
        """
        params = []

        if date_from:
            sql += " AND DOCDATE >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND DOCDATE <= ?"
            params.append(date_to)

        sql += " ORDER BY DOCDATE, DOCNO"

        cur = self.conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

        documents = []
        for row in rows:
            dockey = row[0]
            doc = ARDocRecord(
                doc_type="CF",
                doc_no=(row[1] or "").strip(),
                doc_date=str(row[2]) if row[2] else "",
                code=(row[3] or "").strip(),
                description=(row[4] or "").strip(),
                currency_code=(row[5] or "").strip(),
                currency_rate=float(row[6] or 1),
                amount=float(row[7] or 0),
                local_amount=float(row[8] or 0),
                payment_method=(row[9] or "").strip(),
                cheque_no=(row[10] or "").strip(),
            )
            doc.knockoffs = self._read_knockoffs(dockey, from_doc_type="CF")
            documents.append(doc)

        cur.close()
        if self.logger:
            self.logger.info(f"Read {len(documents)} CF documents from source")
        return documents

    def _read_details(self, dockey: int, detail_table: str) -> list:
        """Read document detail lines."""
        cur = self.conn.cursor()
        cur.execute(f"""
            SELECT SEQ, ACCOUNT, DESCRIPTION,
                   TAX, TAXRATE, TAXINCLUSIVE, TAXAMT,
                   EXEMPTED_TAXRATE, EXEMPTED_TAXAMT, AMOUNT
            FROM {detail_table}
            WHERE DOCKEY = ?
            ORDER BY SEQ
        """, (dockey,))
        details = []
        for row in cur.fetchall():
            details.append(DocDetailRecord(
                seq=int(row[0] or 0),
                account=(row[1] or "").strip(),
                description=(row[2] or "").strip(),
                tax=(row[3] or "").strip(),
                tax_rate=(row[4] or "").strip(),
                tax_inclusive=(row[5] or "F").strip(),
                tax_amt=float(row[6] or 0),
                exempted_tax_rate=(row[7] or "").strip(),
                exempted_tax_amt=float(row[8] or 0),
                amount=float(row[9] or 0),
            ))
        cur.close()
        return details

    def _read_knockoffs(self, dockey: int, from_doc_type: str = "PM") -> list:
        """Read knock-off records for a payment or credit note."""
        cur = self.conn.cursor()
        try:
            cur.execute(f"""
                SELECT
                    A.TODOCTYPE,
                    (CASE
                      WHEN (A.TODOCTYPE='IV') THEN (SELECT DOCNO FROM AR_IV WHERE DOCKEY=A.TODOCKEY)
                      WHEN (A.TODOCTYPE='DN') THEN (SELECT DOCNO FROM AR_DN WHERE DOCKEY=A.TODOCKEY)
                      WHEN (A.TODOCTYPE='CN') THEN (SELECT DOCNO FROM AR_CN WHERE DOCKEY=A.TODOCKEY)
                      WHEN (A.TODOCTYPE='PM') THEN (SELECT DOCNO FROM AR_PM WHERE DOCKEY=A.TODOCKEY)
                    END) AS DOCNO,
                    A.KOAMT, A.LOCALKOAMT, A.ACTUALLOCALKOAMT, A.GAINLOSS
                FROM AR_KNOCKOFF A
                WHERE (A.FROMDOCTYPE='{from_doc_type}')
                AND A.FROMDOCKEY = ?
            """, (dockey,))
            knockoffs = []
            for row in cur.fetchall():
                doc_no = (row[1] or "").strip()
                if doc_no:  # Only include if we resolved a doc number
                    knockoffs.append(KnockOffRecord(
                        doc_type=(row[0] or "").strip(),
                        doc_no=doc_no,
                        ko_amt=float(row[2] or 0),
                        local_ko_amt=float(row[3] or 0),
                        actual_local_ko_amt=float(row[4] or 0),
                        gain_loss=float(row[5] or 0),
                    ))
            return knockoffs
        except Exception:
            return []
        finally:
            cur.close()

    def _parse_cancelled(self, value) -> bool:
        """Parse CANCELLED field - handles both bool (v207+) and string ('T'/'F')."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().upper() in ("T", "TRUE")
        return False

    def _doc_table(self, doc_type: str) -> str:
        """Map document type to main table name."""
        return {
            "IV": "AR_IV",
            "DN": "AR_DN",
            "CN": "AR_CN",
            "CT": "AR_CT",
            "PM": "AR_PM",
            "CF": "AR_CF",
        }.get(doc_type, "")

    def _detail_table(self, doc_type: str) -> str:
        """Map document type to detail table name."""
        return {
            "IV": "AR_IVDTL",
            "DN": "AR_DNDTL",
            "CN": "AR_CNDTL",
            "CT": "",
            "PM": "",
            "CF": "",
        }.get(doc_type, "")
