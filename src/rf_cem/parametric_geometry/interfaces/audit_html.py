"""Self-contained HTML audit view for parametric RF vacuum geometry."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path


def write_parametric_audit_html(
    path: Path,
    *,
    parametric_geometry: dict,
    geometry_validation: dict,
    reverse_fit_report: dict,
    source_evidence: dict,
    cst_payload: dict,
    resolved_prior: dict,
) -> None:
    """Write a helper2-style offline audit HTML for the generated STEP package."""
    try:
        from plotly.offline import get_plotlyjs

        plotly_js = get_plotlyjs()
    except ModuleNotFoundError:
        plotly_js = "window.__RFCEM_PLOTLY_MISSING__ = true;"

    payload = _build_payload(
        parametric_geometry=parametric_geometry,
        geometry_validation=geometry_validation,
        reverse_fit_report=reverse_fit_report,
        source_evidence=source_evidence,
        cst_payload=cst_payload,
        resolved_prior=resolved_prior,
    )
    html = _build_html(plotly_js, payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _build_payload(
    *,
    parametric_geometry: dict,
    geometry_validation: dict,
    reverse_fit_report: dict,
    source_evidence: dict,
    cst_payload: dict,
    resolved_prior: dict,
) -> dict:
    kernel_report = source_evidence.get("kernel_report", {})
    mesh = kernel_report.get("generated_mesh", {})
    profile = parametric_geometry.get("profile", {})
    mesh_trace = {
        "type": "mesh3d",
        "name": "generated_vacuum.step",
        "x": [point[0] for point in mesh.get("vertices", [])],
        "y": [point[1] for point in mesh.get("vertices", [])],
        "z": [point[2] for point in mesh.get("vertices", [])],
        "i": [tri[0] for tri in mesh.get("triangles", [])],
        "j": [tri[1] for tri in mesh.get("triangles", [])],
        "k": [tri[2] for tri in mesh.get("triangles", [])],
        "color": "#6aa6c8",
        "opacity": 0.86,
        "flatshading": False,
        "hovertemplate": "generated_vacuum.step<extra></extra>",
        "showscale": False,
    }
    profile_points = _profile_points_from_segments(profile.get("segments", []))
    profile_trace = {
        "type": "scatter3d",
        "name": "r-z profile controls",
        "mode": "lines+markers",
        "x": [radius for _, radius in profile_points],
        "y": [0.0 for _ in profile_points],
        "z": [z for z, _ in profile_points],
        "line": {"color": "#d14f3f", "width": 6},
        "marker": {"color": "#d14f3f", "size": 4},
        "hovertemplate": "z=%{z:.3f}<br>r=%{x:.3f}<extra></extra>",
    }
    return {
        "schema_version": "parametric_geometry_audit_html.v0",
        "model_name": "generated_vacuum.step",
        "plot": {
            "traces": [mesh_trace, profile_trace],
            "mesh_vertex_count": len(mesh.get("vertices", [])),
            "mesh_triangle_count": len(mesh.get("triangles", [])),
        },
        "parametric_geometry": parametric_geometry,
        "geometry_validation": geometry_validation,
        "reverse_fit_report": reverse_fit_report,
        "source_evidence": source_evidence,
        "cst_payload": cst_payload,
        "mapping_rules": _mapping_rules(resolved_prior),
        "interface_contract": _interface_contract(parametric_geometry, cst_payload),
        "resolved_prior": resolved_prior,
        "semantic_risks": _semantic_risks(),
    }


def _build_html(plotly_js: str, payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    title = escape(str(payload.get("model_name", "parametric geometry audit")))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} - RF-CEM Parametric Audit</title>
<style>
body {{ margin:0; font-family: Arial, sans-serif; background:#f5f7fa; color:#1f2933; }}
.shell {{ display:grid; grid-template-columns:minmax(520px, 58vw) 1fr; min-height:100vh; }}
#plot {{ height:100vh; background:#fff; }}
.panel {{ padding:18px 20px 28px; overflow:auto; max-height:100vh; box-sizing:border-box; }}
h1 {{ margin:0 0 10px; font-size:22px; }}
h2 {{ margin:22px 0 8px; font-size:16px; border-bottom:1px solid #d7dde5; padding-bottom:5px; }}
.status {{ display:inline-block; padding:3px 8px; border-radius:4px; font-weight:700; }}
.ok {{ background:#d7f2df; color:#155724; }}
.warn {{ background:#fff3cd; color:#7a5900; }}
table {{ width:100%; border-collapse:collapse; margin:8px 0 14px; font-size:12px; background:#fff; }}
th, td {{ border:1px solid #d7dde5; padding:6px 7px; text-align:left; vertical-align:top; }}
th {{ background:#edf1f5; }}
code {{ font-family: Consolas, monospace; font-size:12px; }}
.small {{ color:#52616f; font-size:12px; }}
.mono {{ font-family: Consolas, monospace; white-space:pre-wrap; }}
</style>
<script>{plotly_js}</script>
</head>
<body>
<div class="shell">
  <div id="plot"></div>
  <main class="panel">
    <h1>RF-CEM Parametric Geometry Audit</h1>
    <div id="summary"></div>
    <h2>Defined Parameters</h2>
    <div id="parameters"></div>
    <h2>Derived Curve Parameters</h2>
    <div id="derived-parameters"></div>
    <h2>Consumed Features</h2>
    <div id="features"></div>
    <h2>Feature Mapping Rules</h2>
    <div id="rules"></div>
    <h2>Feature Consumption Flow</h2>
    <div id="flow"></div>
    <h2>Semantic Risk Register</h2>
    <div id="risks"></div>
    <h2>Translator Impact</h2>
    <div id="translator-impact"></div>
    <h2>Profile Segments</h2>
    <div id="segments"></div>
    <h2>Validation</h2>
    <div id="validation"></div>
    <h2>Interface Compatibility</h2>
    <div id="interfaces"></div>
    <h2>Raw Payload</h2>
    <details><summary>Show JSON</summary><pre class="mono" id="raw"></pre></details>
  </main>
</div>
<script>
const payload = {encoded};
function esc(v) {{ return String(v ?? "").replace(/[&<>"]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}}[c])); }}
function table(headers, rows) {{
  return '<table><thead><tr>' + headers.map(h => `<th>${{esc(h)}}</th>`).join('') + '</tr></thead><tbody>' +
    rows.map(r => '<tr>' + r.map(c => `<td>${{esc(c)}}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
}}
function list(values) {{ return Array.isArray(values) ? values.join(', ') : values; }}
if (window.__RFCEM_PLOTLY_MISSING__ || typeof Plotly === 'undefined') {{
  document.getElementById('plot').innerHTML =
    '<div style="padding:24px;font-family:Arial,sans-serif;color:#7a5900">' +
    '<h2>3D preview unavailable</h2>' +
    '<p>Install plotly or the project review extra to enable the embedded audit viewer.</p>' +
    '<code>python -m pip install -e ".[review]"</code>' +
    '</div>';
}} else {{
  Plotly.newPlot('plot', payload.plot.traces, {{
    margin: {{l:0,r:0,t:24,b:0}},
    scene: {{aspectmode:'data', xaxis:{{title:'x / r (mm)'}}, yaxis:{{title:'y (mm)'}}, zaxis:{{title:'z (mm)'}}}},
    legend: {{orientation:'h'}}
  }}, {{responsive:true}});
}}
const pg = payload.parametric_geometry;
const gv = payload.geometry_validation;
document.getElementById('summary').innerHTML =
  `<span class="status ${{gv.pass ? 'ok' : 'warn'}}">${{gv.pass ? 'PASS' : 'CHECK'}}</span>` +
  `<p class="small">Mesh vertices: ${{payload.plot.mesh_vertex_count}}, triangles: ${{payload.plot.mesh_triangle_count}}</p>` +
  table(['Field','Value'], [
    ['schema', pg.schema_version],
    ['model_type', pg.model_type],
    ['axis', pg.axis?.name],
    ['generated_step', pg.export_metadata?.generated_step],
    ['truth source', 'parametric_geometry.v0.json; STEP is an export artifact']
  ]);
document.getElementById('parameters').innerHTML = table(
  ['Parameter','Value','Unit','Prior rule','Extraction','Feature refs','Affects STEP','Affects Translator','Confidence'],
  Object.entries(pg.named_parameters || {{}}).map(([k,v]) => [k, v.value, v.unit, v.prior_rule_id, v.provenance, list(v.feature_refs), v.affects_generated_step, v.affects_translator, v.confidence])
);
document.getElementById('derived-parameters').innerHTML = table(
  ['Parameter','Value','Unit','Segment','Role','Feature refs','Optimization candidate'],
  Object.entries(pg.derived_parameters || {{}}).map(([k,v]) => [k, v.value, v.unit, v.segment_id, v.parameter_role, list(v.feature_refs), v.optimization_candidate])
);
document.getElementById('features').innerHTML = table(
  ['Feature','Type','Geometry refs','Parameters','Segments','Provenance'],
  (pg.feature_bindings || []).map(f => [f.feature_id, f.feature_type, list(f.geometry_refs), list(f.parameter_ids), list(f.segment_ids), f.provenance])
);
document.getElementById('rules').innerHTML = table(
  ['Rule','Feature type','Description','Consumes','Defines','Segments','Extraction','Fallback','Affects STEP','Affects Translator'],
  payload.mapping_rules.map(r => [r.rule_id, r.feature_type, r.human_description, r.consumes, list(r.defines), list(r.segment_ids), r.extraction, r.fallback_policy, r.affects_generated_step, r.affects_translator])
);
document.getElementById('flow').innerHTML = table(
  ['Step','Artifact','Purpose'],
  [
    ['1', 'reviewed_feature_labels.yaml', 'Human-reviewed answer to what each face/solid means.'],
    ['2', 'resolved_expert_prior.v0.yaml/json', 'Expert rules for how features become parameters and profile segments.'],
    ['3', 'parametric_geometry.v0.json', 'Run truth source containing chosen parameters, segments, feature bindings, and evidence.'],
    ['4', 'generated_vacuum.step', 'Export artifact generated from the parametric profile.'],
    ['5', 'cst_payload.json + CSTTranslator actions', 'Translator imports the generated STEP and reuses verified CST setup templates.']
  ]
);
document.getElementById('risks').innerHTML = table(
  ['Risk','Control'],
  payload.semantic_risks.map(r => [r.risk, r.control])
);
document.getElementById('translator-impact').innerHTML = table(
  ['Question','Answer'],
  [
    ['Does prior change CST face-level boundary assignment?', 'No. v0 only changes generated STEP; global boundary template is still reused.'],
    ['Which prior fields can affect Translator?', 'Generated STEP path/content and RFVacuumVolume role in cst_payload.'],
    ['Where is the active Translator input?', payload.cst_payload?.geometry?.step_path]
  ]
);
document.getElementById('segments').innerHTML = table(
    ['Segment','Kind','Curve','Start (z,r)','End (z,r)','Feature refs','Face refs','Fallback / policy','Continuity'],
  (pg.profile?.segments || []).map(s => [s.id, s.kind, s.curve?.type, `(${{s.start.z}}, ${{s.start.r}})`, `(${{s.end.z}}, ${{s.end.r}})`, list(s.feature_refs), list(s.face_refs), s.fallback_reason || s.fit_metrics?.deviation_policy || '', `${{s.continuity_start}} -> ${{s.continuity_end}}`])
);
document.getElementById('validation').innerHTML =
  table(['Metric','Value'], [
    ['BRep valid', gv.generated?.brep_valid],
    ['bbox pass', gv.comparison?.bbox_pass],
    ['volume relative error', gv.comparison?.volume_relative_error],
    ['surface area relative error', gv.comparison?.surface_area_relative_error],
    ['curve generation mode', gv.source_kernel_curve_generation_mode],
    ['curve generation fallbacks', list(gv.source_kernel_curve_generation_fallbacks)],
    ['warnings', list(gv.warnings)],
    ['blocking errors', list(gv.blocking_errors)]
  ]);
document.getElementById('interfaces').innerHTML = table(
  ['Contract','Value'],
  Object.entries(payload.interface_contract).map(([k,v]) => [k, Array.isArray(v) ? v.join(', ') : (typeof v === 'object' ? JSON.stringify(v) : v)])
);
document.getElementById('raw').textContent = JSON.stringify(payload, null, 2);
</script>
</body>
</html>
"""


def _profile_points_from_segments(segments: list[dict]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for segment in segments:
        sampled_points = segment.get("sampled_points", [])
        if sampled_points:
            sampled = [(float(point.get("z", 0.0)), float(point.get("r", 0.0))) for point in sampled_points]
            if points and sampled:
                sampled = sampled[1:]
            points.extend(sampled)
            continue
        start = segment.get("start", {})
        end = segment.get("end", {})
        if not points:
            points.append((float(start.get("z", 0.0)), float(start.get("r", 0.0))))
        points.append((float(end.get("z", 0.0)), float(end.get("r", 0.0))))
    return points


def _mapping_rules(resolved_prior: dict) -> list[dict]:
    rules = []
    for feature_type, rule in sorted(resolved_prior.get("feature_mappings", {}).items()):
        rules.append(
            {
                "feature_type": feature_type,
                "rule_id": rule.get("rule_id", feature_type),
                "human_description": rule.get("human_description", ""),
                "consumes": rule.get("consumes", ""),
                "defines": rule.get("defines", []),
                "segment_ids": rule.get("segment_ids", []),
                "extraction": rule.get("extraction", ""),
                "fallback_policy": rule.get("fallback_policy", ""),
                "affects_generated_step": rule.get("affects_generated_step", False),
                "affects_translator": rule.get("affects_translator", False),
            }
        )
    return rules


def _semantic_risks() -> list[dict]:
    return [
        {
            "risk": "Natural-language expert knowledge may be translated into the wrong prior field.",
            "control": "Resolved prior is written beside every run and shown in this audit page.",
        },
        {
            "risk": "Feature labels and prior mappings may disagree.",
            "control": "Required mappings fail clearly; low-confidence or unused fields are reported.",
        },
        {
            "risk": "A prior may produce geometry that looks plausible but is physically wrong.",
            "control": "BRep/geometry validation and later CST eigenmode checks remain mandatory.",
        },
        {
            "risk": "Prior changes may unexpectedly affect CST setup.",
            "control": "v0 prior only affects generated STEP; CST boundary/solver templates are unchanged.",
        },
    ]


def _interface_contract(parametric_geometry: dict, cst_payload: dict) -> dict:
    return {
        "schema_version": "parametric_geometry_audit_html.v0",
        "truth_source": "metadata/parametric_geometry.v0.json",
        "generated_step_role": cst_payload.get("geometry", {}).get("role"),
        "generated_step_units": cst_payload.get("geometry", {}).get("units"),
        "translator_step_path": cst_payload.get("geometry", {}).get("step_path"),
        "required_parametric_fields": [
            "schema_version",
            "model_type",
            "units",
            "axis",
            "named_parameters",
            "derived_parameters",
            "profile.segments",
            "feature_bindings",
            "constraints",
            "source_evidence",
            "export_metadata",
        ],
        "backward_compatibility": "Additive fields are allowed; existing v0 consumers must ignore unknown fields.",
        "forward_compatibility": "Future non-axisymmetric generators should keep feature_bindings and export_metadata stable.",
    }
