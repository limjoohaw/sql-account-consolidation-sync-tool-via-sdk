"""Consolidation DB writer using SQL Account SDK Live (COM).

Writes Company Categories, Customers, and AR documents to the consol DB.
Uses BizObjects for business logic validation.
"""

import datetime
from config import ConsolDBConfig
from sdk_session import open_consol_session
from logger import SyncLogger


def fetch_company_categories(consol_config: ConsolDBConfig, logger: SyncLogger = None) -> list:
    """Login to consol DB, read all Company Categories, logout.

    Returns list of {"code": str, "description": str}.
    """
    try:
        with open_consol_session(consol_config, logger) as app:
            ds = app.DBManager.NewDataSet(
                "SELECT CODE, DESCRIPTION FROM COMPANYCATEGORY ORDER BY CODE"
            )
            categories = []
            ds.First()
            while not ds.Eof:
                categories.append({
                    "code": (ds.FindField("CODE").AsString or "").strip(),
                    "description": (ds.FindField("DESCRIPTION").AsString or "").strip(),
                })
                ds.Next()
            return categories
    except Exception as e:
        if logger:
            logger.warning(f"Could not fetch Company Categories: {e}")
        return []


class ConsolWriter:
    """Writes transformed data into the consolidation database via SDK."""

    def __init__(self, sdk_app, logger: SyncLogger = None):
        """
        Args:
            sdk_app: Active COM SQLAcc.BizApp object (already logged in).
            logger: SyncLogger instance.
        """
        self.app = sdk_app
        self.logger = logger
        self._default_accounts = {}  # Cache: {"SalesAccount": "500-000", ...}

    def _get_default_account(self, registry_name: str) -> str:
        """Get default GL account from consol DB SY_REGISTRY."""
        if registry_name in self._default_accounts:
            return self._default_accounts[registry_name]
        try:
            ds = self.app.DBManager.NewDataSet(
                f"SELECT RVALUE FROM SY_REGISTRY WHERE RNAME='{registry_name}'"
            )
            ds.First()
            val = (ds.FindField("RVALUE").AsString or "").strip() if not ds.Eof else ""
            self._default_accounts[registry_name] = val
            if self.logger:
                self.logger.info(f"Default GL account [{registry_name}] = '{val}'")
            return val
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not read {registry_name} from SY_REGISTRY: {e}")
            self._default_accounts[registry_name] = ""
            return ""

    def _get_default_payment_method(self) -> str:
        """Get first BANK payment method from consol DB PMMETHOD."""
        if "PaymentMethod" in self._default_accounts:
            return self._default_accounts["PaymentMethod"]
        try:
            ds = self.app.DBManager.NewDataSet(
                "SELECT FIRST 1 CODE FROM PMMETHOD WHERE JOURNAL='BANK'"
            )
            ds.First()
            val = (ds.FindField("CODE").AsString or "").strip() if not ds.Eof else ""
            self._default_accounts["PaymentMethod"] = val
            if self.logger:
                self.logger.info(f"Default payment method = '{val}'")
            return val
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not read PMMETHOD from consol DB: {e}")
            self._default_accounts["PaymentMethod"] = ""
            return ""

    def get_active_tax_codes(self) -> set:
        """Get all active tax codes from consol DB TAX table.

        Returns:
            set of active tax code strings.
        """
        if "_tax_codes" in self._default_accounts:
            return self._default_accounts["_tax_codes"]
        try:
            ds = self.app.DBManager.NewDataSet(
                "SELECT CODE FROM TAX WHERE ISACTIVE=TRUE ORDER BY CODE"
            )
            codes = set()
            ds.First()
            while not ds.Eof:
                code = (ds.FindField("CODE").AsString or "").strip()
                if code:
                    codes.add(code)
                ds.Next()
            self._default_accounts["_tax_codes"] = codes
            if self.logger:
                self.logger.info(f"Loaded {len(codes)} active tax codes from consol DB")
            return codes
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not read TAX table from consol DB: {e}")
            self._default_accounts["_tax_codes"] = {}
            return {}

    def _account_for_doc_type(self, doc_type: str) -> str:
        """Get the default GL account for a given AR document type."""
        if doc_type in ("IV", "DN"):
            return self._get_default_account("SalesAccount")
        elif doc_type == "CN":
            return self._get_default_account("SalesReturnAccount")
        return ""

    # ------------------------------------------------------------------
    # Currency
    # ------------------------------------------------------------------
    def get_consol_currencies(self) -> set:
        """Get all ISOCODEs present in consol DB CURRENCY table."""
        if "_currencies" in self._default_accounts:
            return self._default_accounts["_currencies"]
        try:
            ds = self.app.DBManager.NewDataSet(
                "SELECT ISOCODE FROM CURRENCY ORDER BY CODE"
            )
            codes = set()
            ds.First()
            while not ds.Eof:
                iso = (ds.FindField("ISOCODE").AsString or "").strip()
                if iso:
                    codes.add(iso)
                ds.Next()
            self._default_accounts["_currencies"] = codes
            if self.logger:
                self.logger.info(f"Loaded {len(codes)} currencies from consol DB")
            return codes
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not read CURRENCY table from consol DB: {e}")
            self._default_accounts["_currencies"] = set()
            return set()

    def create_currency(self, isocode: str, description: str, symbol: str) -> bool:
        """Create a new currency in consol DB via SDK BizObject."""
        try:
            biz = self.app.BizObjects.Find("CURRENCY")
            main_ds = biz.DataSets.Find("MainDataSet")

            # Check if already exists
            doc_key = biz.FindKeyByRef("CODE", isocode)
            if doc_key is not None:
                biz.Close()
                return False  # Already exists

            biz.New()
            main_ds.FindField("CODE").AsString = isocode
            main_ds.FindField("DESCRIPTION").AsString = description
            main_ds.FindField("ISOCODE").AsString = isocode
            main_ds.FindField("SYMBOL").AsString = symbol
            biz.Save()
            biz.Close()

            # Invalidate cache
            self._default_accounts.pop("_currencies", None)

            if self.logger:
                self.logger.info(f"Created currency: {isocode} ({description})")
            return True
        except Exception as e:
            try:
                biz.Close()
            except Exception:
                pass
            if self.logger:
                self.logger.error(f"Failed to create currency '{isocode}'", e)
            return False

    # ------------------------------------------------------------------
    # GL Account
    # ------------------------------------------------------------------
    def get_gl_account_codes(self) -> set:
        """Get all GL account codes from consol DB."""
        if "_gl_codes" in self._default_accounts:
            return self._default_accounts["_gl_codes"]
        try:
            ds = self.app.DBManager.NewDataSet(
                "SELECT CODE FROM GL_ACC ORDER BY CODE"
            )
            codes = set()
            ds.First()
            while not ds.Eof:
                code = (ds.FindField("CODE").AsString or "").strip()
                if code:
                    codes.add(code)
                ds.Next()
            self._default_accounts["_gl_codes"] = codes
            if self.logger:
                self.logger.info(f"Loaded {len(codes)} GL accounts from consol DB")
            return codes
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not read GL_ACC from consol DB: {e}")
            self._default_accounts["_gl_codes"] = set()
            return set()

    def _get_ca_parent_dockey(self):
        """Get the DocKey of GL_ACC where CODE='_CA_' (Current Asset parent)."""
        if "_ca_dockey" in self._default_accounts:
            return self._default_accounts["_ca_dockey"]
        try:
            biz = self.app.BizObjects.Find("GL_ACC")
            doc_key = biz.FindKeyByRef("CODE", "_CA_")
            biz.Close()
            self._default_accounts["_ca_dockey"] = doc_key
            if self.logger and doc_key is not None:
                self.logger.info(f"Found GL_ACC '_CA_' parent DocKey = {doc_key}")
            return doc_key
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not find GL_ACC '_CA_' parent: {e}")
            self._default_accounts["_ca_dockey"] = None
            return None

    def create_gl_account(self, gl_code: str, description: str, journal: str,
                         isocode: str) -> bool:
        """Create a GL account for a currency bank/cash in consol DB.

        Creating a GL_ACC with SpecialAccType=BA/CH auto-creates a PMMETHOD
        in SQL Account. After creation, we edit that PMMETHOD to assign the
        correct CurrencyCode.

        Args:
            gl_code: GL account code (e.g. "BANK-USD")
            description: Currency description (e.g. "US Dollar")
            journal: "BANK" or "CASH" — determines SpecialAccType
            isocode: Currency ISO code for PMMETHOD CurrencyCode assignment
        """
        try:
            biz = self.app.BizObjects.Find("GL_ACC")
            main_ds = biz.DataSets.Find("MainDataSet")

            doc_key = biz.FindKeyByRef("CODE", gl_code)
            if doc_key is not None:
                biz.Close()
                return False  # Already exists

            parent_dockey = self._get_ca_parent_dockey()
            if not parent_dockey:
                biz.Close()
                if self.logger:
                    self.logger.error("Cannot create GL account: _CA_ parent not found")
                return False

            biz.New()
            main_ds.FindField("PARENT").value = parent_dockey
            main_ds.FindField("CODE").AsString = gl_code
            main_ds.FindField("DESCRIPTION").AsString = description
            main_ds.FindField("ACCTYPE").AsString = "CA"
            special_acc = "BA" if journal == "BANK" else "CH"
            main_ds.FindField("SPECIALACCTYPE").AsString = special_acc
            biz.Save()
            biz.Close()

            # Invalidate cache
            self._default_accounts.pop("_gl_codes", None)

            if self.logger:
                self.logger.info(f"Created GL account: {gl_code} ({description}) [{special_acc}]")

            # Edit the auto-created PMMETHOD to assign CurrencyCode
            self._set_pmmethod_currency(gl_code, isocode)

            return True
        except Exception as e:
            try:
                biz.Close()
            except Exception:
                pass
            if self.logger:
                self.logger.error(f"Failed to create GL account '{gl_code}'", e)
            return False

    def _set_pmmethod_currency(self, pm_code: str, isocode: str):
        """Edit an auto-created PMMETHOD to assign its CurrencyCode."""
        try:
            biz = self.app.BizObjects.Find("PMMETHOD")
            main_ds = biz.DataSets.Find("MainDataSet")

            doc_key = biz.FindKeyByRef("CODE", pm_code)
            if doc_key is None:
                biz.Close()
                if self.logger:
                    self.logger.warning(f"PMMETHOD '{pm_code}' not found for currency assignment")
                return

            biz.Params.Find("CODE").Value = doc_key
            biz.Open()
            biz.Edit()
            main_ds.FindField("CURRENCYCODE").AsString = isocode
            biz.Save()
            biz.Close()

            if self.logger:
                self.logger.info(f"Set PMMETHOD '{pm_code}' CurrencyCode = '{isocode}'")
        except Exception as e:
            try:
                biz.Close()
            except Exception:
                pass
            if self.logger:
                self.logger.warning(f"Failed to set PMMETHOD currency for '{pm_code}': {e}")

    # ------------------------------------------------------------------
    # Purge & Re-sync
    # ------------------------------------------------------------------
    def get_entity_documents(self, doc_type: str, prefix: str,
                             date_from: str = None, date_to: str = None) -> list:
        """Query consol DB for documents matching entity prefix and date range.

        Returns list of dicts with header fields for comparison.
        """
        table = f"AR_{doc_type}"
        sql = f"SELECT DOCNO, DOCDATE, CODE, DOCAMT, DESCRIPTION, CURRENCYCODE, CURRENCYRATE FROM {table} WHERE DOCNO LIKE '{prefix}-%'"
        if date_from:
            sql += f" AND DOCDATE >= '{date_from}'"
        if date_to:
            sql += f" AND DOCDATE <= '{date_to}'"
        sql += " ORDER BY DOCNO"

        try:
            ds = self.app.DBManager.NewDataSet(sql)
            results = []
            ds.First()
            while not ds.Eof:
                results.append({
                    "doc_no": (ds.FindField("DOCNO").AsString or "").strip(),
                    "doc_date": (ds.FindField("DOCDATE").AsString or "").strip(),
                    "code": (ds.FindField("CODE").AsString or "").strip(),
                    "doc_amt": ds.FindField("DOCAMT").AsFloat,
                    "description": (ds.FindField("DESCRIPTION").AsString or "").strip(),
                    "currency_code": (ds.FindField("CURRENCYCODE").AsString or "").strip(),
                    "currency_rate": ds.FindField("CURRENCYRATE").AsFloat,
                })
                ds.Next()
            return results
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not query {table} for prefix '{prefix}': {e}")
            return []

    def delete_document(self, doc_type: str, doc_no: str) -> bool:
        """Delete a document from consol DB via SDK BizObject.

        SQL Account auto un-knock-offs related documents on delete.
        """
        biz_key = f"AR_{doc_type}"
        try:
            biz = self.app.BizObjects.Find(biz_key)
            doc_key = biz.FindKeyByRef("DOCNO", doc_no)
            if doc_key is None:
                biz.Close()
                if self.logger:
                    self.logger.warning(f"Cannot delete {doc_type} '{doc_no}': not found")
                return False

            biz.Params.Find("DocKey").Value = doc_key
            biz.Open()
            biz.Delete()
            biz.Close()

            if self.logger:
                self.logger.info(f"Deleted {doc_type} '{doc_no}'")
            return True
        except Exception as e:
            try:
                biz.Close()
            except Exception:
                pass
            if self.logger:
                self.logger.error(f"Failed to delete {doc_type} '{doc_no}'", e)
            return False

    # ------------------------------------------------------------------
    # Company Category
    # ------------------------------------------------------------------
    def upsert_company_category(self, code: str, description: str) -> bool:
        """Create or update a Company Category in the consol DB."""
        try:
            biz = self.app.BizObjects.Find("COMPANYCATEGORY")
            main_ds = biz.DataSets.Find("MainDataSet")

            doc_key = biz.FindKeyByRef("CODE", code)

            if doc_key is None:
                # Create new
                biz.New()
                main_ds.FindField("CODE").value = code
                main_ds.FindField("DESCRIPTION").value = description
            else:
                # Update existing
                biz.Params.Find("CODE").Value = doc_key
                biz.Open()
                biz.Edit()
                main_ds.FindField("DESCRIPTION").value = description

            biz.Save()
            biz.Close()
            if self.logger:
                self.logger.success(f"Company Category '{code}' upserted")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to upsert Company Category '{code}'", e)
            try:
                biz.Close()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # Customer
    # ------------------------------------------------------------------
    def upsert_customer(self, data: dict) -> bool:
        """Create or update a Customer in the consol DB.

        Args:
            data: Dict with keys: code, company_name, attention, phone1,
                  email, address1-4, postcode, company_category
        """
        code = data["code"]
        try:
            biz = self.app.BizObjects.Find("AR_CUSTOMER")
            main_ds = biz.DataSets.Find("MainDataSet")
            branch_ds = biz.DataSets.Find("cdsBranch")

            doc_key = biz.FindKeyByRef("CODE", code)

            if doc_key is None:
                # Create new customer
                biz.New()
                main_ds.FindField("CODE").value = code
                main_ds.FindField("COMPANYNAME").value = data.get("company_name", "")
                main_ds.FindField("COMPANYNAME2").value = data.get("company_name2", "")
                main_ds.FindField("COMPANYCATEGORY").value = data.get("company_category", "")
                if data.get("currency_code"):
                    main_ds.FindField("CURRENCYCODE").AsString = data["currency_code"]

                # Set billing branch details
                branch_ds.Edit()
                branch_ds.FindField("BRANCHNAME").AsString = "BILLING"
                branch_ds.FindField("ATTENTION").AsString = data.get("attention", "")
                branch_ds.FindField("PHONE1").AsString = data.get("phone1", "")
                branch_ds.FindField("EMAIL").AsString = data.get("email", "")
                branch_ds.FindField("ADDRESS1").AsString = data.get("address1", "")
                branch_ds.FindField("ADDRESS2").AsString = data.get("address2", "")
                branch_ds.FindField("ADDRESS3").AsString = data.get("address3", "")
                branch_ds.FindField("ADDRESS4").AsString = data.get("address4", "")
                branch_ds.FindField("POSTCODE").AsString = data.get("postcode", "")
                branch_ds.Post()
            else:
                # Update existing customer
                biz.Params.Find("CODE").Value = doc_key
                biz.Open()
                biz.Edit()
                main_ds.FindField("COMPANYNAME").value = data.get("company_name", "")
                main_ds.FindField("COMPANYNAME2").value = data.get("company_name2", "")
                main_ds.FindField("COMPANYCATEGORY").value = data.get("company_category", "")

            biz.Save()
            biz.Close()
            if self.logger:
                self.logger.success(f"Customer '{code}' upserted")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to upsert Customer '{code}'", e)
            try:
                biz.Close()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # AR Documents (IV, DN, CN)
    # ------------------------------------------------------------------
    def insert_ar_document(self, data: dict) -> bool:
        """Insert an AR document (IV, DN, CN) into the consol DB.

        Args:
            data: Transformed document dict from DataTransformer.
        """
        doc_type = data["doc_type"]
        doc_no = data["doc_no"]
        biz_key = self._ar_biz_key(doc_type)

        if not biz_key:
            if self.logger:
                self.logger.error(f"Unknown document type: {doc_type}")
            return False

        try:
            biz = self.app.BizObjects.Find(biz_key)
            main_ds = biz.DataSets.Find("MainDataSet")
            detail_ds = biz.DataSets.Find("cdsDocDetail")

            # Check if already exists
            doc_key = biz.FindKeyByRef("DOCNO", doc_no)
            if doc_key is not None:
                if self.logger:
                    self.logger.warning(f"{doc_type} '{doc_no}' already exists, skipping")
                biz.Close()
                return False

            biz.New()

            # Header
            main_ds.FindField("DOCNO").AsString = doc_no
            if data.get("doc_date"):
                main_ds.FindField("DOCDATE").AsString = self._parse_date(data["doc_date"])
            if data.get("post_date"):
                main_ds.FindField("POSTDATE").AsString = self._parse_date(data["post_date"])
            main_ds.FindField("CODE").AsString = data["code"]
            if data.get("description"):
                main_ds.FindField("DESCRIPTION").AsString = data["description"]
            if data.get("currency_code"):
                main_ds.FindField("CURRENCYCODE").AsString = data["currency_code"]
                main_ds.FindField("CURRENCYRATE").AsFloat = data.get("currency_rate", 1.0)

            # Detail lines — use consol DB default GL account
            default_account = self._account_for_doc_type(doc_type)
            for i, dtl in enumerate(data.get("details", [])):
                detail_ds.Append()
                detail_ds.FindField("SEQ").value = i + 1
                if default_account:
                    detail_ds.FindField("ACCOUNT").AsString = default_account
                # Description = "OriginalGLAccount || OriginalDescription"
                desc_parts = []
                if dtl.account:
                    desc_parts.append(dtl.account)
                if dtl.description:
                    desc_parts.append(dtl.description)
                if desc_parts:
                    detail_ds.FindField("DESCRIPTION").AsString = " || ".join(desc_parts)
                if dtl.tax:
                    detail_ds.FindField("TAX").AsString = dtl.tax
                if dtl.tax_rate:
                    detail_ds.FindField("TAXRATE").AsString = dtl.tax_rate
                detail_ds.FindField("TAXINCLUSIVE").value = (dtl.tax_inclusive == "T")
                detail_ds.FindField("TAXAMT").AsFloat = dtl.tax_amt
                if dtl.exempted_tax_rate:
                    detail_ds.FindField("EXEMPTED_TAXRATE").AsString = dtl.exempted_tax_rate
                detail_ds.FindField("EXEMPTED_TAXAMT").AsFloat = dtl.exempted_tax_amt
                detail_ds.FindField("AMOUNT").AsFloat = dtl.amount
                detail_ds.Post()

            # Knock-off for CN (CN knocks off IV/DN)
            if doc_type == "CN" and data.get("knockoffs"):
                ko_ds = biz.DataSets.Find("cdsKnockOff")
                for ko in data["knockoffs"]:
                    v = [ko["doc_type"], ko["doc_no"]]
                    if ko_ds.Locate("DocType;DocNo", v, False, False):
                        ko_ds.Edit()
                        ko_ds.FindField("KOAmt").AsFloat = ko["ko_amt"]
                        ko_ds.FindField("LocalKOAmt").AsFloat = ko.get("local_ko_amt", 0)
                        ko_ds.FindField("ActualLocalKOAmt").AsFloat = ko.get("actual_local_ko_amt", 0)
                        ko_ds.FindField("GainLoss").AsFloat = ko.get("gain_loss", 0)
                        ko_ds.FindField("KnockOff").value = True
                        ko_ds.Post()
                    else:
                        if self.logger:
                            self.logger.warning(
                                f"CN knock-off target not found: {ko['doc_type']} '{ko['doc_no']}'"
                            )

            biz.Save()
            biz.Close()
            if self.logger:
                self.logger.success(f"{doc_type} '{doc_no}' inserted")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to insert {doc_type} '{doc_no}'", e)
            try:
                biz.Close()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # AR Contra (CT)
    # ------------------------------------------------------------------
    def insert_ar_contra(self, data: dict) -> bool:
        """Insert an AR Contra with knock-off into the consol DB."""
        doc_no = data["doc_no"]

        try:
            biz = self.app.BizObjects.Find("AR_CT")
            main_ds = biz.DataSets.Find("MainDataSet")
            ko_ds = biz.DataSets.Find("cdsKnockOff")

            # Check if already exists
            doc_key = biz.FindKeyByRef("DOCNO", doc_no)
            if doc_key is not None:
                if self.logger:
                    self.logger.warning(f"CT '{doc_no}' already exists, skipping")
                biz.Close()
                return False

            biz.New()

            # Header
            main_ds.FindField("DOCNO").AsString = doc_no
            if data.get("doc_date"):
                main_ds.FindField("DOCDATE").AsString = self._parse_date(data["doc_date"])
            if data.get("post_date"):
                main_ds.FindField("POSTDATE").AsString = self._parse_date(data["post_date"])
            main_ds.FindField("CODE").AsString = data["code"]
            main_ds.FindField("DOCAMT").AsFloat = data.get("amount", 0)
            if data.get("description"):
                main_ds.FindField("DESCRIPTION").AsString = data["description"]
            if data.get("currency_code"):
                main_ds.FindField("CURRENCYCODE").AsString = data["currency_code"]
                main_ds.FindField("CURRENCYRATE").AsFloat = data.get("currency_rate", 1.0)

            # Knock-off invoices (CT knocks off IV/DN)
            for ko in data.get("knockoffs", []):
                v = [ko["doc_type"], ko["doc_no"]]
                if ko_ds.Locate("DocType;DocNo", v, False, False):
                    ko_ds.Edit()
                    ko_ds.FindField("KOAmt").AsFloat = ko["ko_amt"]
                    ko_ds.FindField("LocalKOAmt").AsFloat = ko.get("local_ko_amt", 0)
                    ko_ds.FindField("ActualLocalKOAmt").AsFloat = ko.get("actual_local_ko_amt", 0)
                    ko_ds.FindField("GainLoss").AsFloat = ko.get("gain_loss", 0)
                    ko_ds.FindField("KnockOff").value = True
                    ko_ds.Post()
                else:
                    if self.logger:
                        self.logger.warning(
                            f"CT knock-off target not found: {ko['doc_type']} '{ko['doc_no']}'"
                        )

            biz.Save()
            biz.Close()
            if self.logger:
                self.logger.success(f"CT '{doc_no}' inserted")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to insert CT '{doc_no}'", e)
            try:
                biz.Close()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # AR Payment (PM)
    # ------------------------------------------------------------------
    def insert_ar_payment(self, data: dict) -> bool:
        """Insert an AR Payment with knock-off into the consol DB."""
        doc_no = data["doc_no"]

        try:
            biz = self.app.BizObjects.Find("AR_PM")
            main_ds = biz.DataSets.Find("MainDataSet")
            ko_ds = biz.DataSets.Find("cdsKnockOff")

            # Check if already exists
            doc_key = biz.FindKeyByRef("DOCNO", doc_no)
            if doc_key is not None:
                if self.logger:
                    self.logger.warning(f"PM '{doc_no}' already exists, skipping")
                biz.Close()
                return False

            biz.New()

            # Header
            main_ds.FindField("DOCNO").AsString = doc_no
            if data.get("doc_date"):
                main_ds.FindField("DOCDATE").AsString = self._parse_date(data["doc_date"])
            if data.get("post_date"):
                main_ds.FindField("POSTDATE").AsString = self._parse_date(data["post_date"])
            main_ds.FindField("CODE").AsString = data["code"]
            main_ds.FindField("DOCAMT").AsFloat = data.get("amount", 0)
            pm_method = data.get("payment_method") or self._get_default_payment_method()
            if pm_method:
                main_ds.FindField("PAYMENTMETHOD").AsString = pm_method
            if data.get("cheque_no"):
                main_ds.FindField("CHEQUENUMBER").AsString = data["cheque_no"]
            if data.get("description"):
                main_ds.FindField("DESCRIPTION").AsString = data["description"]
            if data.get("currency_code"):
                main_ds.FindField("CURRENCYCODE").AsString = data["currency_code"]
                main_ds.FindField("CURRENCYRATE").AsFloat = data.get("currency_rate", 1.0)

            # Knock-off invoices
            for ko in data.get("knockoffs", []):
                # Locate the matching outstanding document
                v = [ko["doc_type"], ko["doc_no"]]
                if ko_ds.Locate("DocType;DocNo", v, False, False):
                    ko_ds.Edit()
                    ko_ds.FindField("KOAmt").AsFloat = ko["ko_amt"]
                    ko_ds.FindField("LocalKOAmt").AsFloat = ko.get("local_ko_amt", 0)
                    ko_ds.FindField("ActualLocalKOAmt").AsFloat = ko.get("actual_local_ko_amt", 0)
                    ko_ds.FindField("GainLoss").AsFloat = ko.get("gain_loss", 0)
                    ko_ds.FindField("KnockOff").value = True
                    ko_ds.Post()
                else:
                    if self.logger:
                        self.logger.warning(
                            f"Knock-off target not found: {ko['doc_type']} '{ko['doc_no']}'"
                        )

            biz.Save()
            biz.Close()
            if self.logger:
                self.logger.success(f"PM '{doc_no}' inserted")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to insert PM '{doc_no}'", e)
            try:
                biz.Close()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # AR Customer Refund (CF)
    # ------------------------------------------------------------------
    def insert_ar_refund(self, data: dict) -> bool:
        """Insert an AR Customer Refund with knock-off into the consol DB.

        CF is like PM but knocks off CN or PM (not IV/DN).
        """
        doc_no = data["doc_no"]

        try:
            biz = self.app.BizObjects.Find("AR_CF")
            main_ds = biz.DataSets.Find("MainDataSet")
            ko_ds = biz.DataSets.Find("cdsKnockOff")

            # Check if already exists
            doc_key = biz.FindKeyByRef("DOCNO", doc_no)
            if doc_key is not None:
                if self.logger:
                    self.logger.warning(f"CF '{doc_no}' already exists, skipping")
                biz.Close()
                return False

            biz.New()

            # Header
            main_ds.FindField("DOCNO").AsString = doc_no
            if data.get("doc_date"):
                main_ds.FindField("DOCDATE").AsString = self._parse_date(data["doc_date"])
            if data.get("post_date"):
                main_ds.FindField("POSTDATE").AsString = self._parse_date(data["post_date"])
            main_ds.FindField("CODE").AsString = data["code"]
            main_ds.FindField("DOCAMT").AsFloat = data.get("amount", 0)
            pm_method = data.get("payment_method") or self._get_default_payment_method()
            if pm_method:
                main_ds.FindField("PAYMENTMETHOD").AsString = pm_method
            if data.get("cheque_no"):
                main_ds.FindField("CHEQUENUMBER").AsString = data["cheque_no"]
            if data.get("description"):
                main_ds.FindField("DESCRIPTION").AsString = data["description"]
            if data.get("currency_code"):
                main_ds.FindField("CURRENCYCODE").AsString = data["currency_code"]
                main_ds.FindField("CURRENCYRATE").AsFloat = data.get("currency_rate", 1.0)

            # Knock-off (CF knocks off CN or PM)
            for ko in data.get("knockoffs", []):
                v = [ko["doc_type"], ko["doc_no"]]
                if ko_ds.Locate("DocType;DocNo", v, False, False):
                    ko_ds.Edit()
                    ko_ds.FindField("KOAmt").AsFloat = ko["ko_amt"]
                    ko_ds.FindField("LocalKOAmt").AsFloat = ko.get("local_ko_amt", 0)
                    ko_ds.FindField("ActualLocalKOAmt").AsFloat = ko.get("actual_local_ko_amt", 0)
                    ko_ds.FindField("GainLoss").AsFloat = ko.get("gain_loss", 0)
                    ko_ds.FindField("KnockOff").value = True
                    ko_ds.Post()
                else:
                    if self.logger:
                        self.logger.warning(
                            f"CF knock-off target not found: {ko['doc_type']} '{ko['doc_no']}'"
                        )

            biz.Save()
            biz.Close()
            if self.logger:
                self.logger.success(f"CF '{doc_no}' inserted")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to insert CF '{doc_no}'", e)
            try:
                biz.Close()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def check_doc_exists(self, biz_key: str, doc_no: str) -> bool:
        """Check if a document already exists in the consol DB."""
        try:
            biz = self.app.BizObjects.Find(biz_key)
            doc_key = biz.FindKeyByRef("DOCNO", doc_no)
            biz.Close()
            return doc_key is not None
        except Exception:
            return False

    def _ar_biz_key(self, doc_type: str) -> str:
        """Map AR document type to BizObject key."""
        return {
            "IV": "AR_IV",
            "DN": "AR_DN",
            "CN": "AR_CN",
            "CT": "AR_CT",
            "PM": "AR_PM",
            "CF": "AR_CF",
        }.get(doc_type, "")

    def _parse_date(self, date_val) -> str:
        """Convert date value to dd/mm/yyyy string for SDK.

        Accepts datetime.date, datetime.datetime, or string formats.
        Returns dd/mm/yyyy string that SDK accepts directly.
        """
        if not date_val:
            return datetime.datetime.now().strftime("%d/%m/%Y")

        # Already a datetime.date or datetime.datetime
        if isinstance(date_val, (datetime.date, datetime.datetime)):
            return date_val.strftime("%d/%m/%Y")

        # String parsing
        date_str = str(date_val).strip()
        try:
            # "2026-03-11" or "2026-03-11 00:00:00"
            dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
        try:
            # Already dd/mm/yyyy — validate and return
            dt = datetime.datetime.strptime(date_str[:10], "%d/%m/%Y")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
        return datetime.datetime.now().strftime("%d/%m/%Y")
