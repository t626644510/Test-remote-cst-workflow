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
    POST /api/helper2-review
      <- {"expected_revision": 3, "projection_id": "...", "review": {...}}
    GET  /api/paper-source
      -> the checksum-verified source PDF for the active paper

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
    review_scope = payload.get("review_scope")
    scope = dict(review_scope) if isinstance(review_scope, Mapping) else {}
    scope_text = escape(
        " / ".join(
            str(value)
            for value in (
                scope.get("paper_id"),
                scope.get("operating_regime"),
                scope.get("cavity_family"),
            )
            if value not in {None, ""}
        )
        or "single-paper review",
        quote=True,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-{_CSP_NONCE}'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'self'; frame-src blob:; object-src 'none'; base-uri 'none'; form-action 'none'">
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
.topbar h1 {{ margin:0; max-width:46vw; overflow:hidden; font-size:18px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }}
.topbar .spacer {{ flex:1; }}
.connection {{ padding:4px 9px; border-radius:999px; background:#41586a; font-size:12px; }}
.connection.ok {{ background:#176b48; }} .connection.bad {{ background:#9a3412; }}
.workspace {{ display:grid; grid-template-columns:minmax(480px,56vw) minmax(420px,1fr); min-height:0; }}
.visuals {{ display:grid; grid-template-rows:auto minmax(0,1fr); min-height:calc(100vh - 49px); border-right:1px solid var(--line); background:#fff; }}
.visual-modebar {{ display:flex; align-items:center; gap:6px; min-height:44px; padding:6px 10px; border-bottom:1px solid var(--line); overflow-x:auto; }}
.visual-modebar button.active {{ color:#fff; border-color:var(--blue); background:var(--blue); }}
.visual-modebar .locator {{ margin-left:auto; color:var(--muted); font-size:12px; white-space:nowrap; }}
.visual-stage {{ position:relative; min-height:0; }}
.visual-mode {{ display:none; width:100%; height:100%; min-height:0; }} .visual-mode.active {{ display:block; }}
.model-grid {{ display:grid; grid-template-rows:minmax(380px,2fr) minmax(210px,1fr); height:100%; min-height:0; }}
.plot-wrap {{ position:relative; min-height:0; border-bottom:1px solid var(--line); }}
#model-plot,#profile-plot {{ width:100%; height:100%; min-height:210px; }}
.plot-label {{ position:absolute; z-index:2; top:9px; left:10px; padding:4px 8px; border-radius:5px; background:rgba(255,255,255,.9); color:#425466; font-size:12px; box-shadow:0 1px 4px #bcc6d1; }}
.evidence-reader {{ display:grid; grid-template-rows:auto minmax(0,1fr); height:100%; min-height:0; background:#f5f7fa; }}
.evidence-reader-head {{ padding:10px 12px; border-bottom:1px solid var(--line); background:#fff; }}
.evidence-reader-body {{ min-height:0; overflow:auto; padding:12px; text-align:center; }}
.evidence-reader-body img {{ max-width:100%; height:auto; border:1px solid var(--line); background:#fff; box-shadow:0 2px 12px #73808d55; }}
.evidence-reader-body iframe {{ width:100%; height:100%; min-height:680px; border:1px solid var(--line); background:#fff; }}
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
.evidence-open {{ width:100%; margin:7px 0 3px; }}
.semantic-group {{ margin:0 0 14px; padding:10px; border:1px solid var(--line); border-radius:9px; background:#f7f9fb; }}
.semantic-group>h3 {{ display:flex; align-items:center; gap:7px; margin:0 0 9px; }}
.semantic-fields {{ display:grid; grid-template-columns:130px minmax(0,1fr); margin:9px 0; border:1px solid var(--line); border-bottom:0; }}
.semantic-fields dt,.semantic-fields dd {{ margin:0; padding:6px 8px; border-bottom:1px solid var(--line); }}
.semantic-fields dt {{ color:#526273; background:#edf2f7; }} .semantic-fields dd {{ background:#fff; overflow-wrap:anywhere; }}
.semantic-value {{ margin:9px 0; padding:8px; max-height:190px; overflow:auto; border-radius:5px; background:#f6f8fa; white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.4 Consolas,monospace; }}
.note {{ width:100%; min-height:58px; resize:vertical; padding:7px 8px; border:1px solid #bdc8d4; border-radius:5px; }}
.actions {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:7px; }}
.actions [data-status="accepted"] {{ border-color:#45a878; color:var(--green); }}
.actions [data-status="accepted_as_soft_only"] {{ border-color:#9376d2; color:var(--violet); }}
.actions [data-status="rejected"] {{ border-color:#e57d76; color:var(--red); }}
.actions [data-status="needs_more_evidence"] {{ border-color:#d3a22d; color:var(--amber); }}
.subtabs {{ display:flex; gap:5px; margin:0 0 10px; }} .subtab.active {{ color:#fff; border-color:var(--blue); background:var(--blue); }}
.subview {{ display:none; }} .subview.active {{ display:block; }}
.helper-grid {{ display:grid; gap:9px; }}
.helper-row {{ padding:9px; border:1px solid var(--line); border-radius:6px; background:#fff; }}
.helper-row-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }}
.face-chips {{ display:flex; flex-wrap:wrap; gap:5px; margin:7px 0; }}
.face-chip {{ display:inline-flex; align-items:center; gap:2px; }}
.face-chip button {{ padding:3px 6px; font-size:12px; }}
.helper-input {{ width:100%; padding:6px; border:1px solid #bdc8d4; border-radius:5px; }}
.helper-summary {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:9px; }}
.warning-list {{ margin:7px 0; padding-left:21px; color:var(--amber); }}
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
  <header class="topbar"><h1>{title}</h1><span class="small">{scope_text} · 严格隔离审核</span><span class="spacer"></span><span id="revision">revision —</span><span id="connection" class="connection">连接中</span><button id="refresh-preview">重新生成模型</button></header>
  <div class="workspace">
    <section class="visuals" aria-label="Geometry comparisons">
      <div class="visual-modebar"><button class="active" data-visual-mode="model">模型对比</button><button data-visual-mode="evidence">论文证据</button><button data-visual-mode="helper2">Helper2 面审核</button><button id="clear-helper-selection">清除选面</button><span id="visual-locator" class="locator">模型模式</span></div>
      <div class="visual-stage">
        <div id="visual-model" class="visual-mode active"><div class="model-grid">
          <div class="plot-wrap"><span class="plot-label">baseline / current / previous — 3D overlay</span><div id="model-plot"></div></div>
          <div class="plot-wrap"><span class="plot-label">r-z profile comparison (mm)</span><div id="profile-plot"></div></div>
        </div></div>
        <div id="visual-evidence" class="visual-mode"><div class="evidence-reader">
          <div id="evidence-reader-head" class="evidence-reader-head">点击 Evidence 或语义卡片中的证据引用。</div>
          <div id="evidence-reader-body" class="evidence-reader-body muted">尚未选择论文证据。</div>
        </div></div>
        <div id="visual-helper2" class="visual-mode"><div id="helper2-plot" style="width:100%;height:100%;min-height:620px"></div></div>
      </div>
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
const API = Object.freeze({{session:"/api/session",events:"/api/review-events",manual:"/api/manual-items",preview:"/api/preview",helper2:"/api/helper2-review",paper:"/api/paper-source"}});
const COLORS = Object.freeze({{baseline:"#7b8794",previous:"#d97706",current:"#1677b8"}});
const STATE = {{data:BOOTSTRAP,session:{{revision:0,review_decisions:{{}},manual_items:[],helper2_reviews:{{}}}},preview:BOOTSTRAP.preview || BOOTSTRAP.geometry_projection || null,previewSequence:0,busy:false,parameterDraft:{{}},visualMode:"model",currentEvidence:null,pdfUrl:"",helper2:null,activeSubview:"geometry",helper2SaveTimer:null}};

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

function activePaper() {{ const id=String(STATE.data.active_paper_id || ""); return object(array(STATE.data.papers).find(paper=>String(object(paper).id || object(paper).paper_id)===id) || array(STATE.data.papers)[0]); }}
function setVisualMode(mode) {{
  if (!["model","evidence","helper2"].includes(mode)) return;
  STATE.visualMode=mode;
  document.querySelectorAll("[data-visual-mode]").forEach(button=>button.classList.toggle("active",button.dataset.visualMode===mode));
  document.querySelectorAll(".visual-mode").forEach(node=>node.classList.toggle("active",node.id==="visual-"+mode));
  document.getElementById("visual-locator").textContent=mode==="evidence"?(STATE.currentEvidence?.locator || "论文证据"):mode==="helper2"?"Helper2 面级审核":"模型模式";
  if (mode==="helper2") renderHelper2Plot();
  else if (mode==="model") renderPlots();
}}
function evidencePageImage(item) {{
  const direct=safeImage(item.data_uri || item.image_data_uri || item.src); if (direct) return direct;
  const paper=activePaper(),gallery=array(object(paper.evidence_layers).gallery),locator=object(item.source_locator),page=Number(locator.page ?? item.page);
  const evidenceId=String(locator.evidence_id || item.original_id || item.id || item.item_id || "");
  const match=gallery.find(entry=>Number(object(entry).page)===page) || gallery.find(entry=>array(object(entry).evidence_refs).map(String).includes(evidenceId));
  return safeImage(object(match).data_uri);
}}
function openEvidence(item) {{
  const locator=object(item.source_locator),page=locator.page ?? item.page ?? "—",section=locator.section || item.section || item.figure_id || "";
  const label=String(activePaper().title || STATE.data.active_paper_id || "paper")+" · page "+String(page)+(section?" · "+String(section):"");
  STATE.currentEvidence={{item,image:evidencePageImage(item),page,section,locator:label}};
  renderEvidenceReader(); setVisualMode("evidence");
}}
function findEvidenceByRef(ref) {{
  const target=String(ref); return evidenceItems().find(item=>{{ const locator=object(item.source_locator); return [item.original_id,item.id,item.item_id,locator.evidence_id].map(String).includes(target) || array(item.evidence_refs).map(String).includes(target); }});
}}
function renderEvidenceReader() {{
  const head=document.getElementById("evidence-reader-head"),body=document.getElementById("evidence-reader-body"),selected=STATE.currentEvidence;
  if (!selected) {{ head.textContent="点击 Evidence 或语义卡片中的证据引用。"; body.className="evidence-reader-body muted"; body.textContent="尚未选择论文证据。"; return; }}
  const caption=selected.item.caption || selected.item.evidence_summary || selected.item.summary || selected.item.text || "";
  head.innerHTML='<div class="card-head"><div class="grow"><div class="card-title">'+esc(selected.locator)+'</div><div class="card-meta">'+esc(caption)+'</div></div></div><div class="actions"><button id="reader-back-model">返回模型</button><button id="reader-page-image">页面图像</button><button id="reader-open-pdf">PDF 原文同页</button></div>';
  body.className="evidence-reader-body";
  body.innerHTML=selected.image?'<img alt="'+esc(selected.locator)+'" src="'+esc(selected.image)+'">':'<div class="card muted">该证据有页码，但没有对应页面图像；可尝试打开 PDF 原文。</div>';
  document.getElementById("reader-back-model").onclick=()=>setVisualMode("model");
  document.getElementById("reader-page-image").onclick=()=>renderEvidenceReader();
  document.getElementById("reader-open-pdf").onclick=()=>openPaperPdf(selected.page);
}}
async function openPaperPdf(page) {{
  try {{
    const response=await fetch(API.paper,{{headers:{{"X-Review-Token":TOKEN}},credentials:"same-origin"}});
    if (!response.ok) throw new Error("PDF endpoint returned HTTP "+String(response.status));
    const blob=await response.blob(); if (STATE.pdfUrl) URL.revokeObjectURL(STATE.pdfUrl); STATE.pdfUrl=URL.createObjectURL(blob);
    document.getElementById("evidence-reader-body").innerHTML='<iframe title="论文 PDF" src="'+esc(STATE.pdfUrl)+'#page='+encodeURIComponent(page)+'"></iframe>';
  }} catch (error) {{ notify(error.message,true); }}
}}

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
  host.querySelectorAll("article.card").forEach((card,index)=>{{
    const button=document.createElement("button"); button.className="evidence-open"; button.textContent="定位到论文原页";
    button.addEventListener("click",()=>openEvidence(rows[index]));
    card.insertBefore(button,card.querySelector(".card-head"));
  }});
  bindReviewActions(host,reviewRows);
}}

const ACTIONS=[
  ["accepted","OK / 接受"],["accepted_as_soft_only","Soft OK / 仅软建议"],
  ["rejected","Reject / 拒绝"],["needs_more_evidence","Needs evidence / 补证据"]
];
function reviewActionButtons(id) {{ return ACTIONS.map(action=>`<button data-review-id="${{esc(id)}}" data-status="${{action[0]}}">${{action[1]}}</button>`).join(""); }}
function displayed(value) {{
  if (value===null || value===undefined || value==="") return "N/A";
  if (Array.isArray(value)) return value.length?value.map(displayed).join(", "):"N/A";
  if (typeof value==="object") {{
    const rows=Object.entries(value).filter(([,item])=>item!==null&&item!==undefined&&item!==""&&(!Array.isArray(item)||item.length));
    return rows.length?rows.map(([key,item])=>key+": "+displayed(item)).join("；"):"N/A";
  }}
  return String(value);
}}
function semanticView(row) {{
  const item=row.item,view=object(item.semantic_candidate_view);
  if (Object.keys(view).length) return view;
  const content=object(item.content || item),rawSubject=content.feature_name || content.curve_region || content.parameter_name || content.motif_name || content.objective_name || content.constraint_id || item.label || row.id;
  return {{
    schema_version:"literature_semantic_candidate_view.v1",
    section:row.section,
    subject:{{canonical_id:String(rawSubject),entity_type:"manual_or_legacy",aliases:[]}},
    claim:{{kind:row.section,predicate:"states",value:content,unit:content.unit ?? null}},
    applicability:{{status:"applicable",operating_regime:object(STATE.data.review_scope).operating_regime ?? null,cavity_family:object(STATE.data.review_scope).cavity_family ?? null,cell_count:object(STATE.data.review_scope).cell_count ?? null,scope:content.scope ?? null}},
    provenance:{{paper_id:row.paperId,source_refs:array(item.source_refs || item.evidence_refs || content.source_refs || content.evidence_refs),semantic_path:item.semantic_path || row.section}},
    assessment:{{confidence:content.confidence ?? null,"human_review_status":item.human_review_status || "pending",review_note:item.review_note || ""}},
    geometry_binding:{{grammar_region:null,parameter_names:[],feature_types:[],binding_status:"unbound"}}
  }};
}}
function semanticCard(row,view) {{
  const item=row.item,status=statusOf(item,row.id),note=noteOf(item,row.id),subject=object(view.subject),claim=object(view.claim),app=object(view.applicability),provenance=object(view.provenance),binding=object(view.geometry_binding);
  const refs=array(provenance.source_refs || item.source_refs || item.evidence_refs);
  const refButtons=refs.length?'<div class="face-chips">'+refs.map(ref=>'<button data-evidence-ref="'+esc(ref)+'">'+esc(ref)+'</button>').join("")+'</div>':'<span class="muted">N/A</span>';
  return '<article class="card semantic-card" data-item-key="'+esc(row.id)+'"><div class="card-head"><div class="grow"><div class="card-title">'+esc(subject.canonical_id || row.id)+'</div><div class="card-meta">'+esc(row.paperId || "paper")+' · '+esc(row.section)+' · '+esc(claim.kind || "claim")+'</div></div><span class="pill '+esc(status)+'">'+esc(status)+'</span></div>'+
    '<dl class="semantic-fields"><dt>Subject type</dt><dd>'+esc(displayed(subject.entity_type))+'</dd><dt>Claim / Predicate</dt><dd>'+esc(displayed(claim.kind))+' / '+esc(displayed(claim.predicate))+'</dd><dt>Value</dt><dd>'+esc(displayed(claim.value))+(claim.unit?' ['+esc(claim.unit)+']':'')+'</dd><dt>Applicability</dt><dd>'+esc(displayed({{status:app.status,operating_regime:app.operating_regime,cavity_family:app.cavity_family,cell_count:app.cell_count,frequency_mhz:app.frequency_mhz,scope:app.scope}}))+'</dd><dt>Confidence</dt><dd>'+esc(displayed(object(view.assessment).confidence))+'</dd><dt>Geometry binding</dt><dd>'+esc(displayed({{grammar_region:binding.grammar_region,parameter_names:binding.parameter_names,feature_types:binding.feature_types,status:binding.binding_status}}))+'</dd><dt>Evidence</dt><dd>'+refButtons+'</dd></dl>'+
    '<label class="small">中文备注 / review_note<textarea class="note" data-note="'+esc(row.id)+'" lang="zh-CN">'+esc(note)+'</textarea></label><div class="actions">'+reviewActionButtons(row.id)+'<button data-save-note="'+esc(row.id)+'">保存备注</button></div></article>';
}}
function renderGroupedSemantics() {{
  const rows=semanticItems(),host=document.getElementById("semantic-list"),groups=new Map(),patches=[];
  rows.forEach(row=>{{ const view=semanticView(row); if (row.section==="draft_prior_patch" || object(view.claim).kind==="proposed_patch") patches.push({{row,view}}); else {{ const key=String(object(view.subject).canonical_id || "unclassified"); if (!groups.has(key)) groups.set(key,[]); groups.get(key).push({{row,view}}); }} }});
  const sections=[...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([subject,items])=>'<section class="semantic-group"><h3>'+esc(subject)+' <span class="pill">'+items.length+' claims</span></h3>'+items.map(entry=>semanticCard(entry.row,entry.view)).join("")+'</section>');
  if (patches.length) sections.push('<section class="semantic-group"><h3>配置应用建议 / Draft patches <span class="pill">'+patches.length+'</span></h3><div class="muted">该组是待审核的配置动作，不与论文事实混排。</div>'+patches.map(entry=>semanticCard(entry.row,entry.view)).join("")+'</section>');
  host.innerHTML=sections.join("") || '<div class="card muted">没有可审核的语义候选。</div>';
  const options=SEMANTIC_SECTIONS.map(section=>'<option value="'+esc(section)+'">'+esc(section)+'</option>').join("");
  document.getElementById("manual-add").innerHTML='<details class="card"><summary><b>Add structured semantic / 新增结构化语义</b></summary><form id="manual-form" class="form-grid"><label>Section<select name="section">'+options+'</select></label><label>ID<input name="id" required placeholder="manual_semantic_001"></label><label class="wide">结构化 JSON（除 section/id 外的字段）<textarea name="body" rows="7" spellcheck="false">{{}}</textarea></label><label class="wide">中文备注<input name="review_note" lang="zh-CN"></label><div class="wide"><button type="submit">Add as pending and render / 新增并渲染</button></div></form></details><div class="global-note"><label><b>全局中文备注</b><textarea id="global-note" class="note" lang="zh-CN">'+esc(noteOf({{}},"__global_note__"))+'</textarea></label><div class="actions"><button id="save-global-note">保存全局备注</button></div></div>';
  bindSemanticActions(rows,host);
  host.querySelectorAll("[data-evidence-ref]").forEach(button=>button.addEventListener("click",()=>{{ const evidence=findEvidenceByRef(button.dataset.evidenceRef); if (evidence) openEvidence(evidence); else notify("未找到证据引用: "+button.dataset.evidenceRef,true); }}));
}}
function renderSemantics() {{
  renderGroupedSemantics();
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
function parameterEditor() {{
  const values=activeParameterValues();
  return `<form id="parameter-form" class="card"><div class="card-title">SLS-2 parameter iteration / 参数迭代</div><div class="card-meta">单位均为 mm；提交后 previous/current 将并列保留用于比较。</div><div class="form-grid">${{PARAMETER_KEYS.map(key=>`<label>${{esc(key)}} (mm)<input data-parameter="${{esc(key)}}" name="${{esc(key)}}" type="number" min="0.000001" step="any" required value="${{esc(Number.isFinite(values[key])?values[key]:"")}}"></label>`).join("")}}</div><div class="actions"><button type="submit">Render parameters / 按参数渲染</button></div></form>`;
}}
function helper2Payload() {{
  const root=previewRoot(),embedded=object(object(root.helper2).review_payload);
  if (Object.keys(embedded).length) return embedded;
  return object(object(object(STATE.data.geometry_projection).helper2).review_payload);
}}
function helper2ProjectionId() {{ const root=previewRoot(); return String(root.candidate_id || root.id || object(STATE.data.geometry_projection).candidate_id || "geometry_projection"); }}
function ensureHelper2State() {{
  const payload=helper2Payload(),projectionId=helper2ProjectionId();
  if (!Object.keys(payload).length) {{ STATE.helper2=null; return null; }}
  if (STATE.helper2 && STATE.helper2.projectionId===projectionId && STATE.helper2.sessionRevision===currentRevision()) return STATE.helper2;
  const saved=object(object(object(STATE.session.helper2_reviews)[projectionId]).review),geometry={{}},candidates={{}},bindings={{}};
  Object.keys(object(payload.faces)).forEach(id=>{{ geometry[id]={{status:object(object(saved.geometry)[id]).status || "unreviewed"}}; }});
  const featureCandidates=new Map(array(object(object(payload.layers).features).feature_candidates).map(item=>[String(item.id || item.feature_id),item]));
  array(object(payload.draft).features).forEach(feature=>{{
    const id=String(feature.id),prior=object(object(saved.candidates)[id]),generated=object(featureCandidates.get(id));
    candidates[id]={{status:prior.status || generated.status || "requires_review",type:String(prior.type || feature.type || ""),geometry_refs:array(prior.geometry_refs || feature.geometry_refs).map(String)}};
  }});
  array(object(object(payload.layers).udsg).bindings).forEach(binding=>{{
    const id=String(binding.binding_id),prior=object(object(saved.bindings)[id]);
    bindings[id]={{status:prior.status || binding.status || "requires_review",feature_id:String(prior.feature_id || binding.feature_id || ""),geometry_node_id:String(prior.geometry_node_id || binding.geometry_node_id || ""),deleted:Boolean(prior.deleted)}};
  }});
  STATE.helper2={{projectionId,payload,geometry,candidates,bindings,selected:new Set(array(saved.selected_faces).map(String)),manual_groups:object(saved.manual_groups),notes:String(saved.notes || ""),active_tab:String(saved.active_tab || "geometry"),sessionRevision:currentRevision()}};
  return STATE.helper2;
}}
function helper2ReviewSnapshot() {{
  const state=ensureHelper2State(); if (!state) return null;
  return {{schema_version:"helper2_review_session.v1",active_tab:STATE.activeSubview,selected_faces:[...state.selected].sort(),geometry:state.geometry,candidates:state.candidates,bindings:state.bindings,manual_groups:state.manual_groups,notes:state.notes}};
}}
function queueHelper2Save() {{
  const state=ensureHelper2State(),review=helper2ReviewSnapshot(); if (!state || !review) return;
  window.clearTimeout(STATE.helper2SaveTimer);
  STATE.helper2SaveTimer=window.setTimeout(async()=>{{
    try {{ const value=await request(API.helper2,{{method:"POST",body:{{expected_revision:currentRevision(),projection_id:state.projectionId,review}}}}); acceptSession(value); }}
    catch (error) {{ if (error.code==="revision_conflict") await loadSession(); notify("Helper2 保存失败: "+error.message,true); }}
  }},180);
}}
function rawFace(ref) {{ const value=String(ref || ""); return value.startsWith("face:")?value.slice(5):value; }}
function helper2FaceColor(id) {{
  const state=ensureHelper2State(),face=object(object(state?.payload).faces?.[id]); if (!state) return "#9aa6b2";
  if (state.selected.has(id)) return "#f4c542";
  if (STATE.activeSubview==="geometry") return object(face.colors).geometry || "#8a9aa5";
  if (STATE.activeSubview==="features") return object(face.colors).features || "#8a9aa5";
  const ref="face:"+id,statuses=array(object(object(state.payload.layers).udsg).bindings).filter(binding=>{{ const edit=object(state.bindings[String(binding.binding_id)]); return !edit.deleted && edit.geometry_node_id===ref; }}).map(binding=>object(state.bindings[String(binding.binding_id)]).status);
  if (statuses.includes("rejected") || statuses.includes("broken_binding") || statuses.includes("deleted")) return "#b42318";
  if (statuses.includes("requires_review")) return "#d97706";
  if (statuses.includes("accepted") || statuses.includes("modified")) return "#18794e";
  return object(face.colors).udsg || "#9aa6b2";
}}
function helper2Meshes() {{
  const geometry=geometryPayload(),mesh=object(geometry.face_mesh),faces=object(object(ensureHelper2State()).payload).faces;
  return array(mesh.faces).map(face=>{{
    const id=String(face.face_id),vertices=array(face.vertices),triangles=array(face.triangles),meta=object(faces[id]);
    return {{type:"mesh3d",name:id,x:vertices.map(point=>array(point)[0]),y:vertices.map(point=>array(point)[1]),z:vertices.map(point=>array(point)[2]),i:triangles.map(item=>array(item)[0]),j:triangles.map(item=>array(item)[1]),k:triangles.map(item=>array(item)[2]),color:helper2FaceColor(id),opacity:.88,flatshading:false,showscale:false,hovertemplate:"<b>"+esc(id)+"</b><br>"+esc(meta.surface_type || "unknown")+"<extra></extra>"}};
  }});
}}
function renderHelper2Plot() {{
  const host=document.getElementById("helper2-plot"),state=ensureHelper2State();
  if (!state) {{ host.innerHTML='<div class="card muted">当前模型没有 Helper2 审核 payload。</div>'; return; }}
  if (window.__RFCEM_PLOTLY_MISSING__ || typeof Plotly==="undefined") {{ host.innerHTML='<div class="card muted">Plotly 未安装；仍可在右侧审核表中编辑。</div>'; return; }}
  const traces=helper2Meshes();
  Plotly.react(host,traces.length?traces:[{{type:"scatter3d",mode:"markers",x:[],y:[],z:[]}}],{{margin:{{l:0,r:0,t:30,b:0}},paper_bgcolor:"#fff",scene:{{aspectmode:"data",dragmode:"orbit"}},showlegend:false,uirevision:"helper2-"+state.projectionId}},{{responsive:true,displaylogo:false,scrollZoom:true}});
  if (typeof host.removeAllListeners==="function") host.removeAllListeners("plotly_click");
  host.on("plotly_click",event=>{{ const id=String(event.points?.[0]?.data?.name || ""); if (!object(state.payload.faces)[id]) return; if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id); queueHelper2Save(); renderGeometry(); renderHelper2Plot(); }});
}}
function helper2SummaryHtml() {{
  const state=ensureHelper2State(); if (!state) return "";
  const counts=(items,status)=>Object.values(items).filter(item=>object(item).status===status).length;
  return '<div class="helper-summary"><span class="pill">selected '+state.selected.size+'</span><span class="pill accepted">geometry accepted '+counts(state.geometry,"accepted")+'</span><span class="pill needs_more_evidence">geometry open '+(counts(state.geometry,"unreviewed")+counts(state.geometry,"requires_review"))+'</span><span class="pill accepted">features confirmed '+(counts(state.candidates,"confirmed")+counts(state.candidates,"modified"))+'</span><span class="pill needs_more_evidence">bindings open '+counts(state.bindings,"requires_review")+'</span></div>';
}}
function helper2GeometryHtml() {{
  const state=ensureHelper2State(); if (!state) return '<div class="card muted">尚无面级 Geometry 审核数据。</div>';
  const groups={{}}; Object.entries(object(state.payload.faces)).forEach(([id,face])=>{{ const type=String(object(face).surface_type || "unknown"); (groups[type] ||= []).push(id); }});
  const grouped=Object.entries(groups).sort((a,b)=>a[0].localeCompare(b[0])).map(([type,ids])=>'<div class="helper-row"><div class="helper-row-head"><b>'+esc(type)+'</b><span class="pill">'+ids.length+' faces</span></div><div class="face-chips">'+ids.sort().map(id=>'<button data-helper-face="'+esc(id)+'">'+esc(id)+'</button>').join("")+'</div></div>').join("");
  const audits=Object.entries(object(state.payload.faces)).sort((a,b)=>a[0].localeCompare(b[0])).map(([id,face])=>{{ const checks=array(object(face).geometry_checks); return '<div class="helper-row"><div class="helper-row-head"><b>'+esc(id)+'</b><span class="pill">'+esc(object(state.geometry[id]).status)+'</span></div><div class="small">'+esc(checks.length?checks.join(", "):"clean")+'</div><div class="actions"><button data-helper-face="'+esc(id)+'">高亮</button><button data-geometry-state="accepted" data-helper-id="'+esc(id)+'">OK</button><button data-geometry-state="requires_review" data-helper-id="'+esc(id)+'">需复核</button><button data-geometry-state="rejected" data-helper-id="'+esc(id)+'">拒绝</button></div></div>'; }}).join("");
  const selected=[...state.selected].sort(),details=selected.length?selected.map(id=>{{ const face=object(object(state.payload.faces)[id]); return '<div><b>'+esc(id)+'</b> · '+esc(face.surface_type || "unknown")+' · area '+esc(displayed(face.area))+' · adjacent '+esc(displayed(face.adjacent_faces))+'</div>'; }}).join(""):'<span class="muted">尚未选面。</span>';
  return helper2SummaryHtml()+'<div class="card"><div class="card-title">Surface classification / 表面分类</div><div class="helper-grid">'+grouped+'</div></div><div class="card"><div class="card-title">Geometry audit / 逐面审核</div><div class="helper-grid">'+audits+'</div></div><div class="card"><div class="card-title">Selected faces</div>'+details+'</div>';
}}
function helper2FeaturesHtml() {{
  const state=ensureHelper2State(); if (!state) return '<div class="card muted">尚无 Features 投影。</div>';
  const groups={{}}; Object.entries(state.candidates).forEach(([id,item])=>{{ const type=String(item.type || "Unclassified"); (groups[type] ||= []).push([id,item]); }});
  const content=Object.entries(groups).sort((a,b)=>a[0].localeCompare(b[0])).map(([type,items])=>'<section class="semantic-group"><h3>'+esc(type)+' <span class="pill">'+items.length+'</span></h3>'+items.map(([id,item])=>'<div class="helper-row"><div class="helper-row-head"><b>'+esc(id)+'</b><span class="pill">'+esc(item.status)+'</span></div><label class="small">Feature type<input class="helper-input" data-candidate-type="'+esc(id)+'" value="'+esc(item.type)+'"></label><div class="face-chips">'+(item.geometry_refs.length?item.geometry_refs.map(ref=>'<span class="face-chip"><button data-helper-ref="'+esc(ref)+'">'+esc(ref)+'</button><button data-remove-ref="'+esc(id)+'" data-ref="'+esc(ref)+'">×</button></span>').join(""):'<span class="muted">No geometry refs</span>')+'</div><div class="actions"><button data-candidate-state="confirmed" data-helper-id="'+esc(id)+'">确认</button><button data-candidate-state="requires_review" data-helper-id="'+esc(id)+'">需复核</button><button data-candidate-state="rejected" data-helper-id="'+esc(id)+'">拒绝</button><button data-add-selected="'+esc(id)+'">加入已选面</button></div></div>').join("")+'</section>').join("");
  const manual=Object.entries(state.manual_groups).map(([id,group])=>'<div class="helper-row"><b>'+esc(id)+'</b> / '+esc(object(group).type)+'<div>'+esc(displayed(object(group).geometry_refs))+'</div></div>').join("") || '<div class="muted">尚无人工组。</div>';
  return helper2SummaryHtml()+content+'<div class="card"><div class="card-title">Manual group / 人工分组</div><div class="form-grid"><label>ID<input id="manual-group-id"></label><label>Type<input id="manual-group-type"></label></div><div class="actions"><button id="add-manual-group">将已选面加入新组</button></div>'+manual+'</div>';
}}
function helper2UdsgHtml() {{
  const state=ensureHelper2State(); if (!state) return '<div class="card muted">尚无 UDSG 投影。</div>';
  const udsg=object(object(state.payload.layers).udsg),groups={{}};
  array(udsg.bindings).forEach(binding=>{{ const id=String(binding.binding_id),edit=object(state.bindings[id]),group=String(edit.feature_id || binding.feature_id || "unclassified"); (groups[group] ||= []).push([binding,edit]); }});
  const warnings=array(object(udsg.validation).warnings),summary='<div class="card"><div class="card-title">UDSG Geometry Layer</div><dl class="semantic-fields"><dt>Status</dt><dd>'+esc(displayed(object(udsg.validation).status))+'</dd><dt>Geometry nodes</dt><dd>'+array(udsg.geometry_nodes).length+'</dd><dt>Features</dt><dd>'+array(udsg.feature_candidates).length+'</dd><dt>Bindings</dt><dd>'+array(udsg.bindings).length+'</dd><dt>Warnings</dt><dd>'+esc(displayed(warnings))+'</dd></dl></div>';
  const content=Object.entries(groups).sort((a,b)=>a[0].localeCompare(b[0])).map(([featureId,items])=>'<section class="semantic-group"><h3>'+esc(featureId)+' <span class="pill">'+items.length+' bindings</span></h3>'+items.map(([binding,edit])=>{{ const id=String(binding.binding_id); return '<div class="helper-row"><div class="helper-row-head"><b>'+esc(id)+'</b><span class="pill">'+esc(edit.deleted?"deleted":edit.status)+'</span></div><div class="form-grid"><label>Feature<input class="helper-input" data-binding-feature="'+esc(id)+'" value="'+esc(edit.feature_id)+'"></label><label>Geometry node<input class="helper-input" data-binding-geometry="'+esc(id)+'" value="'+esc(edit.geometry_node_id)+'"></label></div><div class="small muted">Original: '+esc(binding.feature_id)+' → '+esc(binding.geometry_node_id)+' · confidence '+esc(displayed(binding.confidence))+'</div><div class="actions"><button data-binding-action="highlight" data-helper-id="'+esc(id)+'">高亮</button><button data-binding-action="apply" data-helper-id="'+esc(id)+'">应用编辑</button><button data-binding-action="accepted" data-helper-id="'+esc(id)+'">接受</button><button data-binding-action="requires_review" data-helper-id="'+esc(id)+'">需复核</button><button data-binding-action="rejected" data-helper-id="'+esc(id)+'">拒绝</button><button data-binding-action="deleted" data-helper-id="'+esc(id)+'">删除</button><button data-binding-action="restore" data-helper-id="'+esc(id)+'">恢复</button></div></div>'; }}).join("")+'</section>').join("");
  return helper2SummaryHtml()+summary+content+'<div class="card"><label>Helper2 总备注<textarea id="helper2-notes" class="note">'+esc(state.notes)+'</textarea></label><div class="actions"><button id="save-helper2-notes">保存 Helper2 备注</button></div></div>';
}}
function selectHelperFace(id,exclusive=false) {{
  const state=ensureHelper2State(); if (!state || !object(state.payload.faces)[id]) return;
  if (exclusive) state.selected.clear(); state.selected.add(id); queueHelper2Save(); renderGeometry(); setVisualMode("helper2");
}}
function bindHelper2Actions() {{
  const state=ensureHelper2State(); if (!state) return;
  document.querySelectorAll("[data-helper-face]").forEach(button=>button.onclick=()=>selectHelperFace(button.dataset.helperFace));
  document.querySelectorAll("[data-helper-ref]").forEach(button=>button.onclick=()=>selectHelperFace(rawFace(button.dataset.helperRef),true));
  document.querySelectorAll("[data-geometry-state]").forEach(button=>button.onclick=()=>{{ state.geometry[button.dataset.helperId].status=button.dataset.geometryState; queueHelper2Save(); renderGeometry(); renderHelper2Plot(); }});
  document.querySelectorAll("[data-candidate-state]").forEach(button=>button.onclick=()=>{{ state.candidates[button.dataset.helperId].status=button.dataset.candidateState; queueHelper2Save(); renderGeometry(); }});
  document.querySelectorAll("[data-candidate-type]").forEach(input=>input.onchange=()=>{{ const item=state.candidates[input.dataset.candidateType]; item.type=input.value.trim(); item.status="modified"; queueHelper2Save(); renderGeometry(); }});
  document.querySelectorAll("[data-add-selected]").forEach(button=>button.onclick=()=>{{ const item=state.candidates[button.dataset.addSelected],refs=new Set(item.geometry_refs); state.selected.forEach(id=>refs.add("face:"+id)); item.geometry_refs=[...refs].sort(); item.status="modified"; queueHelper2Save(); renderGeometry(); }});
  document.querySelectorAll("[data-remove-ref]").forEach(button=>button.onclick=()=>{{ const item=state.candidates[button.dataset.removeRef]; item.geometry_refs=item.geometry_refs.filter(ref=>ref!==button.dataset.ref); item.status="modified"; queueHelper2Save(); renderGeometry(); }});
  document.getElementById("add-manual-group")?.addEventListener("click",()=>{{ const id=String(document.getElementById("manual-group-id")?.value || "").trim(),type=String(document.getElementById("manual-group-type")?.value || "").trim(); if (!id || !type || !state.selected.size) {{ notify("人工组需要 ID、Type 和至少一个已选面",true); return; }} state.manual_groups[id]={{type,geometry_refs:[...state.selected].sort().map(face=>"face:"+face)}}; queueHelper2Save(); renderGeometry(); }});
  document.querySelectorAll("[data-binding-action]").forEach(button=>button.onclick=()=>{{
    const id=button.dataset.helperId,action=button.dataset.bindingAction,item=state.bindings[id],original=array(object(object(state.payload.layers).udsg).bindings).find(binding=>String(binding.binding_id)===id); if (!item || !original) return;
    if (action==="highlight") {{ selectHelperFace(rawFace(item.geometry_node_id),true); return; }}
    if (action==="apply") {{ item.feature_id=String(document.querySelector('[data-binding-feature="'+CSS.escape(id)+'"]')?.value || "").trim(); item.geometry_node_id=String(document.querySelector('[data-binding-geometry="'+CSS.escape(id)+'"]')?.value || "").trim(); item.deleted=false; item.status="modified"; }}
    else if (action==="restore") {{ item.feature_id=String(original.feature_id); item.geometry_node_id=String(original.geometry_node_id); item.deleted=false; item.status=String(original.status || "requires_review"); }}
    else if (action==="deleted") {{ item.deleted=true; item.status="deleted"; }}
    else {{ item.deleted=false; item.status=action; }}
    queueHelper2Save(); renderGeometry(); renderHelper2Plot();
  }});
  document.getElementById("save-helper2-notes")?.addEventListener("click",()=>{{ state.notes=String(document.getElementById("helper2-notes")?.value || ""); queueHelper2Save(); }});
}}
function compactGeometrySummary(geometry,validation) {{
  const manifest=object(geometry.manifest),index=object(object(geometry.geometry_graph).geometry_index),features=Array.isArray(featurePayload())?featurePayload():array(object(featurePayload()).feature_candidates),udsg=object(udsgPayload()),blocking=array(validation.blocking_errors),warnings=array(validation.warnings);
  return '<div class="card"><div class="card-head"><div class="grow"><div class="card-title">Geometry summary / 几何摘要</div><div class="card-meta">完整 generation.core.json 仅保留为机器审计产物，不在人工 GUI 展开。</div></div><span class="pill '+(validation.pass?'accepted':'pending')+'">'+(validation.pass?'kernel verified':'not verified')+'</span></div><dl class="semantic-fields"><dt>Candidate</dt><dd>'+esc(displayed(previewRoot().candidate_id || previewRoot().id))+'</dd><dt>Model / unit</dt><dd>'+esc(displayed(geometry.model_type))+' / '+esc(displayed(geometry.unit || "mm"))+'</dd><dt>STEP</dt><dd>'+esc(geometry.step_path?"generated":"N/A")+'</dd><dt>Faces</dt><dd>'+esc(displayed(array(manifest.faces).length || index.face_count))+'</dd><dt>Features / bindings</dt><dd>'+features.length+' / '+array(udsg.bindings).length+'</dd><dt>BBox</dt><dd>'+esc(displayed(index.bbox || manifest.bbox))+'</dd></dl>'+(blocking.length?'<ul class="warning-list">'+blocking.map(item=>'<li>'+esc(item)+'</li>').join("")+'</ul>':"")+(warnings.length?'<ul class="warning-list">'+warnings.map(item=>'<li>'+esc(item)+'</li>').join("")+'</ul>':"")+'</div>';
}}

function compactGeometryReviewCards(rows) {{
  return rows.map(row=>{{ const item=row.item,content=object(item.content),status=statusOf(item,row.id),note=noteOf(item,row.id),tuple=object(content.parameter_tuple),values=object(tuple.values); return '<article class="card"><div class="card-head"><div class="grow"><div class="card-title">'+esc(item.label || item.title || row.id)+'</div><div class="card-meta">Geometry projection · '+esc(displayed(content.claim))+'</div></div><span class="pill '+esc(status)+'">'+esc(status)+'</span></div><dl class="semantic-fields"><dt>Candidate</dt><dd>'+esc(displayed(content.candidate_id))+'</dd><dt>Parameters</dt><dd>'+esc(displayed(values))+(tuple.unit?' ['+esc(tuple.unit)+']':'')+'</dd><dt>Lineage</dt><dd>'+esc(displayed(content.lineage))+'</dd></dl><label class="small">中文备注 / review_note<textarea class="note" data-note="'+esc(row.id)+'" lang="zh-CN">'+esc(note)+'</textarea></label><div class="actions">'+reviewActionButtons(row.id)+'<button data-save-note="'+esc(row.id)+'">保存备注</button></div></article>'; }}).join("");
}}
function renderGeometryV2() {{
  const root=previewRoot(),geometry=geometryPayload(),validation=object(root.validation || object(STATE.data.geometry_projection).validation),reviewRows=geometryReviewItems(),geometryHost=document.getElementById("subview-geometry"),helper=ensureHelper2State();
  geometryHost.innerHTML=parameterEditor()+compactGeometrySummary(geometry,validation)+compactGeometryReviewCards(reviewRows)+(helper?helper2GeometryHtml():'<div class="card muted">当前模型尚无 Helper2 面级审核数据。</div>');
  const featureSource=featurePayload(),features=Array.isArray(featureSource)?featureSource:array(object(featureSource).feature_candidates || object(featureSource).items);
  document.getElementById("subview-features").innerHTML=helper?helper2FeaturesHtml():(features.length?'<div class="card"><div class="card-title">Feature candidates</div><table><thead><tr><th>ID</th><th>Type</th><th>Geometry refs</th><th>Confidence / status</th></tr></thead><tbody>'+features.map(feature=>'<tr><td>'+esc(feature.id || feature.feature_id)+'</td><td>'+esc(feature.type || feature.feature_type)+'</td><td>'+esc(array(feature.geometry_refs).join(", "))+'</td><td>'+esc(displayed([feature.confidence,feature.status]))+'</td></tr>').join("")+'</tbody></table></div>':'<div class="card muted">尚无 Features 投影。</div>');
  const udsg=object(udsgPayload());
  document.getElementById("subview-udsg").innerHTML=helper?helper2UdsgHtml():(Object.keys(udsg).length?'<div class="card"><div class="card-title">UDSG summary</div><dl class="semantic-fields"><dt>Schema</dt><dd>'+esc(displayed(udsg.schema_version))+'</dd><dt>Geometry nodes</dt><dd>'+array(udsg.geometry_nodes || udsg.nodes).length+'</dd><dt>Bindings</dt><dd>'+array(udsg.bindings).length+'</dd><dt>Validation</dt><dd>'+esc(displayed(object(udsg.validation).status))+'</dd></dl></div>':'<div class="card muted">尚无 UDSG 投影。</div>');
  document.querySelectorAll("[data-parameter]").forEach(input=>input.addEventListener("input",()=>{{ const value=Number(input.value); if (Number.isFinite(value)) STATE.parameterDraft[input.dataset.parameter]=value; }}));
  document.getElementById("parameter-form")?.addEventListener("submit",event=>{{ event.preventDefault(); const parameters={{}}; PARAMETER_KEYS.forEach(key=>{{ const input=event.currentTarget.elements.namedItem(key),value=Number(input?.value); if (Number.isFinite(value)) parameters[key]=value; }}); if (Object.keys(parameters).length!==PARAMETER_KEYS.length) {{ notify("六个参数都必须是有效数字",true); return; }} STATE.parameterDraft=parameters; generatePreview("parameter_iteration","",parameters); }});
  bindReviewActions(geometryHost,reviewRows); bindHelper2Actions();
  if (STATE.visualMode==="helper2") renderHelper2Plot();
}}
function renderGeometry() {{
  renderGeometryV2();
}}
function renderSummary() {{
  const counts=Object.fromEntries([...REVIEW_STATUSES].map(status=>[status,0])),reviewRows=new Map();
  [...semanticItems(),...geometryReviewItems()].forEach(row=>reviewRows.set(row.id,row));
  array(STATE.data.review_items).filter(raw=>String(object(raw).layer || "").toLowerCase()==="evidence").forEach((raw,index)=>{{ const item=object(raw),id=itemId(item,index,"evidence",String(item.paper_id || "")); reviewRows.set(id,{{item,id}}); }});
  reviewRows.forEach(row=>{{ const status=statusOf(row.item,row.id); counts[status]=(counts[status]||0)+1; }});
  const validation=object(previewRoot().validation); document.getElementById("review-summary").innerHTML=`<div class="summary-row"><b>Review summary</b>${{[...REVIEW_STATUSES].map(status=>`<span class="pill ${{esc(status)}}">${{esc(status)}} ${{counts[status]||0}}</span>`).join("")}}<span class="pill">model: ${{validation.generated?"generated":validation.pass?"verified":"waiting"}}</span></div>`;
}}
function renderAll() {{ renderSummary(); renderEvidence(); renderSemantics(); renderGeometry(); renderEvidenceReader(); if (STATE.visualMode==="helper2") renderHelper2Plot(); else renderPlots(); if (STATE.busy) document.querySelectorAll("button").forEach(button=>button.disabled=true); }}

async function generatePreview(reason="manual_refresh",item_id="",parameters=null) {{
  const sequence=++STATE.previewSequence; setConnection("生成模型中");
  const parameterValues=parameters || activeParameterValues();
  try {{ const value=await request(API.preview,{{method:"POST",body:{{expected_revision:currentRevision(),reason,...(item_id?{{item_id}}:{{}}),...(Object.keys(parameterValues).length?{{parameters:parameterValues}}:{{}})}}}}); if (sequence!==STATE.previewSequence) return; STATE.preview=value.preview || value.geometry_projection || value; STATE.helper2=null; setConnection("模型已刷新","ok"); renderGeometry(); if (STATE.visualMode==="helper2") renderHelper2Plot(); else renderPlots(); renderSummary(); notify("几何预览已刷新"); }}
  catch (error) {{ if (sequence===STATE.previewSequence) {{ setConnection("生成失败","bad"); notify(error.message,true); }} }}
}}

document.querySelectorAll("[data-layer]").forEach(button=>button.addEventListener("click",()=>{{ document.querySelectorAll("[data-layer]").forEach(node=>node.classList.toggle("active",node===button)); document.querySelectorAll(".layer").forEach(node=>node.classList.toggle("active",node.id===`layer-${{button.dataset.layer}}`)); }}));
document.querySelectorAll("[data-subview]").forEach(button=>button.addEventListener("click",()=>{{ document.querySelectorAll("[data-subview]").forEach(node=>node.classList.toggle("active",node===button)); document.querySelectorAll(".subview").forEach(node=>node.classList.toggle("active",node.id===`subview-${{button.dataset.subview}}`)); }}));
document.querySelectorAll("[data-visual-mode]").forEach(button=>button.addEventListener("click",()=>setVisualMode(button.dataset.visualMode)));
document.querySelectorAll("[data-subview]").forEach(button=>button.addEventListener("click",()=>{{ STATE.activeSubview=button.dataset.subview; const state=ensureHelper2State(); if (state) state.active_tab=STATE.activeSubview; if (["features","udsg"].includes(STATE.activeSubview)) setVisualMode("helper2"); else if (STATE.visualMode==="helper2") renderHelper2Plot(); queueHelper2Save(); renderGeometry(); }}));
document.getElementById("clear-helper-selection").addEventListener("click",()=>{{ const state=ensureHelper2State(); if (!state) return; state.selected.clear(); queueHelper2Save(); renderGeometry(); if (STATE.visualMode==="helper2") renderHelper2Plot(); }});
window.addEventListener("beforeunload",()=>{{ if (STATE.pdfUrl) URL.revokeObjectURL(STATE.pdfUrl); }});
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
