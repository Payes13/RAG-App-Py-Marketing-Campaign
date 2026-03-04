"""
Tests for in-memory PDF generation.
"""
import io
from datetime import datetime, timezone

import pytest

from src.output.pdf_generator import generate_campaign_pdf, generate_metadata_pdf


SAMPLE_CAMPAIGN = {
    "subject_line": "Discover Montreal This Summer!",
    "preview_text": "Your family adventure awaits — book now!",
    "body": "Dear traveler,\n\nWe have an amazing offer for you this summer. "
            "Fly from Montreal to San Salvador and experience the best of Central America.\n\n"
            "To unsubscribe from marketing emails, click here.",
    "cta": "Book Your Adventure",
}

SAMPLE_METADATA = {
    "route": "Montreal-San Salvador",
    "audience_description": "young families with children",
    "campaign_type": "email",
    "language": "en",
    "tone": "warm and exciting",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
    "max_tokens": 2048,
    "tokens_used": 1234,
    "sql_queries": ["SELECT * FROM customers WHERE city = 'Montreal'"],
    "tables_accessed": ["customers", "flights"],
    "csv_files_used": ["audiences/latam_families_2024.csv"],
    "rag_chunks": [
        {
            "source_file": "campaign_guide.pdf",
            "content_excerpt": "Family-focused campaigns perform best with warm, engaging language...",
            "similarity": 0.92,
        }
    ],
    "audience_data": "3200 customers found in Montreal area traveling to LATAM routes.",
    "marketing_context": "Previous campaigns for family routes achieved 32% open rates.",
    "full_prompt": "You are a marketing expert...\n[Full prompt content here]",
}


class TestGenerateCampaignPdf:
    def test_returns_bytesio(self):
        buf = generate_campaign_pdf(SAMPLE_CAMPAIGN, "Montreal-San Salvador", "2026-03-04T10:00:00Z")
        assert isinstance(buf, io.BytesIO)

    def test_non_empty_content(self):
        buf = generate_campaign_pdf(SAMPLE_CAMPAIGN, "Montreal-San Salvador", "2026-03-04T10:00:00Z")
        content = buf.read()
        assert len(content) > 1000

    def test_valid_pdf_header(self):
        buf = generate_campaign_pdf(SAMPLE_CAMPAIGN, "Montreal-San Salvador", "2026-03-04T10:00:00Z")
        content = buf.read()
        assert content[:4] == b"%PDF"

    def test_seekable_after_generation(self):
        buf = generate_campaign_pdf(SAMPLE_CAMPAIGN, "Montreal-San Salvador", "2026-03-04T10:00:00Z")
        buf.seek(0)
        assert buf.tell() == 0


class TestGenerateMetadataPdf:
    def test_returns_bytesio(self):
        buf = generate_metadata_pdf(SAMPLE_METADATA)
        assert isinstance(buf, io.BytesIO)

    def test_non_empty_content(self):
        buf = generate_metadata_pdf(SAMPLE_METADATA)
        content = buf.read()
        assert len(content) > 1000

    def test_valid_pdf_header(self):
        buf = generate_metadata_pdf(SAMPLE_METADATA)
        content = buf.read()
        assert content[:4] == b"%PDF"

    def test_empty_metadata_does_not_crash(self):
        buf = generate_metadata_pdf({})
        content = buf.read()
        assert len(content) > 0
