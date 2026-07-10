# CST 自动化与优化项目总状态上下文

更新时间：2026-07-10（严格 workflow 分支隔离重构后）

本文是当前仓库的总入口，供人类维护者和后续 agent 快速恢复上下文。
代码、测试、当前 Git diff 和分支本身优先于历史报告。除非用户明确要求，
不要运行 CST、杀进程、删除锁、清理 campaign 或改写本地结果。

## 1. 执行摘要

四个用户提供的目录原本不是四个独立仓库，而是同一 Git 仓库的多个
worktree。2026-07-10 已按“严格隔离式 main”重构：

- `main` 只保留共享核心、通用 CST history/STEP 工具、官方 CST 文档和
  纯共享测试；不包含具体 workflow、入口、campaign 配置或 workflow-only
  测试。
- 每个具体工作流位于独立的 canonical `workflow/*` 分支，并从严格
  `main` 建立。
- WF2 已把收口后未提交的“未知纵向 HOM 频率窗口拟合”纳入正式分支，
  同时重写收口状态和科学限制。
- 本次重构只运行 no-CST 测试与 `compileall`，没有启动 live-CST。
- 所有大改动前已创建本地归档、完整 Git bundle 和远端备份分支。

## 2. Canonical 分支与 worktree

| 分支 | 当前 worktree | 责任边界 | no-CST 基线 |
|---|---|---|---:|
| `main` | `C:\Users\lau\cst_ver3` | 共享核心与通用工具 | 581 passed |
| `workflow/1-rfgun-sao` | `C:\Users\lau\cst_ver3_wf1` | WF1 SAO、单/双 pass、分阶段与自适应搜索 | 1087 passed, 1 skipped |
| `workflow/2-rfgun-hom-antenna` | `C:\Users\lau\cst_ver3_wf2_major_refactor` | WF2 双工程 HOM 天线优化、wake PSO | 724 passed, 1 skipped |
| `workflow/3-rfgun-recovery-tolerance` | `C:\Users\lau\cst_ver3_wf3` | WF3 recovery 与 tolerance 工具链 | 692 passed, 1 skipped |
| `workflow/4-rfgun-hom-eigenmode` | `C:\Users\lau\cst_ver3_HOMwork` | WF4 HOM 本征模批量 campaign | 615 passed, 2 skipped |
| `workflow/rf-cem-500mhz` | `C:\Users\lau\cst_ver3_project` | RF-CEM 500 MHz 逆向参数化几何与优化 | 606 passed, 1 skipped |

`codex/S01-known-mode-pso-closure` 是 WF2 的收口兼容 ref，应与
`workflow/2-rfgun-hom-antenna` 指向同一状态。历史 phase/codex 分支不是
开发基线；需要历史证据时使用第 12 节的备份。

查询当前准确提交，不要从旧报告复制 hash：

```powershell
git fetch --prune origin
git rev-parse main
git rev-parse workflow/2-rfgun-hom-antenna
git worktree list
```

## 3. 分支使用规则

1. 共享代码只在 `main` 开发和验证。
2. workflow 分支定期 rebase 到最新 `main`，但不得把其他 workflow 包带入。
3. workflow-specific 代码先留在自己的 `workflows/<package>/`。
4. 只有在两个以上工作流真实复用、接口稳定、单位和错误语义清楚后，才提级
   到 `src/cst_optimization/`。
5. 提级时先在 `main` 添加共享实现和纯核心测试，再让各 workflow 分支删除
   本地副本并改用共享实现。
6. 禁止把共享模块复制到 workflow 包下换名保留；这会重新制造漂移。
7. 本地 CST 路径、结果、数据库、JSONL、checkpoint、日志和 scratch 脚本
   不得提交。

## 4. `main`：共享核心

### 4.1 包结构

| 路径 | 作用 |
|---|---|
| `src/cst_optimization/core/` | 已验证 CST connection/project/solver/results/retry/cleanup/timeout wrapper |
| `src/cst_optimization/evaluation/` | SQLite evaluation DB、schema、dedup、warm start、reuse、failure skip、retry taxonomy/runtime |
| `src/cst_optimization/objectives/` | 通用频率、Q、场、mode objective |
| `src/cst_optimization/optimization/` | SAO、SAEA、acquisition、sampling、adaptive bounds、resume |
| `src/cst_optimization/parameters/` | 参数范围、参数集与约束 |
| `src/cst_optimization/physics/` | cavity、wakefield、Poynting、heating 和单位明确的公式 |
| `src/cst_optimization/workflows/` | workflow 间稳定的 evaluator/evaluation contract；不是具体 workflow 包 |
| `src/cst_optimization/factory.py` | 共享 parameter/objective/optimizer/weight builders；没有具体 `build_workflow_N` |
| `src/cst_optimization/runner.py` | workflow CLI 可继承的 `BaseRunner` |
| `src/cst_optimization/checkpoint.py` | pickle checkpoint 与 evaluation 状态 |
| `src/cst_optimization/database.py` | CST 1D 曲线记录、NPZ 保存与离线 replay |
| `src/cst_history_extractor/` | CST history/macro 提取与 recipe manifest |
| `src/step_feature_assistant/` | STEP 拓扑、FeatureGraph、UDSG 层和人工审核器 |

### 4.2 CST wrapper 边界

- `CSTConnection.new_mws_project()` 使用 CST 2026 已验证的
  `DesignEnvironment.new_mws()`。
- `CSTProject.execute_vba(..., timeout=...)` 只透传已验证
  `Model3D.add_to_history` timeout 语义。
- `CSTConnection.close_targeted()` 只处理当前连接记录的 PID，不进行全局进程
  sweep；只适用于独占 `mode="new"` DesignEnvironment 且工程已显式关闭的
  workflow。
- 不得根据名称猜测新的 `cst.interface` 或 `cst.results` API。

### 4.3 通用工具入口

安装推荐使用 editable 模式：

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

CST history 提取：

```powershell
.venv\Scripts\python.exe -m cst_history_extractor `
  --history-macro examples\example_history.bas `
  --output-dir runs\history_example
```

STEP feature assistant：

```powershell
.venv\Scripts\python.exe -m step_feature_assistant `
  --step-file StepData\bare_cavity_500mhz.stp `
  --output-dir runs\bare_cavity_500mhz `
  --axis z `
  --model-type bare_cavity_500mhz `
  --backend cadquery `
  --preview html
```

CadQuery/OCP 在此 Windows 环境可能在解释器退出时触发 access violation。
生产路径使用隔离 worker；不要把直接 `import cadquery` 后的异常退出误判为
几何计算结果失败。

## 5. WF1：RF gun SAO

- 分支：`workflow/1-rfgun-sao`
- 根入口：`run_workflow_1.py`
- 实际 runner：`workflows/rfgun_sao/run.py`
- 运行配置：`workflows/rfgun_sao/config.yaml`
- validated reference：`workflows/rfgun_single_pass/`

帮助与常用入口：

```powershell
.venv\Scripts\python.exe run_workflow_1.py --help
.venv\Scripts\python.exe run_workflow_1.py --config workflows\rfgun_sao\config.local.yaml
.venv\Scripts\python.exe run_workflow_1.py --seed 43 --n-initial 1 --n-iter 0
```

主要能力：

- 默认 single-pass SAO；保留 validated single-pass reference。
- 可选 two-pass calibration/measurement。
- metric role：optimize、threshold、report-only、gate。
- staged search、adaptive bounds、evaluation DB warm start、success reuse、
  failure-skip 和多层 retry。
- checkpoint 与可选 JSONL diagnostic sidecar。

限制与要求：

- live-CST 路径只能放在 gitignored `config.local.yaml` 或显式 `--config`。
- 两 pass 的 CST runtime 必须显式启用；不要把 placeholder 路径当作 live 结果。
- 对 cleanup、retry、checkpoint 或 DB schema 的更改必须跑完整分支测试。
- 根 shim 只属于该分支，`main` 上不存在。

## 6. WF2：双工程 HOM 天线优化

- 分支：`workflow/2-rfgun-hom-antenna`
- 收口兼容 ref：`codex/S01-known-mode-pso-closure`
- 根入口：`run_workflow_2.py`
- 实际 runner：`workflows/rfgun_hom_antenna/run.py`
- 唯一配置源：`workflows/rfgun_hom_antenna/config.yaml`
- builder：`workflows/rfgun_hom_antenna/workflow.py`
- 收口文档：`docs/workflows/wf2_known_mode_pso_closure.md`
- 操作契约：`docs/workflows/wf2_known_mode_pso_operational_contract.md`

CLI：

```powershell
.venv\Scripts\python.exe run_workflow_2.py --help
.venv\Scripts\python.exe run_workflow_2.py --auto-resume --heartbeat
.venv\Scripts\python.exe run_workflow_2.py --auto-resume --recovery-only
.venv\Scripts\python.exe run_workflow_2.py --warmup-from-db D:\Results\wf2_warmup_total\index.total.jsonl
.venv\Scripts\python.exe run_workflow_2.py --config D:\smoke\config.yaml --smoke-only
```

主要能力：

- `DualProjectOrchestrator` 顺序管理 frequency-domain 与 wakefield 工程。
- `template_copy` 模式为每次 attempt 使用工程副本，避免直接污染模板。
- crash recovery、phase snapshot、heartbeat、warmup bundle 和 adaptive gate。
- antenna absorption、transmission、longitudinal/transverse impedance objective。
- wake-domain PSO 支持固定 known longitudinal modes，并拟合剩余未知 HOM。
- 未知纵向 HOM 可选 bounded frequency fit：默认关闭；启用后变量由 `[A,Q]`
  变为 `[f,A,Q]`，频率只能在显式 `half_width_hz` 窗内移动；重叠窗口和
  transverse frequency fit fail closed。
- `quadratic_peak_barrier` scalarization 同时保留在直接 CST impedance 和
  PSO reconstruction 路径。

科学限制：

- known mode 的频率、Q、R/Q 仍是固定输入；频率拟合只作用于剩余未知
  longitudinal HOM。
- 单次 PSO 的 HOM Q/RQ 或重建阻抗不是唯一物理解。
- 主要可信证据是多起点/多 seed 的 wake residual、correlation 和稳定性。
- 不得把该模块单独作为最终 pass/fail gate。

代码边界：

- `main` 的 `cst_optimization.factory` 不再提供
  `build_workflow_2` compatibility wrapper。
- WF2-only retry adapter 已回到 `workflows/rfgun_hom_antenna/workflow.py`。
- 原始 `analysis_outputs/` 和研究草稿保持本地，不提交。

## 7. WF3：recovery 与 tolerance

- 分支：`workflow/3-rfgun-recovery-tolerance`
- recovery 入口：`run_workflow_3.py`
- recovery 配置：`config/workflow_3.yaml`
- tolerance 默认配置：`config/default.yaml`
- 包：`workflows/rfgun_recovery/`、`workflows/rfgun_tolerance/`

Recovery：

```powershell
.venv\Scripts\python.exe run_workflow_3.py --help
.venv\Scripts\python.exe run_workflow_3.py `
  --resume-from runs\workflow3\stage_2\evaluation_records.jsonl
```

Tolerance sampling（需要 CST）：

```powershell
.venv\Scripts\python.exe -m workflows.rfgun_tolerance.run `
  --config config\default.yaml `
  --tolerance-scale 1.0 1.67 3.33
```

单数据库分析（no-CST）：

```powershell
.venv\Scripts\python.exe -m workflows.rfgun_tolerance.cli `
  --db path\to\evaluations.db `
  --output runs\tolerance\report.md
```

跨 tolerance level 分析（no-CST）：

```powershell
.venv\Scripts\python.exe -m workflows.rfgun_tolerance.campaign_cli `
  --config config\default.yaml `
  --db 3=path\to\tolerance_eval_3um.db `
  --db 5=path\to\tolerance_eval_5um.db `
  --output runs\tolerance\campaign_report.md
```

限制：数据库、分析报告和 campaign 结果全部是本地产物；recovery 的
`--resume-from` 必须指向 schema 兼容的成功记录，不能把部分失败记录静默
当作零 penalty。

## 8. WF4：HOM eigenmode campaign

- 分支：`workflow/4-rfgun-hom-eigenmode`
- 根入口：`run_workflow_4.py`
- 包：`workflows/rfgun_hom_eigenmode/`
- 配置：`workflows/rfgun_hom_eigenmode/config.yaml`
- 测量目标：`HOMwork/eigenmode_frequency_targets.csv`
- 当前 campaign 交接：`HOMwork/HOM_Campaign_Current_Status_2026-06-25.md`

CLI：

```powershell
.venv\Scripts\python.exe run_workflow_4.py --help
.venv\Scripts\python.exe run_workflow_4.py --plan-only
.venv\Scripts\python.exe run_workflow_4.py --resume-preview
.venv\Scripts\python.exe run_workflow_4.py --offline-only <campaign_dir>
.venv\Scripts\python.exe run_workflow_4.py --audit-results
```

只有用户明确要求时才可实际 resume/run CST。模板 revision adoption 需要
显式 `--adopt-template-revision` 和 provenance note。

当前 campaign 摘要：

- 60 条测量目标，聚为 39 个 target cluster。
- 116 个 solver windows，323 条 eigenmode candidate。
- 576 条 mode-target map，995 条 mode-condition result，0 unmatched target。
- 频率匹配高度歧义：2 matched、574 ambiguous。
- 316/323 条模式触及每窗口最多 3 模的模板上限；63 个 window 标为
  `mode_enumeration_incomplete`。
- native CST Voltage 与 `R over Q beta=1` 是纵向权威量；Ez line integral
  crosscheck 只作 warning。
- 传播端口 warning 和 template revision 混合必须保留 provenance，不能据此
  删除原始候选。

原始 campaign CSV/JSON 保持不可变。下游派生表另存新文件，不得覆盖输入
CSV 或顶层输出。

## 9. RF-CEM 500 MHz 参数化几何

- 分支：`workflow/rf-cem-500mhz`
- 共享前置：`cst_history_extractor`、`step_feature_assistant`
- RF-CEM 包：`src/rf_cem/`
- 优化包：`workflows/rf_cem_500mhz_parametric_opt/`
- 配置：`workflows/rf_cem_500mhz_parametric_opt/config.yaml`
- 状态：`docs/rf_cem_parametric_geometry_status.zh.md`
- 工作站交接：`docs/rf_cem_workstation_agent_handoff_2026-07-09.md`

数据链：

```text
reviewed feature labels / expert prior
  -> 12D curve controls
  -> parametric_geometry.v0.json
  -> generated_vacuum.step
  -> CSTTranslator setup
  -> Tetrahedral eigenmode solve
  -> Frequency / R over Q / Q result-tree readback
```

No-CST candidate generation：

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m workflows.rf_cem_500mhz_parametric_opt.runner `
  --output-dir runs\rf_cem_500mhz_parametric_opt_12d_no_cst_smoke
```

Live campaign（需要已验证模板、CST 2026 library 和许可证）：

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m workflows.rf_cem_500mhz_parametric_opt.live_campaign `
  --mode sao `
  --output-dir runs\rf_cem_500mhz_sao `
  --template-project-dir "D:\ModelData\bare" `
  --library-path "D:\CST2026\CST Studio Suite 2026\AMD64\python_cst_libraries" `
  --seed-candidate-index 4 `
  --local-bounds-scale 0.35 `
  --max-evals 10
```

已验证状态：

- `free_equator_smooth` 是当前几何基线，预设为 `exploratory_12d`。
- 几何参数通过 expert-prior override 重新生成 STEP，不直接使用
  CST `StoreParameter` 作为真值源。
- 成功 live 路径是 Copper (annealed) background、Vacuum imported body、
  Tetrahedral eigenmode 和 `.rpp/.r0d` result-template registration。
- 第一轮 seeded SAO campaign 为 60/60 `SUCCESS`。
- 当前优先候选是 candidate 039（最高 R/Q）和 candidate 046（最高
  `R=(R/Q)*Q`），但必须在工作站审计完整 STEP、validation、audit HTML 和
  CST 工程后才能作为新 seed。

当前缺口：

- objective 仍过度奖励精确贴近 500 MHz；下一步应把 490–510 MHz 作为
  低/零惩罚窗口，主要提高 R/Q 与 shunt impedance，Q 使用 soft floor。
- CLI 还不能从上一轮 `live_records.jsonl` 任意选择 seed record；目前只支持
  quick-scan `--seed-candidate-index`。
- smooth NURBS 必要时仍 fallback 到 dense sampled profile，必须保留
  generation-mode provenance。
- 12D 范围和物理 hard gate 尚需人工确认；multi-cell、非轴对称、
  coupler/HOM/thermal/structural/multipacting 不在当前完成范围。
- `Appendix/`、CST 工程、工作站 `runs/` 和二进制参考资料是本地输入/产物，
  不提交。

## 10. 配置、单位和 CST 安全要求

- 频率必须明确 Hz、MHz 或 GHz；不要靠字段名猜测单位。
- Q 无量纲；R/Q 使用 ohm；横向阻抗使用 ohm/m；wake distance 在进入公式前
  统一为 m。
- 派生 `R = (R/Q) * Q` 的单位是 ohm。
- CST project/library/output 路径应放在 gitignored local config 或 CLI。
- 当前部分历史 tracked YAML 仍带本机 `D:/...` 示例路径；它们是已验证机器
  默认值，不是可移植保证。后续应拆成 portable example + local override，
  在此之前不要在其他机器盲目运行默认配置。
- `EvaluateResultTemplates` 在 RF-CEM Tetrahedral 路径可能产生非致命
  `HEX mesh is invalid`；result-tree readback 已足够时不要默认启用。
- 任何 kill、lock 删除、result-folder 清理或 campaign recovery 都需要用户
  明确授权。

## 11. 验证方法与本次结果

统一使用：

```powershell
.venv\Scripts\python.exe -m pytest tests -q --tb=short
.venv\Scripts\python.exe -m compileall -q src workflows run_workflow_*.py
git diff --check
```

本次 no-CST 结果见第 2 节。测试中的 skipped 项主要来自本地可选 CAD/HDF5
fixture 或依赖，不代表 CST live 测试。一次 WF1 重跑时共享 Python 3.9 在
标准库 `ast.walk` 中发生 Windows access violation；隔离测试 40/40 通过后，
完整 WF1 suite 稳定重跑为 1087 passed、1 skipped。

本次没有进行 live-CST 验证。历史 live 结果只能作为已知证据，不能替代修改
后的新 live smoke。

## 12. 重构前备份与恢复

本地备份目录：

```text
C:\Users\lau\cst_ver3_strict_reorg_backup_20260710T121115
```

内容：

- `repository-all-refs.bundle`：完整 Git refs，已通过 `git bundle verify`。
- 四个原始 worktree ZIP：包含 tracked、modified 和 untracked 文件；排除
  `.venv/`、`runs/`、`dist/`、cache 和 pyc。
- `README.md`：SHA-256 与恢复说明。

远端备份 refs：

```text
backup/pre-strict-reorg-20260710-main
backup/pre-strict-reorg-20260710-homwork
backup/pre-strict-reorg-20260710-cst-step
backup/pre-strict-reorg-20260710-wf2-closure
backup/pre-clean-wf2-closure-20260710
backup/pre-strict-reorg-20260710-wf2-worktree
backup/pre-strict-reorg-20260710-stale-workflows
backup/post-backup-cst-step-assistant-changes-20260710
```

其中后三条分别保留旧 WF2 worktree、旧 WF1/WF3 同源分支，以及初始归档后
才提交的 CST/STEP assistant 改动。对应旧 `codex/*`、`phase/*` 和过时
`workflow/*` 开发 ref 已在确认这些备份可达后清理；WF2 收口兼容 ref 除外。

不要直接覆盖当前 worktree。恢复时先克隆到新目录：

```powershell
git clone C:\Users\lau\cst_ver3_strict_reorg_backup_20260710T121115\repository-all-refs.bundle restored-repository
```

## 13. 交接检查清单

后续 agent 开始工作时：

1. 确认 cwd、branch、HEAD、`git status --short --branch`。
2. 阅读根 `AGENTS.md`、本文和目标 workflow 自己的 README/status。
3. 确认要改的是共享核心还是 workflow-only 行为。
4. 搜索现有 wrapper、builder、objective 和测试，禁止猜 CST API。
5. 先跑目标测试建立基线。
6. 修改科学计算时写明单位、假设和失败语义。
7. 不碰本地结果和未跟踪输入；大改动前创建新备份 ref/归档。
8. 完成后运行 branch-local 全量 no-CST、`compileall`、`git diff --check`。
9. 明确报告 no-CST 与 live-CST 哪些已运行、哪些未运行。

## 14. 当前优先级

1. RF-CEM：工作站审计 candidate 039/046，确定下一轮 seed。
2. RF-CEM：实现 `--seed-record-path` + `--seed-record-index`，并重新标定
   490–510 MHz window objective。
3. WF2：只在有物理依据时启用 unknown-HOM frequency fit；补多 seed 稳定性
   报告，不把单解当唯一反演。
4. WF4：对关键频段解决 3-mode enumeration censoring 和 ambiguous mapping；
   非明确要求不要重跑全 campaign。
5. 所有 workflow：逐步把 tracked 本机路径拆成 portable example 与
   gitignored local config，但不得破坏已验证 CST 路径。
