"""Render the local interactive literature-semantics review application.

The renderer is deliberately server-agnostic.  ``payload`` may contain a
static corpus plus an optional initial geometry preview; the browser then uses
the following same-origin API contract supplied by the local review server::

    GET  /api/session
      -> {"session": {"revision": 1, "review_decisions": {...},
                       "manual_items": [...]}}
    POST /api/review-events
      <- {"expected_revision": 1, "item_id": "...", "status": "...",
          "review_note": "..."}
    POST /api/manual-items
      <- {"expected_revision": 2, "item": {"section": "shape_motifs", ...}}
    POST /api/preview
      <- {"expected_revision": 3, "reason": "semantic_review_updated"}

The preferred corpus adapter supplies ``review_items`` with stable, globally
unique ``item_id`` values, a ``layer`` of ``evidence``, ``semantics`` or
``geometry``, and optional ``paper_id``, ``section``, ``title`` and ``content``
fields.  This lets classification claims and draft-prior patch items appear in
the semantic layer without flattening their content.  When ``review_items`` is
absent, the six ontology sections are discovered directly.  Paper evidence
may be flat or grouped below ``evidence.text/images/gallery``; identity may be
on the paper or its nested ``manifest``/``source_manifest``.

Every request carries the supplied token in ``X-Review-Token``.  Review
statuses are the strict literature semantics vocabulary.  A preview may be
absent initially and later contain a ``literature_geometry_generation.v0``
payload with ``preview.baseline/current/previous``, ``geometry``, ``features``,
``udsg`` and ``validation`` fields.  All of those fields are optional so a
partially generated model remains reviewable.

The result is a single HTML document: Plotly is embedded from the existing
``review`` extra and no CDN or remote resource is used.
"""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any, Mapping

from .types import REVIEW_STATUSES, SEMANTIC_ITEM_SECTIONS


_CSP_NONCE = "rfcem-literature-review-v1"


def build_interactive_review_html(payload: Mapping[str, Any], token: str) -> str:
    """Return a self-contained literature review GUI as UTF-8 HTML.

    ``token`` must be non-empty because the generated page is intended to be
    served only by the loopback review server.  Untrusted payload values are
    encoded for a script-data context and are escaped again before insertion
    into rendered markup.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("token must be a non-empty string")

    try:
        from plotly.offline import get_plotlyjs

        plotly_js = get_plotlyjs()
    except (ImportError, ModuleNotFoundError):
        plotly_js = "window.__RFCEM_PLOTLY_MISSING__ = true;"

    encoded_payload = _script_json(dict(payload))
    encoded_token = _script_json(token)
    encoded_statuses = _script_json(sorted(REVIEW_STATUSES))
    encoded_sections = _script_json(list(SEMANTIC_ITEM_SECTIONS))
    title = escape(str(payload.get("title") or "RF-CEM Literature Review"), quote=True)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-{_CSP_NONCE}'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{title}</title>
<style nonce="{_CSP_NONCE}">
:root {{ --ink:#17212b; --muted:#637282; --line:#d7dee7; --paper:#fff; --bg:#eef2f6;
  --blue:#1769aa; --green:#18794e; --amber:#986801; --red:#b42318; --violet:#6941c6; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:var(--bg); font:14px/1.45 "Segoe UI","Microsoft YaHei",Arial,sans-serif; }}
button,input,select,textarea {{ font:inherit; }}
button {{ border:1px solid #b8c3d0; background:#fff; color:var(--ink); border-radius:6px; padding:6px 10px; cursor:pointer; }}
button:hover {{ border-color:var(--blue); color:var(--blue); }}
button:disabled {{ cursor:wait; opacity:.55; }}
.app {{ display:grid; grid-template-rows:auto 1fr; min-height:100vh; }}
.topbar {{ display:flex; align-items:center; gap:14px; padding:10px 16px; color:#fff; background:#142b3d; }}
.topbar h1 {{ margin:0; font-size:18px; font-weight:650; }}
.topbar .spacer {{ flex:1; }}
.connection {{ padding:4px 9px; border-radius:999px; background:#41586a; font-size:12px; }}
.connection.ok {{ background:#176b48; }} .connection.bad {{ background:#9a3412; }}
.workspace {{ display:grid; grid-template-columns:minmax(480px,56vw) minmax(420px,1fr); min-height:0; }}
.visuals {{ display:grid; grid-template-rows:minmax(380px,2fr) minmax(210px,1fr); min-height:calc(100vh - 49px); border-right:1px solid var(--line); background:#fff; }}
.plot-wrap {{ position:relative; min-height:0; border-bottom:1px solid var(--line); }}
#model-plot,#profile-plot {{ width:100%; height:100%; min-height:210px; }}
.plot-label {{ position:absolute; z-index:2; top:9px; left:10px; padding:4px 8px; border-radius:5px; background:rgba(255,255,255,.9); color:#425466; font-size:12px; box-shadow:0 1px 4px #bcc6d1; }}
.side {{ min-height:0; max-height:calc(100vh - 49px); overflow:auto; }}
.layer-tabs {{ position:sticky; top:0; z-index:3; display:grid; grid-template-columns:repeat(3,1fr); background:#f7f9fb; border-bottom:1px solid var(--line); }}
.layer-tab {{ border:0; border-radius:0; padding:13px 8px; background:transparent; font-weight:650; }}
.layer-tab.active {{ color:var(--blue); background:#fff; box-shadow:inset 0 -3px var(--blue); }}
.summary {{ padding:12px 16px; background:#fff; border-bottom:1px solid var(--line); }}
.summary-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px; }}
.pill {{ display:inline-flex; align-items:center; gap:4px; padding:3px 8px; border-radius:999px; background:#e9eef4; font-size:12px; }}
.pill.accepted {{ background:#d8f3e5; color:#0d6841; }}
.pill.accepted_as_soft_only {{ background:#f0e8ff; color:#5b35a3; }}
.pill.rejected {{ background:#fee4e2; color:#9d1d18; }}
.pill.needs_more_evidence {{ background:#fff1c7; color:#805800; }}
.pill.pending {{ background:#e9eef4; color:#526273; }}
.layer {{ display:none; padding:15px 16px 28px; }} .layer.active {{ display:block; }}
.layer h2 {{ margin:3px 0 11px; font-size:18px; }} .layer h3 {{ margin:14px 0 8px; font-size:15px; }}
.muted {{ color:var(--muted); }} .small {{ font-size:12px; }} .mono {{ font-family:Consolas,monospace; }}
.card {{ margin:0 0 11px; padding:12px; border:1px solid var(--line); border-radius:8px; background:var(--paper); box-shadow:0 1px 2px rgba(23,33,43,.04); }}
.card-head {{ display:flex; align-items:flex-start; gap:9px; }} .card-head .grow {{ flex:1; min-width:0; }}
.card-title {{ font-weight:650; overflow-wrap:anywhere; }} .card-meta {{ margin-top:2px; color:var(--muted); font-size:12px; }}
.evidence-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; }}
.evidence-image {{ width:100%; max-height:280px; object-fit:contain; background:#f5f6f8; border:1px solid var(--line); border-radius:5px; }}
.semantic-value {{ margin:9px 0; padding:8px; max-height:190px; overflow:auto; border-radius:5px; background:#f6f8fa; white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.4 Consolas,monospace; }}
.note {{ width:100%; min-height:58px; resize:vertical; padding:7px 8px; border:1px solid #bdc8d4; border-radius:5px; }}
.actions {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:7px; }}
.actions [data-status="accepted"] {{ border-color:#45a878; color:var(--green); }}
.actions [data-status="accepted_as_soft_only"] {{ border-color:#9376d2; color:var(--violet); }}
.actions [data-status="rejected"] {{ border-color:#e57d76; color:var(--red); }}
.actions [data-status="needs_more_evidence"] {{ border-color:#d3a22d; color:var(--amber); }}
.subtabs {{ display:flex; gap:5px; margin:0 0 10px; }} .subtab.active {{ color:#fff; border-color:var(--blue); background:var(--blue); }}
.subview {{ display:none; }} .subview.active {{ display:block; }}
table {{ width:100%; border-collapse:collapse; background:#fff; font-size:12px; }}
th,td {{ padding:7px; border:1px solid var(--line); text-align:left; vertical-align:top; overflow-wrap:anywhere; }} th {{ background:#edf2f7; }}
details {{ margin-top:8px; }} pre {{ max-height:330px; overflow:auto; padding:9px; background:#f6f8fa; border-radius:5px; white-space:pre-wrap; overflow-wrap:anywhere; }}
.form-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }} .form-grid .wide {{ grid-column:1/-1; }}
.form-grid label {{ display:grid; gap:3px; color:#425466; font-size:12px; }}
.form-grid input,.form-grid select,.form-grid textarea {{ width:100%; padding:7px; border:1px solid #bdc8d4; border-radius:5px; background:#fff; color:var(--ink); }}
.global-note {{ margin-top:14px; padding-top:12px; border-top:1px solid var(--line); }}
.notice {{ display:none; position:fixed; right:18px; bottom:18px; z-index:9; max-width:420px; padding:10px 13px; border-radius:7px; color:#fff; background:#30475a; box-shadow:0 4px 16px #61708066; }}
.notice.show {{ display:block; }} .notice.error {{ background:#9a3412; }}
@media (max-width:980px) {{ .workspace {{ grid-template-columns:1fr; }} .visuals {{ min-height:760px; border-right:0; }} .side {{ max-height:none; }} }}
</style>
<script nonce="{_CSP_NONCE}">{plotly_js}</script>
</head>
<body>
<div class="app">
  <header class="topbar"><h1>{title}</h1><span class="small">三层语义—几何校核</span><span class="spacer"></span><span id="revision">revision —</span><span id="connection" class="connection">连接中</span><button id="refresh-preview">重新生成模型</button></header>
  <div class="workspace">
    <section class="visuals" aria-label="Geometry comparisons">
      <div class="plot-wrap"><span class="plot-label">baseline / current / previous — 3D overlay</span><div id="model-plot"></div></div>
      <div class="plot-wrap"><span class="plot-label">r-z profile comparison (mm)</span><div id="profile-plot"></div></div>
    </section>
    <main class="side">
      <nav class="layer-tabs" aria-label="Review layers">
        <button class="layer-tab active" data-layer="evidence">Layer 1 · Evidence</button>
        <button class="layer-tab" data-layer="semantics">Layer 2 · Semantic candidates</button>
        <button class="layer-tab" data-layer="geometry">Layer 3 · Geometry projection</button>
      </nav>
      <section id="review-summary" class="summary"></section>
      <section id="layer-evidence" class="layer active"><h2>论文证据 / Evidence</h2><div id="evidence-list"></div></section>
      <section id="layer-semantics" class="layer"><h2>语义候选 / Semantic candidates</h2><div id="semantic-list"></div><div id="manual-add"></div></section>
      <section id="layer-geometry" class="layer"><h2>几何投影 / Geometry projection</h2>
        <div class="subtabs"><button class="subtab active" data-subview="geometry">Geometry</button><button class="subtab" data-subview="features">Features</button><button class="subtab" data-subview="udsg">UDSG</button></div>
        <div id="subview-geometry" class="subview active"></div><div id="subview-features" class="subview"></div><div id="subview-udsg" class="subview"></div>
      </section>
    </main>
  </div>
</div>
<div id="notice" class="notice" role="status"></div>
<script nonce="{_CSP_NONCE}">
"use strict";
const BOOTSTRAP = {encoded_payload};
const TOKEN = {encoded_token};
const REVIEW_STATUSES = new Set({encoded_statuses});
const SEMANTIC_SECTIONS = {encoded_sections};
const API = Object.freeze({{session:"/api/session",events:"/api/review-events",manual:"/api/manual-items",preview:"/api/preview"}});
const COLORS = Object.freeze({{baseline:"#7b8794",previous:"#d97706",current:"#1677b8"}});
const STATE = {{data:BOOTSTRAP,session:{{revision:0,review_decisions:{{}},manual_items:[]}},preview:BOOTSTRAP.preview || BOOTSTRAP.geometry_projection || null,previewSequence:0,busy:false,parameterDraft:{{}}}};

function esc(value) {{
  return String(value ?? "").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[ch]));
}}
function pretty(value) {{ try {{ return JSON.stringify(value,null,2); }} catch (_) {{ return String(value); }} }}
function object(value) {{ return value && typeof value === "object" && !Array.isArray(value) ? value : {{}}; }}
function array(value) {{ return Array.isArray(value) ? value : []; }}
function itemId(item,index,section,paperId="") {{ return String(item.id || item.item_id || item.semantic_id || `${{paperId}}:${{section}}:${{index}}`); }}
function statusOf(item,id) {{ return String(object(STATE.session.review_decisions)[id]?.status || item.human_review_status || item.status || "pending"); }}
function noteOf(item,id) {{ return String(object(STATE.session.review_decisions)[id]?.review_note ?? item.review_note ?? ""); }}
function currentRevision() {{ return Number(STATE.session.revision || 0); }}

function notify(message,isError=false) {{
  const box=document.getElementById("notice"); box.textContent=String(message); box.className=`notice show${{isError?" error":""}}`;
  window.clearTimeout(notify.timer); notify.timer=window.setTimeout(()=>box.className="notice",4200);
}}
function setConnection(label,kind="") {{ const node=document.getElementById("connection"); node.textContent=label; node.className=`connection ${{kind}}`; }}
function setBusy(value) {{ STATE.busy=value; document.querySelectorAll("button").forEach(button=>button.disabled=value); }}

async function request(path,options={{}}) {{
  const headers={{"Accept":"application/json","X-Review-Token":TOKEN,...object(options.headers)}};
  const init={{method:options.method || "GET",headers,credentials:"same-origin"}};
  if (options.body !== undefined) {{ headers["Content-Type"]="application/json"; init.body=JSON.stringify(options.body); }}
  const response=await fetch(path,init);
  let value={{}}; try {{ value=await response.json(); }} catch (_) {{ value={{ok:false,error:{{message:`HTTP ${{response.status}} returned non-JSON`}}}}; }}
  if (!response.ok || value.ok === false) {{
    const error=new Error(value.error?.message || `HTTP ${{response.status}}`); error.code=value.error?.code; error.currentRevision=value.error?.current_revision; throw error;
  }}
  return value;
}}
function acceptSession(value) {{
  const session=object(value?.session); if (Object.keys(session).length) STATE.session={{...STATE.session,...session}};
  document.getElementById("revision").textContent=`revision ${{currentRevision()}}`;
}}
async function loadSession() {{
  try {{ const value=await request(API.session); acceptSession(value); setConnection("已连接","ok"); renderAll(); }}
  catch (error) {{ setConnection("离线/未授权","bad"); notify(error.message,true); renderAll(); }}
}}

function semanticItems() {{
  const found=[];
  const reviewRows=array(STATE.data.review_items).filter(raw=>{{ const layer=String(object(raw).layer || "").toLowerCase(); return layer==="semantics" || layer==="semantic"; }});
  reviewRows.forEach((raw,index)=>{{ const item=object(raw); found.push({{item,section:String(item.section || item.kind || "review_item"),paperId:String(item.paper_id || ""),index}}); }});
  const addSections=(source,paperId="")=>{{
    const container=object(source);
    SEMANTIC_SECTIONS.forEach(section=>array(container[section]).forEach((item,index)=>found.push({{item:object(item),section,paperId,index}})));
  }};
  if (!reviewRows.length) {{
    array(STATE.data.semantic_candidates || STATE.data.semantic_items).forEach((raw,index)=>{{ const item=object(raw); found.push({{item,section:String(item.section || "manual"),paperId:String(item.paper_id || ""),index}}); }});
    addSections(STATE.data.literature_semantics || STATE.data.semantics);
    array(STATE.data.papers).forEach(paper=>{{ const p=object(paper),manifest=object(p.manifest || p.source_manifest); addSections(p.literature_semantics || p.semantics || p.semantic_package,String(p.id || p.paper_id || p.arxiv_id || manifest.id || manifest.arxiv_id || "")); }});
  }}
  array(STATE.session.manual_items).forEach((raw,index)=>{{ const item=object(raw); found.push({{item,section:String(item.section || "manual"),paperId:String(item.paper_id || ""),index}}); }});
  const unique=new Map(); found.forEach(row=>{{ const id=itemId(row.item,row.index,row.section,row.paperId); unique.set(id,{{...row,id}}); }}); return [...unique.values()];
}}

function evidenceItems() {{
  const found=[];
  const append=(value,base={{}})=>{{
    if (Array.isArray(value)) {{ value.forEach(item=>append(item,base)); return; }}
    if (typeof value==="string") {{ found.push({{...base,text:value}}); return; }}
    const item=object(value); if (!Object.keys(item).length) return;
    const nested=["text","images","gallery"].some(key=>Array.isArray(item[key]) || (item[key] && typeof item[key]==="object"));
    if (nested) {{ ["text","images","gallery"].forEach(key=>append(item[key],base)); const remainder=Object.fromEntries(Object.entries(item).filter(([key])=>!["text","images","gallery"].includes(key))); if (Object.keys(remainder).length) found.push({{...base,...remainder}}); }}
    else found.push({{...base,...item}});
  }};
  const reviewEvidence=array(STATE.data.review_items).filter(raw=>String(object(raw).layer || "").toLowerCase()==="evidence");
  reviewEvidence.forEach(raw=>{{ const wrapper=object(raw),content=object(wrapper.content),text=typeof wrapper.content==="string"?wrapper.content:undefined; append({{...content,...wrapper,content:undefined,...(text?{{text}}:{{}})}},{{reviewable:true}}); }});
  if (reviewEvidence.length) return found;
  append(STATE.data.evidence);
  array(STATE.data.papers).forEach(paper=>{{
    const p=object(paper),manifest=object(p.manifest || p.source_manifest),paperId=String(p.id || p.paper_id || p.arxiv_id || manifest.id || manifest.arxiv_id || ""),paperTitle=p.title || manifest.title;
    const before=found.length; append(p.evidence || p.evidence_images || p.images,{{paper_id:paperId,paper_title:paperTitle}});
    if (found.length===before) found.push({{paper_id:paperId,title:paperTitle,summary:p.summary || p.paper_summary || manifest.summary,authors:p.authors || manifest.authors}});
  }}); return found;
}}
function safeImage(value) {{ const source=String(value || ""); return /^data:image\\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=\\s]+$/i.test(source) ? source : ""; }}

function renderEvidence() {{
  const rows=evidenceItems(); const host=document.getElementById("evidence-list");
  if (!rows.length) {{ host.innerHTML='<div class="card muted">当前会话没有内嵌论文证据。</div>'; return; }}
  const reviewRows=[]; host.innerHTML='<div class="evidence-grid">'+rows.map((item,index)=>{{
    const image=safeImage(item.data_uri || item.image_data_uri || item.src);
    const id=itemId(item,index,"evidence",String(item.paper_id || "")),title=item.title || item.figure_id || item.label || item.id || item.item_id || item.paper_title || `Evidence ${{index+1}}`;
    const caption=item.caption || item.evidence_summary || item.summary || item.text || item.content || "",reviewable=Boolean(item.reviewable || item.item_id || item.layer==="evidence"),status=statusOf(item,id),note=noteOf(item,id);
    if (reviewable) reviewRows.push({{item,id,section:"evidence",paperId:String(item.paper_id || ""),index}});
    return `<article class="card">${{image?`<img class="evidence-image" alt="${{esc(title)}}" src="${{esc(image)}}">`:""}}<div class="card-head"><div class="grow"><div class="card-title">${{esc(title)}}</div><div class="card-meta">${{esc(item.paper_id || item.page ? `paper ${{item.paper_id || "—"}} · page ${{item.page || "—"}}`:item.paper_id || "")}}</div></div>${{reviewable?`<span class="pill ${{esc(status)}}">${{esc(status)}}</span>`:""}}</div><div>${{esc(typeof caption === "string" ? caption : pretty(caption))}}</div>${{item.evidence_refs?`<div class="small muted">refs: ${{esc(array(item.evidence_refs).join(", "))}}</div>`:""}}${{reviewable?`<label class="small">中文备注 / review_note<textarea class="note" data-note="${{esc(id)}}" lang="zh-CN">${{esc(note)}}</textarea></label><div class="actions">${{reviewActionButtons(id)}}<button data-save-note="${{esc(id)}}">保存备注</button></div>`:""}}</article>`;
  }}).join("")+'</div>';
  bindReviewActions(host,reviewRows);
}}

const ACTIONS=[
  ["accepted","OK / 接受"],["accepted_as_soft_only","Soft OK / 仅软建议"],
  ["rejected","Reject / 拒绝"],["needs_more_evidence","Needs evidence / 补证据"]
];
function reviewActionButtons(id) {{ return ACTIONS.map(action=>`<button data-review-id="${{esc(id)}}" data-status="${{action[0]}}">${{action[1]}}</button>`).join(""); }}
function renderSemantics() {{
  const rows=semanticItems(); const host=document.getElementById("semantic-list");
  host.innerHTML=rows.length ? rows.map(row=>{{
    const item=row.item,status=statusOf(item,row.id),note=noteOf(item,row.id);
    const label=item.title || item.name || item.label || item.feature_name || item.motif_name || item.parameter || row.id;
    const refs=array(item.evidence_refs || item.source_refs).join(", ");
    return `<article class="card semantic-card" data-item-key="${{esc(row.id)}}"><div class="card-head"><div class="grow"><div class="card-title">${{esc(label)}}</div><div class="card-meta">${{esc(row.paperId || "corpus")}} · ${{esc(row.section)}} · <span class="mono">${{esc(row.id)}}</span></div></div><span class="pill ${{esc(status)}}">${{esc(status)}}</span></div><div class="semantic-value">${{esc(pretty(item.content ?? item))}}</div>${{refs?`<div class="small muted">evidence: ${{esc(refs)}}</div>`:""}}<label class="small">中文备注 / review_note<textarea class="note" data-note="${{esc(row.id)}}" lang="zh-CN">${{esc(note)}}</textarea></label><div class="actions">${{reviewActionButtons(row.id)}}<button data-save-note="${{esc(row.id)}}">保存备注</button></div></article>`;
  }}).join("") : '<div class="card muted">没有可审核的语义候选。</div>';
  const options=SEMANTIC_SECTIONS.map(section=>`<option value="${{esc(section)}}">${{esc(section)}}</option>`).join("");
  document.getElementById("manual-add").innerHTML=`<details class="card"><summary><b>Add structured semantic / 新增结构化语义</b></summary><form id="manual-form" class="form-grid"><label>Section<select name="section">${{options}}</select></label><label>ID<input name="id" required placeholder="manual_semantic_001"></label><label class="wide">结构化 JSON（除 section/id 外的字段）<textarea name="body" rows="7" spellcheck="false">{{}}</textarea></label><label class="wide">中文备注<input name="review_note" lang="zh-CN"></label><div class="wide"><button type="submit">Add as pending and render / 新增并渲染</button></div></form></details><div class="global-note"><label><b>全局中文备注</b><textarea id="global-note" class="note" lang="zh-CN">${{esc(noteOf({{}},"__global_note__"))}}</textarea></label><div class="actions"><button id="save-global-note">保存全局备注</button></div></div>`;
  bindSemanticActions(rows,host);
}}

function bindReviewActions(host,rows) {{
  const byId=new Map(rows.map(row=>[row.id,row]));
  host.querySelectorAll("[data-review-id]").forEach(button=>button.addEventListener("click",()=>{{ const row=byId.get(button.dataset.reviewId); if (row) saveReview(row.id,button.dataset.status,true); }}));
  host.querySelectorAll("[data-save-note]").forEach(button=>button.addEventListener("click",()=>{{ const row=byId.get(button.dataset.saveNote); if (row) saveReview(row.id,statusOf(row.item,row.id),false); }}));
}}
function bindSemanticActions(rows,host) {{
  bindReviewActions(host,rows);
  document.getElementById("manual-form")?.addEventListener("submit",addManualItem);
  document.getElementById("save-global-note")?.addEventListener("click",()=>saveGlobalNote());
}}
function noteInput(id) {{ return [...document.querySelectorAll("[data-note]")].find(node=>node.dataset.note===id); }}

async function saveReview(id,status,regenerate) {{
  if (!REVIEW_STATUSES.has(status)) {{ notify(`非法审核状态: ${{status}}`,true); return; }}
  const review_note=String(noteInput(id)?.value || ""); setBusy(true);
  try {{
    const value=await request(API.events,{{method:"POST",body:{{expected_revision:currentRevision(),item_id:id,status,review_note}}}}); acceptSession(value); renderAll();
    if (regenerate) await generatePreview("semantic_review_updated",id); else notify("备注已保存");
  }} catch (error) {{ await handleMutationError(error); }} finally {{ setBusy(false); }}
}}
async function saveGlobalNote() {{
  const review_note=String(document.getElementById("global-note")?.value || ""); setBusy(true);
  try {{ const value=await request(API.events,{{method:"POST",body:{{expected_revision:currentRevision(),item_id:"__global_note__",status:"pending",review_note}}}}); acceptSession(value); renderAll(); notify("全局备注已保存"); }}
  catch (error) {{ await handleMutationError(error); }} finally {{ setBusy(false); }}
}}
async function addManualItem(event) {{
  event.preventDefault(); const form=new FormData(event.currentTarget); let extra={{}};
  try {{ extra=JSON.parse(String(form.get("body") || "{{}}")); if (!extra || Array.isArray(extra) || typeof extra!=="object") throw new Error("JSON 必须是对象"); }}
  catch (error) {{ notify(`结构化 JSON 无效: ${{error.message}}`,true); return; }}
  const item={{...extra,section:String(form.get("section") || ""),id:String(form.get("id") || "").trim(),review_note:String(form.get("review_note") || "")}};
  if (!SEMANTIC_SECTIONS.includes(item.section) || !item.id) {{ notify("Section 或 ID 无效",true); return; }} setBusy(true);
  try {{ const value=await request(API.manual,{{method:"POST",body:{{expected_revision:currentRevision(),item}}}}); acceptSession(value); renderAll(); await generatePreview("manual_semantic_added",item.id); }}
  catch (error) {{ await handleMutationError(error); }} finally {{ setBusy(false); }}
}}
async function handleMutationError(error) {{ if (error.code==="revision_conflict") await loadSession(); notify(error.message,true); }}

function previewRoot() {{ return object(STATE.preview); }}
function previewModels() {{
  const root=previewRoot(),container=object(root.preview || root.plot || root); const result={{}};
  ["baseline","previous","current"].forEach(key=>{{ if (container[key]) result[key]=object(container[key]); }});
  array(container.models).forEach(model=>{{ const key=String(model.role || model.name || "current").toLowerCase(); result[key in COLORS?key:"current"]=object(model); }}); return result;
}}
function meshTrace(model,role) {{
  const mesh=object(model.mesh || model.generated_mesh || model); const vertices=array(mesh.vertices),triangles=array(mesh.triangles);
  const x=array(mesh.x).length?array(mesh.x):vertices.map(p=>array(p)[0]); const y=array(mesh.y).length?array(mesh.y):vertices.map(p=>array(p)[1]); const z=array(mesh.z).length?array(mesh.z):vertices.map(p=>array(p)[2]);
  const i=array(mesh.i).length?array(mesh.i):triangles.map(t=>array(t)[0]); const j=array(mesh.j).length?array(mesh.j):triangles.map(t=>array(t)[1]); const k=array(mesh.k).length?array(mesh.k):triangles.map(t=>array(t)[2]);
  if (!x.length || !i.length) return null; return {{type:"mesh3d",name:String(model.label || role),x,y,z,i,j,k,color:COLORS[role],opacity:role==="current"?.72:.30,flatshading:false,showscale:false,hovertemplate:`${{esc(model.label || role)}}<extra></extra>`}};
}}
function profilePoints(model) {{
  const raw=array(model.profile_points || object(model.profile).points); return raw.map(point=>Array.isArray(point)?{{z:Number(point[0]),r:Number(point[1])}}:{{z:Number(point.z),r:Number(point.r)}}).filter(point=>Number.isFinite(point.z)&&Number.isFinite(point.r));
}}
function renderPlots() {{
  const modelHost=document.getElementById("model-plot"),profileHost=document.getElementById("profile-plot");
  if (window.__RFCEM_PLOTLY_MISSING__ || typeof Plotly==="undefined") {{ modelHost.innerHTML='<div class="card muted">Plotly 未安装；表格审核仍可使用。请安装项目 review extra。</div>'; profileHost.innerHTML=""; return; }}
  const models=previewModels(),meshTraces=[],profileTraces=[];
  ["baseline","previous","current"].forEach(role=>{{ const model=models[role]; if (!model) return; const mesh=meshTrace(model,role); if (mesh) meshTraces.push(mesh); const points=profilePoints(model); if (points.length) profileTraces.push({{type:"scatter",mode:"lines",name:String(model.label || role),x:points.map(p=>p.z),y:points.map(p=>p.r),line:{{color:COLORS[role],width:role==="current"?3:2,dash:role==="current"?"solid":"dash"}},hovertemplate:"z=%{{x:.3f}} mm<br>r=%{{y:.3f}} mm<extra></extra>"}}); }});
  if (!meshTraces.length) meshTraces.push({{type:"scatter3d",mode:"markers",x:[],y:[],z:[],name:"等待几何预览"}});
  if (!profileTraces.length) profileTraces.push({{type:"scatter",mode:"lines",x:[],y:[],name:"等待 r-z profile"}});
  Plotly.react(modelHost,meshTraces,{{margin:{{l:0,r:0,t:34,b:0}},paper_bgcolor:"#fff",scene:{{aspectmode:"data",xaxis:{{title:"x / r (mm)"}},yaxis:{{title:"y (mm)"}},zaxis:{{title:"z (mm)"}}}},legend:{{orientation:"h"}}}},{{responsive:true,displaylogo:false,scrollZoom:true}});
  Plotly.react(profileHost,profileTraces,{{margin:{{l:58,r:18,t:35,b:48}},paper_bgcolor:"#fff",plot_bgcolor:"#f8fafc",xaxis:{{title:"z (mm)",gridcolor:"#dfe5ec"}},yaxis:{{title:"r (mm)",gridcolor:"#dfe5ec",scaleanchor:"x",scaleratio:1}},legend:{{orientation:"h"}}}},{{responsive:true,displaylogo:false,scrollZoom:true}});
}}

function geometryPayload() {{ const root=previewRoot(); return object(root.geometry || object(STATE.data.geometry_projection).geometry); }}
function featurePayload() {{ const root=previewRoot(); return root.features || object(STATE.data.geometry_projection).features || []; }}
function udsgPayload() {{ const root=previewRoot(); return root.udsg || object(STATE.data.geometry_projection).udsg || {{}}; }}
const PARAMETER_KEYS=["L","l","r","R","a","b"];
function sourceParameterValues() {{
  const root=previewRoot(); const tuple=object(root.parameter_tuple || object(STATE.data.geometry_projection).parameter_tuple); const values=object(tuple.values || root.parameters || object(STATE.data.geometry_projection).parameters);
  return Object.fromEntries(PARAMETER_KEYS.map(key=>{{ const raw=object(values[key]).value ?? values[key]; return [key,Number(raw)]; }}).filter(([,value])=>Number.isFinite(value)));
}}
function activeParameterValues() {{ return {{...sourceParameterValues(),...STATE.parameterDraft}}; }}
function geometryReviewItems() {{
  const combined=[...array(STATE.data.review_items),...array(previewRoot().review_items)]; const unique=new Map();
  combined.filter(raw=>String(object(raw).layer || "").toLowerCase()==="geometry").forEach((raw,index)=>{{ const item=object(raw),id=itemId(item,index,"geometry",String(item.paper_id || "")); unique.set(id,{{item,id,section:"geometry",paperId:String(item.paper_id || ""),index}}); }}); return [...unique.values()];
}}
function geometryReviewCards(rows) {{
  return rows.map(row=>{{ const item=row.item,status=statusOf(item,row.id),note=noteOf(item,row.id),label=item.title || item.label || item.name || row.id; return `<article class="card"><div class="card-head"><div class="grow"><div class="card-title">${{esc(label)}}</div><div class="card-meta">Geometry projection · <span class="mono">${{esc(row.id)}}</span></div></div><span class="pill ${{esc(status)}}">${{esc(status)}}</span></div><div class="semantic-value">${{esc(pretty(item.content ?? item))}}</div><label class="small">中文备注 / review_note<textarea class="note" data-note="${{esc(row.id)}}" lang="zh-CN">${{esc(note)}}</textarea></label><div class="actions">${{reviewActionButtons(row.id)}}<button data-save-note="${{esc(row.id)}}">保存备注</button></div></article>`; }}).join("");
}}
function parameterEditor() {{
  const values=activeParameterValues();
  return `<form id="parameter-form" class="card"><div class="card-title">SLS-2 parameter iteration / 参数迭代</div><div class="card-meta">单位均为 mm；提交后 previous/current 将并列保留用于比较。</div><div class="form-grid">${{PARAMETER_KEYS.map(key=>`<label>${{esc(key)}} (mm)<input data-parameter="${{esc(key)}}" name="${{esc(key)}}" type="number" min="0.000001" step="any" required value="${{esc(Number.isFinite(values[key])?values[key]:"")}}"></label>`).join("")}}</div><div class="actions"><button type="submit">Render parameters / 按参数渲染</button></div></form>`;
}}
function renderGeometry() {{
  const root=previewRoot(),geometry=geometryPayload(),validation=object(root.validation || object(STATE.data.geometry_projection).validation),reviewRows=geometryReviewItems(),geometryHost=document.getElementById("subview-geometry");
  geometryHost.innerHTML=parameterEditor()+geometryReviewCards(reviewRows)+`<div class="card"><div class="card-head"><div class="grow"><div class="card-title">Generated geometry hypothesis</div><div class="card-meta">论文近似 / geometry hypothesis，不等同于 RF 性能复现</div></div><span class="pill ${{validation.pass?"accepted":"pending"}}">${{validation.pass?"kernel verified":"not verified"}}</span></div>${{keyValueTable(geometry)}}${{validation && Object.keys(validation).length?`<details><summary>Validation</summary><pre>${{esc(pretty(validation))}}</pre></details>`:""}}</div>`;
  const featureSource=featurePayload(),features=Array.isArray(featureSource)?featureSource:object(featureSource).feature_candidates || object(featureSource).items || [];
  document.getElementById("subview-features").innerHTML=features.length?`<table><thead><tr><th>ID</th><th>Type</th><th>Geometry refs</th><th>Segments / parameters</th><th>Confidence / status</th><th>Evidence</th></tr></thead><tbody>${{features.map(feature=>`<tr><td>${{esc(feature.id || feature.feature_id)}}</td><td>${{esc(feature.type || feature.feature_type)}}</td><td>${{esc(array(feature.geometry_refs).join(", "))}}</td><td>${{esc([...array(feature.segment_refs),...array(feature.parameter_refs)].join(", "))}}</td><td>${{esc([feature.confidence,feature.status].filter(value=>value!==undefined&&value!==null).join(" / "))}}</td><td>${{esc(typeof feature.evidence==="object"?pretty(feature.evidence):feature.evidence || array(feature.evidence_refs).join(", "))}}</td></tr>`).join("")}}</tbody></table>`:'<div class="card muted">尚无 Features 投影。</div>';
  const udsg=udsgPayload(); document.getElementById("subview-udsg").innerHTML=Object.keys(object(udsg)).length?`<div class="card"><div class="card-title">UDSG preview</div><pre>${{esc(pretty(udsg))}}</pre></div>`:'<div class="card muted">尚无 UDSG 投影。</div>';
  document.querySelectorAll("[data-parameter]").forEach(input=>input.addEventListener("input",()=>{{ const value=Number(input.value); if (Number.isFinite(value)) STATE.parameterDraft[input.dataset.parameter]=value; }}));
  document.getElementById("parameter-form")?.addEventListener("submit",event=>{{ event.preventDefault(); const parameters={{}}; PARAMETER_KEYS.forEach(key=>{{ const input=event.currentTarget.elements.namedItem(key),value=Number(input?.value); if (Number.isFinite(value)) parameters[key]=value; }}); if (Object.keys(parameters).length!==PARAMETER_KEYS.length) {{ notify("六个参数都必须是有效数字",true); return; }} STATE.parameterDraft=parameters; generatePreview("parameter_iteration","",parameters); }});
  bindReviewActions(geometryHost,reviewRows);
}}
function keyValueTable(value) {{ const rows=Object.entries(object(value)); return rows.length?`<table><tbody>${{rows.map(([key,item])=>`<tr><th>${{esc(key)}}</th><td>${{esc(typeof item==="object"?pretty(item):item)}}</td></tr>`).join("")}}</tbody></table>`:'<p class="muted">尚未生成几何；审核语义后将自动刷新。</p>'; }}

function renderSummary() {{
  const counts=Object.fromEntries([...REVIEW_STATUSES].map(status=>[status,0])),reviewRows=new Map();
  [...semanticItems(),...geometryReviewItems()].forEach(row=>reviewRows.set(row.id,row));
  array(STATE.data.review_items).filter(raw=>String(object(raw).layer || "").toLowerCase()==="evidence").forEach((raw,index)=>{{ const item=object(raw),id=itemId(item,index,"evidence",String(item.paper_id || "")); reviewRows.set(id,{{item,id}}); }});
  reviewRows.forEach(row=>{{ const status=statusOf(row.item,row.id); counts[status]=(counts[status]||0)+1; }});
  const validation=object(previewRoot().validation); document.getElementById("review-summary").innerHTML=`<div class="summary-row"><b>Review summary</b>${{[...REVIEW_STATUSES].map(status=>`<span class="pill ${{esc(status)}}">${{esc(status)}} ${{counts[status]||0}}</span>`).join("")}}<span class="pill">model: ${{validation.generated?"generated":validation.pass?"verified":"waiting"}}</span></div>`;
}}
function renderAll() {{ renderSummary(); renderEvidence(); renderSemantics(); renderGeometry(); renderPlots(); if (STATE.busy) document.querySelectorAll("button").forEach(button=>button.disabled=true); }}

async function generatePreview(reason="manual_refresh",item_id="",parameters=null) {{
  const sequence=++STATE.previewSequence; setConnection("生成模型中");
  const parameterValues=parameters || activeParameterValues();
  try {{ const value=await request(API.preview,{{method:"POST",body:{{expected_revision:currentRevision(),reason,...(item_id?{{item_id}}:{{}}),...(Object.keys(parameterValues).length?{{parameters:parameterValues}}:{{}})}}}}); if (sequence!==STATE.previewSequence) return; STATE.preview=value.preview || value.geometry_projection || value; setConnection("模型已刷新","ok"); renderGeometry(); renderPlots(); renderSummary(); notify("几何预览已刷新"); }}
  catch (error) {{ if (sequence===STATE.previewSequence) {{ setConnection("生成失败","bad"); notify(error.message,true); }} }}
}}

document.querySelectorAll("[data-layer]").forEach(button=>button.addEventListener("click",()=>{{ document.querySelectorAll("[data-layer]").forEach(node=>node.classList.toggle("active",node===button)); document.querySelectorAll(".layer").forEach(node=>node.classList.toggle("active",node.id===`layer-${{button.dataset.layer}}`)); }}));
document.querySelectorAll("[data-subview]").forEach(button=>button.addEventListener("click",()=>{{ document.querySelectorAll("[data-subview]").forEach(node=>node.classList.toggle("active",node===button)); document.querySelectorAll(".subview").forEach(node=>node.classList.toggle("active",node.id===`subview-${{button.dataset.subview}}`)); }}));
document.getElementById("refresh-preview").addEventListener("click",()=>generatePreview());
renderAll(); loadSession();
</script>
</body>
</html>
"""


def write_interactive_review_html(path: Path, payload: Mapping[str, Any], token: str) -> None:
    """Write :func:`build_interactive_review_html` atomically as UTF-8."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(build_interactive_review_html(payload, token), encoding="utf-8")
    temporary.replace(output)


def _script_json(value: object) -> str:
    """Encode JSON so untrusted text cannot terminate an inline script."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
