"""
Tests for the RAG pipeline (vector store similarity search).
"""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestSimilaritySearch:
    @patch("src.db.vector_store.get_connection")
    def test_returns_top_k_results(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {"id": 1, "content": "Campaign for families", "source_file": "doc1.pdf",
             "metadata": {}, "similarity": 0.95},
            {"id": 2, "content": "Montreal route info", "source_file": "doc2.pdf",
             "metadata": {}, "similarity": 0.88},
            {"id": 3, "content": "Latin America marketing tips", "source_file": "doc3.pdf",
             "metadata": {}, "similarity": 0.81},
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from src.db.vector_store import similarity_search
        results = similarity_search([0.1] * 1536, top_k=3)

        assert len(results) == 3
        assert results[0]["similarity"] == 0.95

    @patch("src.db.vector_store.get_connection")
    def test_empty_results_returns_empty_list(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        from src.db.vector_store import similarity_search
        results = similarity_search([0.0] * 1536, top_k=3)
        assert results == []


class TestPdfRagTool:
    @patch("src.tools.pdf_rag_tool.similarity_search")
    @patch("src.tools.pdf_rag_tool.get_embeddings")
    def test_tool_formats_results(self, mock_embeddings, mock_search):
        mock_embeddings.return_value.embed_query.return_value = [0.1] * 1536
        mock_search.return_value = [
            {"id": 1, "content": "Great family destinations", "source_file": "guide.pdf",
             "similarity": 0.92},
        ]

        from src.tools.pdf_rag_tool import search_campaign_documents
        result = search_campaign_documents.invoke("family marketing strategies")

        assert "Great family destinations" in result
        assert "guide.pdf" in result

    @patch("src.tools.pdf_rag_tool.similarity_search")
    @patch("src.tools.pdf_rag_tool.get_embeddings")
    def test_tool_returns_no_results_message(self, mock_embeddings, mock_search):
        mock_embeddings.return_value.embed_query.return_value = [0.0] * 1536
        mock_search.return_value = []

        from src.tools.pdf_rag_tool import search_campaign_documents
        result = search_campaign_documents.invoke("unknown topic")
        assert "No relevant documents" in result
