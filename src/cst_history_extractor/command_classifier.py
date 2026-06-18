"""Classify parsed CST history macro commands into recipe-oriented groups."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence, Tuple

from .macro_parser import HistoryItem


@dataclass(frozen=True)
class ClassifiedCommand:
    """A parsed history item with a conservative classification."""

    index: int
    raw_name: str
    category: str
    subcategory: str
    confidence: float
    evidence: List[str]
    raw_macro_excerpt: str
    macro_body: str

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "index": self.index,
            "raw_name": self.raw_name,
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "raw_macro_excerpt": self.raw_macro_excerpt,
        }


@dataclass(frozen=True)
class _Rule:
    category: str
    subcategory: str
    confidence: float
    patterns: Tuple[str, ...]
    evidence_label: str


_RULES: Tuple[_Rule, ...] = (
    _Rule("project", "units", 0.95, (r"\bwith\s+units\b", r"\.setunit\b", r"\bunits\."), "sets project units"),
    _Rule("project", "background", 0.9, (r"\bbackground\b", r"\bwith\s+background\b"), "sets background material"),
    _Rule("project", "coordinate_system", 0.82, (r"\bwcs\b", r"\bcoordinate\s*system\b", r"\bpick\.setcoordinate"), "uses coordinate system"),
    _Rule(
        "project",
        "parameters",
        0.9,
        (
            r"\bstoreparameter\b",
            r"\bstoreparameterwithdescription\b",
            r"\bwith\s+parameter\b",
            r"\bparameter\.",
        ),
        "sets project parameter",
    ),
    _Rule(
        "geometry",
        "import",
        0.9,
        (
            r"\bwith\s+(step|sat|iges|stl|acis)\b",
            r"\.filename\s+\"[^\"]+\.(step|stp|sat|sab|iges|igs|stl|dxf|brep|x_t|x_b)\"",
            r"^\s*\.import\b",
        ),
        "imports geometry",
    ),
    _Rule("geometry", "primitive_creation", 0.88, (r"\bwith\s+(brick|cylinder|sphere|cone|torus|extrude|loft|wire|curve)\b", r"\.create\b"), "creates primitive geometry"),
    _Rule("geometry", "boolean", 0.86, (r"\bboolean\b", r"\bsolid\.(add|subtract|intersect|insert)\b", r"\bwith\s+trimcurves\b"), "uses boolean geometry operation"),
    _Rule("geometry", "transform", 0.82, (r"\bwith\s+transform\b", r"\btransform\.", r"\b(translate|rotate|mirror)\b"), "uses transform"),
    _Rule("geometry", "fillet_chamfer", 0.85, (r"\bfillet\b", r"\bchamfer\b", r"\bsolid\.blendedge\b"), "uses fillet or chamfer"),
    _Rule(
        "geometry",
        "component_solid_management",
        0.82,
        (
            r"\bcomponent\.",
            r"\bsolid\.(rename|delete|merge|split|changecomponent)\b",
            r"\bcurve\.deletecurveitem\b",
            r"\.component\s+\"",
        ),
        "manages components, solids, or curves",
    ),
    _Rule("geometry", "face_or_pick_operation", 0.8, (r"\bpick\.", r"\bface\b", r"\bselectedface\b"), "uses face or pick operation"),
    _Rule("material", "material_definition", 0.95, (r"\bwith\s+material\b", r"\bmaterial\.", r"\.setmaterialunit\b"), "defines material"),
    _Rule("material", "material_assignment", 0.82, (r"\bchangematerial\b", r"\bassignmaterial\b", r"\bsolid\.changematerial\b"), "assigns material"),
    _Rule("boundary", "symmetry_boundary", 0.9, (r"\bsymmetry\b", r"\bwith\s+symmetry"), "sets symmetry boundary"),
    _Rule("boundary", "global_boundary", 0.9, (r"\bwith\s+boundary\b", r"\bboundary\."), "sets global boundary"),
    _Rule("boundary", "electric_boundary", 0.78, (r"\belectric\b", r"\bet\b", r"\bpec\b"), "mentions electric boundary"),
    _Rule("boundary", "magnetic_boundary", 0.78, (r"\bmagnetic\b", r"\bpmc\b"), "mentions magnetic boundary"),
    _Rule("boundary", "open_boundary", 0.78, (r"\bopen\b", r"\bexpanded open\b", r"\bpml\b"), "mentions open boundary"),
    _Rule("boundary", "periodic_boundary", 0.78, (r"\bperiodic\b",), "mentions periodic boundary"),
    _Rule("ports", "waveguide_port", 0.9, (r"\bwith\s+waveguideport\b", r"\bwaveguideport\b", r"\bwith\s+port\b"), "defines waveguide or generic CST port"),
    _Rule("ports", "discrete_port", 0.95, (r"\bwith\s+discrete(port|faceport)\b", r"\bdiscreteport\b", r"\bdiscretefaceport\b"), "defines discrete port"),
    _Rule("ports", "coaxial_port", 0.9, (r"\bwith\s+coaxialport\b", r"\bcoaxialport\b"), "defines coaxial port"),
    _Rule("ports", "multipin_port", 0.9, (r"\bmultipin\b", r"\bmultipinport\b"), "defines multipin port"),
    _Rule("ports", "port_mode_setting", 0.82, (r"\bportmode\b", r"\bmodes?\s*\"", r"\bmodecount\b"), "sets port mode"),
    _Rule("mesh", "adaptive_mesh", 0.92, (r"\badaptive\s*mesh\b", r"\badaptivemesh\b", r"\bmeshadapt"), "sets adaptive mesh"),
    _Rule("mesh", "curved_mesh", 0.86, (r"\bcurved\s*mesh\b", r"\bcurvature\b"), "sets curved mesh"),
    _Rule("mesh", "mesh_refinement", 0.84, (r"\brefinement\b", r"\bmeshrefinement\b", r"\blocalmesh\b"), "sets mesh refinement"),
    _Rule("mesh", "local_mesh", 0.82, (r"\blocal\s*mesh\b", r"\bwith\s+meshlocal\b"), "sets local mesh"),
    _Rule("mesh", "global_mesh", 0.82, (r"\bwith\s+mesh\b", r"\bmesh\.", r"\bmeshsettings\b"), "sets global mesh"),
    _Rule("solver", "eigenmode_solver", 0.95, (r"\beigenmodesolver\b", r"\beigenmode\b", r"change\s*solver\s*type\s*\".*eigen"), "sets eigenmode solver"),
    _Rule("solver", "frequency_domain_solver", 0.95, (r"\bfrequencydomainsolver\b", r"\bfrequency\s*domain\b", r"change\s*solver\s*type\s*\".*frequency"), "sets frequency-domain solver"),
    _Rule("solver", "time_domain_solver", 0.9, (r"\btimedomainsolver\b", r"\btime\s*domain\b", r"change\s*solver\s*type\s*\".*time"), "sets time-domain solver"),
    _Rule("solver", "wakefield_solver", 0.9, (r"\bwakefield\b", r"\bwakesolver\b"), "sets wakefield solver"),
    _Rule("solver", "frequency_range", 0.86, (r"\bsolver\.frequencyrange\b", r"\bfrequencyrange\b"), "sets frequency range"),
    _Rule("solver", "number_of_modes", 0.84, (r"\.modes\b", r"\bnumber\s*of\s*modes\b", r"\bnmodes\b"), "sets number of modes"),
    _Rule("solver", "solver_accuracy", 0.82, (r"\.accuracy\b", r"\bsolveraccuracy\b", r"\baccuracy\s*\""), "sets solver accuracy"),
    _Rule("solver", "convergence_settings", 0.82, (r"\bconvergence\b", r"\bresidual\b", r"\bmaxpasses\b"), "sets convergence"),
    _Rule("monitors", "e_field_monitor", 0.9, (r"\be[-_ ]?field\b", r"\belectric\s*field\b", r"\bfieldtype\s*\"e"), "defines E-field monitor"),
    _Rule("monitors", "h_field_monitor", 0.9, (r"\bh[-_ ]?field\b", r"\bmagnetic\s*field\b", r"\bfieldtype\s*\"h"), "defines H-field monitor"),
    _Rule("monitors", "farfield_monitor", 0.9, (r"\bfarfield\b",), "defines farfield monitor"),
    _Rule("monitors", "field_on_axis", 0.84, (r"\bon\s*axis\b", r"\baxis\s*field\b", r"\bez_on_axis\b"), "defines on-axis field"),
    _Rule("monitors", "probe", 0.84, (r"\bprobe\b",), "defines probe"),
    _Rule("monitors", "template_based_postprocessing", 0.82, (r"\btemplatebasedpostprocessing\b", r"\bpostprocessing\s*template\b"), "uses template post-processing"),
    _Rule("results", "result_template", 0.9, (r"\bresulttemplate\b", r"\btemplate\s*based\b", r"\bwith\s+resultstorage\b", r"\bresultstorage\b"), "defines result template or storage"),
    _Rule("results", "export_1d", 0.86, (r"\bexport1d\b", r"\b1d\s*results\b"), "exports 1D result"),
    _Rule("results", "export_2d", 0.86, (r"\bexport2d\b", r"\b2d\s*results\b"), "exports 2D result"),
    _Rule("results", "export_3d", 0.86, (r"\bexport3d\b", r"\b3d\s*field\b", r"\bfieldexport\b"), "exports 3D result"),
    _Rule("results", "q_factor", 0.82, (r"\bq[\s_-]*factor\b", r"\bqvalue\b"), "extracts Q factor"),
    _Rule("results", "r_over_q", 0.82, (r"\br\s*/\s*q\b", r"\broverq\b", r"\br_over_q\b"), "extracts R over Q"),
    _Rule("results", "shunt_impedance", 0.82, (r"\bshunt\s*impedance\b",), "extracts shunt impedance"),
    _Rule("results", "peak_field", 0.82, (r"\bpeak\s*field\b", r"\bepk\b", r"\bhpk\b"), "extracts peak field"),
    _Rule("results", "mode_frequency", 0.82, (r"\bmode\s*frequency\b", r"\bresonant\s*frequency\b"), "extracts mode frequency"),
)


def classify_history_items(items: Sequence[HistoryItem]) -> List[ClassifiedCommand]:
    """Classify parsed history items using deterministic keyword evidence."""
    return [classify_history_item(item) for item in items]


def classify_history_item(item: HistoryItem) -> ClassifiedCommand:
    """Classify a single history item."""
    haystack = f"{item.raw_name}\n{item.macro_body}".lower()
    matches: List[Tuple[_Rule, List[str]]] = []
    for rule in _RULES:
        evidence = []
        for pattern in rule.patterns:
            if re.search(pattern, haystack, re.IGNORECASE):
                evidence.append(rule.evidence_label)
                evidence.append(f"matched /{pattern}/")
                break
        if evidence:
            matches.append((rule, evidence))

    if not matches:
        return ClassifiedCommand(
            index=item.index,
            raw_name=item.raw_name,
            category="unknown",
            subcategory="unclassified",
            confidence=0.0,
            evidence=[],
            raw_macro_excerpt=item.raw_macro_excerpt,
            macro_body=item.macro_body,
        )

    rule, evidence = _choose_best_rule(matches, haystack)
    return ClassifiedCommand(
        index=item.index,
        raw_name=item.raw_name,
        category=rule.category,
        subcategory=rule.subcategory,
        confidence=rule.confidence,
        evidence=_unique(evidence),
        raw_macro_excerpt=item.raw_macro_excerpt,
        macro_body=item.macro_body,
    )


def build_command_inventory(
    project_id: str,
    source: str,
    classified_commands: Sequence[ClassifiedCommand],
) -> dict:
    """Build the ``command_inventory.json`` payload."""
    command_dicts = [command.to_dict() for command in classified_commands]
    unknown = [
        command.to_dict()
        for command in classified_commands
        if command.category == "unknown"
    ]
    return {
        "project_id": project_id,
        "source": source,
        "history_item_count": len(classified_commands),
        "classified_commands": command_dicts,
        "unknown_commands": unknown,
    }


def _choose_best_rule(
    matches: Sequence[Tuple[_Rule, List[str]]],
    haystack: str,
) -> Tuple[_Rule, List[str]]:
    # Specific object-level matches beat generic matches with equal confidence.
    def score(entry: Tuple[_Rule, List[str]]) -> Tuple[float, int]:
        rule = entry[0]
        object_specific = 1 if "with" in " ".join(rule.patterns).lower() else 0
        return (rule.confidence, object_specific)

    best_rule, evidence = max(matches, key=score)

    # If a CST object command also contains generic words like PEC or Mode, keep
    # the object command.  This is why Brick + Material does not become a
    # material-definition command unless the object is actually Material.
    if re.search(r"\bwith\s+material\b", haystack, re.IGNORECASE):
        for rule, rule_evidence in matches:
            if rule.subcategory == "material_definition":
                return rule, rule_evidence
    if re.search(r"\bwith\s+(brick|cylinder|sphere|cone|torus|extrude|loft)\b", haystack, re.IGNORECASE):
        for rule, rule_evidence in matches:
            if rule.subcategory == "primitive_creation":
                return rule, rule_evidence
    return best_rule, evidence


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
