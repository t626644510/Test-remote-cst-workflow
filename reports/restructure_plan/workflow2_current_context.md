# Workflow2 Current Context

## 1. 项目背景

本项目当前处于 CST Code Framework 的 workflow2 legacy 重构前置阶段。

此前 WF1 SAO consolidation / root shim / cleanup hardening / tolerance sweep 等工作已经完成并合入 main。当前 main 应视为 WF1 SAO restructuring baseline 之后的新基线。旧 report、merge note、OPS1 文档和历史状态文件只能作为线索，不能作为当前判断依据。

本轮进入"方案 1.5"阶段：先规划 workflow2 隔离重构，不立即进行大规模 main/core 抽离。所有判断必须回到当前代码、测试和 git diff。

最高优先级治理文档是：

- `reports/restructure_plan/agent_operating_charter.md`

本文件用于网页端 reviewer 与本地 agent 快速恢复 workflow2 当前上下文。它不是历史报告，也不应替代代码审计。

## 2. 当前阶段目标

方案 1.5 的目标是：

1. 在通用治理原则下规划 legacy workflow2 的隔离重构。
2. 不先做大规模 `main/core` 抽离。
3. 不把 workflow2 作为当前大分支的无边界延续。
4. 先将 workflow2 runtime、配置、builder/orchestrator 归属逐步隔离。
5. 在重构过程中只标记真正可能复用的 core candidate。
6. 等 workflow2 产生跨 workflow 证据后，再决定哪些模块进入 shared core。

当前推荐路线是：

1. 固化当前上下文文档。
2. 添加 no-CST characterization tests，钉住 legacy workflow2 当前行为。
3. 创建 workflow2 隔离包骨架。
4. 保留 root `run_workflow_2.py` shim 和 scheduler 兼容。
5. 逐步迁移 workflow2 config、builder、orchestrator ownership。
6. 暂缓 core 晋升，只记录 core candidate。
7. 最后再设计最小 live CST 验证。

## 3. 当前代码状态摘要

当前 workflow2 仍是 legacy 组合形态：

- Root entry：`run_workflow_2.py`
- Shared config：`config/default.yaml` 中的 `workflow_2` 段
- Shared builder：`src/cst_optimization/factory.py::build_workflow_2`
- Shared orchestrator：`src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator`
- Scheduler entry：`scripts/schedule_workflow2.ps1`

当前 `run_workflow_2.py` 的关键行为：

- 读取 `config/default.yaml`
- 提取 `workflow_2` 段
- 将顶层 `cst` / `solver` / `logging` 等 fallback 合并进 workflow2 config
- 调用 `cst_optimization.factory.build_workflow_2`
- 当前调用方按四元组接收 builder 返回值

当前 workflow2 config 的关键行为：

- `workflow_2` 内部包含 `frequency_domain`、`wakefield`、`wakefield_offset` 三项目结构
- 包含 pre-filter、message log、retry、参数、约束和目标定义
- `workflow_2.optimization.solver.stagnation_timeout_s` 当前位于 `optimization.solver` 下，但 builder 似乎读取 workflow2 顶层 `solver`

当前 scheduler 行为：

- `scripts/schedule_workflow2.ps1` 仍直接启动 root `run_workflow_2.py`
- 典型参数包括 `--auto-resume --heartbeat`
- 因此 root shim 兼容是硬边界

## 4. 已完成内容

- Web reviewer 已读取并采用 `reports/restructure_plan/agent_operating_charter.md` 作为最高优先级治理原则。
- Web reviewer 已基于当前 main 做只读审计。
- Web reviewer 已确认本轮路线：先隔离 workflow2，再观察 core candidate，不先做大规模 core 抽离。
- Web reviewer 已识别 workflow2 当前主要风险点。
- **本轮本地 agent 已执行**：基于 origin/main（commit `5269351`）创建 `plan/workflow2-current-context-v2` 分支，更新本文档。
- 本轮本地 agent 已读取以下文件：
  - `reports/restructure_plan/agent_operating_charter.md`
  - `run_workflow_2.py`
  - `config/default.yaml`
  - `src/cst_optimization/factory.py`
  - `src/cst_optimization/core/orchestrator.py`
  - `scripts/schedule_workflow2.ps1`
- 代码审计发现以下潜在风险，需在 W2-1 通过 no-CST characterization tests 确认实际行为（参见第 8 节）：
  - **R2（solver timeout 层级不一致）**：代码路径表明 `build_workflow_2` 从 `workflow_2.solver` 读取，但 intent 写入 `workflow_2.optimization.solver.stagnation_timeout_s: 7200.0`；实际生效值需在 W2-1 钉住。
  - **R4（checkpoint 双触发）**：代码路径显示 `orchestrator.py` 与 `factory.py` 均可能调用同一 `checkpoint_callback`；实际调用次数需在 W2-1 通过 mock callback 测量。
  - **R5（DualProjectOrchestrator core 归属）**：ownership/architecture 风险 — `core/orchestrator.py` 含大量 workflow2 语义，但当前状态是架构观察，不要求立即迁移。
- W2-0 web review: pending acceptance.
- 尚未运行 CST。
- 尚未运行本地测试。

## 5. 当前禁止误改的边界

本阶段必须遵守以下边界：

1. 不把旧 report、merge note、OPS1、历史状态文件当当前结论。
2. 不默认全库阅读。
3. 不默认跑 CST。
4. 不默认跑全量测试。
5. 不先做大规模 `main/core` 抽离。
6. 不把 workflow2 重构做成无边界大分支。
7. 不删除或破坏 root `run_workflow_2.py`。
8. 不破坏 `scripts/schedule_workflow2.ps1` 对 root entry 的依赖。
9. 不默认删除 `config/default.yaml` 中的 `workflow_2` 段。
10. 不把 `DualProjectOrchestrator` 直接认定为 stable shared core。
11. 不新增未验证的 CST API 假设。
12. 不把 workflow2-specific convenience layer 推入 shared core。
13. 不在同一个 diff 中混合文档、测试、runtime 迁移和 core 抽离。
14. 不修改 WF1 SAO 已接受路径，除非有明确、最小且可验证的兼容需求。

## 6. 推荐分支策略

本地 agent 应从当前 `origin/main` 新建 gated branch。

推荐分支名：

- `plan/workflow2-current-context-v2`

或如果同时添加 no-CST characterization tests：

- `test/workflow2-characterization`

如果发现远端存在网页端临时尝试产生的 `docs/workflow2-plan-1-5` 分支，不应直接基于它继续。请从 origin/main 新开干净分支，避免继承不完整文档写入。

## 7. 推荐阶段性推进路线

### W2-0：上下文文档落地

目标：

- 创建 `reports/restructure_plan/workflow2_current_context.md`
- 记录当前目标、已完成内容、禁止误改边界、下一轮本地 agent 读集、最新验证结果、未解决风险

编辑范围：

- 仅新增或更新 `reports/restructure_plan/workflow2_current_context.md`

验证：

- `git diff origin/main...HEAD -- reports/restructure_plan/workflow2_current_context.md`
- 不跑 CST
- 不跑全量测试

### W2-1：no-CST characterization tests

目标：

在移动 runtime 代码前，先用 mock/monkeypatch 钉住 workflow2 当前行为。

建议测试点：

1. `run_workflow_2.py` 当前如何读取 `config/default.yaml`
2. `workflow_2` 段如何合并顶层 `cst` / `solver` / `logging`
3. `build_workflow_2` 当前实际返回四元组
4. solver timeout 实际从哪个 config 层级读取
5. checkpoint callback 是否可能被 builder evaluator 与 orchestrator 双重触发
6. scheduler 仍依赖 root `run_workflow_2.py`

编辑范围：

- 新增或更新 workflow2 相关 tests
- 必要时加入小型测试 helper
- 不修改 runtime 逻辑，除非测试无法导入且需要非常小的 import-safe guard

验证：

- 仅运行新增/相关 tests
- 不跑 CST
- 不跑全量测试

### W2-2：创建 workflow2 隔离包骨架

推荐包名：

- `workflows/rfgun_hom_antenna/`

理由：

- workflow2 当前语义是 RF gun HOM antenna optimization
- 避免与 WF1 的 `rfgun_single_pass` / `rfgun_sao` 命名混淆

建议结构：

```
workflows/rfgun_hom_antenna/
  __init__.py
  run.py
  workflow.py
  config.yaml
  README.md
```

目标：

- 先建立隔离位置
- root run_workflow_2.py 保持兼容 shim
- 不急于移动所有逻辑

验证：

- import test
- CLI parser / dry-run style no-CST test
- 不跑 live CST

### W2-3：workflow2 config 隔离

目标：

- 将 config/default.yaml 中的 workflow_2 语义迁入 workflow-local config
- root shim 继续支持 legacy config fallback
- 不立即删除 legacy config 段

验证：

- config loading tests
- root shim compatibility tests

### W2-4：builder ownership 隔离

目标：

- 将 workflow2 builder 归属迁向 workflows/rfgun_hom_antenna/workflow.py
- src/cst_optimization/factory.py::build_workflow_2 可暂时保留 compatibility wrapper
- 不在本阶段将 workflow2 builder 抽入 shared core

验证：

- mock CST connection
- mock solver
- mock objective registry
- no-CST tests

### W2-5：orchestrator 归属判断

当前 DualProjectOrchestrator 位于 src/cst_optimization/core/orchestrator.py，但语义高度 workflow2-specific：

- multi-project phase orchestration
- frequency-domain / wakefield / wakefield-offset sequencing
- pre-filter
- conditional project execution
- adaptive gate
- raw curve recording
- F2F / F2W / F2WO phase labels

建议先将其标记为 workflow2-owned candidate，而不是 stable shared core。

只有在搜索和测试确认其他 workflow 无真实依赖后，才考虑迁入 workflow2 package，并保留兼容 import。

### W2-6：修复或固化已发现语义风险

建议单独处理，不与大搬迁混合：

- solver timeout 配置层级不一致
- build_workflow_2 注解/文档签名与实际四元返回不一致
- checkpoint callback 可能双触发
- run_workflow_2.py 顶部说明的"两 CST 窗口"与当前 builder 单 connection 行为不一致
- scheduler/root shim compatibility

### W2-7：core candidate 评估

只有 workflow2 隔离后，且与 WF1/WF3 产生真实共同需求，再考虑 core 晋升。

当前初步分类：

Likely shared, but should not be changed now:

- CSTConnection
- SolverRunner
- EvaluationRetryHandler
- ParameterSet
- objective registry

Possible core candidates, but require evidence:

- checkpoint callback protocol
- raw curve recording abstraction
- adaptive conditional gate
- recovery state protocol

Likely workflow2-specific for now:

- DualProjectOrchestrator
- ProjectSpec
- F2F / F2W / F2WO phase policy
- workflow2 scheduler behavior
- workflow2 config layout

### W2-8：最小 live CST 验证

只有 no-CST tests 和结构 diff 被接受后，才进入 live CST 验证设计。

live CST prompt 必须明确：

- 是否会打开 CST
- 是否会写入真实结果目录
- 是否会触碰 D:/Results
- 是否依赖 D:/workflow2/*.cst
- 是否 destructive
- 如何停止和清理
- 如何收集 evidence

## 8. 已发现风险

### R1：文档与代码冲突

`run_workflow_2.py` 顶部说明曾描述 workflow2 会打开两个独立 CST 窗口。

但当前 builder 审计显示，`build_workflow_2` 更像是建立单个 `CSTConnection`，并顺序运行多个 project。

**风险**：如果后续 agent 相信旧 docstring，可能设计错误的 resource cleanup / orphan CST 策略。应先用当前代码和测试确认真实行为，再改文档或 runtime。

### R2：solver timeout 配置层级可能不一致

当前 `config/default.yaml` 中存在：
- `workflow_2.optimization.solver.stagnation_timeout_s: 7200.0`

但 `build_workflow_2`（`factory.py:409`）从 `config.get("solver", {})` 读取 solver config，这在语义上对应 `workflow_2.solver`，而非 `workflow_2.optimization.solver`。`workflow_2.solver` 不存在于当前 YAML 结构中，但由于 `run_workflow_2.py` 会将顶层 `solver` fallback（`stagnation_timeout_s: 300.0`）合并进 `workflow_2`，实际生效 timeout 可能是 300s（全局值）或 0.0（builder 默认），而非 intent 的 7200s。

**风险**：workflow2 intent（7200s）可能未实际生效；重构 config 层级时可能无意改变 runtime 行为。

**需要 W2-1 钉住**：写 no-CST characterization test，mock config loader，确认 `SolverRunner` 实际收到哪个 timeout 值。在此确认前，不得修改 solver timeout 相关的 config 路径或 builder 读取逻辑。

### R3：builder 返回签名不一致（类型注解/文档与实际实现错位）

当前代码审计确认以下错位：

- **类型注解**（`factory.py:327`）：声明 3 元返回 `tuple[DualProjectOrchestrator, BaseOptimizer, Callable]`，**不含** `retry_handler`。
- **文档字符串**（`factory.py:339-344`）：仅列出 orch、optimizer、evaluator 三项，**未记录** `retry_handler`。
- **实际实现**（`factory.py:627`）：返回 4 值 `orchestrator, optimizer, evaluator, retry_handler`。
- **调用方**（`run_workflow_2.py:208`）：按 4 元解包，依赖第四项 `retry_handler`。

这是一个活跃的文档/类型契约错位：类型系统和 docstring 承诺 3 项，但实际实现和调用方依赖 4 项。

**风险**：迁移 builder 时若基于类型注解重构，容易漏掉 `retry_handler` 返回，导致 `run_workflow_2.py` 解包失败。compatibility wrapper 也可能破坏 root runner。

**需要 W2-1 钉住**：在 no-CST characterization test 中确认四元组在 SAO 和 SAEA 两种算法路径下均一致，然后才进入 builder 迁移。注意：本轮 W2-0 不修复 runtime 和类型注解。

### R4：checkpoint callback 可能双触发

当前代码审计发现两条调用路径均可能触发 `checkpoint_callback`：
1. `orchestrator.py:567` — `DualProjectOrchestrator.execute()` 通过 `self._checkpoint_callback(...)` 调用。
2. `factory.py:581` — SAO evaluator（retry handler 路径）在 `retry_handler.execute()` 返回后再度调用同一 callback。

当 retry handler 启用时，`_evaluate_for_retry` → `orchestrator.execute()`（触发 #1），然后 SAO evaluator 汇总结果后再次触发同一 callback（触发 #2）。非 retry 路径同理。

**风险**：每次 evaluation 可能产生重复 checkpoint / progress record。历史运行成功不等于没有重复记账问题。

**需要 W2-1 钉住**：用 mock callback 写 no-CST characterization test，统计每次 evaluation 的 callback 调用次数，确认当前是否双触发。

### R5：DualProjectOrchestrator core 归属不清

虽然 `DualProjectOrchestrator` 位于 `src/cst_optimization/core/orchestrator.py`，但其语义高度 workflow2-specific：

- multi-project phase orchestration（F2F / F2W / F2WO）
- pre-filter 门控
- conditional project 执行
- adaptive gate 集成
- 1D curve recording 和 atomize 保存

**风险**：直接将其作为 shared core 会污染 core，未来 workflow1/workflow3 可能被迫适配 workflow2 concepts。

**建议**：先标记为 workflow2-owned candidate，有跨 workflow 证据后再决定是否抽象。不在本阶段迁移。

### R6：scheduler 绑定 root entry

`scripts/schedule_workflow2.ps1` 当前绑定 root `run_workflow_2.py`。

**风险**：如果 root runner 被直接移动或删除，scheduler 会断；Windows scheduled task / automation 可能失效。

**建议**：root `run_workflow_2.py` 必须先保留 shim；scheduler compatibility 必须有测试或明确人工验证步骤。

## 9. 下一轮 local agent 默认读集

第一轮本地 agent 不应默认全库阅读。建议只读：

- `reports/restructure_plan/agent_operating_charter.md`
- `run_workflow_2.py`
- `config/default.yaml`
- `src/cst_optimization/factory.py`
- `src/cst_optimization/core/orchestrator.py`
- `scripts/schedule_workflow2.ps1`

如果后续轮次不涉及代码修改，可缩小读集：

- `reports/restructure_plan/agent_operating_charter.md`
- `run_workflow_2.py`
- `config/default.yaml`
- `scripts/schedule_workflow2.ps1`

## 10. 最新验证结果

### 本轮（本地 agent W2-0：上下文文档落地 — 第二轮提交）

**执行时间**：2026-06-06

**分支**：`plan/workflow2-current-context-v2`（基于 origin/main，commit `5269351`）

**读取的文件**：
1. `reports/restructure_plan/agent_operating_charter.md`
2. `run_workflow_2.py`
3. `config/default.yaml`
4. `scripts/schedule_workflow2.ps1`
5. `src/cst_optimization/factory.py`
6. `src/cst_optimization/core/orchestrator.py`

**修改的文件**：仅 `reports/restructure_plan/workflow2_current_context.md`

**验证命令**：
```powershell
git status --short
git diff --name-status origin/main...HEAD
git diff origin/main...HEAD -- reports/restructure_plan/workflow2_current_context.md
```

**结果**：
- ✅ 基于 origin/main 创建干净分支，仅包含此文档
- ✅ 未运行 CST
- ✅ 未运行本地测试
- ✅ 未修改 runtime 代码
- ✅ 未修改 tests
- ✅ 未修改 scripts
- ✅ Markdown 结构修复（W2-3~W2-8 标题、代码块 fence、风险章节标题）
- ✅ R2/R4 降级为代码审计发现，需 W2-1 确认
- ⏳ R3：类型注解和 docstring 承诺 3 元返回但实际返回 4 元；需在 W2-1 通过 characterization test 确认四元组在 SAO 和 SAEA 路径下一致

### 整体状态

- Web reviewer read-only audit: pending acceptance.
- W2-0 status: pending final review.
- 未运行本地测试。
- 未运行 CST。
- 未接受任何 runtime 改动。
- 未完成 workflow2 isolation package（W2-2）。
- 未完成 no-CST characterization tests（W2-1）。

后续每一轮本地 agent 都应更新本节，记录实际运行的命令和结果。

## 11. 当前推荐下一步

### W2-0 状态：pending final review

- ✅ 基于 origin/main 创建分支 `plan/workflow2-current-context-v2`
- ✅ 更新 `reports/restructure_plan/workflow2_current_context.md`
- ✅ Markdown 结构修复
- ✅ 不修改 runtime
- ✅ 不跑 CST
- ✅ 不跑测试
- ⏳ 等待 web reviewer 审计通过

### W2-1（通过 W2-0 审计后的建议）：no-CST characterization tests

建议下一轮本地 agent：

1. **确认分支策略**：
   - 从当前 `plan/workflow2-current-context-v2` 继续，或基于 origin/main 新开 `test/workflow2-characterization`
   - 将本文档同样带入新分支

2. **优先测试点**（按风险优先级排序）：
   - **P0**：`config/default.yaml` 的 `workflow_2` 段合并行为 — 确认 `cst` / `solver` / `logging` fallback 如何写入 `wf2_cfg`
   - **P0**：`build_workflow_2` solver timeout 实际来源 — 钉住当前 `SolverRunner` 收到的是 300s（全局 fallback）、7200s（intent）、还是 0.0（builder 默认）
   - **P0**：checkpoint callback 双触发 — 用 mock callback 统计每次 evaluation 的调用次数
   - **P1**：`build_workflow_2` 返回签名 — 确认四元组在 SAO 和 SAEA 两种算法路径下均一致
   - **P1**：`run_workflow_2.py` 与 scheduler 的兼容关系 — 确认 root shim 路径
   - **P2**：`DualProjectOrchestrator` 接口稳定性 — mock CST 连接后的 `execute()` 合约

3. **验证要求**：
   - 不跑 CST（mock / monkeypatch CSTConnection）
   - 仅运行新增的 characterization tests
   - 不跑全量测试
   - 输出实际测试命令和结果

4. **完成后交给 web reviewer 审计**：审计通过后再进入 W2-2（package skeleton）。
