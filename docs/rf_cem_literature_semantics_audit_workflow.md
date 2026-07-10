# RF-CEM Literature Semantics Audit Workflow

Last updated: 2026-07-10

## 目标与边界

本流程把论文证据转换成可审计的 RF-CEM 语义候选，但不会把自然语言、论文图片或单篇论文数值直接转换为生产几何、STEP 或 CST API 调用。

```text
arXiv discovery candidates
  -> 人工选择并固定论文版本
  -> 固定版本 PDF + SHA-256 source manifest
  -> 选页图片证据
  -> literature_semantics.v0
  -> integrity-bound expert_prior.draft.v0
  -> 单篇/语料库 HTML 审计
  -> 人工逐 patch 审核
  -> 可选 merge-prior
  -> 既有 no-CST 几何验证
```

默认安全策略：

- arXiv 搜索结果只代表“发现候选”，不自动标记“经典”、权威或适用于当前设计。
- 下载必须使用显式版本号，例如 `1810.02990v3`；PDF 和 manifest 采用 immutable/no-clobber 写入。
- 多腔、未知分类或当前 grammar 未覆盖的论文只能进入 audit-only metadata。
- 所有 draft patch 初始状态均为 `pending`；无自动接受路径。
- `merge-prior` 默认要求全部 patch 已审核，并同时校验原语义包、base prior 和 draft 的 SHA-256 绑定。
- 全流程可在 no-CST 环境运行；只有用户另行授权时才进入 live-CST 验证。

## CLI

以下示例从仓库根目录执行；本地验证应使用 `.venv\Scripts\python.exe`。

```powershell
# 1. 发现候选；query 使用 arXiv API 查询语法
.venv\Scripts\python.exe -m rf_cem.literature_semantics arxiv-search `
  --query 'all:"radio frequency cavity" AND all:optimization' `
  --max-results 10 `
  --out analysis_outputs\literature\search_candidates.json

# 2. 人工确认后，按显式版本定版下载
.venv\Scripts\python.exe -m rf_cem.literature_semantics arxiv-fetch `
  --id 1810.02990v3 `
  --out-dir analysis_outputs\literature\papers\sls2

# 3. 用 Poppler 只渲染选定的一页或多页；页码从 1 开始
.venv\Scripts\python.exe -m rf_cem.literature_semantics render-evidence `
  --pdf analysis_outputs\literature\papers\sls2\source.pdf `
  --pages 4 8 9 11 `
  --out-dir analysis_outputs\literature\papers\sls2\figures `
  --pdftoppm <path-to-pdftoppm.exe>

# 4. 校验语义包并生成 integrity-bound draft
.venv\Scripts\python.exe -m rf_cem.literature_semantics validate `
  --package <dir-or-json>
.venv\Scripts\python.exe -m rf_cem.literature_semantics draft-prior `
  --package <literature_semantics.v0.json> `
  --base-prior <expert_prior.v0.yaml> `
  --out <expert_prior.draft.v0.yaml>

# 5. 单篇审计，或把多篇论文汇总成一份自包含 HTML
.venv\Scripts\python.exe -m rf_cem.literature_semantics audit `
  --package <literature_semantics.v0.json> `
  --draft-prior <expert_prior.draft.v0.yaml> `
  --out <paper-audit.html>
.venv\Scripts\python.exe -m rf_cem.literature_semantics corpus-audit `
  --bundle-root <corpus-directory> `
  --manifest <corpus_manifest.json> `
  --out <corpus-audit.html>

# 6. 只有完成逐项人工审核后才合并；--package 是完整性校验所必需
.venv\Scripts\python.exe -m rf_cem.literature_semantics merge-prior `
  --package <literature_semantics.v0.json> `
  --base-prior <expert_prior.v0.yaml> `
  --draft-prior <reviewed-expert_prior.draft.v0.yaml> `
  --out <expert_prior.reviewed.v0.yaml>
```

`--allow-unreviewed` 只用于显式的开发诊断；它跳过未审核 patch，但仍会执行完整性、target/value、ontology 和最终 expert-prior schema 校验。

## Corpus manifest

总审计使用 `literature_corpus_audit.v0`：

```json
{
  "schema_version": "literature_corpus_audit.v0",
  "title": "RF-CEM literature pilot",
  "generated_at": "2026-07-10T00:00:00+08:00",
  "papers": [
    {
      "id": "paper_id",
      "arxiv_id": "1810.02990v3",
      "version": 3,
      "title": "Paper title",
      "authors": ["Author"],
      "source_url": "https://arxiv.org/abs/1810.02990",
      "pdf_sha256": "...",
      "source_manifest": "papers/paper_id/source_manifest.json",
      "paper_summary": "papers/paper_id/paper_summary.v0.json",
      "literature_semantics": "papers/paper_id/literature_semantics.v0.json",
      "draft_prior": "papers/paper_id/expert_prior.draft.v0.yaml",
      "evidence_images": [
        {
          "path": "papers/paper_id/figures/page_0004.png",
          "page": 4,
          "figure_id": "Figure 1",
          "caption": "Human-reviewed caption summary",
          "evidence_refs": ["evidence_id"],
          "sha256": "..."
        }
      ]
    }
  ],
  "cross_paper_findings": [],
  "warnings": []
}
```

HTML 生成器会 fail-closed 阻止 bundle-root 路径越界，并检查结构化文件大小、固定版本 PDF 实体的 header/大小/SHA-256、source-manifest/corpus 元数据一致性、draft-semantic/immutable hash 绑定、PNG/JPEG magic、声明的图片 SHA-256、语义验证结果和 evidence-ref 完整性。HTML 内嵌图片，可离线交付。

## 人工审核清单

- 确认 `superconducting`、`normal_conducting` 与论文材料/损耗模型一致；不要用“elliptical”推断 SRF。
- 确认 cavity family、cell count 和 geometry scope；多腔文献不得直接驱动单腔 grammar。
- 检查每条语义的 `source_refs`、`confidence`、`scope`、`applicability` 和 `human_review_status`。
- 单篇数值只能作为 soft candidate；图片单独不能支持 hard numeric rule。
- 单位必须显式：频率 MHz、长度 mm、角度 degree、导电率 S/m、场比和归一化目标注明定义。
- HOM、coupler、wakefield、thermal、structural、multipacting、cooling、tuner 仅可进入 audit warning。
- 不把 beam-pipe radius 自动等同于 iris radius，不混用不同论文的 shunt-impedance 定义。
- 不按目标频率自动缩放文献几何；任何缩放只可作为待验证假设。

## 冲突与优先级

```text
reviewed_feature_labels
  > baseline_geometry
  > human-accepted multi-source text/hybrid literature
  > single-source text literature
  > image-only literature
```

有冲突时保留来源并显式报告，不删除已有 reviewed feature mapping，不覆盖 baseline-derived geometry fact。NC/SRF、single/multi-cell 或不同 objective 定义应拆成不同 applicability 分支。

## 验收

- 非法包给出准确字段路径并阻塞 draft。
- draft 的 executable patch 与 metadata patch 均为 `pending`。
- 当前仅允许唯一匹配且存在相应 curve-region evidence 的 `srf_elliptical`、`nc_elliptical` 或 `nc_reentrant` 单腔分支生成 executable candidate；其余 audit-only。
- 篡改 target、value、语义包、base prior 或 immutable draft 会阻塞合并。
- 生成的总 HTML 能离线打开，文本已转义，证据图和 provenance 可追溯。
- shared-core/runtime/persistence 发生改动时运行分支完整 no-CST suite；live CST 结果另行记录。
