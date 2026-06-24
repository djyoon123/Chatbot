"""
server.py — 인사관리 FAQ 챗봇 웹 UI (표준 라이브러리만 사용, 추가 설치 불필요)

브라우저에서 질문하고 답변·근거 조문·검증 리포트를 확인하는 로컬 웹 앱.
  py server.py                http://localhost:8000 (브라우저 자동 오픈)
  py server.py --no-browser   브라우저 자동 오픈 생략
  py server.py --port 9000    포트 지정

OPENAI_API_KEY가 있으면 하네스(답변+검증) 모드,
없으면 오프라인 모드(FAQ 매칭 답변 + 조문 안내)로 동작한다.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from retriever import Retriever
from harness import harness
from chatbot import best_faq, load_faq
from llm import make_client, transport_label

APP_DIR = Path(__file__).resolve().parent

retriever = Retriever()
FAQ = load_faq()
client = None
if os.environ.get("OPENAI_API_KEY"):
    client = make_client()


# ---------------------------------------------------------------------------
# 질의 처리 (오프라인 / 하네스 공통 진입점)
# ---------------------------------------------------------------------------

def handle_ask(question: str) -> dict:
    results = retriever.search(question, k=4)
    sources = [
        {"source": c.source, "score": round(s, 3), "text": c.text}
        for c, s in results
    ]

    if client is None:
        # 오프라인: FAQ 매칭 → 없으면 조문 발췌 → 점수 낮으면 범위 밖 안내
        item, fscore = best_faq(question, FAQ)
        top_score = results[0][1] if results else 0.0
        if item and fscore >= 0.25:
            return {"mode": "offline", "kind": "faq",
                    "answer": item["answer"], "answer_source": item["source"],
                    "report": None, "sources": sources}
        if results and top_score >= 0.10:
            top = results[0][0]
            return {"mode": "offline", "kind": "excerpt",
                    "answer": top.text, "answer_source": top.source,
                    "report": None, "sources": sources}
        return {"mode": "offline", "kind": "none",
                "answer": "문의하신 내용은 인사관리(근태·공수·복지) FAQ 범위에서 확인되지 않습니다. 관련 담당 부서에 문의하세요.",
                "answer_source": None, "report": None, "sources": []}

    # 하네스: 답변 에이전트 + 검증 에이전트
    draft, report, _ = harness(client, retriever, question)
    return {"mode": "harness", "kind": "harness",
            "answer": draft, "answer_source": None,
            "report": report, "sources": sources}


# ---------------------------------------------------------------------------
# HTTP 핸들러
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            badge = "🟢 하네스 (API 연결)" if client else "🟡 오프라인 (API 키 없음)"
            mode = "harness" if client else "offline"
            html = INDEX_HTML.replace("__BADGE__", badge).replace("__MODE__", mode)
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:
        if self.path != "/api/ask":
            self._send(404, json.dumps({"error": "not found"}))
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            question = (json.loads(raw).get("question") or "").strip()
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "잘못된 요청입니다."}, ensure_ascii=False))
            return
        if not question:
            self._send(400, json.dumps({"error": "질문이 비어 있습니다."}, ensure_ascii=False))
            return
        try:
            result = handle_ask(question)
            self._send(200, json.dumps(result, ensure_ascii=False))
        except Exception as e:  # API 오류 등을 클라이언트에 전달
            self._send(500, json.dumps({"error": f"오류: {e}"}, ensure_ascii=False))

    def log_message(self, *args) -> None:  # 콘솔 로그 억제
        pass


# ---------------------------------------------------------------------------
# 프런트엔드 (단일 HTML)
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>인사관리 FAQ 챗봇</title>
<style>
:root{
  --bg:#f4f6f9;--panel:#fff;--ink:#1f2933;--muted:#6b7280;
  --brand:#2563eb;--brand-weak:#e8f0fe;--line:#e5e7eb;--bad:#dc2626;--warn:#d97706;
}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI','Malgun Gothic',system-ui,sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:14px 20px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
header h1{font-size:17px;margin:0;font-weight:700}
.badge{margin-left:auto;font-size:12px;padding:5px 11px;border-radius:999px;background:var(--brand-weak);color:var(--brand);font-weight:600;white-space:nowrap}
.wrap{max-width:820px;margin:0 auto;padding:18px}
.examples{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:7px 12px;font-size:13px;cursor:pointer}
.chip:hover{border-color:var(--brand);color:var(--brand)}
#chat{display:flex;flex-direction:column;gap:14px;margin-bottom:96px}
.msg{display:flex}
.msg.user{justify-content:flex-end}
.bubble{max-width:85%;padding:10px 14px;border-radius:14px;line-height:1.6;font-size:14px;background:var(--brand);color:#fff;border-bottom-right-radius:4px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;max-width:100%}
.answer{padding:14px 16px;line-height:1.65;font-size:14px}
.answer table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
.answer th,.answer td{border:1px solid var(--line);padding:6px 8px;text-align:left}
.answer th{background:#f8fafc}
.answer p{margin:.4em 0}
.src{font-size:12px;color:var(--muted);padding:0 16px 12px}
.src b{color:var(--brand)}
details{border-top:1px solid var(--line)}
summary{cursor:pointer;padding:10px 16px;font-size:13px;font-weight:600;color:var(--muted);user-select:none}
summary:hover{color:var(--ink)}
.src-item{padding:8px 16px;border-top:1px dashed var(--line)}
.src-item .meta{color:var(--muted);font-size:12px;margin-bottom:4px}
.src-item pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:inherit;color:#374151;font-size:12.5px;max-height:200px;overflow:auto}
.note{font-size:12px;color:var(--muted);padding:0 16px 12px}
.kind-excerpt{background:#fffbeb;border-left:3px solid var(--warn);padding:8px 12px;font-size:12.5px;color:#92400e;margin:12px 16px 0;border-radius:6px}
form{position:fixed;bottom:0;left:0;right:0;background:var(--panel);border-top:1px solid var(--line);padding:12px}
.form-inner{max-width:820px;margin:0 auto;display:flex;gap:8px}
#q{flex:1;border:1px solid var(--line);border-radius:10px;padding:11px 14px;font-size:14px;outline:none}
#q:focus{border-color:var(--brand)}
button.send{background:var(--brand);color:#fff;border:0;border-radius:10px;padding:0 18px;font-size:14px;font-weight:600;cursor:pointer}
button.send:disabled{opacity:.5;cursor:default}
.loading{display:flex;gap:5px;align-items:center;color:var(--muted);font-size:13px;padding:13px 16px}
.dot{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:b 1.2s infinite}
.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
@keyframes b{0%,60%,100%{opacity:.3}30%{opacity:1}}
</style>
</head>
<body>
<header>
  <h1>📋 인사관리 FAQ 챗봇</h1>
  <span class="badge">__BADGE__</span>
</header>
<div class="wrap">
  <div class="examples" id="examples"></div>
  <div id="chat"></div>
</div>
<form id="form">
  <div class="form-inner">
    <input id="q" placeholder="인사규정·근로기준법에 대해 물어보세요. 예) 연차휴가 며칠 발생해?" autocomplete="off">
    <button class="send" type="submit">전송</button>
  </div>
</form>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
const MODE="__MODE__";
const EXAMPLES=["연차휴가 며칠 발생해?","법정 근로시간 얼마야?","배우자 출산 시 경조휴가는?","급여는 언제 지급돼?","인사평가 S등급 성과급은?","정년은 몇 세야?"];
const chat=document.getElementById('chat'),form=document.getElementById('form'),qInput=document.getElementById('q'),sendBtn=form.querySelector('button');
const exWrap=document.getElementById('examples');
EXAMPLES.forEach(t=>{const b=document.createElement('button');b.className='chip';b.type='button';b.textContent=t;b.onclick=()=>{qInput.value=t;form.requestSubmit();};exWrap.appendChild(b);});
function md(t){if(window.marked)return marked.parse(t);const d=document.createElement('div');d.textContent=t;return '<pre style="white-space:pre-wrap;font-family:inherit">'+d.innerHTML+'</pre>';}
function el(h){const d=document.createElement('div');d.innerHTML=h.trim();return d.firstChild;}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function scroll(){window.scrollTo(0,document.body.scrollHeight);}
function addUser(t){chat.appendChild(el(`<div class="msg user"><div class="bubble">${esc(t)}</div></div>`));scroll();}
function addLoading(){const n=el(`<div class="msg bot"><div class="card"><div class="loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span> 답변 생성 중…</div></div></div>`);chat.appendChild(n);scroll();return n;}
function render(r){
  let s='';
  if(r.kind==='excerpt')s+=`<div class="kind-excerpt">정확히 일치하는 FAQ가 없어, 가장 관련 높은 규정 조문을 안내합니다.</div>`;
  s+=`<div class="answer">${md(r.answer||'')}</div>`;
  if(r.answer_source)s+=`<div class="src">출처: <b>${esc(r.answer_source)}</b></div>`;
  if(r.report)s+=`<details open><summary>🔎 검증 에이전트 리포트</summary><div class="answer">${md(r.report)}</div></details>`;
  if(r.sources&&r.sources.length){
    const items=r.sources.map(x=>`<div class="src-item"><div class="meta">(${x.score}) ${esc(x.source)}</div><pre>${esc(x.text)}</pre></div>`).join('');
    s+=`<details><summary>📚 관련 근거 조문 ${r.sources.length}개</summary>${items}</details>`;
  }
  if(MODE==='offline')s+=`<div class="note">※ API 키를 설정하면 OpenAI가 여러 조문을 종합해 답변·검증합니다.</div>`;
  return el(`<div class="msg bot"><div class="card">${s}</div></div>`);
}
async function ask(q){
  addUser(q);qInput.value='';sendBtn.disabled=true;
  const loading=addLoading();
  try{
    const res=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
    const data=await res.json();loading.remove();
    if(data.error)chat.appendChild(el(`<div class="msg bot"><div class="card"><div class="answer" style="color:var(--bad)">⚠️ ${esc(data.error)}</div></div></div>`));
    else chat.appendChild(render(data));
  }catch(e){loading.remove();chat.appendChild(el(`<div class="msg bot"><div class="card"><div class="answer" style="color:var(--bad)">⚠️ 통신 오류: ${esc(String(e))}</div></div></div>`));}
  finally{sendBtn.disabled=false;scroll();qInput.focus();}
}
form.addEventListener('submit',e=>{e.preventDefault();const q=qInput.value.trim();if(q)ask(q);});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    no_browser = "--no-browser" in args
    port = 8000
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except (IndexError, ValueError):
            pass

    mode = f"하네스 (API 연결 · {transport_label(client)})" if client else "오프라인 (API 키 없음)"
    url = f"http://localhost:{port}"
    print("인사관리 FAQ 챗봇 웹 UI")
    print(f"  모드: {mode}")
    print(f"  주소: {url}   (종료: Ctrl+C)")

    if not no_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    server = ThreadingHTTPServer(("", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.shutdown()


if __name__ == "__main__":
    main()
