# RF-CEM CST 后处理模板与结果读取调研记录

Last updated: 2026-07-07

## 背景

RF-CEM 500 MHz 参数优化需要在 CST eigenmode 求解后自动获得：

- `frequency_mhz`
- `r_over_q_ohm`
- `q_factor`

现有 `ModelHistory.json` 通常不会记录 GUI 后处理模板，因此不能只依赖 helper1/history tree。当前策略是从 CST 解包项目文件本身抽取 evidence，再形成可审计的 result metric 配置。2026-07-07 的 live-CST 验证已确认：`Model/3D/Model.rpp` 是 GUI Template Based Post-Processing 的注册表，`.r0d` 是每个模板实例的内容文件。

## 已确认线索

来自 `D:\ModelData` 的只读抽样：

| Source | Evidence | Use |
|---|---|---|
| `D:\ModelData\bare\Model\3D\Frequency (Mode 1).r0d` | `Action=Frequency`, `TemplateType=0D`, `ModeNumbers=1`, `Post Processing Template: 3D Eigenvalue result` | 0D mode frequency 模板证据 |
| `D:\ModelData\bare\Model\3D\Q-Factor (Perturbation) (Mode 1).r0d` | `Action=Q-Factor (Perturbation)`, `TemplateType=0D`, `ModeNumbers=1` | 0D Q-factor 模板证据 |
| `D:\ModelData\bare\Model\3D\R over Q (Mode 1).r0d` | `Action=R over Q`, `TemplateType=0D`, `ModeNumbers=1` | 0D R/Q 模板证据 |
| `D:\ModelData\bare\Model\PC_integration.json` | `outputVariables` lists `3D\Frequency (Mode 1)`, `3D\Q-Factor (Perturbation) (Mode 1)`, `3D\R over Q (Mode 1)` | result metric 名称来源 |
| `D:\ModelData\bare.bak1\bare\Result\Postprocessing.log` | logs `Template based post-processing` and evaluated Frequency/Q/R over Q with units `MHz` | postprocess execution evidence |
| `D:\ModelData\result_navigator.csv` | contains `Tables\0D Results\Frequency (Mode 1)` | result tree path format evidence |
| `D:\ModelData\AllParaVer1_E2\Model\3D\Results%1D Results%Measure Resonances and Q-values from frq-data.mcs` | CST macro for resonance/Q extraction from 1D frequency data | secondary macro reference |

## Important Observations

- `.r0d/.r1d` are CST internal result/template artifacts with binary prefixes plus readable VBA/template text. Treat them as read-only evidence, not files to hand-edit.
- 0D eigenmode metrics appear under a stable naming convention:
  - project-local artifact: `Model\3D\Frequency (Mode 1).r0d`
  - result-tree path: `Tables\0D Results\Frequency (Mode 1)`
- `PC_integration.json` can provide metric names even when history is silent.
- `Postprocessing.log` confirms what CST actually evaluated and records project units.
- Existing repository code already has result readers:
  - `src/cst_optimization/core/results.py`
  - `ResultReader.get_scalar(tree_path)`
  - `ResultReader.list_tree_items(...)`

## Live-CST Confirmed Injection Path

正确注入路径不是只复制 `.r0d`，而是：

```text
Model/3D/Model.rpp
  + Model/3D/Frequency (Mode 1).r0d
  + Model/3D/R over Q (Mode 1).r0d
  + Model/3D/Q-Factor (Perturbation) (Mode 1).r0d
  + optional Model/PC_integration.json outputVariables
  -> open/save CST project
  -> run eigenmode solver
  -> CST automatically evaluates registered templates
  -> Result/Postprocessing.log
  -> Tables/0D Results/*
```

Validated disposable project:

```text
runs/parametric_geometry_500mhz/live_postprocessing/rf_cem_500mhz_auto_solver_vacuum_postprocess_probe.cst
```

当前自动路径已验证：

| Metric | Tree path | Latest automatic readback |
|---|---|---|
| Frequency | `Tables\0D Results\Frequency (Mode 1)` | `556.823422911 MHz` |
| R over Q | `Tables\0D Results\R over Q (Mode 1)` | `1.8056333856152405e-08 Ohm` |
| Q factor | `Tables\0D Results\Q-Factor (Perturbation) (Mode 1)` | `41512.36948675535` |

另一个经用户手动求解的旧 probe 也能读取三项结果，但其 CST 内部导入几何哈希与当前自动 probe 不同，因此频率 `505.583944055 MHz` 不应用来判断同一几何的自动/手动 solver 差异。

## HEX Mesh Error Diagnosis

此前 `EvaluateResultTemplates` 报：

```text
Error: HEX mesh is invalid.
(.Calculate)(Line:719)
```

该错误不是“当前 500 MHz eigenmode 必须切换到 HEX mesh”。用户手动成功项目和当前自动成功项目的 solver log 都显示：

```text
Mesh: Tetrahedral
Method: Classical (Lossless)
solver_used: Solver_HF_TET_E
```

更准确的解释是：早期 probe 在模板注册、求解状态、导入体材料/几何版本尚不完整的上下文里直接调用了 `QFactor.Calculate` / `EvaluateResultTemplates`，CST 的错误文本误导性地指向了 HEX mesh。正确顺序是先注册 `Model.rpp + .r0d`，把全局背景材料设置为导体，确保导入 RF vacuum body 被赋予 `Vacuum` 材料，再运行 eigenmode solver；solver 完成后 CST 会自动执行模板并写入 0D result tree。

当前不需要自动切换到 HEX。若未来确实需要 mesh policy，必须通过 expert prior / workflow config 显式配置，并使用 CST 历史树或官方文档中的 solver mesh block；不能在失败时静默猜测切换。

2026-07-07 后续验证确认：加入历史树验证的 `Copper (annealed)` 背景材料后，自动路径仍使用 Tetrahedral mesh，并成功输出三项指标：

| Metric | Readback |
|---|---:|
| Frequency | `505.583944055 MHz` |
| R over Q | `428.086330643 Ohm` |
| Q factor | `45867.1264209` |

## Proposed Flow

```text
CST project or unpacked project directory
  -> inspect Model/PC_integration.json
  -> inspect Model/3D/*.r0d and *.r1d
  -> inspect Result/Postprocessing.log
  -> emit result_metrics.v0.json
  -> live-CST saves project after solver/postprocess
  -> ResultReader.get_scalar(tree_path)
  -> frequency_mhz / r_over_q_ohm / q_factor
```

## Proposed `result_metrics.v0` Shape

```yaml
schema_version: result_metrics.v0
source_policy:
  primary:
    - pc_integration_json
    - r0d_r1d_template_artifacts
    - postprocessing_log
  secondary:
    - result_tree_discovery
    - mcs_macro_reference
metrics:
  frequency_mhz:
    kind: scalar_0d
    unit: MHz
    tree_path: "Tables\\0D Results\\Frequency (Mode 1)"
    source_name: "3D\\Frequency (Mode 1)"
    postprocess_template:
      action: Frequency
      template_type: 0D
      mode_numbers: "1"
  r_over_q_ohm:
    kind: scalar_0d
    unit: Ohm
    tree_path: "Tables\\0D Results\\R over Q (Mode 1)"
    source_name: "3D\\R over Q (Mode 1)"
    postprocess_template:
      action: R over Q
      template_type: 0D
      mode_numbers: "1"
  q_factor:
    kind: scalar_0d
    unit: dimensionless
    tree_path: "Tables\\0D Results\\Q-Factor (Perturbation) (Mode 1)"
    source_name: "3D\\Q-Factor (Perturbation) (Mode 1)"
    postprocess_template:
      action: Q-Factor (Perturbation)
      template_type: 0D
      mode_numbers: "1"
```

## Parser Responsibilities

No-CST parser should:

1. Read `PC_integration.json` and collect `outputVariables`.
2. Scan `Model/3D/*.r0d` and `*.r1d` as binary-safe text for key/value fragments:
   - `Action`
   - `TemplateType`
   - `ModeNumbers`
   - `a0DValue`
   - `Post Processing Template`
3. Parse `Result/Postprocessing.log` for evaluated item names and units.
4. Produce:
   - candidate metric names
   - candidate tree paths
   - source evidence paths
   - confidence and missing-field warnings
5. Never generate guessed CST VBA when evidence is missing.

## Live-CST Boundary

Live validation has passed for template registration and scalar readback on a disposable project. Before enabling optimizer production runs, keep the following checks in every live-CST smoke test:

1. Generated STEP imports.
2. Global background material is set to the configured conducting-wall material.
3. Imported RF vacuum body is assigned to CST `Vacuum` material.
4. Eigenmode solver runs with the configured mesh policy.
5. Required postprocessing metrics appear in result tree.
6. Project is saved with results after postprocessing.
7. `ResultReader.get_scalar(...)` reads the three metrics.

## Risks

| Risk | Control |
|---|---|
| `.r0d/.r1d` are internal CST files. | Use them only as read-only evidence and template metadata, not as files to modify. |
| Result tree names differ by CST version or language. | Use `ResultReader.list_tree_items(...)` to emit diagnostics before binding. |
| Q-factor meaning differs between perturbation/lossy/external/loaded definitions. | Require metric config to specify exact action string and source artifact. |
| R/Q requires axis/coordinate assumptions. | Preserve template settings such as `coordinates`, `beta`, and source file evidence in `result_metrics`. |
| Postprocess exists in old project but not in newly generated project. | Require `Model.rpp` plus matching `.r0d` files; treat absence as `POSTPROCESS_TEMPLATE_MISSING`. |
| CST reports `HEX mesh is invalid` during QFactor evaluation. | First check template registration, imported body material, stale result state, and solver completion. Do not switch mesh automatically unless a config-selected mesh policy says so. |
| Vacuum-only STEP is physically incomplete without a conducting background. | Set the background material as part of the global boundary/material policy. The current verified default is `Copper (annealed)`. |

## Next Implementation Step

Short-term implementation status:

- `src/rf_cem/live_500mhz_postprocessing_diagnostic.py` now registers templates through filtered `Model.rpp` records.
- The diagnostic can run solver with `--run-solver`; CST then evaluates registered templates automatically.
- Future workflow evaluator should consume the explicit tree paths above through `ResultReader.get_scalar(...)`.

Remaining no-CST parser work: implement a reusable parser that reads a CST project directory and writes:

```text
metadata/result_metrics.v0.json
metadata/postprocessing_template_evidence.json
```

Then wire RF-CEM evaluator to use explicit `result_metrics` tree paths through the existing `ResultReader`.
