# RF-CEM Literature Semantics Schema v0

Last updated: 2026-07-07

## 目标

`literature_semantics.v0.json` 是“文献语义 -> 专家先验”的上传包接口。它只保存可审计的论文文本、图注、图片和人工整理证据，不直接驱动几何生成。

允许链路：

```text
uploaded literature evidence
  -> literature_semantics.v0.json
  -> expert_prior.draft.v0.yaml
  -> human review
  -> reviewed expert_prior.v0.yaml override
```

禁止链路：

```text
natural language / figure pixels -> profile points / STEP / CST API
```

## literature_semantics.v0.json

必需顶层字段：

```json
{
  "schema_version": "literature_semantics.v0",
  "request_context": {},
  "evidence_sources": [],
  "text_evidence": [],
  "image_evidence": [],
  "classification": {},
  "named_features": [],
  "shape_motifs": [],
  "curve_priors": [],
  "parameter_ranges": [],
  "optimization_objectives": [],
  "physical_constraints": []
}
```

`request_context`：

- `design_intent`
- `frequency_target_mhz`
- `operating_regime`: `superconducting`, `normal_conducting`, or `unknown`
- `geometry_scope`: MVP 只支持 `axisymmetric_single_cell_rf_vacuum`
- `exclude`: must include out-of-scope domains such as HOM, coupler, thermal, structural, multipacting when relevant

`evidence_sources` 记录论文、图片或人工文本来源。至少需要 `id` 和 `source_type`，建议包含 `title`, `year`, `venue`, `license`, `version_status`, `file_ref`。

`text_evidence` / `image_evidence` 记录 provenance：

- text: `id`, `paper_id`, `page`, `section`, `short_excerpt`, `excerpt_hash`
- image: `id`, `paper_id`, `page`, `figure_id`, `caption`, `bbox`, `crop_ref`
- `image_evidence` 只能支持 motif-level semantic evidence，不能单独支持 hard numeric rule

每条自动学习语义规则必须包含：

- `source_refs`: non-empty list
- `confidence`: 0.0 to 1.0
- `scope`: where the rule applies
- `applicability`: operating regime / family / geometry scope
- `human_review_status`: `pending`, `accepted`, `accepted_as_soft_only`, `rejected`, or `needs_more_evidence`

## 可抽取语义

MVP 白名单位于 `src/rf_cem/literature_semantics/ontology_v0.yaml`。

可抽取对象：

- 腔型类别：elliptical, reentrant, nose_cone, qwr, hwr, spoke, unknown
- 频段与目标频率：MHz
- operating regime：normal conducting / superconducting
- named features：nose, iris, equator, blend, beam pipe
- aliases：Req, Rir, wall angle, alpha, equator straight segment d
- curve priors：arc, ellipse, local_spline, nurbs, cylinder, supported RF-CEM curve-selection names
- optimization objectives：peak field ratios, R/Q, shunt impedance, transit-time factor, frequency maintenance
- physical constraints：axisymmetry, single cell, smoothness, soft/hard family exclusions

HOM、coupler、wakefield、thermal、structural、multipacting、cooling 等只进入 audit warning，不进入 executable prior。

## expert_prior.draft.v0.yaml

draft prior 是合并前的 patch 层，不是生产 prior。

必需结构：

```yaml
schema_version: expert_prior.draft.v0
base_prior_ref: expert_prior.v0.yaml
literature_semantics_ref: literature_semantics.v0.json
merge_policy:
  precedence:
    - reviewed_feature_labels
    - baseline_geometry
    - human_accepted_multi_source_text_or_hybrid_literature
    - single_source_text_literature
    - image_only_literature
candidate_shape_priors: []
grammar: {}
derived_parameter_candidates: []
source_evidence:
  required_for_all_nonbaseline_fields: true
review:
  merge_blocked: true
  patch_items: []
```

`review.patch_items` 是唯一会被 `merge-prior` 消费的机器合并接口。每项必须有：

- `target_path`
- `value`
- `source_refs`
- `confidence`
- `human_review_status`

允许的 executable target 仅限：

- `grammar.variant_policy.default_selected_variant`
- `grammar.variant_policy.enabled_variants`
- `grammar.variant_policy.curve_selection.*`

其他文献语义只能进入 additive metadata `literature_semantics`。

## 合并规则

`merge-prior --require-reviewed` 只合并 `accepted` 或 `accepted_as_soft_only`。未审核、拒绝、证据不足项会阻塞合并。

规则：

- SRF elliptical intent: prefer `free_equator_smooth` / smooth equator; discourage nose/reentrant default.
- NC intent: may suggest nose/reentrant candidates through current `iris_torus_exact` or smooth nose branches.
- image-only numeric range: hard rule is invalid.
- single-source numeric range: always soft.
- unsupported curve, parameter, or objective: audit-only.
- frequency scaling: `seed_scaling_hint` only, never validated rule.
