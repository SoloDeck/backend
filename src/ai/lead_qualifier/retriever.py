"""
Knowledge retriever for Lead Qualification.

Responsibilities
----------------
- Load the common qualification framework
- Build one FAISS retriever for each profession
- Retrieve the most relevant qualification knowledge
"""

from __future__ import annotations

from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


class LeadQualificationRetriever:
    """
    Loads and caches lead qualification knowledge.

    Expected folder structure:

    ai/
    ├── knowledge/
    │   ├── common/
    │   │   └── qualification-framework.md
    │   └── professions/
    │       ├── software-developer/
    │       │   └── qualification.md
    │       ├── graphic-design/
    │       │   └── qualification.md
    │       └── ...
    """

    def __init__(self):

        # src/ai/knowledge
        self.base_path = (
            Path(__file__).resolve().parent.parent
            / "knowledge"
        )

        self.framework = self._load_framework()

        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=700,
            chunk_overlap=100,
        )

        self.profession_retrievers: dict = {}

        self._build_retrievers()

    # ------------------------------------------------------------
    # Framework
    # ------------------------------------------------------------

    def _load_framework(self) -> str:

        framework_file = (
            self.base_path
            / "common"
            / "qualification-framework.md"
        )

        if not framework_file.exists():
            return ""

        return framework_file.read_text(encoding="utf-8")

    # ------------------------------------------------------------
    # Build FAISS indexes
    # ------------------------------------------------------------

    def _build_retrievers(self):

        professions_dir = (
            self.base_path
            / "professions"
        )

        if not professions_dir.exists():
            return

        for profession_dir in professions_dir.iterdir():

            if not profession_dir.is_dir():
                continue

            qualification_file = (
                profession_dir
                / "qualification.md"
            )

            if not qualification_file.exists():
                continue

            text = qualification_file.read_text(
                encoding="utf-8"
            )

            chunks = self.splitter.create_documents(
                [text]
            )

            vectorstore = FAISS.from_documents(
                chunks,
                self.embeddings,
            )

            self.profession_retrievers[
                profession_dir.name
            ] = vectorstore.as_retriever(
                search_kwargs={"k": 4}
            )

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def retrieve(
        self,
        profession: str | None,
        query: str,
    ) -> str:
        """
        Returns the qualification framework together with the
        most relevant profession-specific qualification knowledge.
        """

        sections = []

        if self.framework:
            sections.append(
                "# Qualification Framework\n\n"
                + self.framework
            )

        if (
            profession
            and profession in self.profession_retrievers
        ):

            docs = self.profession_retrievers[
                profession
            ].invoke(query)

            profession_text = "\n\n".join(
                doc.page_content
                for doc in docs
            )

            sections.append(
                f"# Profession Qualification Guide ({profession})\n\n"
                + profession_text
            )

        return "\n\n".join(sections)