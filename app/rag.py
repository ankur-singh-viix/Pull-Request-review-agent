"""Team-guidelines RAG: a dependency-free TF-IDF retriever behind LangChain's retriever API.

Each `## RULE-ID: title` section in guidelines/*.md becomes one Document. The file name decides
which reviewer category sees the rule. Swap this for Chroma/FAISS + embeddings when the rulebook
grows past a few dozen rules; the node code only depends on `.invoke(query)`.
"""
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from app import heuristics

GUIDELINES_DIR = Path(os.getenv("GUIDELINES_DIR") or Path(__file__).resolve().parent.parent / "guidelines")
FILE_CATEGORY = {"security": "security", "reliability": "bug", "style": "style", "testing": "tests"}
STOP = {"def", "return", "import", "from", "self", "for", "the", "and", "not", "with", "you",
        "that", "this", "are", "use", "any", "all", "else", "elif", "class", "pass"}
MAX_QUERY_CHARS = 4_000


def guidelines_enabled() -> bool:
    return os.getenv("USE_GUIDELINES", "1") != "0"


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", text.lower()) if len(t) > 2 and t not in STOP]


def _vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    vec = {t: (1 + math.log(c)) * idf.get(t, 0.0) for t, c in Counter(tokens).items()}
    norm = math.sqrt(sum(x * x for x in vec.values())) or 1.0
    return {t: x / norm for t, x in vec.items()}


def load_guidelines(directory: Path | None = None) -> list[Document]:
    docs: list[Document] = []
    for path in sorted((directory or GUIDELINES_DIR).glob("*.md")):
        category = FILE_CATEGORY.get(path.stem, "style")
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE):
            title, body = m.group(1).strip(), m.group(2).strip()
            docs.append(Document(
                page_content=f"{title}\n{body}",
                metadata={"rule_id": title.split(":")[0].strip(), "category": category,
                          "source": path.name}))
    return docs


class GuidelineRetriever(BaseRetriever):
    docs: list[Document]
    idf: dict[str, float] = Field(default_factory=dict)
    vectors: list[dict[str, float]] = Field(default_factory=list)
    k: int = 8
    min_score: float = 0.05

    @classmethod
    def from_documents(cls, docs: list[Document], k: int = 8) -> "GuidelineRetriever":
        token_lists = [_tokens(d.page_content) for d in docs]
        df: Counter[str] = Counter()
        for toks in token_lists:
            df.update(set(toks))
        n = len(docs)
        idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        vectors = [_vector(toks, idf) for toks in token_lists]
        return cls(docs=docs, idf=idf, vectors=vectors, k=k)

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun
                                ) -> list[Document]:
        qv = _vector(_tokens(query), self.idf)
        scored = sorted(
            ((sum(w * dv.get(t, 0.0) for t, w in qv.items()), d)
             for d, dv in zip(self.docs, self.vectors, strict=True)),
            key=lambda x: x[0], reverse=True)
        return [d.model_copy(update={"metadata": {**d.metadata, "score": round(s, 3)}})
                for s, d in scored[: self.k] if s >= self.min_score]


@lru_cache(maxsize=1)
def get_retriever() -> GuidelineRetriever:
    return GuidelineRetriever.from_documents(load_guidelines())


def build_query(diff: str, change_types: list[str]) -> str:
    added = "\n".join(text for _, _, text in heuristics.added_lines(diff))
    return (added + "\n" + " ".join(change_types))[:MAX_QUERY_CHARS]