"""Sync engine orchestrator.

Coordinates the full sync workflow: read source → transform → write consol.
Enforces import order: IV → DN → CN → CT → PM → CF.
Supports dry-run preview and incremental sync.
"""

import datetime
import time
import fdb
from dataclasses import dataclass, field
from config import AppConfig, EntityConfig, save_config
from source_reader import SourceReader
from transformer import DataTransformer, TransformError
from consol_writer import ConsolWriter
from sdk_session import open_consol_session
from logger import SyncLogger

# Enforced import order
IMPORT_ORDER = ["IV", "DN", "CN", "CT", "PM", "CF"]

# Reverse order for purge (delete knock-off dependents first)
PURGE_ORDER = ["CF", "PM", "CN", "CT", "DN", "IV"]

# ISO 4217 currency code → description mapping
_CURRENCY_NAMES = {
    "AED": "UAE Dirham", "AFN": "Afghani", "ALL": "Lek", "AMD": "Armenian Dram",
    "ANG": "Netherlands Antillean Guilder", "AOA": "Kwanza", "ARS": "Argentine Peso",
    "AUD": "Australian Dollar", "AWG": "Aruban Florin", "AZN": "Azerbaijan Manat",
    "BAM": "Convertible Mark", "BBD": "Barbados Dollar", "BDT": "Taka",
    "BGN": "Bulgarian Lev", "BHD": "Bahraini Dinar", "BIF": "Burundi Franc",
    "BMD": "Bermudian Dollar", "BND": "Brunei Dollar", "BOB": "Boliviano",
    "BOV": "Mvdol", "BRL": "Brazilian Real", "BSD": "Bahamian Dollar",
    "BTN": "Ngultrum", "BWP": "Pula", "BYN": "Belarusian Ruble",
    "BZD": "Belize Dollar", "CAD": "Canadian Dollar", "CDF": "Congolese Franc",
    "CHE": "WIR Euro", "CHF": "Swiss Franc", "CHW": "WIR Franc",
    "CLF": "Unidad de Fomento", "CLP": "Chilean Peso",
    "CNH": "Yuan Renminbi (International)", "CNY": "Yuan Renminbi (Domestic)",
    "COP": "Colombian Peso", "COU": "Unidad de Valor Real",
    "CRC": "Costa Rican Colon", "CUC": "Peso Convertible", "CUP": "Cuban Peso",
    "CVE": "Cabo Verde Escudo", "CZK": "Czech Koruna", "DJF": "Djibouti Franc",
    "DKK": "Danish Krone", "DOP": "Dominican Peso", "DZD": "Algerian Dinar",
    "EGP": "Egyptian Pound", "ERN": "Nakfa", "ETB": "Ethiopian Birr",
    "EUR": "Euro", "FJD": "Fiji Dollar", "FKP": "Falkland Islands Pound",
    "GBP": "Pound Sterling", "GEL": "Lari", "GHS": "Ghana Cedi",
    "GIP": "Gibraltar Pound", "GMD": "Dalasi", "GNF": "Guinean Franc",
    "GTQ": "Quetzal", "GYD": "Guyana Dollar", "HKD": "Hong Kong Dollar",
    "HNL": "Lempira", "HRK": "Kuna", "HTG": "Gourde", "HUF": "Forint",
    "IDR": "Rupiah", "ILS": "New Israeli Sheqel", "INR": "Indian Rupee",
    "IQD": "Iraqi Dinar", "IRR": "Iranian Rial", "ISK": "Iceland Krona",
    "JMD": "Jamaican Dollar", "JOD": "Jordanian Dinar", "JPY": "Yen",
    "KES": "Kenyan Shilling", "KGS": "Som", "KHR": "Riel",
    "KMF": "Comorian Franc", "KPW": "North Korean Won", "KRW": "Won",
    "KWD": "Kuwaiti Dinar", "KYD": "Cayman Islands Dollar", "KZT": "Tenge",
    "LAK": "Lao Kip", "LBP": "Lebanese Pound", "LKR": "Sri Lanka Rupee",
    "LRD": "Liberian Dollar", "LSL": "Loti", "LYD": "Libyan Dinar",
    "MAD": "Moroccan Dirham", "MDL": "Moldovan Leu", "MGA": "Malagasy Ariary",
    "MKD": "Denar", "MMK": "Kyat", "MNT": "Tugrik", "MOP": "Pataca",
    "MRU": "Ouguiya", "MUR": "Mauritius Rupee", "MVR": "Rufiyaa",
    "MWK": "Malawi Kwacha", "MXN": "Mexican Peso",
    "MXV": "Mexican Unidad de Inversion (UDI)", "MYR": "Malaysian Ringgit",
    "MZN": "Mozambique Metical", "NAD": "Namibia Dollar", "NGN": "Naira",
    "NIO": "Cordoba Oro", "NOK": "Norwegian Krone", "NPR": "Nepalese Rupee",
    "NZD": "New Zealand Dollar", "OMR": "Rial Omani", "PAB": "Balboa",
    "PEN": "Sol", "PGK": "Kina", "PHP": "Philippine Peso",
    "PKR": "Pakistan Rupee", "PLN": "Zloty", "PYG": "Guarani",
    "QAR": "Qatari Rial", "RON": "Romanian Leu", "RSD": "Serbian Dinar",
    "RUB": "Russian Ruble", "RWF": "Rwanda Franc", "SAR": "Saudi Riyal",
    "SBD": "Solomon Islands Dollar", "SCR": "Seychelles Rupee",
    "SDG": "Sudanese Pound", "SEK": "Swedish Krona", "SGD": "Singapore Dollar",
    "SHP": "Saint Helena Pound", "SLL": "Leone", "SOS": "Somali Shilling",
    "SRD": "Surinam Dollar", "SSP": "South Sudanese Pound", "STN": "Dobra",
    "SVC": "El Salvador Colon", "SYP": "Syrian Pound", "SZL": "Lilangeni",
    "THB": "Baht", "TJS": "Somoni", "TMT": "Turkmenistan New Manat",
    "TND": "Tunisian Dinar", "TOP": "Pa'anga", "TRY": "Turkish Lira",
    "TTD": "Trinidad and Tobago Dollar", "TWD": "New Taiwan Dollar",
    "TZS": "Tanzanian Shilling", "UAH": "Hryvnia", "UGX": "Uganda Shilling",
    "USD": "US Dollar", "USN": "US Dollar (Next day)",
    "UYI": "Uruguay Peso en Unidades Indexadas (UI)", "UYU": "Peso Uruguayo",
    "UYW": "Unidad Previsional", "UZS": "Uzbekistan Sum",
    "VED": "Bolivar Soberano", "VES": "Bolivar Soberano", "VND": "Dong",
    "VUV": "Vatu", "WST": "Tala", "XAF": "CFA Franc BEAC",
    "XCD": "East Caribbean Dollar", "XOF": "CFA Franc BCEAO",
    "XPF": "CFP Franc", "YER": "Yemeni Rial", "ZAR": "Rand",
    "ZMW": "Zambian Kwacha", "ZWL": "Zimbabwe Dollar",
}


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration (e.g. '2m 35s')."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m {secs}s"


@dataclass
class PreviewResult:
    """Dry-run preview counts per entity/module."""
    entity_name: str = ""
    prefix: str = ""
    customer_count: int = 0
    doc_counts: dict = field(default_factory=dict)  # {"IV": 10, "DN": 5, ...}


@dataclass
class SyncResult:
    """Results of a sync operation for one entity."""
    entity_name: str = ""
    prefix: str = ""
    customers_synced: int = 0
    customers_skipped: int = 0
    customers_failed: int = 0
    docs_synced: dict = field(default_factory=dict)
    docs_skipped: dict = field(default_factory=dict)
    docs_failed: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


class SyncEngine:
    """Orchestrates the consolidation sync process."""

    def __init__(self, config: AppConfig, logger: SyncLogger = None,
                 progress_callback=None):
        """
        Args:
            config: Application configuration.
            logger: SyncLogger instance.
            progress_callback: Function(current, total, message) for UI updates.
        """
        self.config = config
        self.logger = logger
        self.progress_callback = progress_callback
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the current operation."""
        self._cancelled = True

    @staticmethod
    def _build_currency_map(source_currencies: list) -> dict:
        """Build currency CODE -> ISOCODE map, excluding home currency."""
        return {cur["code"]: cur["isocode"]
                for cur in source_currencies
                if cur["code"] != "----" and cur["isocode"]}

    # ------------------------------------------------------------------
    # Preview (Dry Run)
    # ------------------------------------------------------------------
    def preview(self, entities: list, modules: list,
                date_from: str = None, date_to: str = None) -> list:
        """Dry-run preview: count records per entity/module without importing.

        Args:
            entities: List of EntityConfig to preview.
            modules: List of doc types to include (subset of IMPORT_ORDER).
            date_from: Start date filter (YYYY-MM-DD).
            date_to: End date filter (YYYY-MM-DD).

        Returns:
            List of PreviewResult.
        """
        results = []

        for entity in entities:
            if self._cancelled:
                break

            preview = PreviewResult(entity_name=entity.name)

            try:
                with SourceReader(entity, self.logger) as reader:
                    profile = reader.read_profile()
                    preview.prefix = profile.alias
                    preview.customer_count = len(reader.read_customers())

                    for mod in modules:
                        if mod in IMPORT_ORDER:
                            preview.doc_counts[mod] = reader.count_documents(
                                mod, date_from, date_to
                            )
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Preview failed for '{entity.name}'", e)
                preview.doc_counts = {m: -1 for m in modules}  # -1 = error

            results.append(preview)

        return results

    # ------------------------------------------------------------------
    # Full Sync
    # ------------------------------------------------------------------
    def sync(self, entities: list, modules: list,
             date_from: str = None, date_to: str = None,
             sync_customers: bool = True,
             purge_resync: bool = False) -> list:
        """Execute sync for selected entities and modules.

        Args:
            entities: List of EntityConfig to sync.
            modules: List of doc types (enforced order from IMPORT_ORDER).
            date_from: Start date filter.
            date_to: End date filter.
            sync_customers: Whether to sync customer master data.

        Returns:
            List of SyncResult.
        """
        self._cancelled = False

        # Filter and order modules
        ordered_modules = [m for m in IMPORT_ORDER if m in modules]

        results = []
        total_entities = len(entities)

        for idx, entity in enumerate(entities):
            if self._cancelled:
                if self.logger:
                    self.logger.warning("Sync cancelled by user")
                break

            if self.logger:
                self.logger.info(f"=== Syncing entity: {entity.name} ({idx+1}/{total_entities}) ===")

            result = self._sync_entity(
                entity, ordered_modules, date_from, date_to, sync_customers,
                purge_resync
            )
            results.append(result)

            # Update last_synced timestamp
            entity.last_synced = datetime.datetime.now().isoformat()
            save_config(self.config)

        return results

    def _sync_entity(self, entity: EntityConfig, modules: list,
                     date_from: str, date_to: str,
                     sync_customers: bool,
                     purge_resync: bool = False) -> SyncResult:
        """Sync a single entity."""
        result = SyncResult(entity_name=entity.name)
        entity_start = time.time()

        try:
            # Step 1: Read source data
            with SourceReader(entity, self.logger) as reader:
                profile = reader.read_profile()
                result.prefix = profile.alias

                if not profile.alias:
                    raise Exception(
                        f"SY_PROFILE.ALIAS is empty for '{entity.name}'. "
                        "Please set the Company Alias in SQL Accounting."
                    )

                # Update entity config with profile info
                entity.prefix = profile.alias

                transformer = DataTransformer(entity, profile, self.logger)

                # Read currencies for mapping (source CODE → ISOCODE)
                source_currencies = reader.read_currencies()

                # Build currency CODE → ISOCODE map for transformer
                transformer.currency_map = self._build_currency_map(source_currencies)

                # Read payment methods for GL account auto-creation and pm_lookup
                source_payment_methods = reader.read_payment_methods()

                # Build pm_lookup: source PMMETHOD.CODE → JOURNAL-ISOCODE
                pm_lookup = {}
                for pm in source_payment_methods:
                    pm_lookup[pm["pm_code"]] = f"{pm['journal']}-{pm['isocode']}"
                transformer.pm_lookup = pm_lookup

                # Read customers — only import those with category mappings
                customers = reader.read_customers() if sync_customers else []
                mapped_codes = set(entity.customer_category_map.keys())

                if customers:
                    total_customers = len(customers)
                    customers = [c for c in customers if c.code in mapped_codes]
                    skipped_customers = total_customers - len(customers)
                    if skipped_customers and self.logger:
                        self.logger.info(
                            f"Skipping {skipped_customers} unmapped customer(s) "
                            f"(no category assigned)"
                        )

                # Read documents per module — skip docs for unmapped customers
                all_docs = {}
                for mod in modules:
                    docs = reader.read_documents(
                        mod, date_from, date_to, entity.last_synced
                    )
                    before = len(docs)
                    docs = [doc for doc in docs if doc.code in mapped_codes]
                    skipped = before - len(docs)
                    if skipped and self.logger:
                        self.logger.info(
                            f"Skipped {skipped} {mod} doc(s) for unmapped customers"
                        )
                    all_docs[mod] = docs

            # Step 2: Write to consol DB via SDK
            with open_consol_session(self.config.consol_db, self.logger) as consol_app:
                writer = ConsolWriter(consol_app, self.logger)

                # Validate tax codes before writing
                self._validate_tax_codes(all_docs, writer)

                # Auto-create missing currencies in consol DB
                if sync_customers:
                    self._ensure_currencies(source_currencies, writer)

                # Auto-create GL accounts for foreign currency payment methods
                self._ensure_gl_accounts(source_payment_methods, writer)

                # Purge phase: delete existing documents before re-import
                if purge_resync:
                    self._delete_entity_documents(
                        entity.prefix, modules, date_from, date_to, writer, result)

                # 2a: Sync customers
                if sync_customers:
                    self._sync_customers(customers, transformer, writer, result)

                # 2b: Sync documents in enforced order
                for mod in modules:
                    if self._cancelled:
                        break
                    self._sync_documents(all_docs.get(mod, []), mod,
                                         transformer, writer, result)

        except Exception as e:
            if self.logger:
                self.logger.error(f"Sync failed for '{entity.name}'", e)
            result.errors.append(str(e))

        if self.logger:
            duration = _format_duration(time.time() - entity_start)
            self.logger.info(f"Entity '{entity.name}' completed in {duration}")

        return result

    def _delete_entity_documents(self, prefix: str, modules: list,
                                 date_from: str, date_to: str,
                                 writer, result):
        """Delete all documents for an entity in reverse order before re-import.

        Order: CF → PM → CN → CT → DN → IV
        SQL Account auto un-knock-offs related documents on delete.
        """
        # Only purge modules that were selected, in reverse order
        purge_modules = [m for m in PURGE_ORDER if m in modules]

        if self.logger:
            self.logger.info(f"--- Purging documents for prefix '{prefix}' ---")

        total_deleted = 0
        for doc_type in purge_modules:
            if self._cancelled:
                break

            docs = writer.get_entity_documents(doc_type, prefix, date_from, date_to)
            if not docs:
                continue

            if self.logger:
                self.logger.info(f"Deleting {len(docs)} {doc_type} documents...")

            for doc in docs:
                if self._cancelled:
                    break
                if writer.delete_document(doc_type, doc["doc_no"]):
                    total_deleted += 1

        if self.logger:
            self.logger.info(f"Purge complete: {total_deleted} documents deleted")

    def compare_documents(self, entities: list, modules: list,
                          date_from: str = None, date_to: str = None) -> list:
        """Compare source vs consol documents for preview in Purge & Re-sync mode.

        Returns list of dicts per entity with comparison results.
        """
        results = []

        for entity in entities:
            if self._cancelled:
                break

            entity_result = {"entity_name": entity.name, "prefix": "", "modules": {}}

            try:
                with SourceReader(entity, self.logger) as reader:
                    profile = reader.read_profile()
                    entity_result["prefix"] = profile.alias
                    prefix = profile.alias

                    if not prefix:
                        continue

                    transformer = DataTransformer(entity, profile, self.logger)

                    # Build currency map for transformer
                    source_currencies = reader.read_currencies()
                    transformer.currency_map = self._build_currency_map(source_currencies)

                    # Read consol documents via direct Firebird (no SDK needed)
                    consol_db = self.config.consol_db
                    consol_conn = fdb.connect(
                        host=consol_db.fb_host,
                        database=consol_db.fb_path,
                        user=consol_db.fb_user,
                        password=consol_db.fb_password,
                        charset="UTF8",
                    )
                    consol_cur = consol_conn.cursor()
                    try:
                        mapped_codes = set(entity.customer_category_map.keys())

                        for mod in modules:
                            if mod not in IMPORT_ORDER:
                                continue

                            # Read source documents (filter unmapped customers
                            # to match actual sync behavior)
                            source_docs = reader.read_documents(mod, date_from, date_to)
                            source_docs = [d for d in source_docs if d.code in mapped_codes]
                            source_map = {}
                            for doc in source_docs:
                                transformed_no = transformer.transform_doc_no(doc.doc_no)
                                try:
                                    transformed_code = transformer.transform_customer_code(doc.code)
                                except Exception:
                                    transformed_code = doc.code
                                source_map[transformed_no] = {
                                    "doc_date": str(doc.doc_date),
                                    "code": transformed_code,
                                    "amount": doc.amount,
                                    "description": doc.description,
                                    "currency_code": transformer._map_currency(doc.currency_code),
                                    "currency_rate": doc.currency_rate,
                                }

                            # Read consol documents via Firebird
                            table = f"AR_{mod}"
                            sql = f"SELECT DOCNO, DOCDATE, CODE, DOCAMT, DESCRIPTION, CURRENCYCODE, CURRENCYRATE FROM {table} WHERE DOCNO LIKE ?"
                            params = [f"{prefix}-%"]
                            if date_from:
                                sql += " AND DOCDATE >= ?"
                                params.append(date_from)
                            if date_to:
                                sql += " AND DOCDATE <= ?"
                                params.append(date_to)
                            sql += " ORDER BY DOCNO"

                            try:
                                consol_cur.execute(sql, params)
                                consol_docs = []
                                for row in consol_cur.fetchall():
                                    consol_docs.append({
                                        "doc_no": (row[0] or "").strip(),
                                        "doc_date": str(row[1]) if row[1] else "",
                                        "code": (row[2] or "").strip(),
                                        "doc_amt": float(row[3] or 0),
                                        "description": (row[4] or "").strip(),
                                        "currency_code": (row[5] or "").strip(),
                                        "currency_rate": float(row[6] or 0),
                                    })
                            except Exception as e:
                                if self.logger:
                                    self.logger.warning(f"Could not query {table} for prefix '{prefix}': {e}")
                                consol_docs = []

                            consol_map = {}
                            for doc in consol_docs:
                                consol_map[doc["doc_no"]] = doc

                            # Compare
                            changed = []
                            new_in_source = []
                            deleted_from_source = []

                            for doc_no, src in source_map.items():
                                if doc_no not in consol_map:
                                    new_in_source.append(doc_no)
                                else:
                                    con = consol_map[doc_no]
                                    diffs = []
                                    if abs(src["amount"] - con["doc_amt"]) > 0.001:
                                        diffs.append(f"Amount: {src['amount']} vs {con['doc_amt']}")
                                    if src["code"] != con["code"]:
                                        diffs.append(f"Code: {src['code']} vs {con['code']}")
                                    if src["currency_code"] != con["currency_code"]:
                                        diffs.append(f"Currency: {src['currency_code']} vs {con['currency_code']}")
                                    if diffs:
                                        changed.append({"doc_no": doc_no, "diffs": "; ".join(diffs)})

                            for doc_no in consol_map:
                                if doc_no not in source_map:
                                    deleted_from_source.append(doc_no)

                            entity_result["modules"][mod] = {
                                "source_count": len(source_map),
                                "consol_count": len(consol_map),
                                "changed": changed,
                                "new": new_in_source,
                                "deleted": deleted_from_source,
                            }
                    finally:
                        try:
                            consol_cur.close()
                        except Exception:
                            pass
                        consol_conn.close()

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Compare failed for '{entity.name}'", e)

            results.append(entity_result)

        return results

    def _ensure_currencies(self, source_currencies: list, writer):
        """Auto-create missing currencies in consol DB.

        Matches by ISOCODE. Skips home currency ("----").
        Creates with CODE=ISOCODE, DESCRIPTION=full name, SYMBOL=ISOCODE.
        """
        consol_isocodes = writer.get_consol_currencies()

        for cur in source_currencies:
            if cur["code"] == "----":
                continue  # Home currency, always present
            isocode = cur["isocode"]
            if not isocode:
                continue
            if isocode in consol_isocodes:
                continue

            # Determine description
            description = _CURRENCY_NAMES.get(isocode, cur["description"] or isocode)

            writer.create_currency(isocode, description, isocode)

        if self.logger:
            self.logger.info("Currency auto-creation check completed")

    def _ensure_gl_accounts(self, source_payment_methods: list, writer):
        """Auto-create GL accounts for payment methods.

        For each unique JOURNAL-ISOCODE from source PMMETHOD, creates a GL
        account under _CA_ (Current Asset) parent if it doesn't exist.
        Creating GL_ACC with SpecialAccType=BA/CH auto-creates a PMMETHOD
        in SQL Account, which we then edit to assign CurrencyCode.
        """
        if not source_payment_methods:
            return

        consol_gl_codes = writer.get_gl_account_codes()

        # Deduplicate by JOURNAL-ISOCODE
        seen = set()
        for pm in source_payment_methods:
            gl_code = f"{pm['journal']}-{pm['isocode']}"
            if gl_code in seen or gl_code in consol_gl_codes:
                continue
            seen.add(gl_code)

            description = _CURRENCY_NAMES.get(pm["isocode"], pm["isocode"])
            # Home currency uses "----", foreign uses ISOCODE
            pm_currency = "----" if pm["currency_code"] == "----" else pm["isocode"]
            writer.create_gl_account(gl_code, description, pm["journal"],
                                     pm_currency)

        if self.logger:
            self.logger.info("GL account auto-creation check completed")

    def _validate_tax_codes(self, all_docs: dict, writer):
        """Validate that all source tax codes exist and are active in consol DB.

        Only checks code existence — rate comparison is skipped because the TAX
        table TAXRATE can contain auto-rate markers ("A") and multi-value strings
        ("8%;6%") that don't reliably compare with detail-line rates.
        """
        # Collect unique tax codes from all detail lines
        source_codes = set()
        for mod, documents in all_docs.items():
            for doc in documents:
                for dtl in doc.details:
                    if dtl.tax:
                        source_codes.add(dtl.tax)

        if not source_codes:
            return  # No tax codes to validate

        # Get active tax codes from consol DB
        consol_codes = writer.get_active_tax_codes()

        # Check for missing codes
        missing = sorted(source_codes - consol_codes)
        if missing:
            raise Exception(
                f"Tax code(s) not found or inactive in consol DB: {', '.join(missing)}. "
                "Please enable SST/ GST or create these tax codes in SQL Account > SST/ GST > Maintain Tax."
            )

        if self.logger:
            self.logger.info(
                f"Tax code validation passed: {len(source_codes)} code(s) verified"
            )

    def _sync_customers(self, customers, transformer, writer, result):
        """Sync customer master data."""
        total = len(customers)
        for i, cust in enumerate(customers):
            if self._cancelled:
                break

            if self.progress_callback:
                self.progress_callback(i + 1, total, f"Customer: {cust.code}")

            try:
                transformed = transformer.transform_customer(cust)
                if writer.upsert_customer(transformed):
                    result.customers_synced += 1
                else:
                    result.customers_failed += 1
            except TransformError as e:
                result.customers_skipped += 1
                if self.logger:
                    self.logger.warning(f"Customer skipped: {e}")
            except Exception as e:
                result.customers_failed += 1
                if self.logger:
                    self.logger.error(f"Customer '{cust.code}' failed", e)

    def _sync_documents(self, documents, doc_type, transformer, writer, result):
        """Sync AR documents of a specific type."""
        total = len(documents)
        synced = 0
        skipped = 0
        failed = 0
        mod_start = time.time()

        if self.logger:
            self.logger.info(f"--- Syncing {total} {doc_type} documents ---")

        for i, doc in enumerate(documents):
            if self._cancelled:
                break

            if self.progress_callback:
                self.progress_callback(i + 1, total, f"{doc_type}: {doc.doc_no}")

            try:
                transformed = transformer.transform_document(doc)

                if doc_type == "PM":
                    success = writer.insert_ar_payment(transformed)
                elif doc_type == "CT":
                    success = writer.insert_ar_contra(transformed)
                elif doc_type == "CF":
                    success = writer.insert_ar_refund(transformed)
                else:
                    success = writer.insert_ar_document(transformed)

                if success:
                    synced += 1
                else:
                    skipped += 1  # Already exists

            except TransformError as e:
                skipped += 1
                if self.logger:
                    self.logger.warning(f"{doc_type} '{doc.doc_no}' skipped: {e}")
            except Exception as e:
                failed += 1
                if self.logger:
                    self.logger.error(f"{doc_type} '{doc.doc_no}' failed", e)

        result.docs_synced[doc_type] = synced
        result.docs_skipped[doc_type] = skipped
        result.docs_failed[doc_type] = failed

        if self.logger:
            duration = _format_duration(time.time() - mod_start)
            self.logger.info(
                f"{doc_type} complete: {synced} synced, {skipped} skipped, {failed} failed "
                f"(Duration: {duration})"
            )
