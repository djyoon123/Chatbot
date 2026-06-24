"""
build_law.py — 법령 원문(.txt, CP949)을 조문 단위 마크다운으로 변환

국가법령정보센터에서 받은 법령 텍스트는 CP949 인코딩에 "제N조(제목)" 형식이다.
이를 마크다운 헤딩(## 장 / ### 조)으로 변환해 retriever가 조문 단위로
청킹·검색할 수 있게 한다(사내규정과 동일한 RAG 파이프라인 재사용).

사용법:
    python build_law.py
    → ../법령/근로기준법.md 생성
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "근로기준법(법률)(제21373호)(20260820).txt"
OUT_DIR = ROOT / "법령"
OUT = OUT_DIR / "근로기준법.md"

HEADER = [
    "# 근로기준법",
    "",
    "> [시행 2026. 8. 20.] [법률 제21373호, 2026. 2. 19., 타법개정]",
    "> 출처: 국가법령정보센터 (사내규정과 함께 준수해야 하는 상위 법령)",
    "",
]

_chapter_re = re.compile(r"^(제\d+장(?:의\d+)?)\s+(.+)$")          # 제N장 제목
_article_re = re.compile(r"^(제\d+조(?:의\d+)?)\(([^)]*)\)\s*(.*)$")  # 제N조(제목) 본문
_enforce_re = re.compile(r"\[시행일:\s*([^\]]+)\]")                  # [시행일: YYYY. MM. DD.]


def convert() -> str:
    text = SRC.read_text(encoding="cp949")
    out: list[str] = list(HEADER)
    started = False        # 머리말(전화번호 등)은 첫 장/조 전까지 건너뜀
    cur_head_idx = -1      # 직전에 출력한 조문 헤딩 위치 (시행일 라벨 소급용)

    for raw in text.splitlines():
        line = raw.strip()
        mc = _chapter_re.match(line)
        ma = _article_re.match(line)

        if mc or ma or line.startswith("부칙"):
            started = True
        if not started:
            continue

        if mc:
            out += ["", f"## {mc.group(1)} {mc.group(2)}"]
            cur_head_idx = -1
        elif ma:
            out += ["", f"### {ma.group(1)} ({ma.group(2)})"]
            cur_head_idx = len(out) - 1   # 이 조문 헤딩 위치 기억
            if ma.group(3):
                out.append(ma.group(3))
        elif line.startswith("부칙"):
            out += ["", f"## {line}"]
            cur_head_idx = -1
        elif not line:
            out.append("")
        else:
            # 개정예정 조문이면 [시행일:...]을 직전 헤딩에 라벨로 붙여 현행과 구분
            m_enf = _enforce_re.search(line)
            if m_enf and cur_head_idx >= 0:
                out[cur_head_idx] += f" [{m_enf.group(1).strip()} 시행]"
            out.append(line)

    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"법령 원문을 찾지 못했습니다: {SRC}")
    OUT_DIR.mkdir(exist_ok=True)
    md = convert()
    OUT.write_text(md, encoding="utf-8")
    n_art = md.count("\n### ")
    n_chap = md.count("\n## 제")
    print(f"생성 완료: {OUT}")
    print(f"  장 {n_chap}개 · 조문 {n_art}개")


if __name__ == "__main__":
    main()
