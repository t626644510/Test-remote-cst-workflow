# RF-CEM Phase 1–3 技术规划报告：面向 CSTTranslator 的稳定语义闭环

**项目方向**：面向加速器 RF 腔 / 电子枪的计算工程式自动几何与仿真闭环系统
**文档定位**：CSTTranslator 前三阶段架构规划、接口设计、测试策略与 Codex 执行提示词
**当前目标**：在已完成 `CST history tree reader` 与 `STEP topology extractor` 两个 helper 的基础上，设计从输入到稳定输出的中间语义层与 CST 转译闭环
**建议实施者**：Codex / 本地执行 agent
**版本**：v0.1

---

## 0. 设计前提与约束

### 0.1 已知事实

当前系统已具备两个 helper：

1. **CST history tree reader**
   用于读取 CST 工程中的建模与设置历史，可理解为从已有 CST 工程中抽取操作序列、对象创建过程、边界 / 求解器 / 监视器设置的基础能力。

2. **STEP topology extractor**
   用于从 STEP 模型中提取几何拓扑信息，可理解为从几何文件中抽取 solid、face、edge、邻接关系、几何类型和基础几何特征的能力。

这两个 helper 可以分别视为 CSTTranslator 体系中的“历史输入”和“几何输入”，但它们不能直接互相替代，也不能直接拼接成可靠的 CSTTranslator。

---

### 0.2 核心判断

后续系统不应直接设计为：

```text
STEP topology extractor
  ↓
CSTTranslator
  ↓
CST project
```

而应设计为：

```text
STEP topology graph
  +
CST history graph
  +
Feature / Simulation recipes
  ↓
Unified Design State Graph, UDSG
  ↓
CSTTranslator compiler
  ↓
CST executable script / project
  ↓
ResultParser / evaluation record / optimizer bridge
```

原因是：

- STEP 描述的是几何结构；
- CST history 描述的是操作历史；
- Feature graph 描述的是工程语义；
- Simulation recipe 描述的是本次仿真如何使用这些语义；
- CSTTranslator 应把工程语义和仿真意图编译为 CST 可执行命令，而不是把几何文件机械导入 CST。

因此，本阶段真正需要补齐的是：

```text
Semantic Binder / UDSG layer
```

它负责把几何、历史、语义和仿真意图绑定到一个稳定、可验证、可扩展的中间表示中。

---

## 1. 总体目标

到 Phase 3 结束时，系统应实现以下稳定闭环：

```text
Design Package / STEP / CST baseline
  ↓
Geometry graph + CST history graph
  ↓
UDSG.v0
  ↓
CSTTranslator.v0
  ↓
Generated CST script / project
  ↓
CST run result
  ↓
Normalized results
  ↓
Evaluation record
  ↓
Existing optimizer bridge
```

### 1.1 必须满足的工程要求

1. **输入稳定**
   相同输入文件、相同配置、相同版本 schema 下，解析结果应稳定。

2. **输出可复现**
   同一个 UDSG 输入应生成 hash 一致或语义等价的 CST script / mapping table。

3. **中间状态可审计**
   每一步输出必须保存为 JSON / YAML / JSONL 等可审计文件，不能只存在于内存中。

4. **失败可分类**
   失败不应只返回异常堆栈，而应分类为 geometry、binding、translator、solver、physics、postprocess 等类型。

5. **向前兼容**
   v1 模块应能读取 v0 schema。

6. **向后拒绝**
   v0 模块应明确拒绝未知的高版本 schema，而不是静默误读。

---

## 2. 关键概念定义

### 2.1 Geometry Graph

来源：STEP topology extractor。

描述：几何层事实，不包含工程物理语义。

典型内容：

```json
{
  "schema_version": "geometry_graph.v0",
  "source": {
    "type": "step",
    "path": "geometry/baseline.step",
    "unit": "mm"
  },
  "solids": [],
  "faces": [],
  "edges": [],
  "adjacency": []
}
```

Geometry Graph 应回答：

```text
几何上有什么？
哪些 face 与哪些 solid / edge 相连？
哪些面近似圆柱、平面、旋转面？
哪些几何特征可用于稳定重识别？
```

它不应回答：

```text
哪个面是 cathode？
哪个面是 beam exit？
哪个面应设置 open boundary？
```

---

### 2.2 CST History Graph

来源：CST history tree reader。

描述：CST 工程中的操作历史和设置痕迹。

典型内容：

```json
{
  "schema_version": "cst_history_graph.v0",
  "source": {
    "type": "cst_project",
    "path": "baseline.cst"
  },
  "operations": [],
  "objects": [],
  "boundaries": [],
  "solvers": [],
  "monitors": []
}
```

CST History Graph 应回答：

```text
CST 工程中做过什么？
哪些对象被创建 / 导入 / 修改？
哪些边界、材料、端口、mesh、monitor 被设置？
求解器如何配置？
```

它不应被当作唯一真值，因为 CST history 可能包含：

- 手动操作残留；
- 被覆盖的旧设置；
- 不完整的隐式状态；
- CST 内部对象 ID 变化；
- 与当前几何不再一致的历史记录。

---

### 2.3 Feature Graph

来源：人工标注、模板规则、几何推断、CST history 辅助推断。

描述：工程语义层。

典型内容：

```json
{
  "schema_version": "feature_graph.v0",
  "features": [
    {
      "id": "rf_vacuum",
      "type": "RFVacuumVolume",
      "geometry_ref": "solid_rf_vacuum"
    },
    {
      "id": "beam_exit",
      "type": "BeamAperture",
      "geometry_ref": "face_beam_exit"
    },
    {
      "id": "axis_field_monitor",
      "type": "FieldMonitor",
      "quantity": "Ez_on_axis"
    }
  ]
}
```

Feature Graph 应回答：

```text
这个几何实体在 RF 工程中是什么意思？
它在仿真里可能承担什么角色？
它与哪些几何节点绑定？
它需要哪些后续求解器设置？
```

Feature Graph 不应把所有 solver 设置写死。比如 `beam_exit` 在本征模仿真中可能是电壁，在频域 / wakefield 中可能是 open boundary 或 port。因此 solver 相关策略应由 Simulation Recipe 决定。

---

### 2.4 Simulation Recipe

描述：本次仿真如何使用 Feature Graph。

示例：

```yaml
schema_version: simulation_recipe.v0
solver: CST_Eigenmode
boundary_policy:
  beam_exit: electric
  cathode: electric
  metal_wall: electric
mesh_policy:
  default: coarse_v0
  local_refinement:
    - feature: iris_region
      level: medium
postprocess:
  target_mode:
    mode_type: TM010_like
    frequency_hint_hz: 5.0e8
  metrics:
    - frequency_hz
    - R_over_Q_ohm
    - Epk_over_Eacc
    - Hpk_over_Eacc
```

Simulation Recipe 应回答：

```text
这次仿真用什么 solver？
哪些 feature 应映射到哪些 boundary / port / monitor？
如何设置 mesh？
需要导出哪些结果？
```

---

### 2.5 UDSG：Unified Design State Graph

UDSG 是 Phase 1–3 的核心中间表示。

它聚合：

```text
Geometry Graph
CST History Graph
Feature Graph
Simulation Recipe
Binding Records
Validation Records
```

建议 v0 结构：

```json
{
  "schema_version": "udsg.v0",
  "package_id": "baseline_500MHz_001",
  "sources": {
    "geometry_graph": "semantic/geometry_graph.json",
    "cst_history_graph": "semantic/cst_history_graph.json",
    "feature_graph": "semantic/feature_graph.json",
    "simulation_recipe": "simulation/simulation_recipe.yaml"
  },
  "geometry_nodes": [],
  "history_nodes": [],
  "feature_nodes": [],
  "bindings": [],
  "validation": {
    "status": "unchecked",
    "warnings": [],
    "errors": []
  }
}
```

UDSG 应作为 CSTTranslator 的输入真值。CSTTranslator 不应绕过 UDSG 直接读取 STEP 或 CST history。

---

## 3. Phase 1：Semantic Foundation Layer

### 3.1 Phase 1 目标

建立 UDSG.v0，并实现 STEP geometry graph 与 CST history graph 的只读对齐。

Phase 1 不要求生成新的 CST 工程，不要求真正运行 CST，只要求形成稳定、可审计的中间表示。

---

### 3.2 Phase 1 输入

```text
design_package_v0/
  package.yaml
  geometry/
    baseline.step
    baseline.cst        # optional
    geometry_manifest.json # optional
  semantic/
    feature_graph.json      # optional in early prototype
  simulation/
    simulation_recipe.yaml
```

辅助输入：

```text
helper outputs:
  geometry_graph.json
  cst_history_graph.json
```

---

### 3.3 Phase 1 输出

```text
design_package_v0/
  semantic/
    geometry_graph.normalized.json
    cst_history_graph.normalized.json
    feature_graph.resolved.json
    udsg.v0.json
    binding_report.json
    validation_report.json
```

---

### 3.4 Phase 1 模块拆分

建议目录：

```text
src/rf_cem/
  schema/
    version.py
    registry.py
    validators.py
  geometry/
    graph_models.py
    geometry_indexer.py
    signature.py
  cst_history/
    graph_models.py
    history_normalizer.py
    operation_dag.py
  semantic/
    feature_models.py
    feature_resolver.py
    binding_models.py
    udsg_builder.py
  io/
    json_io.py
    yaml_io.py
```

#### 3.4.1 geometry_indexer

职责：

- 读取 STEP helper 输出；
- 标准化 solid / face / edge ID；
- 计算几何 signature；
- 建立 face adjacency；
- 生成稳定候选 selector。

建议 face signature：

```json
{
  "face_id": "face_00012",
  "surface_type": "plane|cylinder|cone|sphere|bspline|unknown",
  "area": 123.45,
  "center": [0.0, 0.0, 12.3],
  "normal_hint": [0.0, 0.0, 1.0],
  "bbox": [[-1, -1, 0], [1, 1, 0]],
  "adjacent_faces": ["face_00011", "face_00013"],
  "stable_hash": "..."
}
```

#### 3.4.2 cst_history_normalizer

职责：

- 读取 CST helper 输出；
- 标准化 operation 类型；
- 建立操作 DAG；
- 提取对象创建、材料、边界、端口、mesh、monitor、solver 设置；
- 标记失效或被覆盖的历史操作。

建议 operation schema：

```json
{
  "op_id": "op_00045",
  "op_type": "CreateSolid|ImportGeometry|AssignBoundary|SetMaterial|SetSolver|AddMonitor|Unknown",
  "target_ref": "raw_cst_object_ref",
  "parameters": {},
  "depends_on": ["op_00044"],
  "status": "active|overridden|unknown"
}
```

#### 3.4.3 feature_resolver

职责：

- 合并人工 feature_graph 与自动推断；
- 从 geometry pattern 推断候选 feature；
- 从 CST history 设置推断候选 feature；
- 生成 resolved feature graph；
- 对每个绑定给出 confidence 与 evidence。

建议 binding schema：

```json
{
  "binding_id": "bind_0001",
  "feature_id": "beam_exit_left",
  "geometry_node_id": "face_00012",
  "history_node_ids": ["op_00045"],
  "binding_type": "feature_to_geometry",
  "confidence": 0.83,
  "evidence": [
    "face is planar and located at z_min",
    "CST history assigns electric boundary to matching face candidate"
  ],
  "status": "accepted|candidate|rejected|requires_review"
}
```

---

### 3.5 Phase 1 验收标准

Phase 1 完成时，必须满足：

1. `udsg.v0.json` 可被 schema validator 通过；
2. 同一输入重复运行，输出稳定；
3. 未提供 CST history 时，系统仍能生成 geometry-only UDSG；
4. 未提供 STEP 时，系统仍能生成 cst-history-only UDSG，但标记为 `partial`；
5. 每个 feature binding 都必须有 `confidence` 和 `evidence`；
6. 所有无法识别操作必须保留为 `Unknown`，不能丢弃；
7. 对低置信度绑定必须给出 `requires_review`。

---

### 3.6 Phase 1 测试设计

#### Test P1-1：Schema validation

输入：最小 geometry graph、最小 cst history graph。
预期：生成合法 `udsg.v0.json`。

#### Test P1-2：Deterministic output

输入：同一设计包运行 3 次。
预期：输出 JSON 在排序规范化后 hash 一致。

#### Test P1-3：Partial input tolerance

输入：只有 STEP helper 输出。
预期：生成 geometry-only UDSG，validation status 为 `partial_ok`。

#### Test P1-4：Unknown operation preservation

输入：包含无法识别 CST operation。
预期：operation 被保留为 `Unknown`，并进入 warning，不得丢弃。

#### Test P1-5：Low-confidence binding

输入：两个几何面都可疑似 beam exit。
预期：binding status 为 `requires_review`，不得自动确定。

---

## 4. Phase 2：CSTTranslator Compiler

### 4.1 Phase 2 目标

实现：

```text
UDSG.v0 + Simulation Recipe
  ↓
CSTTranslator.v0
  ↓
CST macro / Python script / mapping table
```

Phase 2 不以求解结果正确为主要目标，而以“可稳定生成 CST 可执行工程配置”为目标。

---

### 4.2 Phase 2 输入

```text
design_package_v0/
  semantic/
    udsg.v0.json
  simulation/
    simulation_recipe.yaml
    boundary_recipe.yaml      # optional
    mesh_recipe.yaml          # optional
    postprocess_recipe.yaml   # optional
  geometry/
    baseline.step
```

---

### 4.3 Phase 2 输出

```text
design_package_v0/
  generated/
    cst_script.py
    cst_macro.bas             # optional
    cst_mapping_table.json
    translator_report.json
```

---

### 4.4 CSTTranslator.v0 结构

建议目录：

```text
src/rf_cem/cst_translator/
  translator.py
  geometry_mapper.py
  feature_mapper.py
  solver_compiler.py
  mesh_compiler.py
  monitor_compiler.py
  script_emitter.py
  mapping_table.py
```

建议类结构：

```python
class CSTTranslator:
    def __init__(self, schema_registry, cst_backend):
        ...

    def load_udsg(self, path):
        ...

    def validate_input(self):
        ...

    def map_geometry(self):
        ...

    def map_features(self):
        ...

    def compile_solver(self):
        ...

    def compile_mesh(self):
        ...

    def compile_monitors(self):
        ...

    def emit_script(self):
        ...

    def write_mapping_table(self):
        ...
```

---

### 4.5 Feature 到 CST action 的 v0 映射

| Feature type | CST action v0 | 备注 |
|---|---|---|
| `RFVacuumVolume` | import / select solid; assign vacuum/background | v0 先支持单 vacuum solid |
| `ConductingWall` | PEC or material assignment | v0 可先支持 PEC |
| `BeamAperture` | boundary assignment from recipe | 不在 feature 中写死 |
| `CathodeSurface` | electric boundary / reference surface | 电子枪后续验证需要 |
| `InputCouplerPort` | waveguide/discrete port placeholder | v0 可先输出 TODO 或 dry-run action |
| `MeshRefinementRegion` | local mesh operation | v0 支持 basic placeholder |
| `FieldMonitor` | add field monitor / export axis field | v0 先支持字段声明 |

---

### 4.6 Mapping Table

CSTTranslator 必须输出 mapping table，作为后续 ResultParser 和 BindingValidator 的依据。

示例：

```json
{
  "schema_version": "cst_mapping_table.v0",
  "input_udsg": "semantic/udsg.v0.json",
  "generated_script": "generated/cst_script.py",
  "feature_to_geometry": {
    "rf_vacuum": "solid_0001",
    "beam_exit_left": "face_0012"
  },
  "feature_to_cst_action": {
    "rf_vacuum": ["ImportGeometry", "AssignVacuum"],
    "beam_exit_left": ["AssignBoundary:electric"]
  },
  "unresolved": [],
  "warnings": []
}
```

---

### 4.7 Phase 2 验收标准

Phase 2 完成时，必须满足：

1. 同一 UDSG 生成的 CST script 内容稳定；
2. 生成的 mapping table 可回溯到 UDSG 中的 feature / geometry / history 节点；
3. 低置信度 binding 不得被静默编译为 CST action；
4. 未支持的 feature type 必须进入 `unresolved`，不能丢弃；
5. 生成脚本应支持 dry-run 模式；
6. CST backend 应可替换，至少预留：

```text
CST Python API backend
CST VBA macro backend
Mock backend
```

---

### 4.8 Phase 2 测试设计

#### Test P2-1：Script reproducibility

输入：同一 `udsg.v0.json`。
预期：生成脚本规范化后 hash 一致。

#### Test P2-2：Unresolved feature guard

输入：包含未知 feature type。
预期：translator report 中出现 unresolved，程序不崩溃，不静默忽略。

#### Test P2-3：Low-confidence binding guard

输入：存在 `requires_review` binding。
预期：默认不生成最终 CST action；除非配置显式允许 `allow_low_confidence=true`。

#### Test P2-4：Mock CST backend compile

输入：最小 UDSG + simulation recipe。
预期：Mock backend 能生成操作序列，不需要真实 CST 环境。

#### Test P2-5：Mapping completeness

输入：包含 RFVacuum、ConductingWall、BeamAperture、FieldMonitor。
预期：mapping table 覆盖全部 feature 或明确列入 unresolved。

---

## 5. Phase 3：Closed Loop Validation + Optimizer Bridge

### 5.1 Phase 3 目标

把 CSTTranslator 生成的工程接入已有优化 / evaluation 体系，实现：

```text
CST run output
  ↓
ResultParser
  ↓
Normalized Result
  ↓
Evaluation Record
  ↓
Existing Optimizer Bridge
```

Phase 3 的重点不是扩大物理范围，而是保证主模指标闭环稳定、可复现、可失败回收。

---

### 5.2 Phase 3 输入

```text
design_package_v0/
  generated/
    cst_script.py
    cst_mapping_table.json
  results/
    raw/
      cst_output_files...
  semantic/
    udsg.v0.json
  simulation/
    postprocess_recipe.yaml
```

---

### 5.3 Phase 3 输出

```text
design_package_v0/
  results/
    results.normalized.json
    mode_summary.csv
    binding_validation_report.json
    failure_report.json
    evaluation_records.jsonl
```

---

### 5.4 模块拆分

建议目录：

```text
src/rf_cem/evaluation/
  result_parser.py
  result_normalizer.py
  mode_selector.py
  binding_validator.py
  failure_classifier.py
  optimizer_bridge.py
  records_adapter.py
```

---

### 5.5 Result Normalizer

统一输出示例：

```json
{
  "schema_version": "normalized_result.v0",
  "design_id": "baseline_500MHz_001",
  "solver": "CST_Eigenmode",
  "run_status": "success",
  "target_mode": {
    "mode_index": 1,
    "frequency_hz": 500000000.0,
    "R_over_Q_ohm": 120.5,
    "Epk_over_Eacc": 2.1,
    "Hpk_over_Eacc": 4.0,
    "mode_confidence": 0.95
  },
  "raw_files": [],
  "warnings": []
}
```

---

### 5.6 Failure Classifier

建议错误分类：

```text
input_failed
  missing_design_package
  schema_invalid

geometry_failed
  missing_geometry
  invalid_topology
  non_manifold
  selector_unresolved

binding_failed
  low_confidence_binding
  feature_drift
  ambiguous_feature

translator_failed
  unsupported_feature
  backend_error
  script_emit_error

solver_failed
  cst_launch_failed
  cst_project_load_failed
  convergence_failed
  no_mode_found

postprocess_failed
  missing_result_file
  mode_selection_failed
  metric_missing

physics_failed
  frequency_out_of_range
  Epk_too_high
  Hpk_too_high
```

---

### 5.7 Evaluation Record Adapter

Phase 3 应复用已有 JSONL evaluation record 思路，而不是重新设计优化器记录格式。

建议 adapter 输出：

```json
{
  "schema_version": 1,
  "iteration": 0,
  "solver_ok": true,
  "error": "",
  "objective_names": ["frequency_error", "R_over_Q", "Epk_over_Eacc"],
  "raw_values": {
    "frequency_error": 0.0,
    "R_over_Q": 120.5,
    "Epk_over_Eacc": 2.1
  },
  "penalties": {
    "frequency_error": 0.0,
    "R_over_Q": 0.0,
    "Epk_over_Eacc": 0.0
  },
  "x_phys": [],
  "diagnostics": {
    "mode_confidence": 0.95,
    "binding_status": "validated"
  },
  "metadata": {
    "design_id": "baseline_500MHz_001",
    "udsg_schema_version": "udsg.v0"
  }
}
```

---

### 5.8 Phase 3 验收标准

Phase 3 完成时，必须满足：

1. CST raw result 能被解析为 `results.normalized.json`；
2. normalized result 可转换为 evaluation record；
3. solver 失败、postprocess 失败、binding 失败能被分类记录；
4. 同一输入重复运行时，非数值项输出稳定；
5. 数值项允许设置 tolerance；
6. evaluation record 能被现有优化框架读取或最小兼容；
7. 对 optimizer 暴露的是标准 metric，不直接暴露 CST 内部文件结构。

---

### 5.9 Phase 3 测试设计

#### Test P3-1：Result normalization

输入：mock CST raw result。
预期：输出合法 `normalized_result.v0`。

#### Test P3-2：Evaluation record compatibility

输入：normalized result + objective config。
预期：输出 JSONL record，字段兼容现有 evaluation record。

#### Test P3-3：Failure injection

输入：缺失 raw result 文件。
预期：分类为 `postprocess_failed.missing_result_file`。

#### Test P3-4：Binding validation

输入：mapping table 中 feature 指向不存在 face。
预期：分类为 `binding_failed.feature_drift`。

#### Test P3-5：Repeated-run stability

输入：同一 mock raw result 重复解析 10 次。
预期：normalized result 结构与非时间戳字段一致。

---

## 6. Schema 与兼容性策略

### 6.1 Schema registry

建议目录：

```text
schemas/
  geometry_graph.v0.schema.json
  cst_history_graph.v0.schema.json
  feature_graph.v0.schema.json
  simulation_recipe.v0.schema.json
  udsg.v0.schema.json
  cst_mapping_table.v0.schema.json
  normalized_result.v0.schema.json
```

---

### 6.2 版本规则

```text
v1 reader must accept v0 input.
v0 reader must reject v1 / v2 unless explicitly marked compatible.
Unknown fields should be preserved in metadata when safe.
Unknown required fields should fail validation.
```

---

### 6.3 兼容层设计

建议实现：

```python
def migrate_udsg_v0_to_v1(data: dict) -> dict:
    ...
```

但 Phase 1–3 只需要 v0 schema 与基本 registry，不需要真正实现 v1。

---

## 7. 关键难点与处理策略

### 7.1 STEP face ID 不稳定

风险：同一几何重新导出 / 重新导入后 face 编号可能变化。

策略：

- 不依赖单一 face ID；
- 使用 geometric signature；
- 使用 adjacency fingerprint；
- 使用 bounding box / area / center / surface type 组合；
- 支持人工命名覆盖自动匹配。

---

### 7.2 CST history 不等于当前工程真值

风险：CST history 中可能存在被覆盖的旧操作、手动残留和隐式状态。

策略：

- CST history 只作为 evidence，不作为唯一真值；
- operation 需要 status：`active|overridden|unknown`；
- 与 geometry / feature 冲突时，进入 warning 或 requires_review；
- 不能因为 CST history 中出现某设置就默认它有效。

---

### 7.3 Feature binding 不能绝对化

风险：自动绑定错误会导致错误 boundary / port / monitor，后续结果即使“能跑”也没有物理意义。

策略：

- 所有 binding 必须有 confidence；
- 低置信度默认不编译；
- 每个 binding 保存 evidence；
- 支持人工 override 文件；
- binding validation 贯穿 Phase 2 和 Phase 3。

---

### 7.4 CST backend 脆弱性

风险：CST API / VBA / Python automation 版本差异大。

策略：

- Translator 先输出 backend-independent action list；
- 再由 backend emitter 输出 Python / VBA / mock；
- 单元测试优先覆盖 mock backend；
- 真实 CST 测试作为集成测试。

---

### 7.5 优化器反馈噪声

风险：数值结果受 mesh、mode selection、求解状态影响，直接反馈可能污染优化器。

策略：

- normalized result 中保留 `mode_confidence`；
- evaluation record 中写入 diagnostics；
- 对低置信度模式设置 penalty 或 rejected；
- 初期只做主模指标闭环，不引入 HOM / multipacting / thermal 等复杂目标。

---

## 8. 推荐 Codex 执行提示词

### Prompt A：Phase 1 / UDSG v0

```text
You are working in the repository `t626644510/Test-remote-cst-workflow` on branch `codex/cst-step-assistants`.

Goal:
Implement Phase 1 Semantic Foundation Layer for RF-CEM CSTTranslator planning.

Read first:
- docs related to CST history tree reader
- docs related to STEP topology extractor
- existing optimization/evaluation record modules
- any existing helper output examples

Implement:
1. Schema registry for v0 JSON/YAML artifacts.
2. Geometry graph normalizer wrapping the existing STEP topology helper output.
3. CST history graph normalizer wrapping the existing CST history tree helper output.
4. UDSG.v0 builder.
5. Rule-based feature resolver with confidence/evidence records.
6. Validation reports for partial input, unknown operations, and low-confidence bindings.

Constraints:
- Do not rewrite existing helpers.
- Do not require real CST execution.
- Keep all outputs deterministic.
- Preserve unknown operations and unknown fields where possible.
- All generated artifacts must be serializable JSON/YAML.
- Low-confidence feature binding must be marked `requires_review`, not silently accepted.

Deliverables:
- source modules under an appropriate package path
- schemas under `schemas/`
- minimal examples under `examples/` or `tests/fixtures/`
- unit tests for schema validation, deterministic output, partial input, unknown operation preservation, and low-confidence binding
- a short markdown implementation note

Acceptance:
- tests pass without CST installed
- a minimal STEP-helper-like geometry graph can produce `udsg.v0.json`
- a minimal CST-history-helper-like graph can be merged into UDSG
```

---

### Prompt B：Phase 2 / CSTTranslator v0

```text
You are working in the repository `t626644510/Test-remote-cst-workflow` on branch `codex/cst-step-assistants`.

Goal:
Implement Phase 2 CSTTranslator.v0 compiler from UDSG.v0 to CST backend-independent action list and script output.

Read first:
- Phase 1 UDSG implementation
- existing CST automation patterns in the repository
- existing configuration and evaluation workflow style

Implement:
1. CSTTranslator core class.
2. Geometry mapper from UDSG geometry nodes to CST selection references.
3. Feature mapper from Feature Graph types to CST action model.
4. Solver compiler for CST Eigenmode v0.
5. Mesh and monitor compiler placeholders with explicit unresolved handling.
6. Backend-independent CST action list.
7. Mock backend emitter.
8. Optional Python/VBA emitter skeleton if repository conventions already exist.
9. Mapping table output `cst_mapping_table.v0.json`.
10. Translator report with warnings/unresolved/blocked actions.

Constraints:
- CSTTranslator must read UDSG, not raw STEP or raw CST history directly.
- Deterministic output is required.
- Unknown feature types must be recorded as unresolved.
- Bindings with `requires_review` must block final action generation by default.
- No real CST execution is required in unit tests.

Deliverables:
- translator modules
- action model schemas
- mapping table schema
- mock backend tests
- reproducibility hash test
- unresolved feature guard test
- low-confidence binding guard test

Acceptance:
- same UDSG produces stable action list and script output
- mapping table links feature IDs, geometry IDs, and emitted action IDs
- tests pass without CST installed
```

---

### Prompt C：Phase 3 / Closed-loop evaluation bridge

```text
You are working in the repository `t626644510/Test-remote-cst-workflow` on branch `codex/cst-step-assistants`.

Goal:
Implement Phase 3 closed-loop validation and optimizer bridge for CSTTranslator output.

Read first:
- existing evaluation record system
- existing JSONL logging utilities
- existing gates / metrics / result parsing modules
- Phase 1 UDSG and Phase 2 mapping table outputs

Implement:
1. ResultParser interface for CST raw outputs, with mock raw-result support.
2. Normalized result schema `normalized_result.v0`.
3. Mode selector for target mode metrics, initially mockable.
4. Binding validator using UDSG + mapping table.
5. Failure classifier with typed failure categories.
6. Adapter from normalized result to existing evaluation record JSONL format.
7. Tests for normalization, record compatibility, missing raw result failure, feature drift failure, and repeated-run stability.

Constraints:
- Do not rewrite the existing optimizer.
- Expose standardized metrics, not CST internal file structure.
- Solver failures and postprocess failures must produce structured records.
- Keep Phase 3 focused on main-mode metrics only.
- Tests must run without CST installed.

Deliverables:
- evaluation bridge modules
- normalized result schema
- failure classifier
- JSONL record adapter
- mock result fixtures
- unit tests
- short markdown implementation note

Acceptance:
- mock CST output can be normalized
- normalized result can be converted to existing evaluation record format
- failure injection is classified and logged
- tests pass without CST installed
```

---

## 9. 建议提交粒度

### Phase 1 commit 建议

```text
feat(rf-cem): add UDSG v0 semantic foundation
```

包含：schema、models、normalizers、UDSG builder、feature resolver、测试。

### Phase 2 commit 建议

```text
feat(cst-translator): compile UDSG v0 to CST action model
```

包含：translator core、mapping table、mock backend、script emitter、测试。

### Phase 3 commit 建议

```text
feat(rf-cem): add CST result normalization and evaluation bridge
```

包含：result normalizer、failure classifier、binding validator、evaluation record adapter、测试。

---

## 10. 最终交付状态

完成 Phase 1–3 后，项目应具备：

```text
helper outputs
  ↓
UDSG.v0
  ↓
CSTTranslator.v0
  ↓
generated CST action/script
  ↓
normalized result
  ↓
evaluation record
```

此时系统尚不一定完成完整自动几何生成，也不要求支持 HOM / multipacting / thermal / mechanical。但它已经具备一个稳定的工程主干：

```text
语义化设计包 → CST 自动复现 → 主模结果标准化 → 优化器回流
```

这条主干一旦稳定，后续可以在不推翻现有接口的基础上逐步加入：

- Parametric Geometry Backend；
- Template-based Cavity Grammar；
- X-band 2.3-cell gun 复杂 feature；
- HOM / wakefield；
- multipacting；
- thermal / mechanical / cooling；
- 多求解器 translator。

---

## 11. 一句话总结

Phase 1–3 的核心不是“把 STEP 转成 CST”，而是建立：

```text
STEP / CST history / feature intent
  ↓
UDSG semantic truth layer
  ↓
CSTTranslator compiler
  ↓
result normalization and optimizer bridge
```

这样才能保证输入稳定、输出可靠，并且后续扩展不会推翻当前架构。
