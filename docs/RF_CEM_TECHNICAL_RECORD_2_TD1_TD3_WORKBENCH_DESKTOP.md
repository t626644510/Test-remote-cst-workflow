# TD1–TD3 与 Workbench Desktop 技术记录

整理：2026-09-05。记录对象：PR #10，已由 `ab4a55c` 合并；实现核验基线包含 A0 的 `d17d95f`。当前研究判断及后续优先级见 [PROJECT_STATUS_CONTEXT.md](PROJECT_STATUS_CONTEXT.md)，命令见 [FUNCTIONS_AND_ENTRYPOINTS.md](FUNCTIONS_AND_ENTRYPOINTS.md)。

本文只保留理解现有实现所需的决策。更早的讨论、过渡 proof 和测试日志可从 Git 历史或本地原始产物查找。

## 1. TD1：连续性由工程意图决定

旧实现曾用 `source_native_segment_ref` 是否相同来决定连续性要求。修正后该字段只说明来源；连续性由 `BoundaryContinuityPolicy` 和接口 override 决定。

| 等级 | 当前含义 |
| --- | --- |
| C0 | 端点位置接合；有意角点可显式指定 |
| G1 | C0 成立且切向一致；普通壁面内部及跨语义接口的默认要求 |
| G2 | 额外考察曲率；可显式要求，非通用默认 |

长度 mm、角度 deg、曲率 1/mm。跨语义区域不意味着允许折角，同一原始曲线也不意味着必须 G2。

v2 编译流程：

```text
接口要求
  → 编译器规划端点方向约束
  → 几何 worker 在构造曲线时施加约束
  → 读取实际 CadQuery/OCP edge 的端点与单位切向
  → 检查要求及对原始几何的偏差
```

受约束 spline 使用已实现的 `cadquery.spline.tangent_constrained.v0` 构造路径；没有约束时保留 `splineApprox`。实际 C0/G1 的测量依据是 `kernel_realized_edge`。表示层割线估计仍可用于诊断，但不能冒充实际内核切向；v2 的 G2 仍属于表示估计。

RF500 的两个 Iris↔Nose 接口按默认 G1 处理，未用“有意角点”放宽要求。相关检查覆盖约束未施加、实际角度不符及几何偏差超界的情形。实现集中在 `src/rf_cem/compiler/` 和几何 worker；这些都是 no-CST 几何证据。

## 2. TD2：准确描述样条能力

当前公开表示为 `SplineApproxRepresentation`。实现保留拟合输入、原生控制点提示及拟合容差；默认拟合容差 0.001 mm，即 1 μm。它不宣称提供任意 knots/weights 的完整 exact NURBS 编辑器。

旧 `SplineNurbsRepresentation` 与 v0 序列化只用于兼容。record v0/v1/v2 可读不代表历史记录都具有 v2 的内核连续性证据，判断时要看实际版本和测量依据。

曲线表示保持与 RF family/region 类型独立。R2 编译器负责把图和表示组合起来；region 可拥有多个 patch，每个 patch 只有一个语义 owner。

## 3. TD3：已有语义上的结构归纳

`FamilyInductionEngine` 的当前策略链是：

| 检测器 | 行为 | 证据范围 |
| --- | --- | --- |
| Paired optional | 从已标注残差提出成对可选 motif，允许 0/2 次 | SLS-2/RF500 实例 |
| Single optional | 提出单个可选结构，允许 0/1 次 | 合成审核 fixture |
| Alternative fallback | 记录未被前两者解释的拓扑残差 | 不自动生成通用 grammar 补丁 |

图的内部合法性与对特定 family grammar 的准入分开。TD3 的 ablation 删除 seed 中 nose 的 motif/cardinality/插入邻接规则；RF500 图仍保留人工来源的 `NoseRegion`。检测器生成 pending 提案；accepted 审核才应用补丁，rejected/needs-evidence 保持原 grammar。

v1 支持信息记录结构匹配、证据、审核、实例分布、对称性假设及检测器版本。`score_semantics=heuristic_support_not_probability`，不应解释成预测正确率或贝叶斯后验。

LEReC 的盲测图由 `semantic/induction/blind.py` 中的既定 region 序列和论文证据引用构造。其意义是“归纳输入之外的已标注拓扑可被新 grammar 接受”；没有验证自动读论文、几何定位或新类型发现。

因此当前关系是：

```text
已有资料 → 语义获取（尚未实现完整链路）→ 人工确认图
人工确认图 → R3 受限结构归纳 → grammar
图 + 表示 → R2 几何编译
```

把获取和归纳分开便于复用；这不要求未来必须延续当前六类词表或当前检测器形式。

## 4. R4 回归与边界来源的补充认识

TD 后 R4 仍提供 exact geometry、归一化形状、标量描述符三层，并展示不修改几何的约束求值。21 个描述符定义、240 个值、6 个约束和 12 次求值是两个当前实例的演示规模，不是 RF 物理验收范围。

2026-09-05 核查发现：R2 适配器对多 owner 的原生曲线做参数等分；SLS-2 四个 A0 漏检 junction 来自这一约定。原生几何、粗区域审核、编译坐标可追溯，仍不能证明每个细分坐标有独立语义定位依据。此细节会影响区域描述符的解释，也限制 A0/A0.5 作为“语义真值测试”的结论。

## 5. Workbench/Desktop 的作用

Web 层保持只读，展示证据、审核、R1 图、R2 编译、R3 提案、R4 观测和能力目录。SQLite 是可重建的派生索引。`config/rf_cem_workbench_profile.v0.json` 集中列出源文件和数据库位置。

Desktop 是薄启动器：启动/打开 Workbench、重建数据库、刷新状态、停止自己拥有的服务、打开文档和输出目录、复制地址、快速自检、查看日志。子进程使用固定参数与 `shell=False`；它没有 CST 求解动作。

源码入口为 `python -m rf_cem.workbench.desktop`；构建脚本为 `scripts/build_rf_cem_workbench_desktop.ps1`，本地产物 `dist/RF-CEM-Workbench.exe` 不提交。用户配置位于 `%LOCALAPPDATA%/RF-CEM/workbench_launcher_config.v0.json`。

现有 Workbench 目录数据写在 `workbench/indexer.py` 中，页面上的“阶段通过”描述的是既往工程完成情况。它不会因新讨论而自动反映科研可信度，也未包含 A0.5/A1 实现。

## 6. 查找历史证据

所有路径以当前 profile 为首选，避免在多个文档重复整套 hash：

| 证据 | 当前 profile 所指 bundle |
| --- | --- |
| R2 v2 / TD1–TD2 | `r2_boundary_compiler.24bd2492658ad567` |
| R3 ablation / TD3 | `r3_family_induction_ablation.59db0a7b5f8e158c` |
| R4 TD 回归 | `r4_observation_contract.9e722ec6c8b003cb` |

旧 bundle 保留原样。R4 loader 为若干历史输入做了有限兼容，但当前 bundle 仍绑定 roadmap 原文；本轮因此保留该文档的字节，没有扩张兼容列表或刷新证明。

PR #10 的历史全分支验证为 796 passed / 11 skipped。2026-09-05 本轮对上述模块及 A0 的现有针对性测试为 74 passed。两者均为 no-CST，详细命令和当前状态集中在状态入口与命令索引。

R5 继续暂停；旧 500 MHz 求解链可作为将来 RF 结果工作的基础，跨求解器 Translator、模态/场契约与物理性能复现尚未由 TD1–TD3 完成。
