"""
llm.py — OpenAI 클라이언트 공급자 (SDK 우선, 표준 라이브러리 폴백)

CLAUDE.md는 `openai` SDK 사용을 명시한다. SDK가 설치돼 있으면 그대로 사용하고,
SDK 설치가 불가한 환경(예: 빌드 휠이 아직 없는 베타 Python)에서는 표준 라이브러리
(urllib)만으로 동일한 OpenAI Chat Completions API(SPEC §5.1)를 호출하는 폴백
클라이언트를 제공한다. 추가 의존성은 0개다.

두 경우 모두 openai SDK와 동일한 인터페이스를 노출한다:

    client = make_client()
    resp = client.chat.completions.create(model=..., messages=[...], max_tokens=...)
    text = resp.choices[0].message.content                      # 비스트리밍

    stream = client.chat.completions.create(..., stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content                  # 스트리밍
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def make_client():
    """openai SDK가 있으면 SDK 클라이언트, 없으면 stdlib 폴백 클라이언트를 반환.

    OPENAI_API_KEY가 없으면 RuntimeError를 던진다(호출 측에서 오프라인 전환 판단).
    """
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    try:
        import openai  # SDK가 있으면 CLAUDE.md 명세대로 SDK 사용
        return openai.OpenAI()
    except ModuleNotFoundError:
        return _StdlibClient()


def transport_label(client) -> str:
    """현재 클라이언트가 SDK 기반인지 stdlib 폴백인지 사람이 읽을 라벨."""
    return "stdlib HTTP" if isinstance(client, _StdlibClient) else "openai SDK"


class OpenAIError(RuntimeError):
    """폴백 클라이언트의 API 호출 실패를 SDK 예외와 유사하게 표현."""


# ---------------------------------------------------------------------------
# stdlib 폴백: openai SDK 인터페이스(필요한 부분만) 호환 구현
# ---------------------------------------------------------------------------

@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Response:
    choices: list


@dataclass
class _Delta:
    content: str | None


@dataclass
class _StreamChoice:
    delta: _Delta


@dataclass
class _StreamChunk:
    choices: list


def _raise_http_error(e: urllib.error.HTTPError) -> None:
    """OpenAI 오류 응답(JSON)을 읽어 읽기 쉬운 메시지로 변환."""
    try:
        body = e.read().decode("utf-8")
        msg = json.loads(body).get("error", {}).get("message") or body
    except Exception:
        msg = str(e)
    raise OpenAIError(f"OpenAI API 오류 (HTTP {e.code}): {msg}") from None


class _Completions:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _request(self, body: dict) -> urllib.request.Request:
        return urllib.request.Request(
            OPENAI_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

    def create(self, *, model: str, messages: list, max_tokens: int = 2000,
               stream: bool = False, **_ignored):
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if stream:
            body["stream"] = True
            return self._stream(self._request(body))

        try:
            with urllib.request.urlopen(self._request(body)) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            _raise_http_error(e)
        except urllib.error.URLError as e:
            raise OpenAIError(f"OpenAI API 연결 실패: {e.reason}") from None
        content = payload["choices"][0]["message"]["content"]
        return _Response(choices=[_Choice(message=_Message(content=content))])

    def _stream(self, req: urllib.request.Request):
        """SSE(data: {...}) 스트림을 청크 단위로 디코드해 순차 yield."""
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            _raise_http_error(e)
        except urllib.error.URLError as e:
            raise OpenAIError(f"OpenAI API 연결 실패: {e.reason}") from None
        with resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or [{}]
                delta = (choices[0].get("delta") or {}).get("content")
                yield _StreamChunk(choices=[_StreamChoice(delta=_Delta(content=delta))])


class _Chat:
    def __init__(self, api_key: str) -> None:
        self.completions = _Completions(api_key)


class _StdlibClient:
    """openai.OpenAI() 대체. client.chat.completions.create(...)를 지원한다."""

    def __init__(self) -> None:
        self.chat = _Chat(os.environ["OPENAI_API_KEY"])
