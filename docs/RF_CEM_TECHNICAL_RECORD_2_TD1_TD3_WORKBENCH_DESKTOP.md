# RF-CEM 第二次技术档案：TD1–TD3 技术债收敛与 Workbench 桌面化

**版本**：Technical Record 2 / Roadmap Addendum 2.4
**日期**：2026-08-26（PR #10 follow-up）
**用途**：供项目负责人在本轮开发完成后进行人工复盘，记录连续性合同、样条表示合同、R3 归纳边界以及 Workbench 桌面封装的最终决策。
**实现状态**：本档案定义的 TD1–TD3 与 Desktop v0 已在同一 no-CST closeout 分支实现；最终 proof、测试与 Git 身份见本文末尾实施记录。
**本轮范围**：TD1 Continuity Contract、TD2 Spline Contract Rename、TD3 R3 Ablation / Score Refactor、Workbench Desktop v0。
**明确排除**：R5 live-CST、RF 指标扩展、CST/COMSOL/自研求解器 Translator 深化、大规模语义自学习模块的正式实现。

---

## 0. 本轮决策摘要

本轮确认以下四项结论：

1. **连续性要求由合同决定，不再由 `source_native_segment_ref` 推断。**
2. **同一 SemanticRegion 内部的 patch join 默认要求 G1；跨 SemanticRegion 的接口默认 G1，少数有意角点允许 C0，G2 只作为可扩展等级而非通用默认。**
3. **当前曲线实现应准确命名为近似样条表示，而不是完整 exact NURBS；保留现有 1 μm 拟合容差和优化能力，暂不实现完整 NURBS 内核。**
4. **R3 的职责是从多个 ReviewedInstanceBoundaryGraph 归纳 FamilyGrammar；原始文字、图片、表格、人工提示和偶尔存在的 STEP 到语义图的学习，单独建立 Semantic Graph Acquisition 模块，暂不塞入 R3。**
5. **Workbench Web 保持只读；增加一个 Windows 桌面启动器 EXE，负责启动、重建、状态检查和常用安全操作。**

总体关系保持：

\[
\hat T_x=\operatorname{Acquire}(E_x)
\]

\[
T_x=\operatorname{Review}(\hat T_x)
\]

\[
F_{k+1}=\operatorname{Induce}(F_k,\{T_x\})
\]

\[
G=\operatorname{Compile}(T_x,\{R_i(\theta_i)\})
\]

其中：

- `Acquire` 属于未来独立模块；
- `Review` 输出 R3 可消费的 Reviewed Graph；
- `Induce` 属于 R3；
- `Compile` 属于 R2；
- 本轮只修复这些模块之间的合同边界，不实现 `Acquire`。

---

# 1. R5 暂停与后续记录

R5 后续工作暂缓。

原因不是 R5 合同方向错误，而是 RF 物理结果的自由扩展需要针对不同求解器进行 Translator 级设计，包括但不限于：

```text
CST Translator
COMSOL Translator
未来自研 RF Solver Translator
```

每个 Translator 需要分别定义：

- solver recipe；
- material/boundary/mesh；
- mode identification；
- result locator；
- field export；
- normalization；
- metric extraction；
- solver-specific validation；
- cross-solver comparability。

现有 CST Translator 已覆盖特定物理量和既有路径，但还不是自由扩展的通用 RF 结果翻译层。该任务需要较多人工物理判断，不适合作为本轮无人辅助单 Agent 目标。

因此：

```text
R5 no-CST readiness：保留
R5 live validation：暂停
R5 translator generalization：未来单独立项
```

本轮不得：

- 启动 CST；
- 修改许可证；
- 生成新的 live RF 结果；
- 扩展 RF metric；
- 进行 mesh convergence；
- 继续 R5 Stage A/B。

---

# 2. TD1：Continuity Contract

## 2.1 当前问题

当前 Compiler 对所有相邻 patch 计算：

```text
C0 gap
G1 tangent angle
G2 curvature delta
```

但 required level 的选择由以下规则决定：

```text
相邻 patch 的 source_native_segment_ref 相同
    → required G2

否则
    → required C0
```

这存在三个问题：

1. `source_native_segment_ref` 是来源溯源，不是工程连续性意图；
2. G1 虽被计算，但永远不能成为 required level；
3. G2 对普通 RF 设计过严，例如直线与圆弧相切通常应接受 G1，而不要求曲率相同。

## 2.2 `source_native_segment_ref` 的最终定位

该字段继续保留，用于：

```text
source provenance
source curve partition audit
patch difference tracing
native geometry replay
```

不再用于决定：

```text
required continuity level
```

原则：

```text
来自同一个 source segment
≠ 必须 G2

来自不同 source segment
≠ 只需要 C0
```

## 2.3 连续性层级

### C0：位置连续

两条曲线端点重合，无几何裂缝。

适用于：

- intentional corner；
- port cut；
- flange edge；
- cathode edge；
- 明确允许的几何折角。

### G1：切向连续

端点重合且切向方向一致。

适用于：

- 常规 RF 真空壁；
- 直线接圆弧；
- 圆弧接 spline；
- 同一 semantic region 内部的多 patch 组合；
- 大部分跨 semantic RF wall interface。

### G2：曲率连续

在 G1 的基础上，曲率也连续。

适用于：

- 特别要求平滑曲率过渡的局部；
- 未来明确声明的高级 geometry policy；
- 不作为当前 family 的通用默认。

## 2.4 三类合同

### A. Representation Internal Join Contract

同一个 `SemanticRegion` 内部的 patch join：

```yaml
required_continuity: G1
enforcement: hard
```

本轮不再根据 source segment、representation type 或 patch 来源区分。

### B. Semantic Interface Contract

不同 `SemanticRegion` 之间：

```yaml
default_required_continuity: G1
```

允许显式覆盖：

```yaml
required_continuity: C0 | G1 | G2
intentional_corner: true | false
rationale: ...
```

初版策略：

```text
普通 RF wall interface：G1
明确 intentional corner：C0
G2：保留接口，无通用默认
```

### C. Endpoint Constraint

profile 起点、终点或 port termination 没有左右两条 patch，不应伪装成 continuity join。

单独表达：

```text
position
radius
normal/tangent
termination plane
endpoint role
```

## 2.5 推荐合同形态

建议新增独立版本化合同：

```text
boundary_continuity_policy.v0
```

示意：

```yaml
schema_version: boundary_continuity_policy.v0
family_id: nc_axisymmetric_single_cell_rf_vacuum

internal_patch_policy:
  required_continuity: G1
  enforcement: hard

semantic_interface_policy:
  default_required_continuity: G1
  enforcement: hard

interface_overrides:
  - interface_role: intentional_corner
    required_continuity: C0
    intentional_corner: true

supported_levels: [C0, G1, G2]
```

该合同属于 semantic/compile interface intent，不依赖具体 curve class。

## 2.6 Compiler 行为

Compiler 对每个 join 仍计算完整诊断：

```text
C0
G1
G2
```

但 required level 来自：

```text
within_region
    → internal patch policy

cross_region
    → matching semantic interface override
      or family default
```

`ContinuityCheck` 增加：

```text
requirement_source
policy_ref
intentional_corner
```

例如：

```text
internal_patch_default
semantic_interface_default
semantic_interface_override
```

## 2.7 TD1 出门条件

1. `source_native_segment_ref` 不再参与 required level 判定。
2. 所有 within-region patch join 默认 G1 hard。
3. 所有 cross-region RF wall join 默认 G1 hard。
4. 支持显式 C0 override，并至少有一个 synthetic intentional-corner test。
5. 支持 G2 contract，但当前真实实例不因缺少 G2 而失败。
6. Endpoint 不被错误建模为双侧 continuity join。
7. Compiler 继续记录 C0/G1/G2 全部诊断。
8. `compile_record` 能显示 required level、来源与 policy reference。
9. SLS-2 与 RF500 no-CST 编译均通过新合同。
10. 旧 `compile_record.v0` 和旧 proof 可继续读取，或提供明确兼容迁移读取器。
11. Workbench W2 能显示 interface requirement 与实际诊断。
12. 不运行 CST。

---

# 3. TD2：Spline Contract Rename

## 3.1 当前实现的真实含义

当前 `SplineNurbsRepresentation` 保存：

```text
degree
fit_points
control_points
backend_point_source
fitting_contract
approximation_tolerance_mm
```

最终 CadQuery/OCCT 使用：

```text
splineApprox(points, tolerance=0.001 mm, max degree=...)
```

因此：

- 使用的是标准 CAD 样条拟合；
- 1 μm 容差对当前腔体尺度可接受；
- 可通过点坐标、degree 和控制策略进行有效黑箱优化；
- 但 RF-CEM 没有保存 exact NURBS 的 knots、weights、multiplicity、periodicity 和解析参数域。

## 3.2 准确命名

当前实现应改称：

```text
SplineApproxRepresentation
```

或等价准确名称。

不再把它展示为：

```text
完整 Exact NURBS
```

推荐能力声明：

```yaml
representation_family: spline
fidelity: approximate
backend_contract: cadquery.splineApprox.v0  # source representation contract
approximation_tolerance_mm: 0.001
optimization_ready: true
exact_nurbs: false
```

该字段描述无端点约束时的 source representation realization，不代表 Compiler 必须忽略 semantic continuity plan。若 Compiler 为某个 endpoint 生成方向约束，实际构造合同另记为 `cadquery.spline.tangent_constrained.v0`；两者必须在 compile record 中分开保存。

## 3.3 字段命名

建议把容易误解的字段调整为：

```text
fit_input_points
source_control_point_hints
max_degree
backend_contract
approximation_tolerance_mm
```

避免把输入拟合点直接称为最终 exact NURBS poles。

## 3.4 未来 Exact NURBS

只保留未来合同接口，不要求本轮实现：

```text
degree
poles
weights
knots
multiplicities
periodic
parameter_range
```

Workbench 可以显示：

```text
ExactNurbsRepresentation
status: planned_not_implemented
```

但不得暴露一个看似可用、实际没有 backend 的假实现。

## 3.5 兼容策略

必须保留：

```text
现有 proof 可读
现有 SplineNurbsRepresentation Python API 可迁移
旧 representation_type 可兼容解析
```

推荐：

```text
SplineNurbsRepresentation
    → deprecated compatibility alias

SplineApproxRepresentation
    → 新 canonical class/name
```

新输出使用准确名称；旧输出由兼容 loader 读取。

不要求为轻微命名变更反复重建全部历史 proof。

## 3.6 TD2 出门条件

1. 新 canonical 名称准确表达 approximation。
2. 新对象明确记录 `fidelity=approximate` 和 backend contract。
3. 现有 1 μm 容差不被无理由修改。
4. 现有可优化自由度继续有效。
5. 旧 schema/proof/record 可读。
6. Workbench 显示 approximation、backend、tolerance、optimization-ready。
7. Workbench 不再把当前实现表述为完整 exact NURBS。
8. Exact NURBS 仅作为未来能力记录，不创建误导性 runtime implementation。
9. SLS-2/RF500 编译和 R4 observation 回归通过。
10. 不运行 CST。

---

# 4. TD3：R3 Ablation / Score Refactor

## 4.1 R3 的最终职责

R3 只负责：

```text
多个 ReviewedInstanceBoundaryGraph
    ↓
graph alignment
    ↓
common backbone
    ↓
optional / repeated / alternative motif proposal
    ↓
human review
    ↓
FamilyGrammar patch
```

它不负责：

```text
原始文字理解
图片理解
STEP 自动切分
region candidate 生成
semantic 命名
ontology invention
```

这些属于未来独立模块：

```text
Semantic Graph Acquisition
```

## 4.2 目前 R3 的限制

当前 nose 归纳依赖：

```text
同一实例两个 residual
一个 left
一个 right
插入位置对应
其他实例不存在
```

因此更准确地说，当前实现是：

```text
PairedOptionalMotifDetector
```

而不是通用 induction engine。

当前 scalar confidence 也是确定性证据完整度评分，不是概率。

## 4.3 Reviewed Graph 与 Family Admission 分离

为了真正发现 grammar 中尚不存在的 motif，需要允许：

```text
ReviewedInstanceBoundaryGraph
```

在 R3 输入阶段暂时不符合 seed grammar。

因此应区分：

### Intrinsic Reviewed Graph Validation

检查：

- ontology type 合法；
- graph topology 自洽；
- evidence 完整；
- review terminal；
- landmark/interface 合法；
- ID 唯一；
- 不要求 seed grammar 已接受所有 motif。

### Family Admission Validation

检查：

```text
graph 是否符合当前 FamilyGrammar
```

流程：

```text
Reviewed Graph
→ R3 proposal
→ accepted grammar patch
→ family admission
```

## 4.4 Grammar Ablation Test

从 seed grammar 中删除：

```text
motif.nose_pair.v0
NoseRegion cardinality
Nose insertion adjacency
```

保留 RF500 reviewed graph 中的：

```text
NoseRegion
```

预期：

```text
SLS-2 + RF500
→ common backbone
→ NoseRegion residual
→ optional motif proposal
→ accepted review
→ add_optional_motif
→ both graphs admitted
```

该测试证明：

> R3 可以从已审核实例差异中新增 grammar motif，而不是只确认 R1 已预置的 motif。

它不声称能从原始 STEP/PDF 发现 nose。

## 4.5 Detector 架构

建议重构为：

```text
FamilyInductionEngine
    ├── PairedOptionalMotifDetector
    ├── SingleOptionalMotifDetector
    ├── AlternativeTopologyDetector
    └── future detectors
```

本轮至少实现：

1. 当前 paired optional detector；
2. 一个最小 `SingleOptionalMotifDetector` synthetic fixture，证明 induction engine 不把左右对称写死为全局本质；
3. fallback alternative topology proposal。

真实 family 不需要在本轮新增不对称 semantic。

## 4.6 Score / Support Refactor

将误导性的单一 `confidence` 改为：

```yaml
support:
  structural_match: ...
  evidence_completeness: ...
  review_coverage: ...
  cross_instance_support: ...
  population_size: ...
  symmetry_assumption_used: true | false
  detector_id: ...
  detector_version: ...

proposal_score: ...
score_semantics: heuristic_support_not_probability
```

要求：

- score 是 proposal ranking/support；
- 不宣称统计概率；
- 显示样本数量；
- 显示是否使用 symmetry assumption；
- 允许不同 detector 使用不同 support 分量；
- Workbench 能展开显示各项支持度。

## 4.7 兼容策略

现有 R3 proof 不得被静默覆盖。

可以：

- 保留 v0 loader；
- 新 proposal 使用 v1；
- Workbench 同时索引 v0/v1；
- 新 ablation proof 使用新的 content-addressed bundle；
- 不因小型文档变更重建旧 proof。

## 4.8 TD3 出门条件

1. R3 输入可接受 intrinsic-valid、尚未 family-admitted 的 reviewed graph。
2. seed grammar ablation 后，系统能提出 nose optional motif。
3. accepted review 使用 `add_optional_motif`，而不是 confirm。
4. patch 后 SLS-2 与 RF500 都通过 family admission。
5. rejected / needs-evidence 保持 grammar 不变。
6. detector 采用插件/策略接口，左右对称不再写死为 engine 全局前提。
7. 至少有一个 synthetic single optional motif test。
8. scalar probability-like confidence 被结构化 support 取代。
9. score 明确标注 `not_probability`。
10. Workbench W3 显示 detector、support、ablation before/after grammar diff。
11. 现有 R3 v0 proof 仍可读取。
12. 不实现原始证据到 semantic graph 的学习。
13. 不运行 CST。

---

# 5. 未来独立模块：Semantic Graph Acquisition

本轮只记录，不实施。

## 5.1 输入

未来主要输入预计是：

```text
论文正文
图像
图注
表格
专利/报告
人工提示
已有 ontology
偶尔存在的 STEP
```

## 5.2 输出

```text
instance_boundary_graph_candidate.v0
        ↓ human review
reviewed_instance_boundary_graph.v0
        ↓ R3
family-admitted instance_boundary_graph.v0
```

## 5.3 记录的设计原则

未来规划时保留以下原则：

- pre-semantic boundary signal；
- finite landmark candidate pool；
- multi-scale stability；
- MDL complexity penalty；
- CEGIS / validator feedback；
- split / merge / relabel joint search；
- representation novelty；
- topology novelty；
- semantic novelty；
- low confidence 只产生 unknown candidate；
- semantic novelty 需要跨实例复现；
- R4 的通用几何分析内核可复用，但语义专用 descriptor 不可用于循环论证。

该模块单独规划，不叫 R3.5，不作为本轮出门条件。

---

# 6. Workbench Desktop v0

## 6.1 目标

用户不再需要记忆和输入长命令。

目标体验：

```text
双击 RF-CEM-Workbench.exe
    ↓
自动定位仓库与配置
    ↓
检查数据库和 source status
    ↓
必要时自动重建
    ↓
启动本地 Workbench
    ↓
自动打开浏览器
```

同时保留一个小型 Windows 控制面板，提供固定按钮。

## 6.2 架构原则

Workbench Web 继续保持：

```text
read-only
GET-only
loopback-only
token-authenticated
no shell
no CST
```

Desktop Launcher 负责有限操作：

```text
desktop launcher
    ↓ fixed allowlisted actions
existing Python API / CLI
    ↓
Workbench server and registry
```

不在 Web 页面中加入任意命令执行。

## 6.3 推荐实现

优先采用：

```text
Python stdlib + tkinter launcher
PyInstaller Windows EXE
```

第一版可采用 thin launcher：

- EXE 本身只负责 UI、配置、进程管理；
- 使用仓库 `.venv\Scripts\python.exe`；
- 调用固定的 `rf_cem.workbench` 模块；
- 不把 CadQuery/OCP/CST 全部打包进 EXE；
- 启动快、体积小、容易维护。

## 6.4 Portable Workbench Profile

新增 tracked portable recipe：

```text
workbench_profile.v0.json
```

包含仓库相对路径：

```text
database path
family profile
family grammar
instance graphs
graph diff
compile records
R3 bundle
R4 bundle
optional R5 bundle
architecture document
review sources
```

本地 launcher override 保存到用户目录，例如：

```text
%LOCALAPPDATA%\RF-CEM\workbench_launcher_config.v0.json
```

数据库和 proof 仍位于 ignored `analysis_outputs/`。

Workbench CLI 增加：

```text
rebuild --profile <profile>
status --profile <profile>
serve --profile <profile>
```

或功能等价的 typed API。

## 6.5 首次运行

Launcher 查找仓库顺序：

1. 显式 `--repo-root`；
2. EXE 所在目录及父目录；
3. 当前目录及父目录；
4. 已保存的 local config；
5. 文件夹选择框。

若：

```text
database fresh
    → 直接启动并打开浏览器

database missing/stale，sources 完整
    → 自动重建或显示“重建并打开”

sources missing
    → 显示缺失项，不崩溃、不伪造路径
```

## 6.6 首版按钮

必须提供：

```text
打开 / 启动 Workbench
重建数据库
刷新 Source Status
停止 Workbench
打开 Roadmap
打开 Project Status
打开 analysis_outputs
复制 Workbench URL
运行快速 no-CST Self Check
查看日志
```

约束：

- 无任意命令文本框；
- 无 shell injection；
- subprocess 使用 argument list 和 `shell=False`；
- 只能运行 allowlisted action；
- 不出现 CST 按钮；
- 不执行许可证、cleanup、process sweep；
- 只可停止 launcher 自己启动的 Workbench 子进程。

## 6.7 EXE 交付

提交：

```text
launcher source
profile schema/example
build script
tests
usage docs
```

本地生成但不提交：

```text
dist\RF-CEM-Workbench.exe
```

推荐构建脚本：

```text
scripts\build_rf_cem_workbench_desktop.ps1
```

EXE 必须支持：

```text
--self-test
--repo-root
--no-browser
```

便于无 GUI smoke test。

## 6.8 Workbench Desktop 出门条件

1. 双击 EXE 后无需手工输入命令即可打开 Workbench。
2. 首次运行能定位或选择仓库并保存配置。
3. fresh DB 直接打开。
4. missing/stale DB 能一键重建。
5. source 缺失时显示具体缺失项。
6. 固定按钮全部可用。
7. Web Workbench 保持只读。
8. Launcher 无任意 shell/命令输入。
9. Launcher 不提供 CST/live/R5 操作。
10. Launcher 可干净启动和停止其 own Workbench child。
11. 支持单实例或明确避免重复 server。
12. `--self-test` 通过。
13. 本地成功构建 Windows EXE。
14. 构建产物位于 ignored `dist/`，不提交二进制。
15. Workbench W0–W4 页面均可从 EXE 打开；若以后配置存在 W5，Launcher 无需重写即可显示。
16. 不运行 CST。

---

# 7. 实施顺序

```text
Stage Preflight
    ↓
TD1 Continuity Contract
    ↓
TD2 Spline Approx Contract
    ↓
TD3 R3 Ablation / Support Refactor
    ↓
Workbench Desktop v0
    ↓
Full no-CST closeout
```

一个阶段、一个分支、阶段末一次 push。

推荐分支：

```text
codex/rf-cem-td1-td3-workbench-desktop
```

推荐 base：

```text
workflow/rf-cem-literature-review
```

理由：

- R0B–R4 已合入 canonical；
- R5 当前暂停；
- 不将 R5 live 代码混入本轮技术债修复；
- `codex/rf-cem-r5-rf-result-field` 保持不动，后续另行处理。

---

# 8. 总体出门条件

本轮整体完成必须满足：

1. TD1、TD2、TD3 各自 Hard Gate 全部通过。
2. Workbench Desktop v0 Hard Gate 全部通过。
3. SLS-2 与 RF500 no-CST 编译通过。
4. R1/R2/R3/R4 旧 proof 或 schema 兼容读取通过。
5. 新 ablation proof 通过。
6. Workbench W2/W3 正确显示新合同和 support。
7. Desktop EXE 能打开当前完整 Workbench。
8. targeted tests 通过。
9. full `not cst_required` suite 通过。
10. `compileall` 通过。
11. `git diff --check` 通过。
12. 无 live CST。
13. 无许可证修改。
14. 无 CST process cleanup。
15. 无大规模优化。
16. canonical docs 更新。
17. 一个 closeout commit、一次 push、一个 PR。
18. closeout report 明确列出：
    - TD1 行为变化；
    - TD2 migration；
    - TD3 ablation；
    - EXE 路径和使用方式；
    - 测试；
    - 延期项。

---

# 9. 明确非目标

本轮不做：

- R5 live；
- CST/COMSOL Translator 泛化；
- exact NURBS backend；
- knot/weight optimization；
- 原始文本/图片 semantic extraction；
- STEP 自动 region segmentation；
- MDL/CEGIS 正式实现；
- LLM integration；
- 多用户 Workbench；
-云部署；
- Web write API；
-正式物理优化 campaign。

---

# 10. 本轮完成后的下一步

完成后再单独规划：

# Semantic Graph Acquisition

届时重点讨论：

```text
Evidence bundle
→ candidate graph
→ landmark/atom/region hypothesis
→ generic observation
→ novelty diagnosis
→ human review
→ reviewed graph
```

MDL、CEGIS、multi-scale landmark、split/merge/relabel 以及 representation/topology/semantic novelty 将在该独立模块中系统设计。

---

# 11. 2026-08-24 实施与 2026-08-26 follow-up closeout 记录

## 11.1 Git 与范围

```text
branch: codex/rf-cem-td1-td3-workbench-desktop
base: workflow/rf-cem-literature-review @ 8c6bd0be38e8b2bbf5d72c1254413ee6b552defe
base meaning: R4 canonical merge from PR #9
R5 branch/work: untouched and paused
execution mode: no-CST
```

本轮没有启动/连接 CST，没有运行 solver、修改许可证、删除 lock/result、清理 campaign、kill CST process 或继续 R5 Stage A/B。

## 11.2 TD1 最终行为

过去的 required level 会受 `source_native_segment_ref` 身份影响，导致 provenance 与工程意图混合。现在 `boundary_continuity_policy.v0` 是唯一决策来源：representation 内部 join 与普通跨 semantic RF-wall interface 默认 G1 hard；C0 只用于 port cut、flange edge、入口/出口截断或未来经人工明确确认的特殊非连续设计；G2 是可选扩展；profile 起止点使用独立 endpoint contract。RF500 两侧 `IrisRegion ↔ NoseRegion` 不属于 intentional corner：当前均由 `semantic_interface_default` 要求 G1，`intentional_corner=false`，真实 C0 override 数为 0。

最终科学修复删除了 adapter 中的 0.1 μm endpoint anchor；Stage C/source-native RF500 payload、`fit_input_points` 与 `source_control_point_hints` 不再被静默修改。`fit_input_points` 的首末割线仍相对相邻 line 约有 `56.1661 deg`，并只作为 `pre_kernel_estimate`。Compiler 根据 join plan 生成通用 `CurveRealizationConstraint`，字段包括 patch/start-or-end unit tangent、source join/interface、required continuity、direction-only/scale、source representation 与 enforcement backend。CadQuery worker 通过 `Workplane.spline(..., tangents=..., scale=True)` 执行 `cadquery.spline.tangent_constrained.v0`，再从最终 edge 回读 actual endpoints/tangents；只有 `measurement_basis=kernel_realized_edge` 决定 C0/G1 `required_pass`。两处 RF500 接口的实际角度均为 `0.0 deg` 且 `g1_pass=true`；G1 tolerance 仍为 `2.0 deg`，未放宽。backend 必须同时报告 constraint applied，缺失/忽略约束即使角度偶然接近也 fail closed。每个 join 继续记录 `c0_gap_mm`、`tangent_angle_deg`、`curvature_delta_per_mm`、C0/G1/G2 pass、requirement source、policy ref 和 intentional-corner；当前 G2 curvature 明确是 representation estimate，不伪称 kernel-realized。

新 no-CST proof：

```text
analysis_outputs/rf_cem_boundary_compiler_td1_td2/
  r2_boundary_compiler.24bd2492658ad567/
input SHA-256:
  24bd2492658ad56743f4933c6a3b84c055c396660b9b5fccdec89047ef3a873b
SLS-2 compile:
  sls2.r149.6593e02e.compile.6a840da94a2ed989
RF500 compile:
  rf500.2c27faee.b1r3.compile.b46af83bb85674d5
```

两份 `compile_record.v2` 均 pass。RF500 最大 kernel-realized spline deviation 为 `4.415657314345961e-06 mm`，SLS-2 为 `0.0006511097926837164 mm`，均小于 `0.001 mm`；比较使用 513 点 cosine-clustered normalized-arc-length 双向 edge-to-edge sampling，并保留 source trace point residual。反例测试证明 representation secant 看似 G1 但 fake kernel actual tangent 超差时 compile fail，也证明 backend 接收却未应用约束时 fail closed。anchor-era v1 `.2980548dcdd5a85e`、前一份 v1 `.8f47ca735db8ce8a` 与原 v0 `.aa66a3e90125437b` 均未覆盖；v0/v1/v2 compatibility、synthetic C0、explicit G2、endpoint 与 source-native identity 回归继续通过。

## 11.3 TD2 migration 与兼容性

canonical class/schema 为 `SplineApproxRepresentation` / `boundary_representation.v1`：

```text
fidelity = approximate
backend_contract = cadquery.splineApprox.v0
approximation_tolerance_mm = 0.001
optimization_ready = true
exact_nurbs = false
```

输入字段准确表示 fit input/control hints，不声称是最终 exact NURBS poles。`backend_contract` 是 source representation contract；带 Compiler endpoint constraint 的 patch 会以独立的 `realized_backend_contract=cadquery.spline.tangent_constrained.v0` 构造并记录 constraint/readback/fidelity。历史 `SplineNurbsRepresentation` / `boundary_representation.v0` 是 deprecated compatibility path；旧 payload 可读，新旧 payload round-trip 后在现有容差内生成等价 geometry，优化-facing points 仍可变。Workbench 只把 `ExactNurbsRepresentation` 显示为 planned/not implemented。

`active backend parameters`、`observation-only trace parameters` 与 `parameter_count` 的精确定义仍是未来技术债。本 follow-up 不修改 `parameter_count`，不增加 optimization parameter schema，不重构 optimizer，也不改变无约束 splineApprox behavior。

## 11.4 TD3 ablation、detector 与 support

`validate_reviewed_graph_intrinsic` 不要求 seed grammar 已包含每个 reviewed motif；`validate_graph_against_grammar` 继续负责 admission。真实 seed grammar 删除 nose motif、cardinality 和 insertion adjacency，RF500 保留两个 reviewed NoseRegion；因此 RF500 patch 前 intrinsic-valid 但 admission fail。

`FamilyInductionEngine` 实现：

1. `PairedOptionalMotifDetector`：真实 SLS-2/RF500 nose case；
2. `SingleOptionalMotifDetector`：synthetic one-sided、无 symmetry assumption fixture；
3. `AlternativeTopologyDetector`：前两者不适用时的 fallback。

v1 proposal 的 structured support 保存 structural match、evidence completeness、review coverage、cross-instance support、population size、symmetry assumption、detector ID/version；`proposal_score` 只用于排序，`score_semantics=heuristic_support_not_probability`。accepted review 生成 `add_optional_motif`，patch 后 SLS-2/RF500 都 admitted；rejected/needs-evidence 不改变 grammar。

新 no-CST proof：

```text
analysis_outputs/rf_cem_family_induction_ablation/
  r3_family_induction_ablation.59db0a7b5f8e158c/
input SHA-256:
  59db0a7b5f8e158cddd713f6ff8c4bafd8b2fa56ac08eb000c819c3c70054312
proposal schema: family_extension_proposal.v1
selected detector: paired_optional_motif
blind result: known_optional_motif_present
```

旧 `r3_family_induction.2f6c02557798e606` 未覆盖且由 v0 loader 读取。

## 11.5 R4 与 Workbench 当前 proof chain

架构文件稳定后生成的 R4 regression proof：

```text
analysis_outputs/rf_cem_observation_contract_td/
  r4_observation_contract.9e722ec6c8b003cb/
input SHA-256:
  9e722ec6c8b003cb07af6cc9e8d85c1ae47dd1d0378a3961f1d349a374a2729d
instances: SLS-2 + RF500
descriptor definitions / values: 21 / 240
constraints / evaluations: 6 / 12
```

tracked `config/rf_cem_workbench_profile.v0.json` 继续是唯一默认 profile，只使用 repository-relative paths，绑定当前 W0–W4 chain、literature semantics 与 frozen review session，并预留 nullable W5；未增加 full/core split 或 selector。连续两次 rebuild 结果：

```text
database: analysis_outputs/rf_cem_workbench/td1_td3_desktop.v0.sqlite
database state: fresh
sources / entities / relations: 67 / 826 / 1605
input-set SHA-256:
  3e4f5fcaa9e0e6e65237b693f490f786e227a736ee8fa5374b02de1389ccd585
portable snapshot SHA-256:
  64ddfade0b6855ef17844c2ef8c61f146ca36e55751be14723405e5e80140d55
```

前一份 `.dc4d7d12fb9a8c84`、`.a0fd43bd4bf4de2f` 与旧 `.d06695921d941eee` 均未覆盖。loader 仅针对这些 historical canonical bundle 的精确 path/旧 hash/旧 size 三元组使用窄兼容 allowlist，其语义是证明已知 historical source identity，而不是声明当前 checkout source-byte equivalence；其余错配仍 fail closed。

W2 显示 policy/requirement basis、kernel measurement basis、pre-kernel estimate、endpoint constraint、backend construction/application、actual gap/angle、required pass 与 fidelity；W3 显示 seed、detector、structured support、symmetry/population、pending/accepted、`add_optional_motif`、diff/final admission/single fixture；W4 继续显示 exact/shape/scalar 与非变异约束。

## 11.6 Desktop v0 交付与 QA

```text
launcher source: src/rf_cem/workbench/desktop.py
portable profile API: src/rf_cem/workbench/profile.py
build script: scripts/build_rf_cem_workbench_desktop.ps1
local ignored EXE: dist/RF-CEM-Workbench.exe
local EXE size: 10,633,270 bytes
local config: %LOCALAPPDATA%\RF-CEM\workbench_launcher_config.v0.json
```

PyInstaller 安装仅发生在 ignored repository `.venv`，没有加入生产 dependency。构建脚本生成 windowed one-file thin launcher并自动执行 EXE `--self-test`；独立 `Start-Process -Wait` smoke exit code 为 0。archive inventory 扫描未包含 CST、CST optimisation runtime、CadQuery/OCP、NumPy/Pandas/SciPy/Plotly 等 stack。

真实原生窗口 QA 确认：仓库/profile 正确、十个固定按钮全部可见、自动 freshness check/rebuild 完成、owned loopback child 启动、token URL 显示、默认 Edge 自动打开 Overview。随后向唯一 launcher window 发送正常 `WM_CLOSE`，launcher 与其 child 均退出；未扫描或停止无关进程。Browser automation 因无法可靠确认 Edge 当前 URL 而安全停止，未继续发输入；W0–W4 页面与 POST=405 已由真实 launcher subprocess integration test 直接验证。

## 11.7 验证结论

```text
targeted compiler/observation/Workbench/Desktop/architecture: 49 passed in 29.80s
full pytest -q -m "not cst_required": 796 passed, 11 skipped in 46.99s
R2 current v2 / anchor-era v1 / previous v1 / historical v0 strict validation: pass
R3 current ablation v1 / two historical v0 bundles strict validation: pass
R4 current 9e722 / previous dc4d+a0fd / historical d066 strict validation: pass
deterministic full-profile rebuild: 67 fresh sources / 826 entities / 1605 relations
input-set / portable snapshot: 3e4f5fcaa9e0e6e65237b693f490f786e227a736ee8fa5374b02de1389ccd585 / 64ddfade0b6855ef17844c2ef8c61f146ca36e55751be14723405e5e80140d55
source Desktop self-test and rebuilt local EXE --self-test: pass
live CST: not run
physical acceptance: not established
```

`compileall` 与 `git diff --check` 均通过。tracked cleanliness 在 closeout commit 后复核；精确 Git HEAD、push 与 PR 状态由最终 closeout response 和远端 PR 记录给出。

## 11.8 延期项

- R5 live 与 Translator/result/mode/field contract review；
- exact NURBS backend 与 knot/weight optimization；
- SplineApprox active backend parameters、observation-only trace parameters 与 `parameter_count` 语义；
- historical R4 allowlist 的当前 checkout source-byte equivalence（现有规则只证明已知 historical identity）；
- Semantic Graph Acquisition（raw evidence → candidate/reviewed graph）；
- STEP 自动 segmentation、MDL/CEGIS 正式实现、多用户/云 Workbench；
- 任何正式物理 optimization campaign。
