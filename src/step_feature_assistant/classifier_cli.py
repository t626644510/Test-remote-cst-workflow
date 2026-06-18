"""Dataset export and experimental classifier training CLI."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Sequence

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MultiLabelBinarizer, OneHotEncoder, StandardScaler

from .ml_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, face_feature_row


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="step_feature_assistant.classifier_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    export_parser = sub.add_parser("export")
    export_parser.add_argument("--review-roots", type=Path, nargs="+", required=True)
    export_parser.add_argument("--output-dir", type=Path, required=True)
    train_parser = sub.add_parser("train")
    train_parser.add_argument("--dataset-dir", type=Path, required=True)
    train_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        export_training_dataset(args.review_roots, args.output_dir)
    else:
        train_baseline_classifier(args.dataset_dir, args.output_dir)
    return 0


def export_training_dataset(review_roots: Iterable[Path], output_dir: Path) -> dict:
    """Export labeled face/group datasets from reviewed project directories."""
    project_dirs = _reviewed_project_dirs(review_roots)
    face_rows = []
    group_rows = []
    for project_dir in project_dirs:
        manifest = _read_json(project_dir / "geometry_manifest.json")
        draft = _read_json(project_dir / "feature_graph_draft.json")
        resolved = _read_json(project_dir / "resolved_feature_graph.json")
        project_id = project_dir.name
        labels_by_face, labels_by_group = _resolved_labels(resolved)
        rejected_faces = _rejected_faces(draft, resolved)
        face_map = {face["face_id"]: face for face in manifest.get("faces", [])}
        included_faces = set(labels_by_face) | rejected_faces
        for face_id in sorted(included_faces):
            if face_id not in face_map:
                continue
            row = face_feature_row(manifest, face_map[face_id], project_id)
            row["labels"] = "|".join(sorted(labels_by_face.get(face_id, set())))
            face_rows.append(row)
        for group in draft.get("face_groups", []):
            group_id = str(group.get("group_id"))
            labels = labels_by_group.get(group_id)
            if not labels:
                continue
            group_rows.append(
                {
                    "project_id": project_id,
                    "group_id": group_id,
                    "member_count": len(group.get("member_faces", [])),
                    "group_type_candidate": group.get("group_type_candidate"),
                    "labels": "|".join(sorted(labels)),
                }
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "face_training_dataset.csv", face_rows)
    _write_csv(output_dir / "group_training_dataset.csv", group_rows)
    metadata = {
        "schema_version": "0.1",
        "project_count": len(project_dirs),
        "face_row_count": len(face_rows),
        "group_row_count": len(group_rows),
        "project_ids": [path.name for path in project_dirs],
        "split_policy": "group by project_id; never split faces from one STEP across train and validation",
    }
    _write_json(output_dir / "dataset_metadata.json", metadata)
    return metadata


def train_baseline_classifier(dataset_dir: Path, output_dir: Path) -> dict:
    """Train the non-production multi-label logistic-regression baseline."""
    dataset_path = dataset_dir / "face_training_dataset.csv"
    frame = pd.read_csv(dataset_path).fillna("")
    if frame.empty:
        raise ValueError("face_training_dataset.csv contains no rows")
    label_sets = [set(filter(None, str(value).split("|"))) for value in frame["labels"]]
    if not any(label_sets):
        raise ValueError("Training dataset contains no positive labels")
    mlb = MultiLabelBinarizer()
    target = mlb.fit_transform(label_sets)
    numeric_pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical_pipeline = Pipeline(
        [("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]
    )
    transformer = ColumnTransformer(
        [("numeric", numeric_pipeline, NUMERIC_FEATURES), ("categorical", categorical_pipeline, CATEGORICAL_FEATURES)]
    )
    pipeline = Pipeline(
        [
            ("features", transformer),
            ("classifier", OneVsRestClassifier(LogisticRegression(class_weight="balanced", max_iter=1000))),
        ]
    )
    project_count = int(frame["project_id"].nunique())
    evaluation = "not reported: fewer than two reviewed projects"
    if project_count >= 2:
        predictions = target.copy()
        predictions[:] = 0
        splitter = GroupKFold(n_splits=min(5, project_count))
        for train_indices, test_indices in splitter.split(frame, target, groups=frame["project_id"]):
            fold_model = clone(pipeline)
            fold_model.fit(frame.iloc[train_indices], target[train_indices])
            predictions[test_indices] = fold_model.predict(frame.iloc[test_indices])
        evaluation = f"grouped-project micro-F1={f1_score(target, predictions, average='micro', zero_division=0):.4f}"
    pipeline.fit(frame, target)
    model_version = "experimental-logreg-0.1"
    bundle = {
        "pipeline": pipeline,
        "classes": list(mlb.classes_),
        "model_version": model_version,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output_dir / "classifier.joblib")
    metadata = {
        "schema_version": "0.1",
        "model_version": model_version,
        "experimental": True,
        "production_decision_authority": False,
        "project_count": project_count,
        "row_count": len(frame),
        "classes": list(mlb.classes_),
        "evaluation": evaluation,
    }
    _write_json(output_dir / "model_metadata.json", metadata)
    _write_json(output_dir / "feature_coefficients.json", _feature_coefficients(pipeline, list(mlb.classes_)))
    (output_dir / "training_report.md").write_text(_training_report(metadata), encoding="utf-8")
    return metadata


def _reviewed_project_dirs(roots: Iterable[Path]) -> list[Path]:
    projects = set()
    for root in roots:
        if (root / "resolved_feature_graph.json").exists():
            projects.add(root.resolve())
        if root.exists():
            for resolved in root.rglob("resolved_feature_graph.json"):
                projects.add(resolved.parent.resolve())
    return sorted(projects)


def _resolved_labels(resolved: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    faces: dict[str, set[str]] = {}
    groups: dict[str, set[str]] = {}
    for feature in resolved.get("features", []):
        if feature.get("status") not in {"confirmed", "modified"}:
            continue
        label = str(feature.get("type"))
        for ref in feature.get("geometry_refs", []):
            text = str(ref)
            if text.startswith("face:"):
                faces.setdefault(text.split(":", 1)[1], set()).add(label)
            elif text.startswith("face_group:"):
                groups.setdefault(text.split(":", 1)[1], set()).add(label)
    return faces, groups


def _rejected_faces(draft: dict, resolved: dict) -> set[str]:
    rejected_ids = {feature["id"] for feature in resolved.get("features", []) if feature.get("status") == "rejected"}
    result = set()
    for feature in draft.get("features", []):
        if feature.get("id") not in rejected_ids:
            continue
        for ref in feature.get("geometry_refs", []):
            face_id = str(ref).split(":", 1)[-1]
            if face_id.startswith("F"):
                result.add(face_id)
    return result


def _training_report(metadata: dict) -> str:
    return (
        "# Experimental Feature Classifier\n\n"
        f"- Model: `{metadata['model_version']}`\n"
        f"- Reviewed projects: {metadata['project_count']}\n"
        f"- Face rows: {metadata['row_count']}\n"
        f"- Classes: {metadata['classes']}\n"
        f"- Evaluation: {metadata['evaluation']}\n\n"
        "This model provides suggestions only and cannot modify the rule-based feature graph.\n"
    )


def _feature_coefficients(pipeline: Pipeline, classes: list[str]) -> dict:
    names = list(pipeline.named_steps["features"].get_feature_names_out())
    estimators = pipeline.named_steps["classifier"].estimators_
    result = {}
    for label, estimator in zip(classes, estimators):
        if not hasattr(estimator, "coef_"):
            result[label] = []
            continue
        coefficients = estimator.coef_[0]
        ranked = sorted(zip(names, coefficients), key=lambda item: abs(float(item[1])), reverse=True)[:12]
        result[label] = [{"feature": name, "coefficient": float(value)} for name, value in ranked]
    return {"schema_version": "0.1", "classes": result}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
