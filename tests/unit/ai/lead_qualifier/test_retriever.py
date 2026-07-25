"""Unit tests for the lead qualifier retriever and lazy caching.

Every test here runs fully OFFLINE: no GEMINI_API_KEY and no network.

`LeadQualificationRetriever.__init__` builds a Gemini embeddings client and,
via `_build_retrievers()`, embeds the profession knowledge with
`FAISS.from_documents(...)` -- both would hit the Google API. We patch the
`GoogleGenerativeAIEmbeddings` class and `FAISS` in the retriever module so
construction never touches the network, then assert on how they were wired.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ai.lead_qualifier import retriever as retriever_module
from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.lead_qualifier.retriever import LeadQualificationRetriever
from src.config.settings import settings

BACKEND_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def reset_retriever_cache():
    """Isolate the class-level `_retriever` cache for lazy-build tests."""

    original = LeadQualifier._retriever
    LeadQualifier._retriever = None

    yield

    LeadQualifier._retriever = original


@pytest.fixture
def patched_gemini(monkeypatch):
    """Patch the Gemini embeddings + FAISS so `__init__` stays offline.

    Returns the `GoogleGenerativeAIEmbeddings` mock so tests can assert the
    exact constructor arguments the retriever used.
    """

    fake_embeddings_cls = MagicMock(name="GoogleGenerativeAIEmbeddings")
    fake_faiss = MagicMock(name="FAISS")

    monkeypatch.setattr(
        retriever_module,
        "GoogleGenerativeAIEmbeddings",
        fake_embeddings_cls,
    )
    monkeypatch.setattr(
        retriever_module,
        "FAISS",
        fake_faiss,
    )

    return fake_embeddings_cls


# --------------------------------------------------
# Laziness
# --------------------------------------------------


class TestLaziness:
    def test_import_does_not_build_retriever(self):
        """Importing the chain must NOT construct the Gemini-backed retriever.

        Proven in a fresh subprocess with an empty GEMINI/GOOGLE key: if the
        retriever were built at import time it would raise (empty key), so a
        clean import that also reports `_retriever is None` proves the build
        is deferred to first use.
        """

        code = textwrap.dedent(
            """
            from src.ai.lead_qualifier.chain import LeadQualifier

            assert LeadQualifier._retriever is None, "retriever built at import time"
            print("IMPORT_OK")
            """
        )

        env = {
            **os.environ,
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "SKIP_DB_INIT": "1",
        }
        env.setdefault("SECRET_KEY", "ci-test-secret-key-32-chars-min!!")
        env.setdefault("JWT_SECRET_KEY", "ci-test-jwt-key-32-chars-minimum!")

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(BACKEND_ROOT),
        )

        assert result.returncode == 0, result.stderr
        assert "IMPORT_OK" in result.stdout

    def test_get_retriever_builds_once_and_caches(
        self,
        reset_retriever_cache,
        patched_gemini,
    ):
        """First `_get_retriever()` builds; the second returns the cached one."""

        assert LeadQualifier._retriever is None

        first = LeadQualifier._get_retriever()

        assert isinstance(first, LeadQualificationRetriever)
        assert LeadQualifier._retriever is first

        second = LeadQualifier._get_retriever()

        # Same cached instance, not rebuilt.
        assert second is first
        # Embeddings client constructed exactly once across both calls.
        assert patched_gemini.call_count == 1


# --------------------------------------------------
# Gemini wiring
# --------------------------------------------------


class TestGeminiWiring:
    def test_constructs_gemini_embeddings_with_expected_model(
        self,
        patched_gemini,
    ):
        """Embeddings are the Gemini text-embedding-004 model, no network hit."""

        LeadQualificationRetriever()

        patched_gemini.assert_called_once_with(
            model="models/text-embedding-004",
            google_api_key=settings.gemini_api_key,
        )

    def test_build_uses_gemini_embeddings_for_faiss(
        self,
        patched_gemini,
        monkeypatch,
    ):
        """FAISS indexes are built from the Gemini embeddings instance."""

        fake_faiss = retriever_module.FAISS

        r = LeadQualificationRetriever()

        # If any profession knowledge exists, FAISS was fed the embeddings obj.
        if fake_faiss.from_documents.call_count:
            _, kwargs = fake_faiss.from_documents.call_args
            args, _ = fake_faiss.from_documents.call_args
            passed_embeddings = args[1] if len(args) > 1 else kwargs.get("embedding")
            assert passed_embeddings is r.embeddings
            assert r.embeddings is patched_gemini.return_value


# --------------------------------------------------
# retrieve()
# --------------------------------------------------


class _Doc:
    def __init__(self, content):
        self.page_content = content


class _FakeProfessionRetriever:
    def __init__(self, docs):
        self._docs = docs
        self.invoked_with = None

    def invoke(self, query):
        self.invoked_with = query
        return self._docs


class TestRetrieve:
    def test_includes_framework_and_profession_knowledge(self, patched_gemini):
        r = LeadQualificationRetriever()
        r.framework = "FRAMEWORK-TEXT"

        fake = _FakeProfessionRetriever(
            [_Doc("PROF-CHUNK-1"), _Doc("PROF-CHUNK-2")]
        )
        r.profession_retrievers = {"software-developer": fake}

        out = r.retrieve(profession="software-developer", query="need a website")

        assert "FRAMEWORK-TEXT" in out
        assert "PROF-CHUNK-1" in out
        assert "PROF-CHUNK-2" in out
        assert "software-developer" in out
        assert fake.invoked_with == "need a website"

    def test_unknown_profession_returns_framework_only(self, patched_gemini):
        r = LeadQualificationRetriever()
        r.framework = "FRAMEWORK-TEXT"
        r.profession_retrievers = {}

        out = r.retrieve(profession="nonexistent", query="q")

        assert "FRAMEWORK-TEXT" in out
        assert "Profession Qualification Guide" not in out

    def test_none_profession_returns_framework_only(self, patched_gemini):
        r = LeadQualificationRetriever()
        r.framework = "FRAMEWORK-TEXT"
        r.profession_retrievers = {"software-developer": _FakeProfessionRetriever([])}

        out = r.retrieve(profession=None, query="q")

        assert "FRAMEWORK-TEXT" in out
        assert "Profession Qualification Guide" not in out

    def test_no_framework_no_profession_returns_empty(self, patched_gemini):
        r = LeadQualificationRetriever()
        r.framework = ""
        r.profession_retrievers = {}

        assert r.retrieve(profession=None, query="q") == ""
