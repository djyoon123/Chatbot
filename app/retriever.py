"""
retriever.py — 사내규정 문서 검색기 (오프라인 RAG 리트리버)

- 상위 폴더의 규정 마크다운(.md)을 로드한다.
- 마크다운 헤딩(##/###) 단위로 청크(섹션)로 분할한다.
- 한국어에 강건한 '문자 바이그램 + 토큰 가중' 점수로 질문과 가장 관련 있는 청크를 찾는다.
  (외부 임베딩 API가 필요 없어 오프라인에서도 동작한다.)

이 리트리버가 찾은 청크가 챗봇 답변의 '근거(context)'가 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 규정 문서가 있는 루트 (app 폴더의 상위 = 프로젝트 폴더)
DOCS_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Chunk:
    """규정 문서의 한 섹션(청크)."""

    doc: str          # 문서 파일명 (예: 법령/근로기준법.md)
    heading: str      # 섹션 제목 (예: 제60조 (연차 유급휴가))
    text: str         # 섹션 본문 (제목 포함)

    @property
    def source(self) -> str:
        return f"{self.doc} › {self.heading}"


# ---------------------------------------------------------------------------
# 1) 문서 로드 & 청킹
# ---------------------------------------------------------------------------

def _split_into_chunks(doc_name: str, content: str) -> list[Chunk]:
    """마크다운을 ## / ### 헤딩 기준으로 섹션 청크로 분할."""
    chunks: list[Chunk] = []
    current_heading = "(머리말)"
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if not body:
            return
        # 헤딩 줄을 뺀 실제 본문이 있는 청크만 채택 (장 제목만 있는 빈 섹션 제외)
        has_content = any(
            ln.strip() and not re.match(r"^#{2,3}\s", ln.strip()) for ln in buffer
        )
        if has_content:
            chunks.append(Chunk(doc=doc_name, heading=current_heading, text=body))

    for line in content.splitlines():
        m = re.match(r"^#{2,3}\s+(.*)", line)  # ## 또는 ### 헤딩
        if m:
            flush()
            current_heading = m.group(1).strip()
            buffer = [line]
        else:
            buffer.append(line)
    flush()
    return chunks


# 인사관리 챗봇 범위: 인사규정 + 근로기준법만 인덱싱 (재무·전결·규정체계도 제외)
_REG_DIRS = {"인사", "법령"}
_REG_ROOT_FILES: set[str] = set()


def load_chunks(root: Path = DOCS_ROOT) -> list[Chunk]:
    """인사규정(인사/) 및 근로기준법(법령/)만 로드해 청크 리스트로 반환."""
    chunks: list[Chunk] = []
    for md in sorted(root.rglob("*.md")):
        rel_parts = md.relative_to(root).parts
        # 규정 하위 폴더이거나 루트의 규정체계도 파일만 포함
        if rel_parts[0] not in _REG_DIRS and md.name not in _REG_ROOT_FILES:
            continue
        rel = md.relative_to(root).as_posix()
        content = md.read_text(encoding="utf-8")
        chunks.extend(_split_into_chunks(rel, content))
    return chunks


# ---------------------------------------------------------------------------
# 2) 검색 (문자 바이그램 + 토큰 가중)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    # 한글/영문/숫자만 남기고 소문자화
    return re.sub(r"[^0-9A-Za-z가-힣]+", " ", text).lower()


def _bigrams(text: str) -> set[str]:
    t = _normalize(text).replace(" ", "")
    return {t[i : i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}


def _tokens(text: str) -> set[str]:
    return {w for w in _normalize(text).split() if len(w) >= 2}


def text_similarity(a: str, b: str) -> float:
    """두 텍스트의 유사도 (FAQ 질문 매칭 등에 사용). 0~1 범위."""
    ab, bb = _bigrams(a), _bigrams(b)
    bigram = len(ab & bb) / (len(ab) or 1)
    at, bt = _tokens(a), _tokens(b)
    token = len(at & bt) / (len(at) or 1)
    return bigram * 0.5 + token * 0.5


def _score(query: str, chunk: Chunk) -> float:
    """질문과 청크의 관련도 점수."""
    q_big, c_big = _bigrams(query), _bigrams(chunk.text)
    bigram_overlap = len(q_big & c_big) / (len(q_big) or 1)

    q_tok, c_tok = _tokens(query), _tokens(chunk.text + " " + chunk.heading)
    token_overlap = len(q_tok & c_tok) / (len(q_tok) or 1)

    # 제목에 질문 토큰이 직접 등장하면 가산점 (조문 제목 매칭 강화)
    heading_hit = len(q_tok & _tokens(chunk.heading)) * 0.15

    return bigram_overlap * 0.5 + token_overlap * 0.5 + heading_hit


class Retriever:
    """규정 청크를 1회 로드해두고 질문마다 상위 K개를 검색."""

    def __init__(self, root: Path = DOCS_ROOT) -> None:
        self.chunks = load_chunks(root)
        if not self.chunks:
            raise RuntimeError(f"규정 문서를 찾지 못했습니다: {root}")

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        scored = [(c, _score(query, c)) for c in self.chunks]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(c, s) for c, s in scored[:k] if s > 0]


if __name__ == "__main__":
    # 간단 동작 확인:  python retriever.py "연차휴가 며칠 발생해?"
    import sys

    r = Retriever()
    q = sys.argv[1] if len(sys.argv) > 1 else "연차휴가는 며칠 발생하나요?"
    print(f"질문: {q}\n총 청크 수: {len(r.chunks)}\n")
    for chunk, score in r.search(q):
        print(f"[{score:.3f}] {chunk.source}")
