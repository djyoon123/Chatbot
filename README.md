# 인사관리 FAQ 챗봇 (RAG + 3-에이전트 하네스)

사내 **인사규정**과 상위 법령인 **근로기준법**을 지식베이스로 삼아, 임직원의
근태·공수·복지 질문에 **근거 조문·출처·검증 리포트**를 함께 제공하는 RAG 챗봇입니다.

> 🔗 **라이브 데모 (설치 없이 바로 보기)**: https://djyoon123.github.io/Chatbot/
> — API 키 없이 동작하는 오프라인 UI(FAQ·규정 검색). 생성형 답변·검증은 키 설정 후 로컬 실행에서 동작합니다.

> 환각(없는 규정 지어내기)을 막기 위해 **검색 → 답변 → 검증** 3단계 에이전트를 거치고,
> 사람이 검증 리포트를 보고 최종 신뢰 여부를 판단합니다 (HITL).

```
질문
 └─▶ [검색 에이전트]   인사규정·근로기준법 조항 top-4 검색 (오프라인)
      └─▶ [답변 에이전트]  근거 조항만 사용 + CoT 자기점검         ← OpenAI
           └─▶ [검증 에이전트]  주장 × 조항 매칭표 작성            ← OpenAI
                └─▶ 사람: 검증 리포트 확인 후 신뢰 여부 판단 (HITL)
```

- **모델**: OpenAI `gpt-4o` (Chat Completions API)
- **검색**: 외부 임베딩 불필요 — 문자 바이그램 + 토큰 가중 오프라인 검색
- **오프라인 동작**: API 키가 없어도 `faq.json`(검증된 Q&A) 매칭으로 즉답 + 관련 조문 안내
- **의존성 0개로도 실행 가능**: `openai` SDK가 없으면 표준 라이브러리(urllib) 폴백이 자동 동작

---

## 빠른 시작

> **요구사항**: Python 3.10+ (Windows에서 `python`이 안 되면 `py` 런처 사용)

```bash
git clone <이-저장소-URL>
cd "A1조_FAQ 챗봇/app"

# (선택) OpenAI SDK 설치 — 없어도 stdlib 폴백으로 동작합니다
pip install -r requirements.txt
```

### API 키 없이 바로 체험 (오프라인)
```bash
python chatbot.py --offline "연차휴가 며칠 발생해?"
python retriever.py "법정 근로시간"        # 검색기 단독 점검
```

### AI 답변·검증까지 (API 키 필요)
```bash
# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
# macOS / Linux
export OPENAI_API_KEY="sk-..."

python chatbot.py "연차휴가 며칠 발생해?"           # 3-에이전트 하네스
python chatbot.py --simple "법정 근로시간 얼마야?"   # 스트리밍(답변만)
```

### 웹 UI (브라우저 채팅)
```bash
python server.py          # http://localhost:8000 자동 오픈
```
API 키가 있으면 하네스 모드, 없으면 오프라인 모드로 자동 전환됩니다.

### 설치·서버 없이 더블클릭 데모
```bash
python build_demo.py      # → 루트에 index.html 생성 (더블클릭 / GitHub Pages 배포용)
```

---

## 프로젝트 구조

```
A1조_FAQ 챗봇/
├─ app/                # 실행 코드
│  ├─ chatbot.py        # CLI (하네스 / 단순 / 오프라인)
│  ├─ retriever.py      # 조문 청킹·검색 (오프라인 RAG)
│  ├─ harness.py        # 3-에이전트 파이프라인
│  ├─ llm.py            # OpenAI 클라이언트 (SDK 우선, stdlib 폴백)
│  ├─ server.py         # 웹 UI (표준 라이브러리만)
│  ├─ build_law.py      # 법령 원문(.txt) → 조문 마크다운 변환
│  ├─ build_demo.py     # 공유용 단일 HTML 생성
│  └─ faq.json          # FAQ 데이터셋
├─ 인사/               # 인사규정 (지식베이스 · 수정 시 자동 반영)
├─ 법령/               # 근로기준법.md (build_law.py로 생성)
├─ PRD.md / SPEC_v2.md  # 제품 요구사항 / 구현 명세
└─ README.md            # 이 문서
```

자세한 사용법은 [app/README.md](app/README.md), 설계 명세는 [SPEC_v2.md](SPEC_v2.md) 참조.

---

## 범위와 원칙

- **범위**: 인사관리(근태·공수·복지) + 근로기준법으로 한정. 재무·전결규정은 범위 외입니다.
- **법령 우선**: 근로기준법은 최저기준이며, 사내규정이 법보다 근로자에게 불리하면
  근로기준법이 우선합니다(근로기준법 제3조). 답변은 둘을 함께 고려해 충돌 시 법령 우선을 명시합니다.
- **규정 자동 반영**: `인사/`·`법령/`의 `.md`를 수정하면 코드 재시작 없이 반영됩니다.

> ⚠️ **샘플 데이터 안내**: 저장소의 인사규정·전결규정 등은 **가상의 예시(샘플)**이며 특정
> 회사의 실제 규정이 아닙니다. 근로기준법 원문은 국가법령정보센터 공개 자료입니다.
> 실제 적용 시 노동관계법령·취업규칙과의 정합성 검토가 필요합니다.

---

## 라이선스

[MIT](LICENSE) — 자유롭게 사용·수정·배포할 수 있습니다.
