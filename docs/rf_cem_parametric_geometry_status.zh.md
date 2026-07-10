# RF-CEM 参数化几何项目状态

最后更新：2026-07-07

## 当前架构位置

当前 RF-CEM 参数化几何工作位于“人工审核后的几何语义”和 CSTTranslator 之间：

```text
reviewed_feature_labels.yaml
  -> expert_prior.v0.yaml
  -> parametric_geometry.v0.json
  -> generated_vacuum.step
  -> CSTTranslator eigenmode setup
```

这仍然符合最初的 RF-CEM 架构方向：

- Feature graph / assembly graph：记录每个 solid/face 在几何语义上“是什么”。
- Expert prior / grammar：记录领域知识如何把 Feature 解释为参数和建模规则。
- Parametric geometry：记录本轮运行的参数化几何真值源。
- Solver interface：导入生成几何，并复用已验证的 CST 历史模板设置。

## 已完成能力

- 500 MHz no-CST 参数化几何 pipeline。
- CadQuery/OCP worker 子进程隔离，用于 STEP 生成和审计 mesh payload。
- `generated_vacuum.step` 导出。
- `parametric_geometry.v0.json` 参数化几何真值源。
- 几何验证报告。
- 使用 generated STEP 的 CSTTranslator payload。
- 可渲染 generated STEP、参数、Feature、规则、风险和 Translator 影响的审计 HTML。
- 外部 expert prior 接口，支持 built-in、case、CLI override 的优先级。
- 每次 run 旁路输出 resolved prior，便于审计和复现。
- 500 MHz baseline 的真实曲线 nose / blend 恢复：
  - `iris_torus_exact` 使用 torus face 证据生成真实 arc，并采用专家确认的 NoseCone 规则：10 mm 半圆、反向 10 mm 四分之一圆，再相切回 conductive wall。
  - `expanded_smooth_nose` 使用局部 smooth NURBS-like nose 控制，同时保留 blend/equator 证据。
- 通过 `expert_prior.v0.yaml` 配置曲线选择：
  - `grammar.variant_policy.enabled_variants`
  - `grammar.variant_policy.default_selected_variant`
  - `grammar.variant_policy.curve_selection`
  - `grammar.variant_policy.curve_parameters`
- `free_equator_smooth` 已成为当前工作基线。它把传统等半径 equator 圆柱段替换为可配置的局部 equator crown 曲线。
- 已生成用于人工观察的 equator 手动扰动分支：
  - `manual_equator_inset_3mm`
  - `manual_equator_bulge_3mm`
  - `manual_equator_wide_soft`
- 曲线控制参数已经显式提升到 `parametric_geometry.v0.json` 的 `derived_parameters`：
  - arc center / radius / angle
  - NURBS control points
  - 归一共享控制量，例如 `shared_equator_crown_delta_r_mm`
- `variant_index.json` 和 `audit/variant_comparison.html` 用于汇总所有 variant 和当前 selected 工作基线。
- RF-CEM 500 MHz no-CST 参数扫描 adapter 已落在 `workflows/rf_cem_500mhz_parametric_opt`。
- baseline 差异验证的严重级别已经可通过 `validation.baseline_difference_policy` 配置；当前优化探索阶段将 bbox/volume/surface 差异视为 warning，而不是 hard blocker。
- CST 后处理 / 结果模板证据已经确认不能只依赖 `ModelHistory.json`；正确注册路径为 `Model/3D/Model.rpp + Model/3D/*.r0d`，详见 `docs/rf_cem_cst_postprocessing_template_notes.md`。
- live-CST 已验证后处理模板注册、自动求解后模板执行、以及 `ResultReader` 读取三项 0D 指标：
  - `Tables\0D Results\Frequency (Mode 1)`
  - `Tables\0D Results\R over Q (Mode 1)`
  - `Tables\0D Results\Q-Factor (Perturbation) (Mode 1)`
- 当前成功的 500 MHz eigenmode 自动路径使用 `Tetrahedral` mesh / `Solver_HF_TET_E`，不是 HEX。
- CSTTranslator 已把材料/边界语义拆成两层：
  - 全局背景材料设置为历史树验证过的 `Copper (annealed)`，导电率 `5.8e7 S/m`，用于表示真空模型外侧的腔壁导体。
  - STEP import 后执行 `Solid.ChangeMaterial "...", "Vacuum"`，把导入的 RF vacuum body 显式设置为 `Vacuum` 材料。
- live-CST 已验证 copper background + vacuum solid + Tetrahedral eigenmode 可自动得到：
  - Frequency: `505.583944055 MHz`
  - R over Q: `428.086330643 Ohm`
  - Q-Factor (Perturbation): `45867.1264209`

## 当前工作基线

当前工作基线是：

```text
runs/parametric_geometry_500mhz/variants/free_equator_smooth
```

`runs/parametric_geometry_500mhz/geometry`、`metadata`、`translator`、`audit` 顶层兼容包会从 `free_equator_smooth` 复制而来。

当前 variant 角色：

| Variant | 角色 | 验证含义 |
|---|---|---|
| `iris_torus_exact` | 证据精确参考。 | 应尽量复现原始 500 MHz STEP 的 nose/blend 几何。 |
| `expanded_smooth_nose` | 光滑 nose 参考。 | 保留更光滑的 nose，同时 equator 仍为传统形式。 |
| `free_equator_smooth` | 当前工作基线。 | 使用 smooth nose 和可配置 equator crown。 |
| `manual_equator_inset_3mm` | 人工视觉扰动。 | 展示 equator 中部内收效果；探索模式下 baseline 差异只作为 warning。 |
| `manual_equator_bulge_3mm` | 人工视觉扰动。 | 展示 equator 中部外鼓效果；探索模式下 baseline 差异只作为 warning。 |
| `manual_equator_wide_soft` | 人工视觉扰动。 | 展示更宽缓的 equator 内收效果；探索模式下 baseline 差异只作为 warning。 |

## 尚未完成能力

- smooth variant 的 CAD 原生 NURBS 导出仍未完全稳定；必要时会显式 fallback 到 dense sampled profile，并在 validation 中记录。
- Equator free curve 的物理约束和优化范围仍是临时值。
- 面向 `derived_parameters` 的 live-CST 参数扫描。
- multi-cell grammar。
- 非轴对称几何生成。
- face-level CST boundary assignment。
- HOM、coupler、wakefield、cooling、thermal、structural、multipacting、optimizer。
- 面向优化器的批量 live-CST evaluator：目前已有单点 live-CST 诊断，尚未进入小规模参数扫描。
- `free_equator_smooth` 和手动扰动分支的系统性 live-CST 对比验收。

## 语义风险登记

| 风险 | 控制方式 |
|---|---|
| 专家自然语言被错误转换为 YAML 字段。 | 使用 `docs/rf_cem_expert_prior_schema.md`、schema validation、resolved prior 输出和审计 HTML。 |
| Feature label 与 expert prior mapping 冲突。 | required mapping 明确失败；记录 provenance 与 confidence。 |
| prior 配置过于自由，导致不可解释行为。 | v0 只支持声明过的 extraction method、curve selection 和 segment template；不支持 eval 或任意公式执行。 |
| 几何看起来合理，但物理上不正确。 | 继续要求 geometry validation 和 live-CST eigenmode validation。 |
| prior 意外改变 CST 设置。 | v0 prior 只通过 generated STEP 和 metadata 产生影响；CST boundary / solver 仍由历史模板驱动。 |
| baseline 差异阈值意外阻碍新腔型探索。 | `validation.baseline_difference_policy` 已将 bbox/volume/surface 差异设为 warning；BRep/profile 拓扑仍是 hard gate。 |
| dense sampled fallback 可能掩盖数学 NURBS 意图与导出 STEP 表达之间的差异。 | 在 validation 和 audit 中记录 `source_kernel_curve_generation_mode`、fallback 和 derived curve controls。 |
| CST 后处理模板不会稳定出现在 `ModelHistory.json`。 | 使用解包 CST 项目证据：`Model/3D/*.r0d`、`Model/PC_integration.json`、`Result/Postprocessing.log` 和显式 result tree path。 |
| 只复制 `.r0d` 会导致 CST UI/模板框架看不到后处理模板。 | 必须同时写入 `Model/3D/Model.rpp` 注册表。 |
| `QFactor.Calculate` 可能报误导性的 `HEX mesh is invalid`。 | 先检查模板注册、导入体材料、旧结果状态和 solver 是否完整运行；当前成功路径仍是 Tetrahedral，不自动切 HEX。 |
| 真空 STEP 被导入后，若背景仍是默认空气/未设导体，结果会偏离物理意图。 | 全局背景材料必须作为边界/材料策略的一部分设置为导体；当前默认使用历史树验证的 `Copper (annealed)`。 |

## 需要人工确认的事项

- generated-vs-baseline eigenmode comparison 的最终频率容差。
- nose / blend 局部几何误差容差。
- equator free curve 的允许范围和物理约束。
- 哪些手动 equator 扰动分支应作为后续优化种子。
- mode shape comparison 应采用哪些可接受证据：截图、结果文本、field export，还是数值指标。
- 后续 prior 是否必须支持不完全左右对称的 segment template。
- 探索式几何除 BRep/profile 合法性之外的最终 hard-gate 策略。
- 优化器正式使用的 Frequency/R over Q/Q-factor 权重、约束和失败样本处理策略。
- 是否需要把 solver mesh policy 外置到 expert prior / workflow config；当前默认仍沿用历史模板的 Tetrahedral eigenmode。
- 背景材料后续是否应可配置为 `Copper (annealed)`、OFHC copper 或 PEC；当前首版默认 `Copper (annealed)`，因为已有历史树和 live-CST 验证。

## 维护规则

当以下内容发生变化时，需要同步更新本文档：

- `expert_prior.v0.yaml` schema 形状。
- Feature-to-parameter mapping 语义。
- curve selection policy 或 curve parameter 语义。
- `derived_parameters` contract。
- generated design package contract。
- CSTTranslator consumption contract。
- scope boundary，尤其是引入 face-level boundary 或新增 solver 时。

## 2026-07-09 优化工作流更新

RF-CEM 500 MHz 已增加独立的参数化优化包
`workflows/rf_cem_500mhz_parametric_opt`。当前预设 `exploratory_12d`
围绕 `free_equator_smooth` 基线控制 equator crown、左右 shoulder、左右
nose NURBS 内部控制点和左右 blend arc 半径。

候选参数不会直接写入 CST `StoreParameter`。每次评估先生成
`expert_prior_override.v0.yaml`，再重新生成
`parametric_geometry.v0.json`、`generated_vacuum.step` 和可审计的
CSTTranslator payload。

已完成的 no-CST 扫描会生成基线加六个探索候选；
`POSTPROCESS_TEMPLATE_MISSING` 或 `SOLVER_NOT_RUN` 只表示尚未执行 live-CST，
不表示几何生成失败。

工作站上的第一轮 seeded SAO campaign 已完成 60 次评估，60/60 为
`SUCCESS`，证明 Tetrahedral eigenmode 求解和 0D result-tree 回读链路稳定。
目前需要继续完成两项工作：

- 审计 `candidate_039` 与 `candidate_046` 的完整几何和 CST 工程；
- 将目标函数改为 490–510 MHz 窗口内弱频率惩罚，主要提高 R/Q 和
  `R = (R/Q) * Q`，Q 仅使用 soft floor。

当前 CLI 只能从 quick-scan candidate 取 seed，尚未实现从上一轮
`live_records.jsonl` 读取任意 record 作为新 seed。详细运行状态和建议见
`docs/rf_cem_workstation_agent_handoff_2026-07-09.md`。
