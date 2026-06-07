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

当前 workflow2 处于 W2-4A（builder ownership seam）状态：

- Root entry：`run_workflow_2.py`
- Shared config：`config/default.yaml` 中的 `workflow_2` 段
- Workflow-local builder seam：`workflows/rfgun_hom_antenna/workflow.py::build_workflow_2`（W2-4A，委托到 legacy factory）
- Legacy builder（未修改）：`src/cst_optimization/factory.py::build_workflow_2`
- Shared orchestrator：`src/cst_optimization/core/orchestrator.py::DualProjectOrchestrator`
- Scheduler entry：`scripts/schedule_workflow2.ps1`

当前 `run_workflow_2.py` 的关键行为：

- 读取 `config/default.yaml`
- 提取 `workflow_2` 段
- 将顶层 `cst` / `solver` / `logging` 等 fallback 合并进 workflow2 config
- 调用 `workflows.rfgun_hom_antenna.workflow.build_workflow_2`（W2-4A seam，当前委托到 `cst_optimization.factory.build_workflow_2`）
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
- **W2-0 done**：基于 origin/main 创建 `plan/workflow2-current-context-v2` 分支，本文档经多轮审核后 accepted。
- **W2-1 done**：基于 origin/main 创建 `test/workflow2-characterization` 分支，完成 no-CST characterization tests（21 tests, accepted）。
- **W2-2 done**：基于 `test/workflow2-characterization` 创建 `refactor/workflow2-package-skeleton` 分支，创建 `workflows/rfgun_hom_antenna/` 骨架包。
- 本轮本地 agent 已读取以下文件：
  - `reports/restructure_plan/agent_operating_charter.md`
  - `reports/restructure_plan/workflow2_current_context.md`
  - `run_workflow_2.py`
  - `config/default.yaml`
  - `src/cst_optimization/factory.py`
  - `src/cst_optimization/core/orchestrator.py`
  - `scripts/schedule_workflow2.ps1`
  - 少量现有 tests（`test_rfgun_sao_imports.py`, `test_rfgun_single_pass_imports.py`）作为测试风格参考。
- W2-1 测试覆盖：
  - **P0.1 config fallback merge**：5 tests via `_run_merge()` 复现 `run_workflow_2.py` 合并逻辑
  - **P0.2 solver timeout 来源**：4 tests 用 mock CST 构建实际 `build_workflow_2`，钉住 `SolverRunner._timeout_s`
  - **P0.3 checkpoint callback 双触发**：3 tests 用 mock CST + mock callback，确认 2 次调用 / evaluation（retry 和非 retry 路径均覆盖）
  - **P1.4 build_workflow_2 返回签名**：4 tests 确认四元组，覆盖 SAO 和 SAEA 路径
  - **P1.5 scheduler 兼容性**：4 tests 静态文本确认 `scripts/schedule_workflow2.ps1` 仍绑定 root entry
- 尚未运行 CST。
- 尚未运行 live workflow。
- W2-0 web review: accepted.
- W2-1 status: pending web reviewer re-audit.
  - All 21 tests pass (0.70s).
  - P0.1: added black-box `run_workflow_2.main()` test plus fixed white-box helper (`_run_merge_like_root`) to match exact root code (reference assignment, not deep copy).
  - P0.3: replaced real `orch.execute()` with hermetic fake; no `_execute_phase_1`, no cleanup, no real filesystem paths.
  - Optional: `test_type_annotation_mismatch` uses real assertion instead of print.

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

### 本轮（W2-1：no-CST characterization tests）

**执行时间**：2026-06-06

**分支**：`test/workflow2-characterization`（基于 origin/main，commit `5269351`）

**读取的文件**：
1. `reports/restructure_plan/agent_operating_charter.md`
2. `reports/restructure_plan/workflow2_current_context.md`
3. `run_workflow_2.py`
4. `config/default.yaml`
5. `src/cst_optimization/factory.py`
6. `src/cst_optimization/core/orchestrator.py`
7. `src/cst_optimization/core/solver.py`
8. `src/cst_optimization/core/retry.py`
9. `src/cst_optimization/core/connection.py`
10. `src/cst_optimization/database.py`
11. `scripts/schedule_workflow2.ps1`
12. `tests/workflows/test_rfgun_sao_imports.py`（风格参考）
13. `tests/workflows/test_rfgun_single_pass_imports.py`（风格参考）

**新增文件**：
- `tests/workflows/test_workflow2_characterization.py`

**更新文件**：
- `reports/restructure_plan/workflow2_current_context.md`

**运行命令**：
```powershell
python -m pytest tests/workflows/test_workflow2_characterization.py -v --tb=short
```

**测试结果**：21 / 21 passed (0.70s)

| 覆盖点 | 测试数 | 状态 | 关键发现 |
|--------|--------|------|----------|
| P0.1 config fallback merge | 6 | ✅ | 含白盒 `_run_merge_like_root`（5 tests）和黑盒 `run_workflow_2.main()`（1 test）；均确认顶层 300s fallback 而非 7200s intent |
| P0.2 solver timeout 来源 | 4 | ✅ | `build_workflow_2` 读 `workflow_2.solver.stagnation_timeout_s`；缺失则 fallback 到 SolverRunner 默认（7200s）；`optimization.solver` 路径完全不读取 |
| P0.3 checkpoint callback | 3 | ✅ | **Confirmed: 每次 evaluation 调用 2 次**；使用 hermetic fake `orch.execute`，不进入 `_execute_phase_1`，不调 cleanup，不写文件系统 |
| P1.4 返回签名 | 4 | ✅ | `build_workflow_2` 始终返回 4 元组（SAO 和 SAEA）；类型注解仅承诺 3 项；`test_type_annotation_mismatch` 使用真实 assertion |
| P1.5 scheduler 兼容性 | 4 | ✅ | `scripts/schedule_workflow2.ps1` 仍绑定 root `run_workflow_2.py`，未迁移 |

**修复摘要**：
- P0.1: `_run_merge_like_root` 现在精确匹配 `run_workflow_2.py` 的引用赋值（无 `dict()`、无 `copy.deepcopy`）；新增 `test_root_main_merges_cst_solver_logging` 通过 `run_workflow_2.main()` 实际路径验证 merged config
- P0.3: 使用 hermetic fake `orch.execute`，不触达 `_execute_phase_1`、cleanup 函数或真实文件系统路径；额外 patch 了 `cst_optimization.core.cleanup` 函数

### 本轮（W2-2：创建 workflow2 隔离包骨架）

**执行时间**：2026-06-06

**分支**：`refactor/workflow2-package-skeleton`（基于 `test/workflow2-characterization`）

**读取的文件**：
1. `reports/restructure_plan/agent_operating_charter.md`
2. `reports/restructure_plan/workflow2_current_context.md`
3. `tests/workflows/test_workflow2_characterization.py`
4. `run_workflow_2.py`
5. `workflows/rfgun_sao/__init__.py`（风格参考）
6. `workflows/rfgun_sao/run.py`（风格参考）
7. `workflows/rfgun_single_pass/__init__.py`（风格参考）
8. `workflows/rfgun_single_pass/run.py`（风格参考）
9. `tests/workflows/test_rfgun_sao_imports.py`（风格参考）
10. `tests/workflows/test_rfgun_single_pass_imports.py`（风格参考）

**新增文件**：
- `workflows/rfgun_hom_antenna/__init__.py`
- `workflows/rfgun_hom_antenna/README.md`
- `workflows/rfgun_hom_antenna/run.py`
- `tests/workflows/test_workflow2_package_skeleton.py`

**更新文件**：
- `reports/restructure_plan/workflow2_current_context.md`

**运行命令**：
```powershell
python -m pytest tests/workflows/test_workflow2_package_skeleton.py -q
python -m pytest tests/workflows/test_workflow2_characterization.py -q
```

**测试结果**：
- Workflow2 skeleton tests: 9 / 9 passed
- W2-1 characterization tests: 21 / 21 passed (unchanged)

**关键事实**：
- `workflows/rfgun_hom_antenna/` 已创建，包含 `__init__.py`、`README.md`、`run.py`
- `__init__.py` 声明 `__legacy_entry__ = "run_workflow_2.py"`，docstring 记录完整迁移阶段
- `run.py` 仅含 placeholder 函数（`describe_legacy_entry()`、`get_legacy_entrypoint()`），不导入 CST/builder/orchestrator
- root `run_workflow_2.py` 未修改
- `scripts/schedule_workflow2.ps1` 未修改
- `config/default.yaml` 未修改
- `src/cst_optimization/**` 未修改

### 本轮（W2-3：workflow2 config isolation）

**执行时间**：2026-06-06

**分支**：`refactor/workflow2-config-isolation`（基于 `refactor/workflow2-package-skeleton`）

**读取的文件**：
1. `reports/restructure_plan/agent_operating_charter.md`
2. `reports/restructure_plan/workflow2_current_context.md`
3. `config/default.yaml`
4. `workflows/rfgun_hom_antenna/README.md`
5. `workflows/rfgun_hom_antenna/run.py`
6. `tests/workflows/test_workflow2_characterization.py`
7. `tests/workflows/test_workflow2_package_skeleton.py`
8. `run_workflow_2.py`（仅确认 legacy fallback 行为）
9. `src/cst_optimization/factory.py`（仅确认 builder 当前读取顶层 solver）

**新增文件**：
- `workflows/rfgun_hom_antenna/config.yaml`
- `tests/workflows/test_workflow2_config_isolation.py`

**更新文件**：
- `workflows/rfgun_hom_antenna/__init__.py`（W2-3 phase marker）
- `workflows/rfgun_hom_antenna/README.md`（config status 说明）
- `reports/restructure_plan/workflow2_current_context.md`

**运行命令**：
```powershell
python -m pytest tests/workflows/test_workflow2_config_isolation.py -v --tb=short
python -m pytest tests/workflows/test_workflow2_package_skeleton.py -q
python -m pytest tests/workflows/test_workflow2_characterization.py -q
```

**测试结果**：
- Config isolation tests: 6 / 6 passed
- W2-2 skeleton tests: 9 / 9 passed (unchanged)
- W2-1 characterization tests: 21 / 21 passed (unchanged)

**关键事实**：
- `workflows/rfgun_hom_antenna/config.yaml` 已创建为 raw `workflow_2` subtree snapshot
- 未合并顶层 `cst` / `solver` / `logging` fallback keys — 明确记录这是 raw snapshot 而非 merged runtime snapshot
- `optimization.solver.stagnation_timeout_s: 7200.0` 作为 intent 保留，并在 yaml header 中记录 W2-1 确认的离散
- `config/default.yaml` 未修改
- `run_workflow_2.py` 未修改
- `scripts/schedule_workflow2.ps1` 未修改
- `src/cst_optimization/**` 未修改

### 本轮（W2-4A：建立 workflow-local builder ownership seam）

**执行时间**：2026-06-07

**分支**：`refactor/workflow2-builder-seam`（基于 `refactor/workflow2-config-isolation`）

**读取的文件**：
1. `reports/restructure_plan/agent_operating_charter.md`
2. `reports/restructure_plan/workflow2_current_context.md`
3. `run_workflow_2.py`
4. `workflows/rfgun_hom_antenna/run.py`
5. `workflows/rfgun_hom_antenna/README.md`
6. `workflows/rfgun_hom_antenna/config.yaml`
7. `tests/workflows/test_workflow2_characterization.py`
8. `tests/workflows/test_workflow2_package_skeleton.py`
9. `tests/workflows/test_workflow2_config_isolation.py`
10. `src/cst_optimization/factory.py`（仅确认 import/return contract）

**新增文件**：
- `workflows/rfgun_hom_antenna/workflow.py`
- `tests/workflows/test_workflow2_builder_seam.py`

**更新文件**：
- `run_workflow_2.py`（import repoint: 从 `cst_optimization.factory` → `workflows.rfgun_hom_antenna.workflow`）
- `workflows/rfgun_hom_antenna/__init__.py`（phase markers, docstring）
- `workflows/rfgun_hom_antenna/README.md`（builder seam status, phase markers）
- `reports/restructure_plan/workflow2_current_context.md`

**运行命令**：
```powershell
python -m pytest tests/workflows/test_workflow2_builder_seam.py -v
python -m pytest tests/workflows/test_workflow2_characterization.py -q
python -m pytest tests/workflows/test_workflow2_config_isolation.py -q
python -m pytest tests/workflows/test_workflow2_package_skeleton.py -q
```

**测试结果**：
- Builder seam tests: 9 / 9 passed
- W2-1 characterization tests: 21 / 21 passed (unchanged)
- W2-3 config isolation tests: 6 / 6 passed (unchanged)
- W2-2 skeleton tests: 9 / 9 passed (unchanged)

**关键事实**：
- `workflows/rfgun_hom_antenna/workflow.py` 已创建为 thin delegation wrapper
- `build_workflow_2(config, checkpoint_callback=None)` 通过 `_legacy_build` 委托到 shared factory
- root `run_workflow_2.py` 的 import 已从 `cst_optimization.factory` 改为 `workflows.rfgun_hom_antenna.workflow`
- 未复制任何 builder implementation（W2-4A 只做 seam）
- `src/cst_optimization/factory.py` 未修改
- `src/cst_optimization/core/**` 未修改
- `config/default.yaml` 未修改
- `workflows/rfgun_hom_antenna/config.yaml` 未修改
- `scripts/schedule_workflow2.ps1` 未修改

### 本轮（W2-4B：builder implementation migration）

**执行时间**：2026-06-07

**分支**：`refactor/workflow2-builder-migration`（基于 `refactor/workflow2-builder-seam`）

**读取的文件**：
1. `reports/restructure_plan/agent_operating_charter.md`
2. `reports/restructure_plan/workflow2_current_context.md`
3. `workflows/rfgun_hom_antenna/workflow.py`
4. `src/cst_optimization/factory.py`
5. `tests/workflows/test_workflow2_characterization.py`
6. `tests/workflows/test_workflow2_builder_seam.py`

**修改的文件**：
- `workflows/rfgun_hom_antenna/workflow.py`（实现体迁移 + docstring 修复）
- `src/cst_optimization/factory.py`（`build_workflow_2` → 兼容性 wrapper，lazy import）
- `tests/workflows/test_workflow2_characterization.py`（patch targets → `workflows.rfgun_hom_antenna.workflow.CSTConnection`）
- `tests/workflows/test_workflow2_builder_seam.py`（重写为 W2-4B 语义）
- `workflows/rfgun_hom_antenna/__init__.py`（phase markers）
- `workflows/rfgun_hom_antenna/README.md`（W2-4B status）
- `reports/restructure_plan/workflow2_current_context.md`

**运行命令**：
```powershell
python -m pytest tests/workflows/test_workflow2_characterization.py -q
python -m pytest tests/workflows/test_workflow2_builder_seam.py -q
python -m pytest tests/workflows/test_workflow2_config_isolation.py -q
python -m pytest tests/workflows/test_workflow2_package_skeleton.py -q
```

**测试结果**：43 / 43 passed

| Suite | Tests | Status |
|-------|-------|--------|
| W2-1 characterization | 21 | ✅ |
| W2-4B builder seam | 7 | ✅ |
| W2-3 config isolation | 6 | ✅ |
| W2-2 skeleton | 9 | ✅ |

**关键事实**：
- `workflows/rfgun_hom_antenna/workflow.py` 现在 OWN `build_workflow_2` 完整实现
- 旧 docstring "创建独立 CST 窗口" → "单 CST 连接，顺序执行"（与代码一致）
- `src/cst_optimization/factory.py::build_workflow_2` 现在是兼容性 wrapper（lazy import + 委托）
- 旧 import 路径 `from cst_optimization.factory import build_workflow_2` 仍然可用
- factory wrapper 现带有正确的 4 元返回类型注解（R3 部分解决）
- `DualProjectOrchestrator` 未移动
- `src/cst_optimization/core/**` 未修改
- `config/default.yaml` 未修改
- `scripts/schedule_workflow2.ps1` 未修改

后续每一轮本地 agent 都应更新本节，记录实际运行的命令和结果。

### 整体状态

- W2-0: accepted.
- W2-1: accepted.
- W2-2: accepted.
- W2-3: accepted.
- W2-4A: accepted.
- **W2-4B: pending web review** — 43/43 tests pass, builder implementation migrated.
- 未运行 live workflow。
- 未运行 CST。
- **builder implementation migrated** — factory/orchestrator/core/scheduler/config 均未修改。

## 11. 当前推荐下一步

### W2-4B 已完成

- ✅ 从 `refactor/workflow2-builder-seam` 创建 `refactor/workflow2-builder-migration` 分支
- ✅ `workflows/rfgun_hom_antenna/workflow.py` 现在 OWN `build_workflow_2` 完整实现
- ✅ `src/cst_optimization/factory.py::build_workflow_2` 替换为兼容性 wrapper（lazy import + 委托）
- ✅ 旧 import 路径 `from cst_optimization.factory import build_workflow_2` 仍然可用
- ✅ 修复 builder docstring：单 CST 连接（取代旧"独立窗口"描述）
- ✅ 43 total tests pass
- ✅ `DualProjectOrchestrator` 未移动
- ✅ `src/cst_optimization/core/**` 未修改
- ✅ `config/default.yaml` 未修改
- ✅ `scripts/schedule_workflow2.ps1` 未修改
- ⏳ 等待 web reviewer 审计通过

### W2-5（通过 W2-4B 审计后的建议）：orchestrator ownership assessment

通过 W2-4B 审计后，建议进入 W2-5 评估 `DualProjectOrchestrator` 的归属 — 是保持 core 原位，还是在其他 workflow 无依赖后迁入 workflow2 package。

**注意**：W2-5 只做评估和文档，不做迁移。如果确需迁移，应在后续单独阶段进行。
