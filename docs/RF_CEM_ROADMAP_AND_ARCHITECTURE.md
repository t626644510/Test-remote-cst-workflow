# RF-CEM 路线与架构：语义拓扑编译架构及 R0B–R5 Roadmap

**版本**：Roadmap 2.3
**日期**：2026-08-20
**用途**：供项目负责人、人类工程师和后续参与者复盘 RF-CEM 的目标、当前基础、架构决策、工作台设计及 R0B–R5 的阶段出门条件。
**适用范围**：RF 真空边界语义、边界表示、几何编译、腔族扩展、公共观测、工程约束、RF 结果/模态/场合同；暂不展开复杂曲线方程、可变维数优化、多物理场、HOM、耦合器和冷却结构的具体实现。

---

## 0. 阅读结论

RF-CEM 的最终目标不是建立一套固定参数名并让所有腔型在其中优化，也不是让通用 AI 凭空生成几何，而是建立一个面向加速器 RF 腔的领域计算工程系统：

```text
抽象规格与工程约束
        ↓
腔族语义与实例拓扑
        ↓
边界区域表示方法及其局部参数
        ↓
精确 RF 真空边界编译
        ↓
公共几何观测与工程约束
        ↓
RF 结果、模态与场验证
        ↓
后续优化、腔族扩展、多物理场和设计记忆
```

本轮讨论后，核心几何模型正式定义为：

\[
T_x=\operatorname{Instantiate}(F,M_x)
\]

\[
H_i=R_i(\theta_i)
\]

\[
G=\operatorname{Compile}\left(T_x,\{H_i\}\right)
\]

\[
O=\operatorname{Observe}(G,T_x)
\]

其中：

- \(F\)：某一腔族允许的语义语法；
- \(M_x\)：具体实例采用的可选或替代 semantic motif；
- \(T_x\)：具体实例的 RF 真空边界语义拓扑；
- \(R_i\)：某个语义区域采用的数学边界表示；
- \(\theta_i\)：该表示内部的局部参数；
- \(H_i\)：一个语义区域生成的几何，允许包含一条或多条 patch；
- \(G\)：编译后得到的精确几何；
- \(O\)：从最终几何和语义拓扑中提取的公共观测。

统一的是：

- RF 边界区域的工程语义；
- 区域之间的拓扑和接口；
- landmark；
- 连续性与几何不变量；
- 公共观测及工程约束。

不统一的是：

- 所有腔型的参数名；
- 每个区域的参数维数；
- 曲线方程；
- NURBS 控制点数量；
- patch 的内部数学表达；
- 优化变量集合。

---

## 1. 项目原始目标与本次修正

### 1.1 原始目标

RF-CEM 原始愿景是把类似 LEAP 71 / Noyron 的“计算工程模型”思想迁移到加速器腔领域。用户输入工作频率、模式、R/Q、峰值场、HOM、热、结构、冷却和制造等抽象要求，系统内部通过领域知识、精确几何、求解器接口和优化生成可验证的工程设计。

其核心不是“自动画图”，而是：

```text
抽象规格
→ 精确几何
→ 仿真接口
→ 指标解析
→ 优化回写
→ 可积累的设计记忆
```

### 1.2 早期 500 MHz 优化算例的定位

500 MHz 参数化单腔与已有优化器的衔接，原本只是一个 integration spike，用于验证：

```text
RF-CEM 参数化几何
+
CST 自动化
+
既有优化器与 evaluation 体系
```

能否形成真实计算循环。

该目标已完成。60/60 campaign 证明链路能够运行。项目并不需要继续追逐 candidate 039/046 的工程性能，也不需要为了这个早期算例继续完善目标函数、生产级恢复和长期 campaign 生命周期。

因此正式关闭：

```text
S0：RF-CEM / Optimizer Integration Spike
状态：CLOSED
用途：历史回归与接口证据
```

优化工作在 R5 的 RF 结果、模态、场和物理可比性合同完成后再重新进入。

---

## 2. 已确认的架构决策

### 2.1 Semantic Topology 与 Boundary Representation 独立

RF 真空边界语义由腔型决定，例如：

```text
BeamPipeRegion
IrisRegion
NoseRegion
OuterWallRegion
EquatorRegion
CathodeRegion
CellJunctionRegion
```

数学表示是独立模块，例如：

```text
LineRepresentation
CircularArcRepresentation
EllipseArcRepresentation
BezierRepresentation
NurbsRepresentation
AnalyticExpressionRepresentation
CompositeRegionRepresentation
```

`NurbsRepresentation` 不应知道自己正在表达 nose 还是 equator；`NoseRegion` 也不应知道自己必须由 NURBS、圆弧或某个固定参数集合生成。

### 2.2 Compiler 是唯一同时接触两侧的模块

推荐依赖方向：

```text
semantic  ←  compiler  →  representation
                       ↓
                 geometry kernel
```

约束：

- semantic 模块不得依赖 CadQuery、OCP、CST 或具体表示；
- representation 模块不得依赖 `NoseRegion`、`EquatorRegion` 或某个 family；
- compiler 负责排列、调用、拼接、检查和输出；
- observation 读取最终几何和语义拓扑，但不负责生成。

### 2.3 单向几何所有权

采用：

```text
SemanticRegion
    1 : 1
RegionGeometry
    1 : N
GeometryPatch
```

硬规则：

- 一个语义区域可以拥有多条 patch；
- 每条 patch 有且只有一个语义区域 owner；
- 一条 patch 不允许横跨多个语义区域；
- 跨区域连接通过共享的 `SemanticLandmark` 和 `BoundaryInterface` 表达；
- 多个相邻 patch 可以共同表达一个语义区域。

不采用 patch 与 semantic region 的多对多 binding。

### 2.4 语义区域、几何 patch、数值采样三层分离

```text
Semantic Region
    RF 工程意义的区域，数量少且稳定

Geometry Patch
    数学表示或几何内核需要的分段

Numerical Sampling
    拟合、显示、比较或求解时的采样点
```

采样加密不允许导致 semantic region 数量增加，也不应自动增加 patch。

只有出现以下情况时才增加 patch：

1. 表示类型发生变化；
2. 连续性等级发生变化；
3. 必须保留的 landmark；
4. 参数域奇点、极值或不可跨越的分支；
5. 几何内核、制造或求解器明确要求；
6. 单一 representation 无法稳定表达区域。

采用“最小充分分段”原则，并为每个 `RegionGeometry` 记录 patch 数量、参数数量和复杂度预算。

### 2.5 Family、Motif、Instance 分层

#### Family

描述一个允许的语义结构空间，不是固定拓扑和固定参数模板。

#### Semantic Motif

描述可选、替代或可重复的结构，例如：

```text
nose
reentrant_nose
flat_cathode
rounded_cathode
inter_cell_iris
tapered_beam_pipe
```

#### Instance

选择具体 motif，形成具体 `InstanceBoundaryGraph`。

当前两个实例的主要验证意义是：

```text
SLS-2：nose absent
RF500：nose present
```

无 nose 的实例中不允许创建一个值为 null、0 或 disabled 的假 nose 节点；它在拓扑中应真正不存在。

### 2.6 当前 family profile 的重新定位

已完成的 `family_profile.v0` 是重要基础，但其正确定位是：

```text
Source Instance / Provenance Contract
```

它负责保留：

- 原生参数 schema；
- 参数组和数量；
- 单位；
- 未知字段；
- 源 manifest；
- hash；
- validation layers；
- source-native round trip。

它不是最终的 `Family Semantic Grammar`。

后续新增：

```text
family_grammar.v0
instance_boundary_graph.v0
region_geometry.v0
compile_record.v0
observation_bundle.v0
```

而不是把两个实例进一步压缩为固定公共参数名。

### 2.7 公共观测空间三层结构

#### 第一层：Exact Native Geometry

用于精确重建：

```text
representation implementation
theta
equation / control points / knots
B-Rep / STEP
source and build provenance
```

#### 第二层：Semantic Shape Observation

按 semantic region 观察：

```text
normalized arc coordinate
z(s), r(s)
tangent, normal, curvature
extrema
convexity
monotonic intervals
semantic landmarks
```

用于图匹配、形状区分、相似度、OOD 和 family induction。

#### 第三层：Scalar Engineering Descriptors

用于人类工程约束、查询、快速筛选和后续优化：

```text
total_cavity_length
maximum_radius
minimum_aperture_radius
vacuum_volume
surface_area
nose_tip_radius
equator_maximum_radius
region_arc_length
minimum_radius_of_curvature
nose_present
cell_count
```

工程师提出的“总腔长在某范围”“最大半径在某数值附近”等限制，应主要落在第三层，而不是转化成统一生成参数。

---

## 3. 当前项目基础

### 3.1 已完成资产

当前已经具备：

- 500 MHz 参数化 RF 真空几何生成；
- CadQuery/OCP STEP 输出；
- CSTTranslator 和已验证的 eigenmode 设置路径；
- frequency、R/Q、Q perturbation 读取；
- 60/60 early optimization campaign；
- STEP Feature Assistant；
- CST history extractor；
- 文献语义、证据和人工审核流程；
- SLS-2 几何生成与冻结审核实例；
- SLS-2 和 RF500 的两实例 `family_profile.v0`；
- source-native lossless round trip；
- manifest、artifact、locator、scope 和 hash 的 fail-closed 绑定；
- 现有本地审核 HTML、Plotly 视图和 loopback review server。

### 3.2 当前真正缺失的横向核心

仍未正式建立：

- `FamilyGrammar`；
- `InstanceBoundaryGraph`；
- semantic motif；
- 表示无关的 `BoundaryRepresentation` 协议；
- 通用 `Compile(T,{Ri,θi})`；
- 单向 region→patch 所有权；
- graph alignment 和 family induction；
- 规范化公共观测和工程约束合同；
- 完整 RF result/mode/field contract；
- 系统性的 RF-CEM Workbench。

### 3.3 当前分支状态

当前 Stage C 分支：

```text
codex/rf-cem-family-profile-v0
```

相对：

```text
workflow/rf-cem-literature-review
```

仍领先 9 个提交。下一轮新架构开发前，应先把 Stage C 作为一个完整大阶段收口到 canonical owner，再建立新 phase 分支。

---

## 4. RF-CEM Workbench

### 4.1 定位

Workbench 不是美化层，也不是单次审核 HTML，而是项目的人类可见读模型和进度控制台。

它应回答：

- 已有哪些 family、instance、semantic、motif；
- 已有哪些 representation 和算法；
- 每个对象的实现、测试、使用和审核状态；
- 每次 compile 是怎样发生的；
- 哪些 gate 已通过；
- 哪些资产仍为空白；
- 哪些结论来自 no-CST、live-CST 或 physical acceptance。

### 4.2 真值关系

```text
Canonical source artifacts
        ↓ index / validate
Derived Registry Database
        ↓ query
RF-CEM Workbench
```

SQLite 是可删除、可重建的查询层，不是第二真值源。

任何时候都应允许：

```text
delete workbench.sqlite
→ re-index canonical sources
→ obtain equivalent registry state
```

### 4.3 第一版核心实体

```text
family
instance
semantic_type
semantic_motif
landmark_type
representation
algorithm
boundary_graph
region_geometry
compile_record
observation
constraint
review
validation_record
roadmap_gate
artifact
```

### 4.4 第一版页面

1. Overview；
2. Families；
3. Instances；
4. Semantics；
5. Representations；
6. Algorithms；
7. Compile Records；
8. Reviews；
9. Coverage Matrix；
10. Roadmap / Gates。

### 4.5 Compile Record

每次几何编译都必须形成可观察记录，至少包含：

```text
compile_id
family_id
instance_id
family_grammar_version/hash
instance_graph_version/hash
compiler_version
region_geometry bindings
representation implementations
parameter payload references
patch ownership
landmarks
interface/continuity checks
geometry validation
output artifact references/hashes
warnings
status
parent compile / comparison target
```

### 4.6 Workbench 安全边界

W0 首版：

- no-CST；
- loopback-only；
- read-only 或 read-mostly；
- 不提供任意文件浏览；
- 不直接修改 grammar/ontology；
- 不覆盖 frozen session；
- 不启动 solver；
- 写操作只生成 proposal、annotation 或 review event。

---

## 5. 阶段 Gate 分类

为了兼顾开发速度与工程可靠性，所有出门条件分为三类。

### 5.1 Hard Gate：必须满足

只在以下问题上阻塞 phase 收口：

- 数据可能损坏或丢失；
- schema 或接口无法表达目标；
- semantic/representation 依赖方向被破坏；
- graph、compile、geometry 或物理结果不正确；
- 目标模块的 targeted tests 稳定失败；
- 无法重建必要的 canonical source；
- 工作台显示的状态与 canonical source 相矛盾；
- 声称了没有证据支持的验证状态。

### 5.2 Closeout Gate：阶段末集中修复

开发过程中可以记录，阶段末一次性处理：

- 文档描述轻微漂移；
- 非关键 hash 记录遗漏；
- UI 文案、布局和小型显示问题；
- 未修改区域的 lint；
- 不影响主要能力的历史链接；
- 测试报告格式；
- README 中的计数和日期。

### 5.3 Deferred：明确延期

不应阻塞当前 phase：

- UI 美学；
- 高级动画；
- 所有 curve representation 一次性覆盖；
- 完整多用户权限；
- 云部署；
- 所有历史 artifact 的重新打包；
- 为小文档修改重新生成冻结 proof；
- 早期 500 MHz 优化性能提升。

---

# 6. Roadmap：R0B–R5

---

## R0B：Architecture Re-baseline + Workbench Foundation

### 目标

把本轮讨论形成正式架构，并建立项目级可见性基础。R0B 不要求迁移所有现有几何生成代码，只要求冻结模块边界、数据真值关系和可扩展接口。

### 主要产物

```text
architecture decision record
semantic package skeleton
representation package skeleton
compiler package skeleton
observation package skeleton
workbench registry/indexer/server
SQLite derived read model
roadmap/gate registry
documentation consolidation
```

建议包结构：

```text
src/rf_cem/
  semantic/
  representation/
  compiler/
  observation/
  workbench/
```

### Workbench W0

必须能索引并显示：

- 当前 family profile；
- SLS-2 与 RF500；
- 已有 semantic/Feature 候选；
- 当前曲线/几何实现和算法；
- validation layers；
- roadmap 和 gate；
- 已有审核 session 的入口；
- compile record schema，即使第一批 record 来自 legacy adapter。

### Hard Exit Gate

1. Stage C 分支已完成大阶段收口，并进入 canonical owner 或形成明确的单一 canonical HEAD。
2. semantic 不依赖 representation、geometry kernel 或 CST。
3. representation 不依赖具体 family 或 semantic 类型。
4. compiler 是唯一允许同时组合 semantic 和 representation 的核心模块。
5. observation 不负责几何生成。
6. SQLite 可删除并从 canonical sources 重建。
7. W0 至少显示 family、instance、semantic、representation/algorithm、validation、roadmap/gate。
8. SLS-2 和 RF500 能被索引，且来源和状态不混淆。
9. Workbench 只绑定本地地址，不提供 shell、CST 或任意文件浏览。
10. targeted no-CST tests 通过；现有 no-CST suite 不出现由本阶段引入的稳定回归。
11. canonical 文档集合已确定，重复状态文档已删除、归档或标记 superseded。
12. 形成一个 phase closeout commit，并在阶段结束时统一 push。

### 非目标

- 不实现完整 family grammar；
- 不重写现有 SLS-2/RF500 generator；
- 不启动 CST；
- 不做 graph induction；
- 不设计复杂方程表示；
- 不追求 UI 美学。

---

## R1：RF Boundary Semantic Core

### 目标

建立表示无关的 RF 真空边界语义和拓扑合同，以 SLS-2 与 RF500 验证“同 family、不同 semantic topology”。

### 主要产物

```text
family_grammar.v0
instance_boundary_graph.v0
semantic_region ontology
semantic_landmark ontology
boundary_interface contract
semantic_motif model
graph validator
graph diff
SLS-2 instance graph
RF500 instance graph
Workbench W1 semantic graph pages
```

### 核心语义

第一版至少覆盖：

```text
BeamPipeRegion
IrisRegion
GapShapingRegion
NoseRegion
OuterWallRegion
EquatorRegion
SymmetryBoundary / SymmetryLandmark
```

具体命名可由实现审计后调整，但语义应保持层级关系，避免把所有 family 强迫成相同叶节点。

### Hard Exit Gate

1. SLS-2 与 RF500 均有 schema-valid 的 `InstanceBoundaryGraph`。
2. SLS-2 图中不存在 `NoseRegion` 节点。
3. RF500 图中存在有证据绑定的 `NoseRegion` 节点。
4. 差异被表达为 topology/semantic difference，不是缺失参数或 `nose_enabled=false`。
5. 初始 `FamilyGrammar` 能合法接受有 nose 和无 nose 两种实例。
6. nose 被表达为 optional motif 或等价的可选拓扑规则。
7. 无效 cardinality、非法邻接和断裂 topology 能 fail closed。
8. 每个 semantic region 有稳定 ID、类型、证据/来源和审核状态。
9. graph diff 能显示共同主干、nose 差异和邻接位置。
10. Workbench 能可视化 family grammar、两个 instance graph、nose present/absent 和 diff。
11. 不要求任何公共生成参数。
12. targeted tests 与 no-CST regression gate 通过。
13. 阶段收口时统一 push；不为每个 schema 小改动单独 push。

### 非目标

- 不自动从原始 STEP 完全无监督识别所有语义；
- 不完成 family induction；
- 不完成几何编译迁移；
- 不建立 RF metric contract。

---

## R2：Boundary Representation Core + Compiler v0

### 目标

正式实现：

\[
G=\operatorname{Compile}\left(T_x,\{R_i(\theta_i)\}\right)
\]

并把 semantic topology 与数学边界表示彻底解耦。

### 主要产物

```text
BoundaryRepresentation protocol
RegionGeometry
GeometryPatch
one-way patch ownership
BoundaryInterface / landmark resolver
profile compiler
geometry validator
compile_record.v0
legacy generator adapters
Workbench W2 compiler trace
```

### 第一批内置表示

只要求足够覆盖当前真实实例：

```text
Line
CircularArc
EllipseArc
Spline/NURBS
CompositeRegionRepresentation
```

复杂解析方程、可变 patch 数量优化和 program synthesis 延后。

### Hard Exit Gate

1. representation 类不知道 nose、equator、SLS-2、RF500 或 family 名称。
2. semantic 模块不 import representation 实现。
3. SLS-2 和 RF500 通过同一个 compiler 入口生成几何。
4. 一个 semantic region 可以拥有 1..N 个 patch。
5. 每个 patch 有且只有一个 semantic region owner。
6. 不存在跨两个 semantic region 的单 patch。
7. 跨区域连接通过 landmark/interface 表达。
8. 编译输出具备确定的 region order、patch order 和 boundary orientation。
9. 需要的 C0/G1/G2 或项目定义连续性检查可执行并有报告。
10. profile 无自交、可封闭并能生成合法 B-Rep/STEP。
11. 与现有 SLS-2/RF500 generator 的基准输出在约定几何容差内一致，或差异被明确记录和人工接受。
12. source-native payload 和 Stage C provenance 不因迁移丢失。
13. 每次 compile 生成 `compile_record.v0`，且 Workbench 可浏览：
    - region→representation；
    - region→patch；
    -landmarks；
    - continuity；
    - geometry artifacts；
    - warnings。
14. 至少一个 representation 在两个不同 region 或两个不同 instance 中复用，证明其不是腔型专用类。
15. targeted tests、geometry tests 和 no-CST regression gate 通过。
16. 阶段收口时统一 push。

### 非目标

- 不进行 live-CST；
- 不优化 representation 类型；
- 不引入无限自由度复杂方程；
- 不实现 family induction；
- 不要求完美重构所有历史 candidate。

### 2026-08-20 实现状态

R2 已通过 PR #7 合入 `workflow/rf-cem-literature-review`，canonical merge commit 为 `e81ad20942258380cccb93d17cfdf0ca7e2d0e21`。`rf_cem.representation` 已实现与 family/semantic/CST 无关的 Line、CircularArc、EllipseArc、Spline/NURBS 和 Composite 合同；`rf_cem.compiler.ProfileCompiler.compile` 是 SLS-2 与 RF500 共用的唯一编译入口。

当前 no-CST 内容寻址证明为 `analysis_outputs/rf_cem_boundary_compiler/r2_boundary_compiler.aa66a3e90125437b/`，输入 SHA-256 为 `aa66a3e90125437b32ef900feb296f4512ee4a199b372474cb4c24fb7740813c`。SLS-2 编译为 9 个 `RegionGeometry` / 10 个 patch；RF500 编译为 11 个 `RegionGeometry` / 12 个 patch。所有 patch 均有唯一 owner，语义边界通过 landmark/interface 连接，region/patch 顺序和方向固定；同一原生曲线内部切分要求 G2，其余跨区域连接要求 C0，所有 required continuity gate 均通过。额外 G1/G2 诊断失败仅作为 warning 保存，不被误报为 required pass。

两条 profile 相对各自 source-native 曲线的最大偏差均为 `2.842170943040401e-14 mm`，声明容差为 `1e-6 mm`。SLS-2 还与已物化 frozen STEP 比较：最大 bbox 误差约 `3.37e-8 mm`，体积相对误差约 `1.95e-5`，表面积相对误差约 `3.33e-5`，均小于声明容差。RF500 已接受 STEP 只保留 raw SHA-256 `766365b6b78f3d0a6929f2500cfb49fc306e54be048a638bc813e9c8aeb9e3cd`，本地未物化，因此其 gate 明确限定为 source-native profile 等价、新 B-Rep 有效和未物化基线 warning，不声称完成旧 STEP 的几何量比较。

Workbench indexer 已升级到 `r2.w2.v0`；W2 从完整 W1 proof 与两份 `compile_record.v0` 重建，显示 region→representation→patch、landmark binding、C0/G1/G2、B-Rep/STEP validation、baseline、warning 与 hash-verified artifacts。真实重建包含 20 个 region geometry、22 个 patch、24 个 landmark binding 和 20 个 continuity check；loopback 浏览器验收无乱码、横向页面溢出或控制台错误。R2 全程 `live_cst_status=not_run`、`physical_acceptance_status=not_established`。

---

## R3：Family Induction / Extension v0

### 目标

从多个经过审核的 instance semantic graph 中自动提出 family grammar 的公共主干、optional motif 和 alternative topology；第一核心证明是 nose 差异。

### 主要产物

```text
graph alignment
common backbone detector
optional motif proposal
alternative topology proposal
family_extension_proposal.v0
proposal evidence/confidence
human review workflow
third-instance blind validation
Workbench W3 induction review
```

### 正确的“自动学习 nose”定义

系统不应把两个实例都压成相同参数模板。它应：

```text
T_SLS2 + T_RF500
    ↓ graph alignment
common backbone
    +
RF500-only NoseRegion
    ↓
proposal:
  NoseRegion is an optional motif
  inserted between specified neighboring semantic regions
```

这一步从 reviewed instance graphs 学习 family structure，不宣称已经从原始像素或 STEP 完全无监督地发现 RF 语义。

### Hard Exit Gate

1. 图对齐在不读取固定公共参数名的前提下运行。
2. SLS-2/RF500 对齐能识别共同主干。
3. 系统自动提出 nose optional motif，而不是 missing parameter。
4. proposal 包含：
   - source instance IDs；
   - graph locators；
   - insertion adjacency；
   - evidence；
   - confidence；
   - review status；
   - algorithm version。
5. proposal 默认不修改 canonical family grammar。
6. 人工接受后，通过显式 patch 更新 grammar，并重新验证全部已有实例。
7. 人工拒绝或 needs-evidence 后不影响正式 grammar。
8. 引入一个未参与规则开发的第三个真实 NC axisymmetric single-cell instance。
9. 第三个实例能够：
   - 映射到 nose present；
   - 或映射到 nose absent；
   - 或提出新的、可解释的 motif/topology extension。
10. 第三实例不得要求修改 representation 核心以适配腔型语义。
11. Workbench 显示 alignment、common backbone、proposal、review 和 grammar before/after diff。
12. targeted tests、blind fixture tests 和 no-CST regression gate 通过。
13. 阶段收口时统一 push。

### 非目标

- 不做统计意义上的大规模腔族学习；
- 不自动接受 proposal；
- 不从 RF 性能推导最优 motif；
- 不进入跨 family transfer。

### 2026-08-20 实现状态

R3 已在 `codex/rf-cem-r3-family-induction` 完成本地 Hard Gate、完整 no-CST regression 与浏览器验收，该分支从 R2 canonical merge `e81ad20942258380cccb93d17cfdf0ca7e2d0e21` 建立；phase closeout 尚待单次 push、PR 检查与 canonical merge。验证结果为 targeted 36 passed、explicit no-CST 762 passed/11 skipped、full default 762 passed/11 skipped；live CST 未运行。

`rf_cem_family_induction.v0` 只读取两个 reviewed `instance_boundary_graph.v0` 中有序的 `(side, region_type)` 和审计所需 source/hash，不读取 role、原生 feature/parameter 名或公共几何向量。SLS-2/RF500 产生 9 个 common-backbone slot 和 2 个 RF500-only `NoseRegion` residual；系统据此产生 `optional_motif` proposal，明确记录 `{0,2}` cardinality、左右 insertion adjacency、graph locator、evidence、限制、算法版本和 `0.95` evidence-completeness confidence。未成镜像配对的 residual 走经过测试的 `alternative_topology` 路径。

proposal 初始状态固定为 `pending` / `not_applied`。`rejected` 或 `needs_evidence` 返回原 grammar 的完全相同字节且不产生 patch/diff；只有显式 accepted manual review 可以产生 hash-bound patch。本次 closeout review revision 为 1；patch 对已有 `motif.nose_pair.v0` 执行 `confirm_optional_motif`，更新为 `family_grammar.r3.v0`，记录 6 项可视 diff，并重新验证 SLS-2/RF500。

第三个真实 blind case 是 BNL LEReC 704 MHz normal-conducting single-cell cavity。两份 primary PDF raw SHA-256 分别为 `d806257972ae33208f5244ed31e1329064d120b82491bc4cb9a9e6afb544ba82` 和 `01b6a72aedf32783568cec6e0ab567cd6870d7f4ec7a2e98558d24b790baffab`。adapter 只覆盖文献剖面可审查的 axisymmetric main-cell RF-vacuum wall，明确排除非轴对称 FPC/tuner/pickup/pump/flange。该 graph 在归纳和 patch 完成后才构建/分类，未出现在 training IDs，结果为 `known_optional_motif_present`；这不是 raw-pixel/STEP 无监督语义发现。

当前 no-CST 内容寻址证明为 `analysis_outputs/rf_cem_family_induction/r3_family_induction.2f6c02557798e606/`，输入 SHA-256 为 `2f6c02557798e6062e961d6dea3b4220e4d4076310579754567d570f6ae7c4f0`。两次 fresh test build 字节一致；strict loader 会重新验证 8 个 artifact 与全部 cross-contract identity。Workbench indexer 已升级为 `r3.w3.v0`，W3 必须从完整 W1 + W2 + 一个 R3 bundle 重建，并独立验证 training binding、manual review/patch、训练实例重验证、blind separation、两份 PDF 和未改变的 representation-core hash sentinel。`/family-induction` 显示 alignment、backbone、residual、pending proposal、accepted review、grammar diff 和 LEReC blind result。全程无 CST、无 RF metric、无 physical acceptance。

---

## R4：Boundary Observation & Engineering Constraint Contract

### 目标

建立表示无关的公共观测空间和工程师约束语言，使不同 representation、不同 patch 数量和不同原生参数体系仍可比较和受约束。

### 主要产物

```text
exact_geometry_reference.v0
semantic_shape_observation.v0
scalar_descriptor_registry.v0
observation_bundle.v0
engineering_constraint.v0
constraint_evaluation.v0
Workbench W4 observation/constraint pages
```

### 第一批全局描述符

```text
total_cavity_length
maximum_radius
minimum_aperture_radius
vacuum_volume
surface_area
semantic_region_count
nose_present
```

### 第一批区域描述符

```text
region_axial_extent
region_arc_length
region_maximum_radius
region_minimum_radius
minimum_radius_of_curvature
endpoint_tangent
endpoint_curvature
nose_tip_radius
equator_crest_radius
```

### Hard Exit Gate

1. SLS-2 与 RF500 均能从 compiled geometry 生成 observation bundle。
2. observation 不依赖实例原生参数名。
3. exact geometry、shape observation 和 scalar descriptors 三层明确分开。
4. descriptor 有单位、定义、算法版本和 provenance。
5. 非有限值、未知单位和无效 landmark fail closed。
6. 至少对一种相同几何的不同 patch 分段或不同 representation 进行测试，公共 descriptor 在规定容差内一致。
7. 工程师能表达并评价：
   - 总腔长范围；
   - 最大半径附近；
   - 最小 aperture；
   - 最小曲率半径；
   - nose presence；
   - 区域级约束。
8. constraint 支持 hard、soft、advisory/diagnostic 等作用方式。
9. constraint 只评价几何，不成为几何真值，也不静默修改 theta。
10. Workbench 能显示 descriptor、约束、违反位置和来源。
11. graph alignment 可使用 shape observation，但 exact geometry 不被采样表示替代。
12. targeted tests、cross-representation tests 和 no-CST regression gate 通过。
13. 阶段收口时统一 push。

### 非目标

- 不定义 RF 指标；
- 不启动 CST；
- 不做 optimization；
- 不要求完整制造规则库；
- 不设计所有未来 descriptor。

---

## R5：RF Result / Mode / Field Contract

### 目标

在几何身份、语义拓扑和公共观测已经稳定的基础上，重新建立可比较、可追溯的 RF 物理结果合同。R5 完成后才重新进入正式优化工作。

### 主要产物

```text
physics_case.v0
solver_recipe binding
mode_identity.v0
mode_fingerprint.v0
metric_contract.v0
metric_observation.v0
field_bundle.v0
mesh_convergence.v0
result_provenance.v0
Workbench W5 RF result/mode/field pages
```

### 第一批指标

核心：

```text
eigenfrequency
R/Q
Q perturbation
stored energy
Epk
Bpk
Epk/Eacc
Bpk/Eacc
surface loss
```

任何无法在当前 CST 路径下可靠定义的指标，应保持 `not_available` 或 `not_established`，不得以近似名称冒充。

### Mode Identity

不得只使用：

```text
Mode 1
```

至少绑定：

- frequency；
- field/symmetry fingerprint；
- R/Q 或相关标量；
- mode family/role；
- solver result locator；
- geometry compile record；
- physics case；
- 人工/自动判定状态。

### Hard Exit Gate

1. 每个 RF result 绑定：
   - family；
   - instance；
   - instance boundary graph；
   - compile record；
   - exact geometry artifact/hash；
   - physics case；
   - solver/version；
   - material；
   - boundary；
   - mesh；
   - mode identity；
   - result locator；
   - unit；
   - extraction method；
   - validation status。
2. `Q perturbation` 保留原生物理语义，不在无证据时改名为 Q0。
3. R/Q、Epk/Eacc、Bpk/Eacc 等量有明确 normalization 和 mode requirement。
4. 不同 material、boundary、mesh、normalization 或 mode identity 的结果默认 `not_comparable`，除非合同明确允许。
5. 至少对 RF500 形成一份完整、可重放的 live-CST RF bundle。
6. 至少一个代表性 case 完成多个 mesh level 的 convergence 记录。
7. mode identity 不依赖单一 mode index。
8. field bundle 采用外部 artifact + manifest/hash 引用，不把大场数据直接塞进 SQLite。
9. Workbench 能浏览：
   - physics case；
   - mode identity；
   - scalar metrics；
   - field artifact；
   - mesh convergence；
   - comparability；
   - validation layers。
10. SLS-2 若未建立 live-CST 链接，必须明确保持 `not_linked`，不阻碍其 geometry/semantic 状态。
11. R5 的 live CST 操作必须经过项目负责人明确授权，并使用副本和受控输出目录。
12. 正式优化 campaign 不属于 R5 出门条件；R5 完成后另立优化阶段。
13. targeted no-CST tests、bounded live-CST validation、result replay tests 和 regression gate 通过。
14. 阶段收口时统一 push。

### 非目标

- 不完成多物理场；
- 不做 HOM/wake；
- 不做 coupler/port；
- 不启动大规模优化 campaign；
- 不把一个 live case 当成 physical acceptance。

---

## 7. R5 出门后的系统状态

R5 完成时，RF-CEM 应具备：

```text
Family grammar
    ↓
Instance semantic topology
    ↓
Region-specific mathematical representations
    ↓
Generic geometry compiler
    ↓
Exact geometry + compile provenance
    ↓
Representation-independent observations
    ↓
Human engineering constraints
    ↓
Mode-identified, case-bound RF metrics and fields
    ↓
Human-visible Workbench
```

这时再进入：

- 正式优化；
- robust optimization/UQ；
- 第二 family；
- 多物理场；
- HOM/ports/couplers；
- cooling/auxiliary structures；
- design memory。

---

## 8. 开发节奏与版本策略

### 8.1 Push 策略

本项目采用个人项目的快速节奏：

- phase 内允许本地小提交或 checkpoint；
- 不为每个 schema 字段、hash、文档修正单独 push；
- 每个大 phase 通过 Hard Gate 后统一 push；
- 一个大 phase 对应一个主要远端分支和一次收口 PR/merge；
- 小型 closeout 修正并入该 phase，不开微型 PR。

### 8.2 Hash 策略

保持必要 provenance，但避免过度阻塞：

必须严格：

- canonical source；
- 外部证据；
- 冻结 manifest；
- exact geometry artifact；
- compile/result linkage；
- schema-breaking migration。

阶段内可延后：

- derived DB 行级 hash；
- UI cache hash；
- 文档计数；
- 不影响来源识别的可选 hash；
- minor code/doc change 后重建旧 proof bundle。

原则：

> Hash 用于证明对象身份和防止错误绑定，不用于让每个开发动作变成法证审计工程。

### 8.3 文档策略

建议 canonical 人类文档：

```text
README.md
CONTRIBUTING.md
AGENTS.md
docs/PROJECT_STATUS_CONTEXT.md
docs/AGENT_CONTEXT_RECOVERY.md
docs/FUNCTIONS_AND_ENTRYPOINTS.md
docs/CST_AUTOMATION_INTERFACES.md
docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md
```

Agent 长期目标放在：

```text
.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md
```

清理原则：

- 删除已被上述文档替代且可从 Git 恢复的旧 Markdown；
- 有历史价值但不再维护的内容放入已有 archive，而不是继续并行维护；
- 不创建按日期不断追加的小状态报告；
- 阶段状态更新到 `PROJECT_STATUS_CONTEXT.md`；
- CLI/API 更新到 `FUNCTIONS_AND_ENTRYPOINTS.md`；
- 恢复步骤更新到 `AGENT_CONTEXT_RECOVERY.md`；
- 架构与 roadmap 更新到本档案。

---

## 9. 当前状态与立即动作

1. Stage C 已通过 PR #4 合入 `workflow/rf-cem-literature-review`，canonical merge commit 为 `3867a9a8eae502359556a83bcad15b3a519e64de`；
2. R0B 已通过 PR #5 合入，canonical merge commit 为 `c0b4574ee2dc87ee98938b282ec023aeebfa12d3`；
3. R1 已通过 PR #6 合入，canonical merge commit 为 `5ae1ba07b841d6adf6e180ec1eedfd073657987b`；
4. R2 已通过 PR #7 合入，canonical merge commit 为 `e81ad20942258380cccb93d17cfdf0ca7e2d0e21`；
5. 当前 phase 分支为 `codex/rf-cem-r3-family-induction`，从上述 R2 canonical merge 建立；
6. 当前动作是完成 R3 单次 closeout push、PR 检查与 canonical merge；
7. R3 只建立 reviewed graph alignment、proposal/manual review/explicit patch、真实 blind validation 和 Workbench W3，不实现 observation/RF result contract 或优化搜索；
8. R3 不运行 CST，不建立 RF physical acceptance；只有 R3 Hard Gate 合入 canonical owner 后再从该 merge 建立 R4 分支；
9. canonical 架构档案仍为本文件，Agent 执行目标仍为 `.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md`。
