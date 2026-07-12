"""
Knowledge retriever for Lead Qualification.

Responsibilities
----------------
- Load the qualification framework
- Build one FAISS retriever for each profession
- Retrieve the most relevant profession knowledge
"""

from __future__ import annotations

from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


class LeadQualificationRetriever:
    """
    Loads and caches qualification knowledge.

    Framework:
        qualification-framework.md

    Profession Guides:
        software_developer.md
        uiux_designer.md
        graphic_designer.md
        digital_marketing.md
        copywriter.md
        photographer.md
    """

    def __init__(self):

        self.base_path = (
            Path(__file__).parent
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

        self.profession_retrievers = {}

        self._build_retrievers()

    # ------------------------------------------------------------
    # Framework
    # ------------------------------------------------------------

    def _load_framework(self) -> str:

        framework_file = (
            self.base_path
            / "qualification-framework.md"
        )

        if not framework_file.exists():
            return ""

        return framework_file.read_text(encoding="utf-8")

    # ------------------------------------------------------------
    # Build FAISS indexes
    # ------------------------------------------------------------

    def _build_retrievers(self):

        profession_files = {
            "software_developer": "software_developer.md",
            "uiux_designer": "uiux_designer.md",
            "graphic_designer": "graphic_designer.md",
            "digital_marketing": "digital_marketing.md",
            "copywriter": "copywriter.md",
            "photographer": "photographer.md",
        }

        for profession, filename in profession_files.items():

            file_path = self.base_path / filename

            if not file_path.exists():
                continue

            text = file_path.read_text(encoding="utf-8")

            chunks = self.splitter.create_documents([text])

            vectorstore = FAISS.from_documents(
                chunks,
                self.embeddings,
            )

            self.profession_retrievers[profession] = (
                vectorstore.as_retriever(
                    search_kwargs={"k": 4}
                )
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
        Returns all retrieved knowledge as one string.
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
                f"# Profession Guide ({profession})\n\n"
                + profession_text
            )

        return "\n\n".join(sections)