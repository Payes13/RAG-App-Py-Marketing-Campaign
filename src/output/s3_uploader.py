"""
Upload generated PDFs to the output S3 bucket.

Handles duplicate key detection and counter-suffix appending.
Never saves to disk — works entirely from BytesIO buffers.
"""
import io
import logging
import os

from src.utils.file_naming import generate_unique_campaign_key, generate_unique_metadata_key
from src.utils.s3_client import key_exists, upload_file

logger = logging.getLogger(__name__)


def upload_campaign_pdfs(
    campaign_pdf: io.BytesIO,
    metadata_pdf: io.BytesIO,
    route: str,
    date: str,
) -> dict[str, str]:
    """
    Upload campaign and metadata PDFs to the output S3 bucket.

    Checks for existing keys and appends a counter suffix if a file
    with the same route+date already exists.

    Returns:
        {
            "campaign_pdf": "s3://bucket/campaigns/campaign-MTL-SAL-20260304.pdf",
            "metadata_pdf": "s3://bucket/metadata/metadata-campaign-MTL-SAL-20260304.pdf",
        }
    """
    bucket = os.environ["S3_OUTPUT_BUCKET_NAME"]

    # Build set of existing keys so we can detect duplicates
    existing_keys: set[str] = set()

    def _check_and_add(key: str) -> str:
        """Return unique key, adding to existing_keys set after resolution."""
        unique = _resolve_unique_key(key, existing_keys, bucket)
        existing_keys.add(unique)
        return unique

    campaign_key = generate_unique_campaign_key(route, date, existing_keys)
    if key_exists(bucket, campaign_key):
        # Fall back to counter resolution
        existing_keys.add(campaign_key)
        campaign_key = generate_unique_campaign_key(route, date, existing_keys)

    metadata_key = generate_unique_metadata_key(route, date, existing_keys)
    if key_exists(bucket, metadata_key):
        existing_keys.add(metadata_key)
        metadata_key = generate_unique_metadata_key(route, date, existing_keys)

    # Upload campaign PDF
    campaign_uri = upload_file(bucket, campaign_key, campaign_pdf.read())
    logger.info(f"Campaign PDF uploaded: {campaign_uri}")

    # Upload metadata PDF
    metadata_pdf.seek(0)
    metadata_uri = upload_file(bucket, metadata_key, metadata_pdf.read())
    logger.info(f"Metadata PDF uploaded: {metadata_uri}")

    return {
        "campaign_pdf": campaign_uri,
        "metadata_pdf": metadata_uri,
    }


def _resolve_unique_key(base_key: str, existing_keys: set, bucket: str) -> str:
    """Check S3 and local set; return a unique key."""
    if base_key not in existing_keys and not key_exists(bucket, base_key):
        return base_key
    base_no_ext = base_key[:-4]  # strip .pdf
    counter = 2
    while True:
        candidate = f"{base_no_ext}-{counter}.pdf"
        if candidate not in existing_keys and not key_exists(bucket, candidate):
            return candidate
        counter += 1
