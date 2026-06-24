# SPEC_v2.md — 인사관리 FAQ 챗봇

> **참조 문서:** PRD.md (인사관리 FAQ 챗봇)
> **적용 범위:** 근태·공수·복지 등 인사관리 / RAG + 3-에이전트 하네스
> **API:** OpenAI API (`gpt-4o`)
> **문서 버전:** v2.0
> **작성일:** 2026-06-24
> **상태:** 반영 완료

---

## 0. 이 문서의 목적

PRD에서 정의한 요구사항을 실제 구현에 필요한 상세 명세로 기술한다.

- PRD가 "무엇을 만들 것인가"라면, 이 SPEC은 **"어떻게 만들 것인가"** 를 정의한다.
- v1 대비 핵심 변경: **LLM 제공자를 OpenAI API로 전환**(§5).
- 설계 결정의 근거가 불명확한 항목은 `[결정 필요]`, 이후로 미루는 항목은 `[POST-MVP]`로 표시한다.

---

## 1. 범위 정의

### 1.1 포함 (In Scope)

| 기능 ID | 기능명 | 구현 내용 |
| --- | --- | --- |
| FR-001 | 규정 기반 답변 | 검색된 인사규정·근로기준법 조항(`<근거>`)만 근거로 답변, 문서 밖 생성 금지 |
| FR-002 | 답변 형식 | 결론 → 근거 조문 → 출처 표기 구조 |
| FR-003 | 출처 표기 | 답변 말미에 `(출처: 문서 › 조문)` 형식 |
| FR-004 | 범위 외 처리 | 인사관리(근태·공수·복지) 밖이면 "확인되지 않습니다" + 담당 부서 안내 |
| FR-005 | CoT 자기점검 | 근거 매핑 → 1:1 대조 → 근거 없으면 `(확인 필요)` |
| FR-006 | 인용 검증 | 검증 에이전트가 답변 주장 × 근거 조항 매칭표 생성 |
| FR-007 | 법령 우선 | 사내규정이 근로기준법보다 불리하면 법령 우선 명시(근로기준법 제3조) |
| FR-008 | 오프라인 폴백 | API 키 없으면 FAQ 매칭 답변 + 조문 안내 |
| UX-001 | 웹 UI | 브라우저 채팅 인터페이스(`server.py`), Enter 전송 |
| UX-002 | 예시 질문 칩 | 클릭 시 즉시 질의 |
| UX-003 | 근거/검증 표시 | 근거 조문 접이식, 검증 리포트 표시 |

### 1.2 제외 (Out of Scope)

| 항목 | 제외 이유 |
| --- | --- |
| 로그인 / 권한 관리 | 소규모, 인증 불필요 |
| 대화 이력 영구 저장 | 세션 내 무상태(stateless) |
| 재무·전결규정 영역 | 인사관리로 범위 한정 (PRD 비목표) |
| 인사평가·징계 자동 처리 | 민감 의사결정 제외 (PRD 비목표) |
| 임베딩 기반 검색 | `[POST-MVP]` — 현재는 바이그램+토큰 검색 |

---

## 2. 시스템 구성

### 2.1 전체 구조

```
사용자 (CLI 또는 브라우저)
    │  질문 텍스트
    ▼
[retriever]  인사규정+근로기준법 조문 청크 검색 (오프라인, 바이그램+토큰)
    │  관련 조항 top-4 (<근거>)
    ▼
[harness — 3 에이전트]
    ├─ 답변 에이전트 : <근거>만 사용 + CoT 자기점검   ← OpenAI API
    └─ 검증 에이전트 : 답변 × 근거 조항 매칭표         ← OpenAI API
    ▼
답변 + 출처 + 검증 리포트 → 사람 최종 확인 (HITL)
```

- 검색(retriever)은 외부 API 없이 로컬에서 동작. LLM 호출만 OpenAI API 사용.
- API 키 미설정 시 오프라인 모드(FAQ 매칭 + 조문 안내)로 자동 전환.

### 2.2 파일 구성

```
A1조_FAQ 챗봇/
├── app/
│   ├── chatbot.py       # CLI (하네스/단순/오프라인 모드)
│   ├── retriever.py     # 조문 청킹·검색 (오프라인)
│   ├── harness.py       # 3-에이전트 파이프라인 (OpenAI 호출)
│   ├── llm.py           # OpenAI 클라이언트 공급 (SDK 우선, stdlib 폴백)
│   ├── server.py        # 웹 UI (브라우저 채팅)
│   ├── build_law.py     # 법령 원문(.txt) → 조문 마크다운 변환
│   ├── build_demo.py    # 팀원 공유용 단일 HTML 생성
│   ├── faq.json         # 인사·근로기준법 FAQ 데이터셋
│   └── requirements.txt # 의존성 (openai)
├── 인사/                # 인사규정 (지식베이스)
├── 법령/                # 근로기준법.md (지식베이스)
├── PRD.md
└── SPEC_v2.md           # 본 문서
```

---

## 3. 시스템 프롬프트 명세

### 3.1 구조 (답변 에이전트)

```
[ROLE]    인사관리 FAQ 어시스턴트 — 인사규정 + 근로기준법 근거
[RULES]   CoT 자기점검 절차 (근거 매핑 → 1:1 대조 → 확인 필요)
[법령우선] 근로기준법 최저기준, 충돌 시 법령 우선
[FORMAT]  결론 먼저 → 근거 조문 → (출처: 문서 › 조문)
```

### 3.2 RULES 블록 (CoT 자기점검)

```
1. 질문을 세부 항목으로 분해하고, 각 항목에 대응하는 <근거> 조항을 매핑하라 (누락 점검).
2. 각 주장을 쓰기 전, 그 근거가 <근거> 안에 실제로 있는지 1:1 대조하라.
3. 근거가 없는 내용은 생성하지 말고, 불확실하면 '(확인 필요)'를 붙여라.
4. 점검을 마친 뒤 최종 답변을 출력하라.
```

### 3.3 FORMAT 블록

```
- 결론 먼저, 그다음 근거 조문 제시
- 답변 끝에 반드시 (출처: 문서 › 조문) 표기
- 금액·비율·일수 등 수치는 정확히 인용 (임의 변경 금지)
- 근거에서 답 못 찾으면: "제공된 규정에서는 확인되지 않습니다. 관련 담당 부서에 문의하세요."
```

### 3.4 질문 유형별 처리

| 질문 유형 | 처리 방법 |
| --- | --- |
| 정상 — 규정 내 | FORMAT대로 답변 + 출처 |
| 정상 — 범위 외 | "확인되지 않습니다" + 담당 부서 안내 |
| 법령 충돌 | 근로기준법 우선 명시 |
| 근거 불충분 | `(확인 필요)` 표기 |

---

## 4. UI 명세

### 4.1 화면 구성 (server.py)

```
┌─────────────────────────────────────────┐
│  헤더: 인사관리 FAQ 챗봇   [모드 배지]   │
├─────────────────────────────────────────┤
│  예시 질문 칩들                          │
│  [사용자] 연차휴가 며칠 발생해?          │
│  [챗봇]   답변 + (출처: …)               │
│           ▸ 검증 에이전트 리포트         │
│           ▸ 관련 근거 조문 4개           │
├─────────────────────────────────────────┤
│  [입력창]  Enter 전송           [전송]   │
└─────────────────────────────────────────┘
```

- 모드 배지: API 키 있으면 `🟢 하네스`, 없으면 `🟡 오프라인`.
- 답변·검증 리포트는 마크다운 렌더링(표 포함, marked.js).

---

## 5. API 연동 명세 (OpenAI)

### 5.1 호출 방식 (HTTP)

```http
POST https://api.openai.com/v1/chat/completions

Headers:
  Content-Type: application/json
  Authorization: Bearer {OPENAI_API_KEY}

Body:
{
  "model": "gpt-4o",
  "max_tokens": 2000,
  "messages": [
    { "role": "system",    "content": "{시스템 프롬프트}" },
    { "role": "user",      "content": "<근거>...</근거>\n질문: ..." }
  ]
}
```

### 5.2 Python SDK 호출

```python
import openai
client = openai.OpenAI()          # OPENAI_API_KEY 환경변수 사용

# 단발(검증 에이전트 등)
resp = client.chat.completions.create(
    model="gpt-4o",
    max_tokens=2000,
    messages=[
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ],
)
text = resp.choices[0].message.content

# 스트리밍(단순 모드)
stream = client.chat.completions.create(
    model="gpt-4o", max_tokens=4000, stream=True,
    messages=[{"role": "system", "content": SYSTEM},
              {"role": "user", "content": user_content}],
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

> **클라이언트 공급 (`llm.make_client()`):** 코드는 `openai.OpenAI()`를 직접 만들지
> 않고 `llm.make_client()`로 클라이언트를 얻는다. `openai` SDK가 설치돼 있으면 SDK를
> 그대로 사용하고(본 명세 기준), 설치가 불가한 환경(예: 빌드 휠이 아직 없는 베타
> Python)에서는 표준 라이브러리(urllib)만으로 §5.1의 HTTP API를 호출하는 폴백
> 클라이언트를 반환한다. 두 경로 모두 `client.chat.completions.create(...)`와
> `choices[0].message.content` / `choices[0].delta.content` 인터페이스가 동일하다.

### 5.3 Claude API 대비 변경점 (v1 → v2)

| 항목 | v1 (Claude) | v2 (OpenAI) |
| --- | --- | --- |
| 패키지 | `anthropic` | `openai` |
| 클라이언트 | `anthropic.Anthropic()` | `openai.OpenAI()` |
| 환경변수 | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` |
| 모델 | `claude-opus-4-8` | `gpt-4o` |
| 호출 | `client.messages.create/stream` | `client.chat.completions.create` |
| system | 별도 `system=` 파라미터 | `messages[0] {role:"system"}` |
| 응답 추출 | `resp.content[0].text` | `resp.choices[0].message.content` |
| 스트림 | `stream.text_stream` | `chunk.choices[0].delta.content` |
| 프롬프트 캐싱 | `cache_control: ephemeral` | 자동 (명시 불필요) |

### 5.4 대화 이력 관리

- 현재는 질문 단위 무상태(stateless). 멀티턴 이력은 `[POST-MVP]`.
- 검색된 `<근거>`를 매 요청 system/user에 포함해 grounding 유지.

### 5.5 오류 처리

| 오류 상황 | 처리 |
| --- | --- |
| API 키 미설정 | 오프라인 모드 자동 전환 (FAQ 매칭) |
| API 호출 실패 | 웹 UI: 오류 메시지 카드 표시 / CLI: 예외 출력 |
| 검색 결과 없음 | "확인되지 않습니다" + 담당 부서 안내 |

---

## 6. 비기능 명세

| 항목 | 목표 |
| --- | --- |
| 응답 시간 | OpenAI API 응답 기준 (로딩 표시로 대기 안내) |
| 동시 사용자 | 소규모, 각자 독립 세션 |
| 검색 비용 | 0 (오프라인 로컬 검색) |
| API 키 보안 | 환경변수만 사용, 코드 하드코딩·커밋 금지(.gitignore) |
| 규정 반영 | 마크다운 수정 시 재시작 없이 자동 반영 |

---

## 7. 테스트 명세

### 7.1 검증 체크리스트

```
[ ] FR-001: 검색 조항 밖 내용을 생성하지 않는가
[ ] FR-003: 답변 말미에 (출처: 문서 › 조문)을 표기하는가
[ ] FR-004: 범위 외(재무·전결) 질문에 "확인되지 않습니다"를 안내하는가
[ ] FR-006: 검증 에이전트가 조항 매칭표를 생성하는가
[ ] FR-007: 법령 충돌 시 근로기준법 우선을 명시하는가
[ ] FR-008: API 키 없이 오프라인 답변(FAQ 매칭)이 동작하는가
[ ] §5: OpenAI API로 정상 호출·스트리밍되는가
```

### 7.2 오프라인 검증 (API 키 불필요)

```powershell
py chatbot.py --offline "연차휴가 며칠 발생해?"   # FAQ 매칭 답변
py retriever.py "법정 근로시간"                    # 검색 단독 점검
```

---

## 8. 산출물 및 버전 관리

| 파일 | 설명 |
| --- | --- |
| `app/*.py` | 챗봇 코드 (OpenAI 연동) |
| `app/faq.json` | FAQ 데이터셋 |
| `index.html` | 팀원 공유용 단일 HTML 데모 (더블클릭 / GitHub Pages 배포) |
| `SPEC_v2.md` | 본 명세 (v1 SPEC.md 대체) |

---

## 9. 미결 사항

| # | 항목 | 옵션 |
| --- | --- | --- |
| 1 | OpenAI 모델 | `gpt-4o` (기본) vs `gpt-4o-mini`(저비용) vs `gpt-4.1` |
| 2 | 검증 에이전트 모델 | 답변과 동일 vs 저비용 모델 분리 |

---

## 10. POST-MVP 항목

| 항목 | 우선순위 |
| --- | --- |
| 임베딩 기반 검색(정확도↑) | 높음 |
| 멀티턴 대화 이력 | 중간 |
| 답변 정확도 자동 회귀 테스트(faq.json 평가셋) | 중간 |

---

*본 SPEC_v2는 PRD.md를 기준으로 작성되었으며, v1(Claude API) 대비 OpenAI API 전환을 반영한다.*
