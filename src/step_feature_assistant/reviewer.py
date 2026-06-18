"""Generate a self-contained Plotly face-review application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Optional


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


def write_interactive_reviewer(
    path: Path,
    mesh_path: Path,
    geometry_manifest: dict,
    feature_graph_draft: dict,
    classifier_suggestions: Optional[dict] = None,
) -> None:
    """Write a single-file offline HTML reviewer."""
    from plotly.offline import get_plotlyjs

    mesh_payload = json.loads(mesh_path.read_text(encoding="utf-8"))
    face_map = {face["face_id"]: face for face in geometry_manifest.get("faces", [])}
    memberships = _feature_memberships(feature_graph_draft)
    unassigned = set(feature_graph_draft.get("unassigned_faces", []))
    classifier_map = {
        item["face_id"]: item.get("suggestions", [])
        for item in (classifier_suggestions or {}).get("faces", [])
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
        color = "#d64045" if face_id in unassigned else PALETTE.get(feature_type, "#8a9aa5")
        traces.append(
            {
                "type": "mesh3d",
                "name": face_id,
                "meta": {"face_id": face_id, "base_color": color, "feature_type": feature_type},
                "x": [point[0] for point in vertices],
                "y": [point[1] for point in vertices],
                "z": [point[2] for point in vertices],
                "i": [triangle[0] for triangle in triangles],
                "j": [triangle[1] for triangle in triangles],
                "k": [triangle[2] for triangle in triangles],
                "color": color,
                "opacity": 0.88,
                "flatshading": False,
                "hovertemplate": (
                    f"<b>{face_id}</b><br>{face.get('surface_type', 'unknown')}"
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
        }

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
    html = _build_html(
        get_plotlyjs(),
        traces,
        len(mesh_payload.get("faces", [])),
        face_data,
        feature_graph_draft,
        feature_types,
        str(Path(geometry_manifest.get("source_step", "model.step")).name),
    )
    path.write_text(html, encoding="utf-8")


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


def _fmt(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return str(value)


def _build_html(
    plotly_js: str,
    traces: list,
    face_trace_count: int,
    face_data: dict,
    draft: dict,
    feature_types: list,
    model_name: str,
) -> str:
    payload = json.dumps(
        {
            "traces": traces,
            "faceTraceCount": face_trace_count,
            "faces": face_data,
            "draft": draft,
            "featureTypes": feature_types,
            "modelName": model_name,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>STEP Face Review - {model_name}</title>
<script>{plotly_js}</script>
<style>
:root {{ color-scheme: light; font-family: Inter, "Segoe UI", Arial, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #1f2933; background: #eef1f4; }}
header {{ height: 52px; display:flex; align-items:center; justify-content:space-between; padding:0 16px; background:#fff; border-bottom:1px solid #cfd6dd; }}
h1 {{ margin:0; font-size:16px; font-weight:650; letter-spacing:0; }}
.badge {{ font-size:12px; color:#52606d; }}
main {{ height:calc(100vh - 52px); display:grid; grid-template-columns:minmax(0,1fr) 360px; }}
.workspace {{ min-width:0; display:grid; grid-template-rows:44px minmax(0,1fr); background:#fff; }}
.toolbar {{ display:flex; align-items:center; gap:8px; padding:6px 10px; border-bottom:1px solid #d9e0e6; overflow-x:auto; }}
button, select, input {{ font:inherit; }}
button {{ height:30px; border:1px solid #aeb8c2; background:#fff; color:#26323d; padding:0 10px; border-radius:4px; cursor:pointer; }}
button:hover {{ background:#eef4f7; }}
button.primary {{ background:#176b87; border-color:#176b87; color:#fff; }}
button.danger {{ color:#a4262c; }}
select, input[type=text] {{ height:30px; border:1px solid #aeb8c2; background:#fff; border-radius:4px; padding:0 8px; }}
label.control {{ display:flex; align-items:center; gap:5px; font-size:12px; white-space:nowrap; }}
#plot {{ width:100%; height:100%; min-height:0; }}
aside {{ overflow:auto; border-left:1px solid #cfd6dd; background:#f8fafb; }}
.panel {{ padding:12px; border-bottom:1px solid #d9e0e6; }}
.panel h2 {{ margin:0 0 9px; font-size:13px; font-weight:700; }}
.kv {{ display:grid; grid-template-columns:88px 1fr; gap:5px 8px; font-size:12px; }}
.kv dt {{ color:#66737f; }}
.kv dd {{ margin:0; overflow-wrap:anywhere; }}
.empty {{ color:#7b8792; font-size:12px; }}
.candidate {{ padding:8px 0; border-top:1px solid #e1e6ea; }}
.candidate:first-of-type {{ border-top:0; }}
.candidate-head {{ display:flex; justify-content:space-between; gap:8px; font-size:12px; }}
.candidate input {{ width:100%; margin:6px 0; }}
.candidate-actions {{ display:flex; gap:6px; }}
.candidate-status {{ font-size:11px; color:#52606d; }}
.candidate-members {{ display:flex; flex-wrap:wrap; gap:5px; margin:6px 0; }}
.face-chip {{ display:inline-flex; align-items:center; border:1px solid #bcc7d0; background:#eef3f6; border-radius:3px; overflow:hidden; }}
.face-chip button {{ height:24px; border:0; border-radius:0; padding:0 6px; background:transparent; font-family:Consolas, monospace; font-size:11px; }}
.face-chip button.remove-ref {{ color:#a4262c; border-left:1px solid #cbd4db; font-family:inherit; font-weight:700; }}
.candidate-add {{ margin-left:auto; }}
#selected-faces {{ font-family:Consolas, monospace; font-size:12px; min-height:24px; overflow-wrap:anywhere; }}
.manual-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
.manual-grid input {{ width:100%; }}
.wide {{ width:100%; margin-top:7px; }}
@media (max-width:900px) {{ main {{ grid-template-columns:1fr; grid-template-rows:60vh auto; height:auto; }} aside {{ border-left:0; border-top:1px solid #cfd6dd; }} .workspace {{ height:60vh; }} }}
</style>
</head>
<body>
<header><h1>{model_name}</h1><div class="badge">CadQuery face review</div></header>
<main>
  <section class="workspace">
    <div class="toolbar">
      <button data-view="iso">ISO</button><button data-view="+x">+X</button><button data-view="-x">-X</button>
      <button data-view="+y">+Y</button><button data-view="-y">-Y</button><button data-view="+z">+Z</button><button data-view="-z">-Z</button>
      <select id="feature-filter"><option value="all">All features</option><option value="unassigned">Unassigned</option></select>
      <label class="control"><input id="labels-toggle" type="checkbox"> Face IDs</label>
      <label class="control">Opacity <input id="opacity" type="range" min="0.1" max="1" step="0.05" value="0.88"></label>
    </div>
    <div id="plot"></div>
  </section>
  <aside>
    <section class="panel"><h2>Selected face</h2><div id="face-details" class="empty">Click a face.</div></section>
    <section class="panel"><h2>Selected faces</h2><div id="selected-faces" class="empty">None</div><button id="clear-selection" class="wide">Clear selection</button></section>
    <section class="panel"><h2>Candidates</h2><div id="candidate-list"></div></section>
    <section class="panel"><h2>Manual group</h2>
      <div class="manual-grid"><input id="manual-id" type="text" placeholder="group id"><input id="manual-type" type="text" placeholder="feature type"></div>
      <button id="add-group" class="wide">Add selected faces</button>
      <div id="manual-groups" class="empty">None</div>
    </section>
    <section class="panel"><button id="export-yaml" class="primary wide">Download reviewed labels YAML</button></section>
  </aside>
</main>
<script>
const APP={payload};
const plot=document.getElementById("plot");
const faceTraceCount=APP.faceTraceCount;
const labelsTraceIndex=faceTraceCount;
const traceIndex={{}};
const baseColors={{}};
APP.traces.slice(0,faceTraceCount).forEach((t,i)=>{{traceIndex[t.name]=i;baseColors[t.name]=t.color;}});
const selected=new Set();
const candidateState={{}};
const candidateTypes={{}};
const candidateRefs={{}};
APP.draft.features.forEach(f=>{{candidateTypes[f.id]=f.type;candidateRefs[f.id]=new Set(f.geometry_refs);}});
const manualGroups={{}};
const layout={{
  margin:{{l:0,r:0,t:0,b:0}}, paper_bgcolor:"#fff", scene:{{
    aspectmode:"data", bgcolor:"#fff",
    xaxis:{{title:"X",showbackground:false}},yaxis:{{title:"Y",showbackground:false}},zaxis:{{title:"Z",showbackground:false}},
    camera:{{eye:{{x:1.45,y:1.45,z:1.15}}}}
  }}, showlegend:false
}};
Plotly.newPlot(plot,APP.traces,layout,{{responsive:true,displaylogo:false,scrollZoom:true}});
const filter=document.getElementById("feature-filter");
APP.featureTypes.forEach(v=>{{const o=document.createElement("option");o.value=v;o.textContent=v;filter.appendChild(o);}});
function esc(v){{return String(v??"").replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));}}
function rawFace(ref){{const v=String(ref);return v.startsWith("face:")?v.slice(5):v;}}
function showFace(id){{
  const f=APP.faces[id]; if(!f)return;
  const memberships=(f.feature_memberships||[]).map(x=>`${{x.type}} (${{x.confidence}})`).join(", ")||"Unassigned";
  const suggestions=(f.classifier_suggestions||[]).map(x=>`${{x.type}} (${{Number(x.probability).toFixed(3)}})`).join(", ")||"None";
  document.getElementById("face-details").innerHTML=`<dl class="kv">
    <dt>Face</dt><dd><b>${{esc(id)}}</b></dd><dt>Surface</dt><dd>${{esc(f.surface_type)}}</dd>
    <dt>Area</dt><dd>${{Number(f.area||0).toPrecision(7)}}</dd><dt>Centroid</dt><dd>${{esc(JSON.stringify(f.centroid))}}</dd>
    <dt>Radius</dt><dd>${{esc(f.radius)}}</dd><dt>Adjacent</dt><dd>${{esc((f.adjacent_faces||[]).join(", "))}}</dd>
    <dt>Features</dt><dd>${{esc(memberships)}}</dd><dt>Classifier</dt><dd>${{esc(suggestions)}}</dd></dl>`;
}}
function updateSelection(){{
  const box=document.getElementById("selected-faces");box.textContent=selected.size?[...selected].sort().join(", "):"None";box.className=selected.size?"":"empty";
}}
plot.on("plotly_click",ev=>{{const id=ev.points?.[0]?.data?.name;if(!id||id==="__labels__")return;
  if(selected.has(id))selected.delete(id);else selected.add(id);
  showFace(id);updateSelection();
}});
document.getElementById("clear-selection").onclick=()=>{{selected.clear();updateSelection();}};
const cameras={{
 iso:{{x:1.45,y:1.45,z:1.15}},"+x":{{x:2.2,y:0,z:0}},"-x":{{x:-2.2,y:0,z:0}},
 "+y":{{x:0,y:2.2,z:0}},"-y":{{x:0,y:-2.2,z:0}},"+z":{{x:0,y:0,z:2.2}},"-z":{{x:0,y:0,z:-2.2}}
}};
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>Plotly.relayout(plot,{{"scene.camera.eye":cameras[b.dataset.view]}}));
function applyFilter(){{
  const value=filter.value;
  const visible=Object.keys(traceIndex).map(id=>value==="all"||value==="unassigned"&&APP.faces[id].unassigned||(APP.faces[id].feature_memberships||[]).some(x=>x.type===value));
  Plotly.restyle(plot,{{visible}},Array.from({{length:faceTraceCount}},(_,i)=>i));
}}
filter.onchange=applyFilter;
document.getElementById("labels-toggle").onchange=e=>Plotly.restyle(plot,{{visible:e.target.checked}},[labelsTraceIndex]);
document.getElementById("opacity").oninput=e=>Plotly.restyle(plot,{{opacity:Number(e.target.value)}},Array.from({{length:faceTraceCount}},(_,i)=>i));
function renderCandidates(){{
 const root=document.getElementById("candidate-list");root.innerHTML="";
 APP.draft.features.forEach(f=>{{
  const refs=[...candidateRefs[f.id]].sort();
  const chips=refs.length?refs.map(ref=>`<span class="face-chip"><button data-show-ref="${{esc(ref)}}">${{esc(ref)}}</button><button class="remove-ref" data-remove-candidate="${{esc(f.id)}}" data-remove-ref="${{esc(ref)}}" title="Remove">×</button></span>`).join(""):`<span class="empty">No geometry refs</span>`;
  const d=document.createElement("div");d.className="candidate";
  d.innerHTML=`<div class="candidate-head"><b>${{esc(f.id)}}</b><span>${{f.confidence}}</span></div>
    <input type="text" value="${{esc(candidateTypes[f.id])}}" data-type="${{esc(f.id)}}">
    <div class="candidate-members">${{chips}}</div>
    <div class="candidate-actions"><button data-confirm="${{esc(f.id)}}">Confirm</button><button class="danger" data-reject="${{esc(f.id)}}">Reject</button><button class="candidate-add" data-add-selected="${{esc(f.id)}}">Add selected faces</button><span class="candidate-status" id="status-${{esc(f.id)}}">${{esc(candidateState[f.id]||"")}}</span></div>`;
  root.appendChild(d);
 }});
 root.querySelectorAll("[data-type]").forEach(input=>input.oninput=()=>{{candidateTypes[input.dataset.type]=input.value;}});
 root.querySelectorAll("[data-confirm]").forEach(b=>b.onclick=()=>setCandidate(b.dataset.confirm,"confirmed"));
 root.querySelectorAll("[data-reject]").forEach(b=>b.onclick=()=>setCandidate(b.dataset.reject,"rejected"));
 root.querySelectorAll("[data-add-selected]").forEach(b=>b.onclick=()=>addSelectedToCandidate(b.dataset.addSelected));
 root.querySelectorAll("[data-remove-ref]").forEach(b=>b.onclick=()=>removeCandidateRef(b.dataset.removeCandidate,b.dataset.removeRef));
 root.querySelectorAll("[data-show-ref]").forEach(b=>b.onclick=()=>showCandidateRef(b.dataset.showRef));
}}
function setCandidate(id,status){{candidateState[id]=status;document.getElementById(`status-${{id}}`).textContent=status;}}
function addSelectedToCandidate(id){{
 if(!selected.size)return;
 selected.forEach(faceId=>candidateRefs[id].add(`face:${{faceId}}`));
 candidateState[id]="confirmed";
 renderCandidates();
}}
function removeCandidateRef(id,ref){{
 candidateRefs[id].delete(ref);
 candidateState[id]="confirmed";
 renderCandidates();
}}
function showCandidateRef(ref){{
 const faceId=rawFace(ref);
 if(!APP.faces[faceId])return;
 selected.add(faceId);showFace(faceId);updateSelection();
}}
renderCandidates();
document.getElementById("add-group").onclick=()=>{{
 const id=document.getElementById("manual-id").value.trim(),type=document.getElementById("manual-type").value.trim();
 if(!id||!type||!selected.size)return;
 manualGroups[id]={{type,geometry_refs:[...selected].sort().map(x=>`face:${{x}}`)}};
 document.getElementById("manual-groups").textContent=Object.keys(manualGroups).join(", ");document.getElementById("manual-groups").className="";
}};
function q(v){{return JSON.stringify(String(v));}}
function yaml(){{
 const lines=["confirmed_features:"];
 let confirmed=0;
 APP.draft.features.forEach(f=>{{if(candidateState[f.id]!=="confirmed")return;confirmed++;const type=candidateTypes[f.id];const refs=[...candidateRefs[f.id]].sort();lines.push(`  ${{f.id}}:`,`    type: ${{q(type)}}`,`    geometry_refs: [${{refs.map(q).join(", ")}}]`);if(f.default_boundary_role)lines.push(`    default_boundary_role: ${{q(f.default_boundary_role)}}`);}});
 if(!confirmed)lines.push("  {{}}");
 lines.push("rejected_candidates:");
 const rejected=Object.keys(candidateState).filter(x=>candidateState[x]==="rejected");rejected.length?rejected.forEach(x=>lines.push(`  - ${{q(x)}}`)):lines.push("  []");
 lines.push("manual_groups:");
 const groups=Object.entries(manualGroups);groups.length?groups.forEach(([id,g])=>lines.push(`  ${{id}}:`,`    type: ${{q(g.type)}}`,`    geometry_refs: [${{g.geometry_refs.map(q).join(", ")}}]`)):lines.push("  {{}}");
 return lines.join("\\n")+"\\n";
}}
document.getElementById("export-yaml").onclick=()=>{{const blob=new Blob([yaml()],{{type:"text/yaml"}});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="reviewed_feature_labels.yaml";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
</script>
</body></html>"""
