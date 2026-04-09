"""Data transformation logic for consolidation.

Handles prefix mapping, customer code transformation, and document number rewriting.
"""

from config import EntityConfig
from source_reader import CustomerRecord, ARDocRecord, SYProfile
from logger import SyncLogger


class TransformError(Exception):
    """Raised when a transformation rule fails."""
    pass


class DataTransformer:
    """Transforms source data for the consolidation database."""

    def __init__(self, entity: EntityConfig, profile: SYProfile, logger: SyncLogger = None):
        self.entity = entity
        self.profile = profile
        self.prefix = profile.alias  # Entity prefix from SY_PROFILE.ALIAS
        self.logger = logger
        self.currency_map = {}  # Source currency CODE → ISOCODE mapping
        self.pm_lookup = {}    # Source PMMETHOD.CODE → JOURNAL-ISOCODE mapping

    def transform_customer_code(self, original_code: str) -> str:
        """Transform customer code: strip source prefix, prepend entity prefix.

        Example: '300-A0001' with prefix 'A1' and customer_code_prefix '300-'
                 → strip '300-' → 'A0001' → prepend 'A1-' → 'A1-A0001'
        """
        code_prefix = self.entity.customer_code_prefix

        if not original_code.startswith(code_prefix):
            raise TransformError(
                f"Customer code '{original_code}' does not start with "
                f"expected prefix '{code_prefix}'. Skipping."
            )

        stripped = original_code[len(code_prefix):]
        new_code = f"{self.prefix}-{stripped}"

        # SQL Account limit: 10 characters for customer code
        if len(new_code) > 10:
            raise TransformError(
                f"Transformed customer code '{new_code}' exceeds 10 chars "
                f"(got {len(new_code)}). Original: '{original_code}'"
            )

        return new_code

    def transform_doc_no(self, original_doc_no: str) -> str:
        """Transform document number: prepend entity prefix.

        Example: 'INV-1001' with prefix 'A1' → 'A1-INV-1001'
        """
        return f"{self.prefix}-{original_doc_no}"

    def transform_customer(self, customer: CustomerRecord) -> dict:
        """Transform a customer record for the consol DB.

        Returns a dict with transformed fields ready for SDK insertion.
        """
        new_code = self.transform_customer_code(customer.code)

        return {
            "code": new_code,
            "company_name": customer.company_name,
            "company_name2": self.profile.company_name,  # Source SY_PROFILE.COMPANYNAME
            "attention": customer.attention,
            "phone1": customer.phone1,
            "email": customer.email,
            "address1": customer.address1,
            "address2": customer.address2,
            "address3": customer.address3,
            "address4": customer.address4,
            "postcode": customer.postcode,
            "company_category": self.entity.customer_category_map.get(customer.code, ""),
            "currency_code": self._map_currency(customer.currency_code),
        }

    def _map_currency(self, source_currency_code: str) -> str:
        """Map source currency CODE to consol currency CODE (ISOCODE).

        Home currency ("----") passes through unchanged.
        Foreign currencies are mapped via currency_map (source CODE → ISOCODE).
        """
        if not source_currency_code or source_currency_code == "----":
            return source_currency_code
        return self.currency_map.get(source_currency_code, source_currency_code)

    def transform_document(self, doc: ARDocRecord) -> dict:
        """Transform an AR document for the consol DB.

        Returns a dict with transformed fields ready for SDK insertion.
        """
        new_code = self.transform_customer_code(doc.code)
        new_doc_no = self.transform_doc_no(doc.doc_no)

        result = {
            "doc_type": doc.doc_type,
            "doc_no": new_doc_no,
            "doc_date": doc.doc_date,
            "post_date": doc.post_date,
            "code": new_code,
            "description": doc.description,
            "currency_code": self._map_currency(doc.currency_code),
            "currency_rate": doc.currency_rate,
            "amount": doc.amount,
            "local_amount": doc.local_amount,
            "cancelled": doc.cancelled,
            "details": doc.details,
            "company_category": self.entity.customer_category_map.get(doc.code, ""),
        }

        # Payment-specific fields (PM and CF both have payment method + cheque)
        if doc.doc_type in ("PM", "CF"):
            result["payment_method"] = self.pm_lookup.get(
                doc.payment_method, doc.payment_method)
            result["cheque_no"] = doc.cheque_no

        # Transform knock-off doc numbers (PM and CN both knock off IV/DN)
        if doc.knockoffs:
            result["knockoffs"] = []
            for ko in doc.knockoffs:
                result["knockoffs"].append({
                    "doc_type": ko.doc_type,
                    "doc_no": self.transform_doc_no(ko.doc_no),
                    "ko_amt": ko.ko_amt,
                    "local_ko_amt": ko.local_ko_amt,
                    "actual_local_ko_amt": ko.actual_local_ko_amt,
                    "gain_loss": ko.gain_loss,
                })

        return result
