# RF-CEM Literature Semantics Schema v0

Last updated: 2026-07-10

## 目的

`literature_semantics.v0` 是“论文证据 → 专家先验草案”的可审计接口。它保存来源、文本/图片 provenance、分类、适用范围和人工审核状态；它不直接生成轮廓点、STEP、CST 命令或优化任务。

允许链路：

```text
pinned source + reviewed evidence
  -> literature_semantics.v0
  -> expert_prior.draft.v0
  -> human review
  -> reviewed expert_prior override
```

禁止链路：

```text
natural language / figure pixels / search rank
  -X-> executable geometry / STEP / CST API
```

## 顶层结构

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

`request_context` 必须声明：

- `design_intent`
- `frequency_target_mhz`，单位 MHz
- `operating_regime`: `superconducting`、`normal_conducting` 或 `unknown`
- `geometry_scope`: v0 为 `axisymmetric_single_cell_rf_vacuum`
- `exclude`: 与本次可执行范围隔离的领域

`classification` 使用 ontology 中的 `operating_regime`、`cavity_family`、`cell_count`、`beta_class` 和 `geometry_scope`。分类不全、冲突、多腔或没有唯一分支匹配时，包仍可审计，但只能生成 metadata patch。

## Evidence provenance

`evidence_sources` 至少包含唯一 `id` 和 `source_type`，建议同时保存 title、authors、year、venue、arXiv version、license、file ref 和 SHA-256。

`text_evidence` 建议字段：

- `id`, `paper_id`, `page`, `section`
- 人工转述的 `evidence_summary`
- 如需短引文，保存 `short_excerpt` 和 `excerpt_hash`

`image_evidence` 建议字段：

- `id`, `paper_id`, `page`, `figure_id`
- `caption`, `bbox`, `crop_ref`

ID 必须唯一；子 evidence 的 `paper_id` 必须引用已存在的 source。图片只能支持 motif-level evidence，不能独立支持 hard numeric rule。

## 语义条目

以下分组由 `src/rf_cem/literature_semantics/ontology_v0.yaml` 约束：

- `named_features`
- `shape_motifs`
- `curve_priors`
- `parameter_ranges`
- `optimization_objectives`
- `physical_constraints`

每项必须包含：

- 非空 `source_refs`
- `confidence`，范围 0.0–1.0
- 非空 `scope`
- `applicability` mapping，至少与 package classification 一致
- `human_review_status`: `pending`, `accepted`, `accepted_as_soft_only`, `rejected`, `needs_more_evidence`

v0 ontology 支持 elliptical、reentrant、nose_cone、qwr、hwr、spoke 等分类；支持的术语不等于都具有可执行 grammar。分支除分类匹配外，还必须存在与 branch curve region 一致的 `curve_priors` evidence。当前 executable branch 仅为：

| Branch | Operating regime | Family | Cell count | Scope |
|---|---|---|---|---|
| `srf_elliptical` | superconducting | elliptical | single | axisymmetric single-cell RF vacuum |
| `nc_elliptical` | normal_conducting | elliptical | single | axisymmetric single-cell RF vacuum |
| `nc_reentrant` | normal_conducting | reentrant/nose_cone | single | axisymmetric single-cell RF vacuum |

HOM、coupler、wakefield、thermal、structural、multipacting、cooling、tuner 等越界语义只进入 warning/metadata。

## expert_prior.draft.v0

draft 是 integrity-bound patch 层，不是生产 prior。关键结构：

```yaml
schema_version: expert_prior.draft.v0
base_prior_ref: expert_prior.v0.yaml
literature_semantics_ref: literature_semantics.v0.json
merge_policy: {}
validation_issues: []
candidate_shape_priors: []
grammar: {}
derived_parameter_candidates: []
source_evidence: {}
review:
  requires_patch_review: true
  patch_items: []
integrity:
  algorithm: sha256
  semantic_package_sha256: sha256:...
  base_prior_sha256: sha256:...
  immutable_draft_sha256: sha256:...
```

每个 `review.patch_items` 包含唯一 `id`、唯一 `target_path`、`value`、`source_refs`、`confidence`、`semantic_paths`、`review_basis` 和 `human_review_status`。生成时所有状态固定为 `pending`。

允许的 executable target 仅限：

- `grammar.variant_policy.default_selected_variant`
- `grammar.variant_policy.enabled_variants`
- `grammar.variant_policy.curve_selection.<region>.<variant>`

其他信息只能写入 additive `literature_semantics` metadata。合并后采用 `literature_semantics_collection.v0.records` 保留多篇论文记录，并用 `semantic_package_sha256` 去重；后合并的论文不得覆盖先前 provenance。target/value 必须与 base prior 和 ontology 中已验证实现一致；文献不能替换一个 curve implementation 字符串或注入自然语言可执行字段。

## 合并规则

`merge-prior` 必须同时传入原语义包、base prior 和 reviewed draft。默认只合并 `accepted` 或 `accepted_as_soft_only`：

- `accepted` executable patch 可进入受支持的 expert-prior 字段。
- `accepted_as_soft_only` executable patch 只保存在 additive metadata，不改变运行语法。
- `pending`、`rejected`、`needs_more_evidence` 在默认模式下阻塞合并。
- 允许人工只编辑每个 patch 顶层的 review 状态、备注、reviewer 和 reviewed_at；`review_basis`、candidate、metadata 或其他嵌套内容变化会使 immutable hash 失效。
- 合并后再次执行 variant-policy 和 expert-prior schema 校验。

单篇数值范围始终视为 soft candidate；频率缩放永远不是已验证规则。
