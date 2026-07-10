"""Generate a self-contained Plotly reviewer for Helper2 outputs."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Optional

from .layer_builders import (
    build_feature_candidates,
    build_geometry_graph,
    build_udsg_geometry_layer,
    detect_review_issues,
)
from .topology_analyzer import build_adjacency_graph


PALETTE = {
    "RFVacuumVolume": "#7f8c8d",
    "BeamPipeLeft": "#2d8fce",
    "BeamPipeRight": "#2070aa",
    "BeamAperture": "#42a5f5",
    "BeamExit": "#1565c0",
    "ConductingWall": "#4f7d35",
    "Iris": "#d18b21",
    "EquatorRegion": "#8e6bbd",
    "TransitionBlend": "#8c6d5a",
    "CathodeSurface": "#c55252",
    "UnknownSidePort": "#00a3a3",
}

SURFACE_PALETTE = {
    "plane": "#5b8def",
    "cylinder": "#45a36f",
    "cone": "#d08b2f",
    "sphere": "#c75f8f",
    "torus": "#7d62b8",
    "bspline": "#7a8794",
    "surface_of_revolution": "#2f8f9d",
    "unknown": "#8a9aa5",
}


def write_interactive_reviewer(
    path: Path,
    mesh_path: Path,
    geometry_manifest: dict,
    feature_graph_draft: dict,
    classifier_suggestions: Optional[dict] = None,
    *,
    geometry_graph: Optional[dict] = None,
    feature_candidates: Optional[dict] = None,
    udsg_geometry_layer: Optional[dict] = None,
    review_session: Optional[dict] = None,
) -> None:
    """Write a single-file offline HTML reviewer."""
    from plotly.offline import get_plotlyjs

    mesh_payload = json.loads(mesh_path.read_text(encoding="utf-8"))
    adjacency_graph = build_adjacency_graph(geometry_manifest)
    geometry_graph = geometry_graph or build_geometry_graph(geometry_manifest, adjacency_graph)
    feature_candidates = feature_candidates or build_feature_candidates(feature_graph_draft)
    udsg_geometry_layer = udsg_geometry_layer or build_udsg_geometry_layer(
        geometry_graph,
        feature_candidates,
        feature_graph_draft.get("face_groups", []),
    )
    review_issues = detect_review_issues(feature_candidates, udsg_geometry_layer)

    payload = _build_payload(
        mesh_payload,
        geometry_manifest,
        feature_graph_draft,
        classifier_suggestions or {},
        geometry_graph,
        feature_candidates,
        udsg_geometry_layer,
        review_issues,
        review_session or {},
    )
    html = _build_html(
        get_plotlyjs(),
        payload,
        str(Path(geometry_manifest.get("source_step", "model.step")).name),
    )
    path.write_text(html, encoding="utf-8")


def _build_payload(
    mesh_payload: dict,
    geometry_manifest: dict,
    feature_graph_draft: dict,
    classifier_suggestions: dict,
    geometry_graph: dict,
    feature_candidates: dict,
    udsg_geometry_layer: dict,
    review_issues: dict,
    review_session: dict,
) -> dict:
    face_map = {face["face_id"]: face for face in geometry_manifest.get("faces", [])}
    memberships = _feature_memberships(feature_graph_draft)
    unassigned = set(feature_graph_draft.get("unassigned_faces", []))
    classifier_map = {
        item["face_id"]: item.get("suggestions", [])
        for item in classifier_suggestions.get("faces", [])
    }

    traces = []
    face_data = {}
    for mesh in mesh_payload.get("faces", []):
        face_id = mesh["face_id"]
        vertices = mesh.get("vertices", [])
        triangles = mesh.get("triangles", [])
        face = face_map.get(face_id, {})
        feature_entries = memberships.get(face_id, [])
        feature_type = feature_entries[0]["type"] if feature_entries else "Unassigned"
        feature_color = "#d64045" if face_id in unassigned else PALETTE.get(feature_type, "#8a9aa5")
        surface_type = str(face.get("surface_type", "unknown"))
        geometry_color = SURFACE_PALETTE.get(surface_type, SURFACE_PALETTE["unknown"])
        traces.append(
            {
                "type": "mesh3d",
                "name": face_id,
                "meta": {
                    "face_id": face_id,
                    "feature_color": feature_color,
                    "geometry_color": geometry_color,
                    "udsg_color": _udsg_face_color(face_id, udsg_geometry_layer),
                    "feature_type": feature_type,
                },
                "x": [point[0] for point in vertices],
                "y": [point[1] for point in vertices],
                "z": [point[2] for point in vertices],
                "i": [triangle[0] for triangle in triangles],
                "j": [triangle[1] for triangle in triangles],
                "k": [triangle[2] for triangle in triangles],
                "color": feature_color,
                "opacity": 0.88,
                "flatshading": False,
                "hovertemplate": (
                    f"<b>{face_id}</b><br>{surface_type}"
                    f"<br>area={_fmt(face.get('area'))}<extra></extra>"
                ),
                "showscale": False,
            }
        )
        face_data[face_id] = {
            **face,
            "feature_memberships": feature_entries,
            "classifier_suggestions": classifier_map.get(face_id, []),
            "unassigned": face_id in unassigned,
            "geometry_checks": _geometry_checks(face),
            "colors": {
                "geometry": geometry_color,
                "features": feature_color,
                "udsg": _udsg_face_color(face_id, udsg_geometry_layer),
            },
        }

    traces.append(_adjacency_trace(geometry_manifest))
    traces.append(
        {
            "type": "scatter3d",
            "name": "__labels__",
            "mode": "text",
            "x": [face.get("centroid", [0, 0, 0])[0] for face in geometry_manifest.get("faces", [])],
            "y": [face.get("centroid", [0, 0, 0])[1] for face in geometry_manifest.get("faces", [])],
            "z": [face.get("centroid", [0, 0, 0])[2] for face in geometry_manifest.get("faces", [])],
            "text": [face["face_id"] for face in geometry_manifest.get("faces", [])],
            "textfont": {"size": 10, "color": "#111827"},
            "hoverinfo": "skip",
            "visible": False,
            "showlegend": False,
        }
    )

    feature_types = sorted({entry["type"] for entries in memberships.values() for entry in entries})
    return {
        "traces": traces,
        "faceTraceCount": len(mesh_payload.get("faces", [])),
        "adjacencyTraceIndex": len(mesh_payload.get("faces", [])),
        "labelsTraceIndex": len(mesh_payload.get("faces", [])) + 1,
        "faces": face_data,
        "draft": feature_graph_draft,
        "featureTypes": feature_types,
        "layers": {
            "geometry": geometry_graph,
            "features": feature_candidates,
            "udsg": udsg_geometry_layer,
        },
        "review": {
            "session": review_session,
            "issues": review_issues,
        },
        "palette": {
            "feature": PALETTE,
            "surface": SURFACE_PALETTE,
        },
        "modelName": str(Path(geometry_manifest.get("source_step", "model.step")).name),
    }


def _feature_memberships(draft: dict) -> dict[str, list]:
    memberships: dict[str, list] = {}
    for feature in draft.get("features", []):
        for ref in feature.get("geometry_refs", []):
            face_id = str(ref).split(":", 1)[-1]
            if face_id.startswith("F"):
                memberships.setdefault(face_id, []).append(
                    {
                        "id": feature.get("id"),
                        "type": feature.get("type"),
                        "confidence": feature.get("confidence"),
                        "evidence": feature.get("evidence", []),
                    }
                )
    return memberships


def _adjacency_trace(geometry_manifest: dict) -> dict:
    face_map = {face.get("face_id"): face for face in geometry_manifest.get("faces", [])}
    x_values = []
    y_values = []
    z_values = []
    seen = set()
    for face in geometry_manifest.get("faces", []):
        face_id = face.get("face_id")
        start = face.get("centroid", [0, 0, 0])
        for neighbor_id in face.get("adjacent_faces", []):
            key = tuple(sorted((str(face_id), str(neighbor_id))))
            if key in seen or neighbor_id not in face_map:
                continue
            seen.add(key)
            end = face_map[neighbor_id].get("centroid", [0, 0, 0])
            x_values.extend([start[0], end[0], None])
            y_values.extend([start[1], end[1], None])
            z_values.extend([start[2], end[2], None])
    return {
        "type": "scatter3d",
        "name": "__adjacency__",
        "mode": "lines",
        "x": x_values,
        "y": y_values,
        "z": z_values,
        "line": {"color": "#6b7280", "width": 3},
        "hoverinfo": "skip",
        "visible": False,
        "showlegend": False,
    }


def _geometry_checks(face: dict) -> list[str]:
    checks = []
    if face.get("surface_type") == "unknown":
        checks.append("unknown_surface")
    confidence = face.get("area_confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.6:
        checks.append("low_area_confidence")
    if not face.get("adjacent_faces"):
        checks.append("isolated_face")
    relation = face.get("axis_relation", {})
    if face.get("surface_type") in {"cylinder", "cone", "torus", "surface_of_revolution"} and not relation.get("is_axisymmetric"):
        checks.append("axis_relation_review")
    if face.get("edge_count", 0) == 0:
        checks.append("missing_edges")
    return checks


def _udsg_face_color(face_id: str, udsg_geometry_layer: dict) -> str:
    ref = f"face:{face_id}"
    statuses = {
        binding.get("status")
        for binding in udsg_geometry_layer.get("bindings", [])
        if binding.get("geometry_node_id") == ref
    }
    if "broken_binding" in statuses:
        return "#b42318"
    if "requires_review" in statuses:
        return "#d97706"
    if statuses:
        return "#18794e"
    return "#9aa6b2"


def _fmt(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return str(value)


def _build_html(plotly_js: str, payload: dict, model_name: str) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = HTML_TEMPLATE.replace("__PLOTLY_JS__", plotly_js)
    html = html.replace("__PAYLOAD__", payload_json)
    html = html.replace("__MODEL_NAME__", escape(model_name))
    return html


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Helper2 Review - __MODEL_NAME__</title>
<script>__PLOTLY_JS__</script>
<style>
:root { color-scheme: light; font-family: Inter, "Segoe UI", Arial, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; color: #1f2933; background: #eef1f4; }
header { height: 52px; display:flex; align-items:center; justify-content:space-between; padding:0 16px; background:#fff; border-bottom:1px solid #cfd6dd; }
h1 { margin:0; font-size:16px; font-weight:650; letter-spacing:0; }
.badge { font-size:12px; color:#52606d; }
main { height:calc(100vh - 52px); display:grid; grid-template-columns:minmax(0,1fr) 420px; }
.workspace { min-width:0; display:grid; grid-template-rows:44px minmax(0,1fr); background:#fff; }
.toolbar { display:flex; align-items:center; gap:8px; padding:6px 10px; border-bottom:1px solid #d9e0e6; overflow-x:auto; }
button, select, input, textarea { font:inherit; }
button { min-height:30px; border:1px solid #aeb8c2; background:#fff; color:#26323d; padding:0 10px; border-radius:4px; cursor:pointer; }
button:hover { background:#eef4f7; }
button.primary { background:#176b87; border-color:#176b87; color:#fff; }
button.danger { color:#a4262c; }
select, input[type=text] { height:30px; border:1px solid #aeb8c2; background:#fff; border-radius:4px; padding:0 8px; }
textarea { width:100%; min-height:64px; border:1px solid #aeb8c2; border-radius:4px; padding:8px; resize:vertical; }
label.control { display:flex; align-items:center; gap:5px; font-size:12px; white-space:nowrap; }
#plot { width:100%; height:100%; min-height:0; }
aside { overflow:auto; border-left:1px solid #cfd6dd; background:#f8fafb; }
.tabs { position:sticky; top:0; display:grid; grid-template-columns:repeat(4,1fr); background:#fff; border-bottom:1px solid #cfd6dd; z-index:2; }
.tab { border:0; border-right:1px solid #e1e6ea; border-radius:0; height:38px; }
.tab.active { background:#176b87; color:#fff; }
.panel { padding:12px; border-bottom:1px solid #d9e0e6; }
.panel h2 { margin:0 0 9px; font-size:13px; font-weight:700; }
.tab-panel { display:none; }
.tab-panel.active { display:block; }
.kv { display:grid; grid-template-columns:112px 1fr; gap:5px 8px; font-size:12px; }
.kv dt { color:#66737f; }
.kv dd { margin:0; overflow-wrap:anywhere; }
.empty { color:#7b8792; font-size:12px; }
.pill { display:inline-flex; align-items:center; gap:4px; min-height:22px; padding:2px 6px; border:1px solid #cbd4db; border-radius:3px; background:#eef3f6; font-size:11px; margin:2px; }
.issue { color:#8a4b00; border-color:#e3c078; background:#fff8e6; }
.bad { color:#a4262c; border-color:#e0a4a8; background:#fff1f2; }
.ok { color:#18794e; border-color:#9fd4b4; background:#eefaf2; }
.muted { color:#52606d; font-size:12px; line-height:1.45; }
.candidate, .binding, .row { padding:8px 0; border-top:1px solid #e1e6ea; }
.candidate:first-child, .binding:first-child, .row:first-child { border-top:0; }
.candidate-head, .binding-head { display:flex; justify-content:space-between; gap:8px; font-size:12px; }
.candidate input { width:100%; margin:6px 0; }
.candidate-actions { display:flex; flex-wrap:wrap; gap:6px; }
.candidate-status { font-size:11px; color:#52606d; align-self:center; }
.candidate-members { display:flex; flex-wrap:wrap; gap:5px; margin:6px 0; }
.audit-actions { display:flex; flex-wrap:wrap; gap:6px; margin-top:7px; }
.face-chip { display:inline-flex; align-items:center; border:1px solid #bcc7d0; background:#eef3f6; border-radius:3px; overflow:hidden; }
.face-chip button { min-height:24px; border:0; border-radius:0; padding:0 6px; background:transparent; font-family:Consolas, monospace; font-size:11px; }
.face-chip button.remove-ref { color:#a4262c; border-left:1px solid #cbd4db; font-family:inherit; font-weight:700; }
#selected-faces { font-family:Consolas, monospace; font-size:12px; min-height:24px; overflow-wrap:anywhere; }
.manual-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
.manual-grid input { width:100%; }
.wide { width:100%; margin-top:7px; }
.actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
@media (max-width:960px) {
  main { grid-template-columns:1fr; grid-template-rows:60vh auto; height:auto; }
  aside { border-left:0; border-top:1px solid #cfd6dd; }
  .workspace { height:60vh; }
}
</style>
</head>
<body>
<header><h1>__MODEL_NAME__</h1><div class="badge">Helper2 geometry review</div></header>
<main>
  <section class="workspace">
    <div class="toolbar">
      <button data-view="iso">ISO</button><button data-view="+x">+X</button><button data-view="-x">-X</button>
      <button data-view="+y">+Y</button><button data-view="-y">-Y</button><button data-view="+z">+Z</button><button data-view="-z">-Z</button>
      <select id="feature-filter"><option value="all">All features</option><option value="unassigned">Unassigned</option></select>
      <select id="drag-mode"><option value="orbit">Orbit</option><option value="turntable">Turntable</option><option value="pan">Pan</option><option value="zoom">Zoom</option></select>
      <label class="control"><input id="labels-toggle" type="checkbox"> Face IDs</label>
      <label class="control"><input id="adjacency-toggle" type="checkbox"> Topology</label>
      <label class="control"><input id="fast-mode" type="checkbox" checked> Fast drag</label>
      <label class="control">Opacity <input id="opacity" type="range" min="0.1" max="1" step="0.05" value="0.88"></label>
    </div>
    <div id="plot"></div>
  </section>
  <aside>
    <nav class="tabs">
      <button class="tab active" data-tab="geometry">Geometry</button>
      <button class="tab" data-tab="features">Features</button>
      <button class="tab" data-tab="udsg">UDSG</button>
      <button class="tab" data-tab="review">Review</button>
    </nav>
    <section id="panel-geometry" class="tab-panel active">
      <section class="panel"><h2>Geometry Index</h2><div id="geometry-summary"></div></section>
      <section class="panel"><h2>Surface Classification</h2><div id="surface-classification"></div></section>
      <section class="panel"><h2>Geometry Audit</h2><div id="geometry-audit"></div></section>
      <section class="panel"><h2>Selected Face</h2><div id="face-details" class="empty">Click a face.</div></section>
      <section class="panel"><h2>Selected Faces</h2><div id="selected-faces" class="empty">None</div><button id="clear-selection" class="wide">Clear selection</button></section>
    </section>
    <section id="panel-features" class="tab-panel">
      <section class="panel"><h2>Feature Candidates</h2><div id="feature-summary"></div><div id="candidate-list"></div></section>
      <section class="panel"><h2>Manual Group</h2>
        <div class="manual-grid"><input id="manual-id" type="text" placeholder="group id"><input id="manual-type" type="text" placeholder="feature type"></div>
        <button id="add-group" class="wide">Add selected faces</button>
        <div id="manual-groups" class="empty">None</div>
      </section>
    </section>
    <section id="panel-udsg" class="tab-panel">
      <section class="panel"><h2>UDSG Geometry Layer</h2><div id="udsg-summary"></div></section>
      <section class="panel"><h2>Binding Review Guide</h2><div id="binding-guide"></div></section>
      <section class="panel"><h2>Bindings</h2><div id="binding-list"></div></section>
    </section>
    <section id="panel-review" class="tab-panel">
      <section class="panel"><h2>Review Summary</h2><div id="review-summary"></div></section>
      <section class="panel"><h2>Reviewer Notes</h2><textarea id="review-notes"></textarea></section>
      <section class="panel"><div class="actions"><button id="export-yaml" class="primary">Download reviewed labels YAML</button><button id="export-session">Download review_session.json</button></div></section>
    </section>
  </aside>
</main>
<script>
const APP=__PAYLOAD__;
const plot=document.getElementById("plot");
const faceTraceCount=APP.faceTraceCount;
const adjacencyTraceIndex=APP.adjacencyTraceIndex;
const labelsTraceIndex=APP.labelsTraceIndex;
const faceIndices=Array.from({length:faceTraceCount},(_,i)=>i);
const traceIndex={};
APP.traces.slice(0,faceTraceCount).forEach((t,i)=>{traceIndex[t.name]=i;});
const selected=new Set();
const geometryState={};
const candidateState={};
const candidateTypes={};
const candidateRefs={};
const bindingState={};
const bindingEdits={};
Object.keys(APP.faces).forEach(id=>{
  geometryState[id]=(APP.review.session.geometry&&APP.review.session.geometry[id]&&APP.review.session.geometry[id].status)||"unreviewed";
});
APP.draft.features.forEach(f=>{
  candidateState[f.id]=(APP.review.session.candidates&&APP.review.session.candidates[f.id]&&APP.review.session.candidates[f.id].status)||"unreviewed";
  candidateTypes[f.id]=f.type;
  candidateRefs[f.id]=new Set(f.geometry_refs||[]);
});
APP.layers.udsg.bindings.forEach(b=>{
  const saved=(APP.review.session.bindings&&APP.review.session.bindings[b.binding_id])||{};
  bindingState[b.binding_id]=saved.status||b.status||"requires_review";
  bindingEdits[b.binding_id]={
    feature_id:saved.feature_id||b.feature_id,
    geometry_node_id:saved.geometry_node_id||b.geometry_node_id,
    deleted:Boolean(saved.deleted)
  };
});
const manualGroups={};
let activeTab="geometry";
let fastModeEnabled=true;
const layout={
  margin:{l:0,r:0,t:0,b:0}, paper_bgcolor:"#fff", scene:{
    aspectmode:"data", bgcolor:"#fff",
    xaxis:{title:"X",showbackground:false}, yaxis:{title:"Y",showbackground:false}, zaxis:{title:"Z",showbackground:false},
    dragmode:"orbit",
    camera:{eye:{x:1.45,y:1.45,z:1.15}}
  }, showlegend:false, uirevision:"helper2-review"
};
Plotly.newPlot(plot,APP.traces,layout,{responsive:true,displaylogo:false,scrollZoom:true,plotGlPixelRatio:1,staticPlot:false});
const filter=document.getElementById("feature-filter");
APP.featureTypes.forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;filter.appendChild(o);});
function esc(v){return String(v??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function rawFace(ref){const v=String(ref);return v.startsWith("face:")?v.slice(5):v;}
function refForFace(id){return `face:${id}`;}
function faceColor(id){
  if(selected.has(id)) return "#f4c542";
  const f=APP.faces[id]||{};
  if(activeTab==="geometry") return f.colors.geometry;
  if(activeTab==="udsg") return udsgFaceColor(id);
  return f.colors.features;
}
function udsgFaceColor(id){
  const ref=refForFace(id);
  const statuses=APP.layers.udsg.bindings.filter(b=>{
    const edit=bindingEdits[b.binding_id]||{};
    return !edit.deleted && (edit.geometry_node_id||b.geometry_node_id)===ref;
  }).map(b=>bindingState[b.binding_id]);
  if(statuses.includes("rejected")||statuses.includes("broken_binding")) return "#b42318";
  if(statuses.includes("requires_review")) return "#d97706";
  if(statuses.includes("accepted")) return "#18794e";
  return (APP.faces[id]&&APP.faces[id].colors.udsg)||"#9aa6b2";
}
function effectiveBinding(binding){
  const edit=bindingEdits[binding.binding_id]||{};
  return {
    ...binding,
    feature_id:edit.feature_id||binding.feature_id,
    geometry_node_id:edit.geometry_node_id||binding.geometry_node_id,
    deleted:Boolean(edit.deleted)
  };
}
function applyColors(){
  const colors=APP.traces.slice(0,faceTraceCount).map(t=>faceColor(t.name));
  Plotly.restyle(plot, {color: colors}, faceIndices);
}
function recolorFaces(faceIds){
  const ids=[...new Set(faceIds)].filter(id=>traceIndex[id]!==undefined);
  if(!ids.length)return;
  if(!fastModeEnabled){
    applyColors();
    return;
  }
  ids.forEach(id=>Plotly.restyle(plot,{color:faceColor(id)},[traceIndex[id]]));
}
function applyFilter(){
  const value=filter.value;
  const visible=APP.traces.slice(0,faceTraceCount).map(t=>{
    const id=t.name, f=APP.faces[id]||{};
    return value==="all" || (value==="unassigned" && f.unassigned) || (f.feature_memberships||[]).some(x=>x.type===value);
  });
  Plotly.restyle(plot,{visible: visible},faceIndices);
}
function showFace(id){
  const f=APP.faces[id]; if(!f)return;
  const memberships=(f.feature_memberships||[]).map(x=>`${x.type} (${x.confidence})`).join(", ")||"Unassigned";
  const suggestions=(f.classifier_suggestions||[]).map(x=>`${x.type} (${Number(x.probability).toFixed(3)})`).join(", ")||"None";
  const issues=APP.review.issues.overlap_geometry_refs.includes(refForFace(id))?'<span class="pill issue">overlap</span>':"";
  const geometryChecks=(f.geometry_checks||[]).map(x=>`<span class="pill issue">${esc(x)}</span>`).join("")||'<span class="pill ok">no geometry checks</span>';
  document.getElementById("face-details").innerHTML=`<dl class="kv">
    <dt>Face</dt><dd><b>${esc(id)}</b> ${issues}</dd><dt>Surface</dt><dd>${esc(f.surface_type)}</dd>
    <dt>Area</dt><dd>${Number(f.area||0).toPrecision(7)}</dd><dt>Centroid</dt><dd>${esc(JSON.stringify(f.centroid))}</dd>
    <dt>Radius</dt><dd>${esc(f.radius)}</dd><dt>Adjacent</dt><dd>${esc((f.adjacent_faces||[]).join(", "))}</dd>
    <dt>Features</dt><dd>${esc(memberships)}</dd><dt>Classifier</dt><dd>${esc(suggestions)}</dd>
    <dt>Checks</dt><dd>${geometryChecks}</dd><dt>Review</dt><dd><span class="pill">${esc(geometryState[id])}</span></dd></dl>
    <div class="audit-actions"><button data-geom-ok="${esc(id)}">Geometry OK</button><button data-geom-review="${esc(id)}">Needs review</button><button class="danger" data-geom-reject="${esc(id)}">Reject geometry</button></div>`;
  document.querySelector("[data-geom-ok]").onclick=e=>setGeometryState(e.target.dataset.geomOk,"accepted");
  document.querySelector("[data-geom-review]").onclick=e=>setGeometryState(e.target.dataset.geomReview,"requires_review");
  document.querySelector("[data-geom-reject]").onclick=e=>setGeometryState(e.target.dataset.geomReject,"rejected");
}
function updateSelection(changedFaceIds=[]){
  const box=document.getElementById("selected-faces");
  box.textContent=selected.size?[...selected].sort().join(", "):"None";
  box.className=selected.size?"":"empty";
  recolorFaces(changedFaceIds);
}
plot.on("plotly_click",ev=>{
  const id=ev.points?.[0]?.data?.name;
  if(!id||id==="__labels__"||id==="__adjacency__")return;
  if(selected.has(id))selected.delete(id);else selected.add(id);
  showFace(id);updateSelection([id]);renderReviewSummary();
});
document.getElementById("clear-selection").onclick=()=>{
  const changed=[...selected];
  selected.clear();
  updateSelection(changed);
  renderReviewSummary();
};
const cameras={
 iso:{x:1.45,y:1.45,z:1.15}, "+x":{x:2.2,y:0,z:0}, "-x":{x:-2.2,y:0,z:0},
 "+y":{x:0,y:2.2,z:0}, "-y":{x:0,y:-2.2,z:0}, "+z":{x:0,y:0,z:2.2}, "-z":{x:0,y:0,z:-2.2}
};
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>Plotly.relayout(plot,{"scene.camera.eye":cameras[b.dataset.view]}));
filter.onchange=applyFilter;
document.getElementById("drag-mode").onchange=e=>Plotly.relayout(plot,{"scene.dragmode":e.target.value});
document.getElementById("labels-toggle").onchange=e=>Plotly.restyle(plot,{visible:e.target.checked},[labelsTraceIndex]);
document.getElementById("adjacency-toggle").onchange=e=>Plotly.restyle(plot,{visible:e.target.checked},[adjacencyTraceIndex]);
document.getElementById("fast-mode").onchange=e=>setFastMode(e.target.checked);
document.getElementById("opacity").oninput=e=>Plotly.restyle(plot,{opacity:Number(e.target.value)},faceIndices);
document.querySelectorAll(".tab").forEach(tab=>tab.onclick=()=>setTab(tab.dataset.tab));
function setTab(name){
  activeTab=name;
  document.querySelectorAll(".tab").forEach(tab=>tab.classList.toggle("active",tab.dataset.tab===name));
  document.querySelectorAll(".tab-panel").forEach(panel=>panel.classList.toggle("active",panel.id===`panel-${name}`));
  applyColors();renderReviewSummary();
}
function setFastMode(enabled){
  fastModeEnabled=enabled;
  const hover = enabled ? "skip" : "all";
  const hoverTemplates = APP.traces.slice(0,faceTraceCount).map(t=>enabled ? "<extra></extra>" : t.hovertemplate);
  Plotly.restyle(plot,{hovertemplate:hoverTemplates, hoverinfo:hover},faceIndices);
  if(enabled){
    document.getElementById("labels-toggle").checked=false;
    document.getElementById("adjacency-toggle").checked=false;
    Plotly.restyle(plot,{visible:false},[labelsTraceIndex, adjacencyTraceIndex]);
  }
}
function renderGeometry(){
  const layer=APP.layers.geometry;
  const counts=Object.entries(layer.geometry_index.surface_counts||{}).map(([k,v])=>`<span class="pill">${esc(k)} ${v}</span>`).join("");
  document.getElementById("geometry-summary").innerHTML=`<dl class="kv">
    <dt>Schema</dt><dd>${esc(layer.schema_version)}</dd><dt>Axis</dt><dd>${esc(layer.geometry_index.detected_axis)}</dd>
    <dt>Faces</dt><dd>${APP.faceTraceCount}</dd><dt>Axisymmetric</dt><dd>${esc(layer.geometry_index.axisymmetric_face_count)}</dd>
    <dt>BBox</dt><dd>${esc(JSON.stringify(layer.geometry_index.bbox))}</dd><dt>Surfaces</dt><dd>${counts}</dd></dl>`;
  renderSurfaceClassification();
  renderGeometryAudit();
}
function renderSurfaceClassification(){
  const root=document.getElementById("surface-classification");
  const groups={};
  Object.entries(APP.faces).forEach(([id,face])=>{
    const type=face.surface_type||"unknown";
    if(!groups[type]) groups[type]=[];
    groups[type].push(id);
  });
  root.innerHTML=Object.entries(groups).sort((a,b)=>a[0].localeCompare(b[0])).map(([type,ids])=>{
    const color=(APP.palette.surface&&APP.palette.surface[type])||"#8a9aa5";
    const chips=ids.sort().map(id=>`<button data-surface-face="${esc(id)}" style="border-color:${color}">${esc(id)}</button>`).join("");
    return `<div class="row"><div class="candidate-head"><b><span class="pill" style="border-color:${color};background:${color};color:#fff">${esc(type)}</span></b><span>${ids.length} face(s)</span></div>
      <div class="muted">Check whether these faces really share the same CAD surface class before accepting downstream feature bindings.</div>
      <div class="audit-actions">${chips}</div></div>`;
  }).join("");
  root.querySelectorAll("[data-surface-face]").forEach(b=>b.onclick=()=>{
    const id=b.dataset.surfaceFace;
    const wasSelected=selected.has(id);
    if(!wasSelected) selected.add(id);
    showFace(id);
    updateSelection([id]);
  });
}
function renderGeometryAudit(){
  const root=document.getElementById("geometry-audit");
  const faces=Object.entries(APP.faces).sort((a,b)=>a[0].localeCompare(b[0]));
  const flagged=faces.filter(([,f])=>(f.geometry_checks||[]).length || geometryState[f.face_id]!=="unreviewed");
  const rows=(flagged.length?flagged:faces).map(([id,f])=>{
    const checks=(f.geometry_checks||[]).map(x=>`<span class="pill issue">${esc(x)}</span>`).join("")||'<span class="pill ok">clean</span>';
    return `<div class="row"><div class="candidate-head"><b>${esc(id)}</b><span class="pill">${esc(geometryState[id])}</span></div>
      <div>${checks}</div>
      <div class="audit-actions"><button data-show-face="${esc(id)}">Show</button><button data-geometry-ok="${esc(id)}">OK</button><button data-geometry-review="${esc(id)}">Needs review</button><button class="danger" data-geometry-reject="${esc(id)}">Reject</button></div></div>`;
  }).join("");
  const open=Object.values(geometryState).filter(x=>x==="unreviewed"||x==="requires_review").length;
  root.innerHTML=`<div><span class="pill">listed ${flagged.length||faces.length}</span><span class="pill issue">open ${open}</span></div>${rows}`;
  root.querySelectorAll("[data-show-face]").forEach(b=>b.onclick=()=>{selected.add(b.dataset.showFace);showFace(b.dataset.showFace);updateSelection([b.dataset.showFace]);});
  root.querySelectorAll("[data-geometry-ok]").forEach(b=>b.onclick=()=>setGeometryState(b.dataset.geometryOk,"accepted"));
  root.querySelectorAll("[data-geometry-review]").forEach(b=>b.onclick=()=>setGeometryState(b.dataset.geometryReview,"requires_review"));
  root.querySelectorAll("[data-geometry-reject]").forEach(b=>b.onclick=()=>setGeometryState(b.dataset.geometryReject,"rejected"));
}
function setGeometryState(id,status){
  geometryState[id]=status;
  renderGeometryAudit();
  if(selected.has(id)) showFace(id);
  renderReviewSummary();
}
function issuePills(id){
  return (APP.review.issues.feature_issues[id]||[]).map(v=>`<span class="pill ${v==="broken_binding"?"bad":"issue"}">${esc(v)}</span>`).join("");
}
function renderFeatures(){
  const candidates=APP.layers.features.feature_candidates||[];
  const low=Object.values(APP.review.issues.feature_issues).filter(v=>v.includes("low_confidence")).length;
  document.getElementById("feature-summary").innerHTML=`<span class="pill">candidates ${candidates.length}</span><span class="pill issue">low confidence ${low}</span><span class="pill issue">overlap refs ${APP.review.issues.overlap_geometry_refs.length}</span>`;
  const root=document.getElementById("candidate-list");root.innerHTML="";
  APP.draft.features.forEach(f=>{
    const refs=[...candidateRefs[f.id]].sort();
    const chips=refs.length?refs.map(ref=>`<span class="face-chip"><button data-show-ref="${esc(ref)}">${esc(ref)}</button><button class="remove-ref" data-remove-candidate="${esc(f.id)}" data-remove-ref="${esc(ref)}" title="Remove">x</button></span>`).join(""):`<span class="empty">No geometry refs</span>`;
    const d=document.createElement("div");d.className="candidate";
    d.innerHTML=`<div class="candidate-head"><b>${esc(f.id)}</b><span>${esc(f.confidence)}</span></div>
      <div>${issuePills(f.id)}</div>
      <input type="text" value="${esc(candidateTypes[f.id])}" data-type="${esc(f.id)}">
      <div class="candidate-members">${chips}</div>
      <div class="candidate-actions"><button data-confirm="${esc(f.id)}">Confirm</button><button data-review="${esc(f.id)}">Requires review</button><button class="danger" data-reject="${esc(f.id)}">Reject</button><button data-add-selected="${esc(f.id)}">Add selected faces</button><span class="candidate-status" id="status-${esc(f.id)}">${esc(candidateState[f.id])}</span></div>`;
    root.appendChild(d);
  });
  root.querySelectorAll("[data-type]").forEach(input=>input.oninput=()=>{candidateTypes[input.dataset.type]=input.value;});
  root.querySelectorAll("[data-confirm]").forEach(b=>b.onclick=()=>setCandidate(b.dataset.confirm,"confirmed"));
  root.querySelectorAll("[data-review]").forEach(b=>b.onclick=()=>setCandidate(b.dataset.review,"requires_review"));
  root.querySelectorAll("[data-reject]").forEach(b=>b.onclick=()=>setCandidate(b.dataset.reject,"rejected"));
  root.querySelectorAll("[data-add-selected]").forEach(b=>b.onclick=()=>addSelectedToCandidate(b.dataset.addSelected));
  root.querySelectorAll("[data-remove-ref]").forEach(b=>b.onclick=()=>removeCandidateRef(b.dataset.removeCandidate,b.dataset.removeRef));
  root.querySelectorAll("[data-show-ref]").forEach(b=>b.onclick=()=>showCandidateRef(b.dataset.showRef));
}
function setCandidate(id,status){
  candidateState[id]=status;
  const statusEl=document.getElementById(`status-${id}`);
  if(statusEl) statusEl.textContent=status;
  renderReviewSummary();
}
function addSelectedToCandidate(id){
  if(!selected.size)return;
  selected.forEach(faceId=>candidateRefs[id].add(`face:${faceId}`));
  candidateState[id]="modified";
  renderFeatures();renderReviewSummary();
}
function removeCandidateRef(id,ref){
  candidateRefs[id].delete(ref);
  candidateState[id]="modified";
  renderFeatures();renderReviewSummary();
}
function showCandidateRef(ref){
  const faceId=rawFace(ref);
  if(!APP.faces[faceId])return;
  selected.add(faceId);showFace(faceId);updateSelection([faceId]);
}
function renderUdsg(){
  const layer=APP.layers.udsg;
  const status=layer.validation.status;
  const warnings=(layer.validation.warnings||[]).map(v=>`<div class="pill issue">${esc(v)}</div>`).join("")||'<span class="pill ok">no warnings</span>';
  document.getElementById("udsg-summary").innerHTML=`<dl class="kv">
    <dt>Schema</dt><dd>${esc(layer.schema_version)}</dd><dt>Status</dt><dd><span class="pill ${status==="partial_ok"?"ok":"issue"}">${esc(status)}</span></dd>
    <dt>Geometry nodes</dt><dd>${layer.geometry_nodes.length}</dd><dt>Bindings</dt><dd>${layer.bindings.length}</dd>
    <dt>Warnings</dt><dd>${warnings}</dd></dl>`;
  document.getElementById("binding-guide").innerHTML=`<div class="muted">UDSG here means a geometry-only traceability layer: feature candidate -> geometry node -> evidence. Accept a binding only when the highlighted faces match the feature meaning, the geometry classification is credible, confidence/evidence are reasonable, and no warning/broken reference applies. Keep requires_review when the face set is plausible but ambiguous. Reject when the feature points at the wrong face, an incomplete face set, or a geometry check you do not trust.</div>`;
  const root=document.getElementById("binding-list");root.innerHTML="";
  layer.bindings.forEach(binding=>{
    const d=document.createElement("div");d.className="binding";
    const effective=effectiveBinding(binding);
    const state=bindingState[binding.binding_id]||binding.status;
    const statusClass=effective.deleted?"bad":state==="rejected"||state==="broken_binding"?"bad":state==="requires_review"?"issue":"ok";
    d.innerHTML=`<div class="binding-head"><b>${esc(binding.binding_id)}</b><span id="binding-status-${esc(binding.binding_id)}" class="pill ${statusClass}">${esc(effective.deleted?"deleted":state)}</span></div>
      <dl class="kv"><dt>Feature</dt><dd><input type="text" value="${esc(effective.feature_id)}" data-binding-feature="${esc(binding.binding_id)}"></dd><dt>Geometry</dt><dd><input type="text" value="${esc(effective.geometry_node_id)}" data-binding-geometry="${esc(binding.binding_id)}"></dd><dt>Original</dt><dd>${esc(binding.feature_id)} -> ${esc(binding.geometry_node_id)}</dd><dt>Confidence</dt><dd>${esc(binding.confidence)}</dd></dl>
      <div class="audit-actions"><button data-binding="${esc(binding.binding_id)}">Highlight binding</button><button data-binding-apply="${esc(binding.binding_id)}">Apply binding edit</button><button data-binding-accept="${esc(binding.binding_id)}">Accept binding</button><button data-binding-review="${esc(binding.binding_id)}">Requires review</button><button class="danger" data-binding-reject="${esc(binding.binding_id)}">Reject binding</button><button class="danger" data-binding-delete="${esc(binding.binding_id)}">Delete binding</button><button data-binding-restore="${esc(binding.binding_id)}">Restore binding</button></div>`;
    root.appendChild(d);
  });
  root.querySelectorAll("[data-binding]").forEach(b=>b.onclick=()=>highlightBinding(b.dataset.binding));
  root.querySelectorAll("[data-binding-apply]").forEach(b=>b.onclick=()=>applyBindingEdit(b.dataset.bindingApply));
  root.querySelectorAll("[data-binding-accept]").forEach(b=>b.onclick=()=>setBindingState(b.dataset.bindingAccept,"accepted"));
  root.querySelectorAll("[data-binding-review]").forEach(b=>b.onclick=()=>setBindingState(b.dataset.bindingReview,"requires_review"));
  root.querySelectorAll("[data-binding-reject]").forEach(b=>b.onclick=()=>setBindingState(b.dataset.bindingReject,"rejected"));
  root.querySelectorAll("[data-binding-delete]").forEach(b=>b.onclick=()=>deleteBinding(b.dataset.bindingDelete));
  root.querySelectorAll("[data-binding-restore]").forEach(b=>b.onclick=()=>restoreBinding(b.dataset.bindingRestore));
}
function setBindingState(bindingId,status){
  if(bindingEdits[bindingId]) bindingEdits[bindingId].deleted=false;
  bindingState[bindingId]=status;
  const binding=APP.layers.udsg.bindings.find(b=>b.binding_id===bindingId);
  const faceId=binding ? rawFace(effectiveBinding(binding).geometry_node_id) : null;
  renderUdsg();
  if(faceId && APP.faces[faceId]) recolorFaces([faceId]); else applyColors();
  renderReviewSummary();
}
function highlightBinding(bindingId){
  const binding=APP.layers.udsg.bindings.find(b=>b.binding_id===bindingId);
  if(!binding)return;
  selected.clear();
  const faceId=rawFace(effectiveBinding(binding).geometry_node_id);
  if(APP.faces[faceId]){selected.add(faceId);showFace(faceId);}
  updateSelection(faceId ? [faceId] : []);
}
function applyBindingEdit(bindingId){
  const feature=document.querySelector(`[data-binding-feature="${CSS.escape(bindingId)}"]`);
  const geometry=document.querySelector(`[data-binding-geometry="${CSS.escape(bindingId)}"]`);
  if(!feature||!geometry)return;
  bindingEdits[bindingId]={feature_id:feature.value.trim(),geometry_node_id:geometry.value.trim(),deleted:false};
  bindingState[bindingId]="modified";
  renderUdsg();applyColors();renderReviewSummary();
}
function deleteBinding(bindingId){
  if(!bindingEdits[bindingId])return;
  bindingEdits[bindingId].deleted=true;
  bindingState[bindingId]="deleted";
  renderUdsg();applyColors();renderReviewSummary();
}
function restoreBinding(bindingId){
  const binding=APP.layers.udsg.bindings.find(b=>b.binding_id===bindingId);
  if(!binding)return;
  bindingEdits[bindingId]={feature_id:binding.feature_id,geometry_node_id:binding.geometry_node_id,deleted:false};
  bindingState[bindingId]=binding.status||"requires_review";
  renderUdsg();applyColors();renderReviewSummary();
}
document.getElementById("add-group").onclick=()=>{
  const id=document.getElementById("manual-id").value.trim(), type=document.getElementById("manual-type").value.trim();
  if(!id||!type||!selected.size)return;
  manualGroups[id]={type,geometry_refs:[...selected].sort().map(x=>`face:${x}`)};
  document.getElementById("manual-groups").textContent=Object.keys(manualGroups).join(", ");
  document.getElementById("manual-groups").className="";
  renderReviewSummary();
};
function q(v){return JSON.stringify(String(v));}
function yaml(){
  const lines=["confirmed_features:"];
  let confirmed=0;
  APP.draft.features.forEach(f=>{
    if(!["confirmed","modified"].includes(candidateState[f.id]))return;
    confirmed++;
    const type=candidateTypes[f.id];
    const refs=[...candidateRefs[f.id]].sort();
    lines.push(`  ${f.id}:`,`    type: ${q(type)}`,`    geometry_refs: [${refs.map(q).join(", ")}]`);
    if(f.default_boundary_role)lines.push(`    default_boundary_role: ${q(f.default_boundary_role)}`);
  });
  if(!confirmed)lines.push("  {}");
  lines.push("rejected_candidates:");
  const rejected=Object.keys(candidateState).filter(x=>candidateState[x]==="rejected");
  rejected.length?rejected.forEach(x=>lines.push(`  - ${q(x)}`)):lines.push("  []");
  lines.push("manual_groups:");
  const groups=Object.entries(manualGroups);
  groups.length?groups.forEach(([id,g])=>lines.push(`  ${id}:`,`    type: ${q(g.type)}`,`    geometry_refs: [${g.geometry_refs.map(q).join(", ")}]`)):lines.push("  {}");
  return lines.join("\\n")+"\\n";
}
function reviewSession(){
  const candidates={};
  APP.draft.features.forEach(f=>{candidates[f.id]={status:candidateState[f.id],type:candidateTypes[f.id],geometry_refs:[...candidateRefs[f.id]].sort()};});
  const geometry={};
  Object.keys(APP.faces).forEach(id=>{geometry[id]={status:geometryState[id],checks:APP.faces[id].geometry_checks||[]};});
  const bindings={};
  APP.layers.udsg.bindings.forEach(b=>{
    const effective=effectiveBinding(b);
    bindings[b.binding_id]={
      status:bindingState[b.binding_id],
      original_feature_id:b.feature_id,
      original_geometry_node_id:b.geometry_node_id,
      feature_id:effective.feature_id,
      geometry_node_id:effective.geometry_node_id,
      deleted:effective.deleted
    };
  });
  return {
    schema_version:"review_session.v0",
    model_name:APP.modelName,
    active_tab:activeTab,
    selected_faces:[...selected].sort(),
    geometry,
    candidates,
    bindings,
    manual_groups:manualGroups,
    notes:document.getElementById("review-notes").value,
    issues:APP.review.issues
  };
}
function download(name,text,type){
  const blob=new Blob([text],{type});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download=name;a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
document.getElementById("export-yaml").onclick=()=>download("reviewed_feature_labels.yaml",yaml(),"text/yaml");
document.getElementById("export-session").onclick=()=>download("review_session.json",JSON.stringify(reviewSession(),null,2)+"\\n","application/json");
function renderReviewSummary(){
  const candidateStatuses=Object.values(candidateState);
  const geometryStatuses=Object.values(geometryState);
  const bindingStatuses=Object.values(bindingState);
  const count=(values,s)=>values.filter(v=>v===s).length;
  const unbound=Object.keys(APP.faces).filter(id=>!(APP.faces[id].feature_memberships||[]).length).length;
  document.getElementById("review-summary").innerHTML=`<div class="row"><b>Geometry</b><br><span class="pill ok">accepted ${count(geometryStatuses,"accepted")}</span><span class="pill issue">requires review ${count(geometryStatuses,"requires_review")}</span><span class="pill bad">rejected ${count(geometryStatuses,"rejected")}</span><span class="pill">unreviewed ${count(geometryStatuses,"unreviewed")}</span></div>
    <div class="row"><b>Features</b><br><span class="pill ok">confirmed ${count(candidateStatuses,"confirmed")}</span><span class="pill">modified ${count(candidateStatuses,"modified")}</span><span class="pill bad">rejected ${count(candidateStatuses,"rejected")}</span><span class="pill issue">requires review ${count(candidateStatuses,"requires_review")}</span><span class="pill">unreviewed ${count(candidateStatuses,"unreviewed")}</span><span class="pill issue">unbound faces ${unbound}</span></div>
    <div class="row"><b>UDSG bindings</b><br><span class="pill ok">accepted ${count(bindingStatuses,"accepted")}</span><span class="pill">modified ${count(bindingStatuses,"modified")}</span><span class="pill issue">requires review ${count(bindingStatuses,"requires_review")}</span><span class="pill bad">rejected ${count(bindingStatuses,"rejected")}</span><span class="pill bad">deleted ${count(bindingStatuses,"deleted")}</span></div>`;
}
renderGeometry();
renderFeatures();
renderUdsg();
renderReviewSummary();
applyColors();
setFastMode(true);
</script>
</body></html>"""
