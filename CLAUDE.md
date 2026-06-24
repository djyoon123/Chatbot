# CLAUDE.md — AI 작업 규칙 (인사관리 FAQ 챗봇)

## 기본 원칙

- 모든 변경 전 루트 `SPEC_v2.md`를 확인하고 성공 기준을 만족하는 코드를 작성한다.
- 한 커밋 = 한 기능/한 수정 (단계별로 작게 커밋).
- 실데이터·비밀키는 절대 커밋하지 않는다 (`.gitignore` 준수).

## 범위

- 인사관리(근태·공수·복지) + 근로기준법으로 한정한다.
- 재무·전결규정은 범위 외다 (PRD 비목표). retriever는 `인사/`, `법령/`만 인덱싱한다.

## 코드 스타일

- 언어: Python 3.10+
- 인코딩: UTF-8 (한글 처리 필수)
- 타입 힌트 사용 (`from __future__ import annotations`)
- 줄 길이 제한 없음, 가독성 우선

## LLM / API

- 제공자: **OpenAI** (`openai` SDK, 모델 `gpt-4o`).
- 호출: `client.chat.completions.create(...)`, 스트리밍은 `stream=True` + `chunk.choices[0].delta.content`.
- 시스템 프롬프트는 `messages[0] {role:"system"}`로 전달한다.
- 키는 `OPENAI_API_KEY` 환경변수로만 사용한다.

## 테스트

- 코드 변경 후 `python retriever.py "테스트 질문"` 으로 검색 동작 확인
- `python chatbot.py --offline "테스트 질문"` 으로 오프라인(API 키 불필요) 확인
- API 호출이 포함된 변경은 실제 실행해서 검증 후 커밋

## 금지 사항

- 실제 개인정보·사내 기밀 데이터를 코드나 파일에 포함하지 않는다
- `OPENAI_API_KEY`를 코드에 하드코딩하지 않는다
- 규정 파일(`*.md`) 외 외부 데이터를 소비자 AI(ChatGPT·claude.ai 등)에 업로드하지 않는다
- 검증 에이전트를 우회해서 답변만 출력하는 코드를 기본값으로 두지 않는다

## 파일 구조 규칙

```
A1조_FAQ 챗봇/
├─ app/              # 실행 코드 (chatbot, retriever, harness, server, build_law, build_demo)
├─ 인사/             # 인사규정 (지식베이스, 수정하면 자동 반영)
├─ 법령/             # 근로기준법.md (build_law.py로 생성)
├─ PRD.md            # 제품 요구사항
├─ SPEC_v2.md        # 구현 명세 (OpenAI API)
├─ CLAUDE.md         # 이 파일
└─ .gitignore
```

## 규정 문서 수정 방법

- `인사/`, `법령/` 아래 `.md` 파일을 직접 편집
- 헤딩(`##`, `###`) 기준으로 청킹되므로 헤딩 형식 유지
- 코드 재시작 없이 자동 반영됨

## 법령 준수

- 근로기준법은 상위 법령이며 최저기준이다. 사내규정이 법보다 근로자에게 불리하면
  근로기준법이 우선한다(근로기준법 제3조).
- 법령 원문(`근로기준법(법률)...txt`, CP949)이 갱신되면 `python app/build_law.py`로
  `법령/근로기준법.md`를 다시 생성한다.
- 답변은 인사규정과 근로기준법을 함께 고려하고, 충돌 시 법령 우선을 명시한다.
