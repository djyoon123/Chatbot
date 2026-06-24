"""
build_demo.py — 팀원 공유용 단일 HTML 챗봇 데모 생성

서버 없이 더블클릭으로 열리는 자체완결 HTML 파일을 만든다.
인사규정+근로기준법 조문과 FAQ를 HTML에 임베드하고, 검색·FAQ 매칭 로직을
JS로 포팅해 브라우저에서 오프라인으로 질문·답변을 체험할 수 있다.
(server.py와 동일한 오프라인 규칙: FAQ 매칭 → 조문 발췌 → 범위 밖 안내)

사용법:
    py build_demo.py
    → ../인사관리_FAQ챗봇_공유.html 생성
"""

from __future__ import annotations

import json
from pathlib import Path

from retriever import Retriever
from chatbot import load_faq

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "인사관리_FAQ챗봇_공유.html"


def build_data() -> dict:
    r = Retriever()
    chunks = [{"doc": c.doc, "heading": c.heading, "text": c.text} for c in r.chunks]
    faq = load_faq().get("items", [])
    return {"chunks": chunks, "faq": faq}


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>인사관리 FAQ 챗봇 (공유 데모)</title>
<style>
:root{
  --bg:#f4f6f9;--panel:#fff;--ink:#1f2933;--muted:#6b7280;
  --brand:#2563eb;--brand-weak:#e8f0fe;--line:#e5e7eb;--bad:#dc2626;--warn:#d97706;
}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI','Malgun Gothic',system-ui,sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:14px 20px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
header h1{font-size:17px;margin:0;font-weight:700}
.badge{margin-left:auto;font-size:12px;padding:5px 11px;border-radius:999px;background:#fef3c7;color:#92400e;font-weight:600;white-space:nowrap}
.wrap{max-width:820px;margin:0 auto;padding:18px}
.intro{font-size:13px;color:var(--muted);background:var(--brand-weak);border-radius:10px;padding:10px 14px;margin-bottom:14px}
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
.loading{display:flex;gap:5px;align-items:center;color:var(--muted);font-size:13px;padding:13px 16px}
.dot{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:b 1.2s infinite}
.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
@keyframes b{0%,60%,100%{opacity:.3}30%{opacity:1}}
</style>
</head>
<body>
<header>
  <h1>📋 인사관리 FAQ 챗봇</h1>
  <span class="badge">🟡 공유 데모 (오프라인)</span>
</header>
<div class="wrap">
  <div class="intro">이 데모는 설치·서버 없이 동작합니다. 인사규정·근로기준법 조문과 FAQ가 파일에 포함돼 있어, 브라우저에서 바로 질문·답변을 체험할 수 있습니다. (생성형 답변은 API 연결 버전에서 동작)</div>
  <div class="examples" id="examples"></div>
  <div id="chat"></div>
</div>
<form id="form">
  <div class="form-inner">
    <input id="q" placeholder="인사규정·근로기준법에 대해 물어보세요. 예) 연차휴가 며칠 발생해?" autocomplete="off">
    <button class="send" type="submit">전송</button>
  </div>
</form>
<script id="appdata" type="application/json">__DATA__</script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
const DATA=JSON.parse(document.getElementById('appdata').textContent);
const EXAMPLES=["연차휴가 며칠 발생해?","법정 근로시간 얼마야?","배우자 출산 시 경조휴가는?","급여는 언제 지급돼?","인사평가 S등급 성과급은?","정년은 몇 세야?"];
function norm(t){return t.replace(/[^0-9A-Za-z가-힣]+/g,' ').toLowerCase();}
function bigrams(t){t=norm(t).replace(/ /g,'');const s=new Set();if(t.length<2){s.add(t);return s;}for(let i=0;i<t.length-1;i++)s.add(t.slice(i,i+2));return s;}
function toks(t){return new Set(norm(t).split(' ').filter(w=>w.length>=2));}
function inter(a,b){let n=0;for(const x of a)if(b.has(x))n++;return n;}
function textSim(a,b){const ab=bigrams(a),bb=bigrams(b),at=toks(a),bt=toks(b);return inter(ab,bb)/(ab.size||1)*0.5+inter(at,bt)/(at.size||1)*0.5;}
function scoreChunk(q,c){const qb=bigrams(q),cb=bigrams(c.text);const bo=inter(qb,cb)/(qb.size||1);const qt=toks(q),ct=toks(c.text+' '+c.heading);const to=inter(qt,ct)/(qt.size||1);const hh=inter(toks(q),toks(c.heading))*0.15;return bo*0.5+to*0.5+hh;}
function search(q,k){const sc=DATA.chunks.map(c=>[c,scoreChunk(q,c)]);sc.sort((a,b)=>b[1]-a[1]);return sc.slice(0,k).filter(x=>x[1]>0);}
function bestFaq(q){let best=null,bs=0;for(const it of DATA.faq){const s=textSim(q,it.question);if(s>bs){bs=s;best=it;}}return [best,bs];}
function compute(q){
  const res=search(q,4);
  const sources=res.map(([c,s])=>({source:c.doc+' › '+c.heading,score:Math.round(s*1000)/1000,text:c.text}));
  const [item,fs]=bestFaq(q);const ts=res.length?res[0][1]:0;
  if(item&&fs>=0.25)return {kind:'faq',answer:item.answer,answer_source:item.source,sources};
  if(res.length&&ts>=0.10)return {kind:'excerpt',answer:res[0][0].text,answer_source:res[0][0].doc+' › '+res[0][0].heading,sources};
  return {kind:'none',answer:'문의하신 내용은 인사관리(근태·공수·복지) FAQ 범위에서 확인되지 않습니다. 관련 담당 부서에 문의하세요.',answer_source:null,sources:[]};
}
const chat=document.getElementById('chat'),form=document.getElementById('form'),qInput=document.getElementById('q'),sendBtn=form.querySelector('button');
const exWrap=document.getElementById('examples');
EXAMPLES.forEach(t=>{const b=document.createElement('button');b.className='chip';b.type='button';b.textContent=t;b.onclick=()=>{qInput.value=t;form.requestSubmit();};exWrap.appendChild(b);});
function md(t){if(window.marked)return marked.parse(t);const d=document.createElement('div');d.textContent=t;return '<pre style="white-space:pre-wrap;font-family:inherit">'+d.innerHTML+'</pre>';}
function el(h){const d=document.createElement('div');d.innerHTML=h.trim();return d.firstChild;}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function scroll(){window.scrollTo(0,document.body.scrollHeight);}
function addUser(t){chat.appendChild(el('<div class="msg user"><div class="bubble">'+esc(t)+'</div></div>'));scroll();}
function addLoading(){const n=el('<div class="msg bot"><div class="card"><div class="loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span> 검색 중…</div></div></div>');chat.appendChild(n);scroll();return n;}
function render(r){
  let s='';
  if(r.kind==='excerpt')s+='<div class="kind-excerpt">정확히 일치하는 FAQ가 없어, 가장 관련 높은 규정 조문을 안내합니다.</div>';
  s+='<div class="answer">'+md(r.answer||'')+'</div>';
  if(r.answer_source)s+='<div class="src">출처: <b>'+esc(r.answer_source)+'</b></div>';
  if(r.sources&&r.sources.length){
    const items=r.sources.map(x=>'<div class="src-item"><div class="meta">('+x.score+') '+esc(x.source)+'</div><pre>'+esc(x.text)+'</pre></div>').join('');
    s+='<details><summary>📚 관련 근거 조문 '+r.sources.length+'개</summary>'+items+'</details>';
  }
  s+='<div class="note">※ 이 공유 데모는 FAQ·규정 검색으로 동작합니다. 여러 조문을 종합한 생성형 답변·검증은 API 연결 버전에서 제공됩니다.</div>';
  return el('<div class="msg bot"><div class="card">'+s+'</div></div>');
}
function ask(q){
  addUser(q);qInput.value='';sendBtn.disabled=true;
  const loading=addLoading();
  setTimeout(()=>{loading.remove();chat.appendChild(render(compute(q)));sendBtn.disabled=false;scroll();qInput.focus();},250);
}
form.addEventListener('submit',e=>{e.preventDefault();const q=qInput.value.trim();if(q)ask(q);});
</script>
</body>
</html>"""


def main() -> None:
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML.replace("__DATA__", payload)
    OUT.write_text(html, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"생성 완료: {OUT}")
    print(f"  청크 {len(data['chunks'])}개 · FAQ {len(data['faq'])}개 · {kb:.0f} KB")
    print("  → 이 파일 하나만 팀원에게 전달하면 브라우저에서 바로 열립니다.")


if __name__ == "__main__":
    main()
