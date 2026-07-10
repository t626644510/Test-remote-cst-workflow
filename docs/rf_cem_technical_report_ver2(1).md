# 技术报告 Ver.2：RF-CEM 第一阶段路线与语义化 CST 闭环设计

**项目方向**：面向加速器 RF 腔/电子枪的计算工程式自动几何与仿真闭环系统
**版本**：v0.2
**日期**：2026-06-17
**当前重点**：语义装配层、CST 转译层、主模指标闭环、导入式 baseline 工作流

---

## 0. 本版报告定位

本报告基于前期关于 LEAP 71 / Noyron / PicoGK、SDF/B-Rep/NURBS/voxel/implicit geometry、LLM、AlphaGo 式搜索以及 RF-CEM 架构的讨论，进一步收敛到第一阶段可执行研发路线。

当前不再把第一目标定义为“从零实现完整自研几何内核”，而是定义为：

```text
建立 Solver-Ready Semantic Design Package：
  设计参数 / 几何文件 / 工程语义 / CST 求解设置 / 后处理指标 / 优化回流
  形成稳定、可复现、可扩展的主模仿真闭环。
```

本阶段应优先解决：

1. 现有几何或 baseline 模型如何被系统语义化；
2. 语义对象如何稳定映射到 CST 中的材料、边界、端口、网格和结果监视器；
3. 如何在没有成熟几何生成器的情况下，先完成导入式闭环；
4. 后续几何生成器如何自然接入，而不推翻语义层和求解器接口。

---

## 1. 当前关键技术决策

### 1.1 第一版腔型选择

当前选择两个已具备工程基础和物理经验的对象：

```text
A. 常温 500 MHz RF 腔
B. X 波段 2.3-cell 电子枪
```

这两个对象的分工建议如下：

| 对象 | 第一阶段角色 | 主要价值 |
|---|---|---|
| 常温 500 MHz RF 腔 | Stage 1 baseline | 几何和物理较熟悉，适合快速打通 spec → CST → result 闭环 |
| X 波段 2.3-cell 电子枪 | Stage 2 复杂验证对象 | 引入 cathode、multi-cell、coupler、局部高场和更复杂语义 |

### 1.2 第一版主求解器

```text
CST
```

因此第一阶段的 solver adapter 应聚焦 CST，不追求多求解器抽象的过度泛化。

但接口设计上仍应预留：

```text
CSTTranslator
HFSSTranslator
ACE3PTranslator
COMSOLTranslator
```

当前只实现 CSTTranslator。

### 1.3 几何主内核

当前预期为自研混合内核，但第一阶段不应让自研内核阻塞闭环。

建议路线：

```text
短期：导入现成模型 / 使用现有几何 / OpenCASCADE 或 CadQuery 辅助
中期：实现椭圆弧、圆弧、直线段、旋转体等 RF profile builder
长期：自研混合内核，参考 OpenCASCADE 与 PicoGK 的思想
```

### 1.4 RF 主表面参数化方式

第一版以：

```text
椭圆弧 / 圆弧 / 直线段
```

为主。后续逐步扩展至：

```text
混合曲线 → Bézier / NURBS → 局部扰动 → implicit/SDF 辅助结构
```

### 1.5 第一阶段物理范围

第一阶段只完成：

```text
主模指标闭环
```

暂不纳入：

```text
HOM
multipacting
thermal
mechanical
cooling
```

这些内容作为后续 phase 扩展。

### 1.6 数据格式与现有模块兼容

当前已有参数化驱动的 RF 自动优化框架。因此第一阶段应优先做 bridge，而不是重写优化系统。

核心原则：

```text
现有优化器继续负责参数搜索；
新的 RF-CEM 层负责语义化设计包、几何/模型导入、CST 转译、结果标准化。
```

---

## 2. 总体架构调整

原始总体架构为：

```text
抽象规格层
  ↓
腔型语法层
  ↓
几何合成层
  ↓
语义装配层
  ↓
仿真接口层
  ↓
评估与优化层
  ↓
数据回流层
```

结合当前实际模块状态，应调整为：

```text
已有优化框架 / 参数驱动框架
  ↓
Design Package v0
  ↓
Imported or Generated Geometry
  ↓
Resolved Feature / Assembly Graph
  ↓
CST Translator
  ↓
CST Run + Result Parser
  ↓
Standardized Results
  ↓
Existing Optimizer Bridge
```

第一阶段的核心不是完整实现所有层，而是实现：

```text
语义化设计包 → CST 自动复现 → 主模结果回读 → 优化器回流
```

---

## 3. Cavity Grammar、Geometry Synthesis、Feature/Assembly Graph 的区别

这是本项目中最容易混淆但非常关键的三层。

### 3.1 Cavity Grammar 是“规则/模板/设计族”

Cavity Grammar 描述的是：

```text
一种腔型由哪些工程对象组成？
这些对象之间有什么拓扑关系？
有哪些合法参数？
有哪些默认边界语义？
哪些几何变化是允许的？
```

它更接近 OOP 中的 class/template。

例如：

```text
XBand23CellGunTemplate:
  components:
    - cathode cell
    - full cell
    - 0.3 cell
    - iris
    - beam exit
    - input coupler
  parameters:
    - cell_radius
    - iris_radius
    - cathode_recess
    - coupler_slot_width
  expected_features:
    - CathodeSurface
    - RFVacuumVolume
    - BeamExit
    - InputCouplerPort
```

Grammar 不一定直接包含具体 CAD 面，也不一定已经有具体 STEP 文件。它描述的是“这一类对象应该怎样被构造和理解”。

### 3.2 Geometry Synthesis 是“把规则实例化为几何”

Geometry Synthesis 做的是：

```text
输入参数 + 腔型规则
  ↓
生成实际几何文件与几何实体
```

例如：

```text
parameters.yaml
  ↓
profile builder / CAD kernel
  ↓
rf_vacuum.step
metal_wall.step
coupler.step
```

它的输出必须包含两类东西：

1. 几何本身，例如 STEP/STL/CST model；
2. 几何标识，例如 solid name、face tag、edge tag、region tag。

没有几何合成层，Cavity Grammar 只是抽象规则；有了几何合成层，规则才变成可导入求解器的实体。

### 3.3 Feature / Assembly Graph 是“几何对象的工程语义说明书”

Feature/Assembly Graph 描述的是：

```text
这个几何实体在工程和仿真中是什么意思？
哪个体是真空区？
哪个面是阴极？
哪个面是束流出口？
哪个口是输入耦合器？
哪些区域需要网格加密？
哪些指标需要后处理？
```

它不负责生成几何，而负责把几何解释给仿真器。

例如：

```json
{
  "id": "cathode",
  "type": "CathodeSurface",
  "geometry_ref": "geometry/rf_gun.step",
  "face_tag": "face_cathode",
  "boundary_role": "electric"
}
```

### 3.4 三者的层级关系

```text
Cavity Grammar
  = 设计族规则 / 模板 / OOP class

Geometry Synthesis
  = 根据规则和参数生成实际几何 / OOP object instantiation

Feature / Assembly Graph
  = 给实际几何对象贴工程语义标签 / OOP object metadata + simulation intent
```

更直观地说：

```text
Grammar 问：应该有什么？
Geometry 问：实际长什么样？
Feature Graph 问：这些东西在仿真里是什么意思？
```

---

## 4. 为什么几何合成位于 Grammar 和 Feature Graph 中间

理想情况下流程是：

```text
Cavity Grammar
  ↓
Geometry Synthesis
  ↓
Feature / Assembly Graph
  ↓
Solver Translator
```

原因是 Feature Graph 往往需要引用实际几何实体，例如：

```text
solid name
face tag
edge tag
coordinate selector
component id
```

这些信息只有几何生成或几何导入后才存在。

不过实际系统中可以拆成两种 graph：

### 4.1 Planned Feature Graph

在几何生成前存在。

它描述预期语义：

```text
这个模板应该有 cathode、beam exit、RF vacuum、input coupler。
```

但它还没有绑定具体 face。

### 4.2 Resolved Feature Graph

在几何生成或导入后存在。

它绑定具体几何引用：

```text
CathodeSurface → face_cathode
BeamExit → face_beam_exit
InputCouplerPort → face_waveguide_port
RFVacuumVolume → solid_rf_vacuum
```

因此更完整的流程是：

```text
Cavity Grammar
  ↓
Planned Feature Graph
  ↓
Geometry Synthesis or Geometry Import
  ↓
Resolved Feature Graph
  ↓
CST Translator
```

这也解释了为什么在没有几何生成器时，仍然可以通过“导入现成模型 + 人工/半自动标注”得到 Resolved Feature Graph。

---

## 5. Phase 1 没有几何生成器时如何推进

Phase 1 不要求系统自动生成 500 MHz baseline 几何。可以采用导入式路线。

### 5.1 导入式 Phase 1 核心思路

```text
现成 CST 模型或 STEP 模型
  ↓
统一命名 / 人工标注 / 模板化标注
  ↓
生成 feature_graph.json
  ↓
CSTTranslator 读取 feature graph
  ↓
自动设置边界、求解器、mesh、monitor、postprocess
  ↓
输出 results.json
```

此时 Feature Graph 不是从几何生成器自动产生，而是由人类或脚本围绕已有模型建立。

### 5.2 Phase 1 最小输入

```text
design_package_500MHz_v0/
  geometry/
    baseline_500MHz.step 或 baseline_500MHz.cst
  metadata/
    parameters.yaml
    feature_graph.json
  simulation/
    simulation_recipe.yaml
    mesh_recipe.yaml
    postprocess_recipe.yaml
```

### 5.3 导入现成模型的两种策略

#### 策略 A：导入 STEP / SAT / STL

适合从外部 CAD 或脚本导出的几何。

优点：

```text
几何来源清晰
便于后续替换为几何生成器
设计包结构干净
```

缺点：

```text
面 ID 可能不稳定
CST 导入后 face 编号可能变化
需要额外命名或选择机制
```

#### 策略 B：直接使用现有 CST baseline project

适合第一阶段快速复现。

优点：

```text
已有材料、边界、端口和 mesh 设置可能可复用
最容易验证结果一致性
```

缺点：

```text
工程可移植性较差
容易隐藏手工设置
不利于长期抽象
```

建议：

```text
Phase 1 可先用 CST baseline project 复现；
同时逐步抽取其语义配置，形成 feature_graph 和 simulation_recipe；
Phase 2 再过渡到 STEP + translator 完全重建 CST project。
```

---

## 6. Feature Graph 如何过渡到 CST 求解器

Feature Graph 不是直接等于 CST 设置。中间需要 CSTTranslator。

```text
Feature Graph + Simulation Recipe + Mesh Recipe
  ↓
CSTTranslator
  ↓
CST macro / Python automation / VBA script
  ↓
CST project
```

### 6.1 Feature Graph 提供“对象语义”

例如：

```json
{
  "id": "beam_exit",
  "type": "BeamAperture",
  "face_tag": "face_beam_exit"
}
```

它只说明：这是束流出口。

### 6.2 Simulation Recipe 决定“本次仿真怎么用它”

例如同一个 beam exit，在不同仿真中可能被处理为：

```text
电壁
开放边界
波导端口
束流端口
```

因此边界条件不应完全写死在 Feature Graph 中，而应由 Simulation Recipe 决定。

示例：

```yaml
simulation:
  solver: CST_Eigenmode
  boundary_policy:
    beam_exit: electric
    cathode: electric
    metal_wall: electric
```

或：

```yaml
simulation:
  solver: CST_FrequencyDomain
  boundary_policy:
    beam_exit: open
    input_coupler: waveguide_port
```

### 6.3 CSTTranslator 做语义映射

CSTTranslator 负责把工程语义变成 CST 命令：

```text
RFVacuumVolume
  → import solid / define vacuum region

ConductingWall
  → assign PEC boundary or copper material

CathodeSurface
  → select named face / assign electric boundary / define monitor reference

InputCouplerPort
  → create waveguide port or discrete port

MeshRefinementRegion
  → local mesh operation

FieldMonitor
  → add E/H field monitor and axis field export
```

### 6.4 最终 CST 运行结果再标准化

CST 的输出不应直接进入优化器，而应由 ResultParser 标准化：

```json
{
  "design_id": "baseline_500MHz_001",
  "solver": "CST_Eigenmode",
  "target_mode": {
    "frequency_hz": 500000000.0,
    "R_over_Q_ohm": 120.5,
    "shunt_impedance_ohm": 3200000.0,
    "Epk_over_Eacc": 2.1,
    "Hpk_over_Eacc": 4.0,
    "mode_confidence": 0.95
  }
}
```

---

## 7. Design Package v0 建议结构

```text
design_package_v0/
  package.yaml
  parameters.yaml
  geometry/
    baseline.step
    baseline.cst        # optional
    geometry_manifest.json
  semantic/
    feature_graph.json
    assembly_graph.json # optional in v0
  simulation/
    simulation_recipe.yaml
    boundary_recipe.yaml
    mesh_recipe.yaml
    postprocess_recipe.yaml
  generated/
    cst_script.py
    cst_macro.bas
  results/
    raw/
    results.json
    mode_summary.csv
```

### 7.1 package.yaml

```yaml
schema_version: 0.1
package_id: baseline_500MHz_001
case_type: NormalConducting500MHzCavity
geometry_source: imported_step
solver_target: CST
```

### 7.2 geometry_manifest.json

用于记录几何来源和实体命名。

```json
{
  "geometry_file": "geometry/baseline.step",
  "units": "mm",
  "entities": [
    {
      "id": "solid_rf_vacuum",
      "type": "solid",
      "source_name": "RF_Vacuum"
    },
    {
      "id": "face_beam_left",
      "type": "face",
      "selector": {
        "method": "named_face",
        "name": "beam_left"
      }
    }
  ]
}
```

### 7.3 feature_graph.json

```json
{
  "schema_version": "0.1",
  "features": [
    {
      "id": "rf_vacuum",
      "type": "RFVacuumVolume",
      "geometry_ref": "solid_rf_vacuum"
    },
    {
      "id": "metal_wall",
      "type": "ConductingWall",
      "target": "rf_vacuum",
      "material": "copper_or_PEC"
    },
    {
      "id": "beam_left",
      "type": "BeamAperture",
      "geometry_ref": "face_beam_left"
    },
    {
      "id": "beam_right",
      "type": "BeamAperture",
      "geometry_ref": "face_beam_right"
    },
    {
      "id": "axis_field_monitor",
      "type": "FieldMonitor",
      "quantity": "Ez_on_axis"
    }
  ]
}
```

---

## 8. Phase 1 推荐任务拆分

### Phase 1A：导入式 500 MHz baseline 复现

目标：

```text
不做几何生成，只做导入现成模型并复现 CST 主模结果。
```

任务：

```text
1. 准备 baseline CST 或 STEP
2. 建立 DesignPackage v0
3. 人工标注最小 feature_graph
4. 编写 CSTTranslator v0
5. 自动运行 eigenmode
6. 解析频率、R/Q、Epk/Hpk 等主模指标
```

退出标准：

```text
自动生成或复现 CST 工程；
主模结果与现有手工流程一致；
results.json 可被现有优化框架读取。
```

### Phase 1B：从现有 CST 工程抽取语义

目标：

```text
把手工 CST 工程中的设置逐步显式化。
```

任务：

```text
1. 列出现有 CST 工程中的 solids/components/faces/ports/monitors
2. 将其映射到 feature_graph
3. 将边界和求解器设置映射到 simulation_recipe
4. 将 mesh 设置映射到 mesh_recipe
5. 将后处理操作映射到 postprocess_recipe
```

退出标准：

```text
现有 CST 工程中的关键手工设置可以在设计包中找到对应配置。
```

### Phase 1C：X-band 2.3-cell gun 语义验证

目标：

```text
验证 feature graph 是否能表达更复杂 RF 对象。
```

新增 feature 类型：

```text
CathodeSurface
GunCell
HalfCell
FullCell
BeamExit
InputCouplerPort
HighFieldRegion
MeshRefinementRegion
```

退出标准：

```text
X-band gun 能通过设计包自动或半自动重建 CST 主模仿真流程。
```

---

## 9. 推荐的长期 Stage / Phase 路线

### Stage 1：Solver-Ready Semantic Design Package

目标：

```text
导入式 baseline + 语义标注 + CST 自动复现。
```

### Stage 2：Parametric Geometry Backend 接入

目标：

```text
用 OpenCASCADE/CadQuery 或简单自研 profile builder 生成几何。
```

### Stage 3：主模自动优化闭环

目标：

```text
接入已有优化框架，完成参数化主模自动优化。
```

### Stage 4：Template-Based Cavity Grammar Library

目标：

```text
通过 case/template 方式逐步沉淀腔型语法。
```

### Stage 5：Geometry Freedom Release

目标：

```text
椭圆弧 → 混合曲线 → Bézier/NURBS → 局部扰动。
```

### Stage 6：RF 扩展

目标：

```text
HOM、外部 Q、wakefield、multipacting 等。
```

### Stage 7：多物理场扩展

目标：

```text
thermal、mechanical、cooling、detuning、stress 等。
```

---

## 10. 当前优先级排序

```text
P0：DesignPackage v0 schema
P1：FeatureGraph v0 schema
P2：SimulationRecipe / BoundaryRecipe / MeshRecipe v0
P3：500 MHz baseline 导入式 CST 复现
P4：CSTTranslator v0
P5：ResultParser v0
P6：Existing Optimizer Bridge
P7：X-band 2.3-cell gun 语义验证
P8：GeometryBackend 抽象接口
P9：OpenCASCADE/CadQuery 几何接入
P10：Template-based Cavity Grammar Library
P11：自研混合几何内核
```

---

## 11. 结论

当前阶段最重要的不是立即实现完整几何生成器，而是把“几何文件”提升为“语义化设计包”。

在没有几何生成器的情况下，Phase 1 仍然可以通过导入现成 500 MHz baseline 模型推进：

```text
导入现成模型
  ↓
建立 geometry manifest
  ↓
人工/模板化 feature graph
  ↓
CSTTranslator 自动设置求解器
  ↓
ResultParser 标准化结果
  ↓
接入现有优化框架
```

Cavity Grammar、Geometry Synthesis、Feature/Assembly Graph 的关系可以总结为：

```text
Cavity Grammar：定义“这一类腔应该由什么组成”
Geometry Synthesis：把规则和参数变成实际几何
Feature/Assembly Graph：说明这些几何在 RF 工程和求解器中是什么意思
Solver Translator：把这些语义翻译成 CST 可执行设置
```

因此，第一阶段最合理的名称是：

```text
Stage 1：Solver-Ready Semantic Design Package
```

它一旦稳定，后续几何生成器、自学习腔型语法、HOM、多物理场和自研混合内核都可以在同一语义框架下逐步接入。
