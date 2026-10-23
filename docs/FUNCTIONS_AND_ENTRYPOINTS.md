# 命令与源码入口

更新：2026-09-05。用途：找到已有能力再动手。项目状态及能力边界见 [PROJECT_STATUS_CONTEXT.md](PROJECT_STATUS_CONTEXT.md)；精确参数以源码和 `--help` 为准。

## 1. 执行环境与输入定位

从当前 clone/worktree 根目录运行，使用它自己的虚拟环境：

```powershell
$py = '.\.venv\Scripts\python.exe'
$taskRecipe = Get-Content -Raw -Encoding UTF8 config/rf_cem_workbench_profile.v0.json | ConvertFrom-Json
```

`pyproject.toml` 记录依赖：基础数值/优化库，`cad` 为 CadQuery，`review` 为 Plotly，`dev` 为 pytest。已有环境能工作时不因一次文档或代码审阅升级依赖。

`config/rf_cem_workbench_profile.v0.json` 集中定位 family profile、R1 图、R2 record、R3/R4 bundle、SLS-2 文献/审核及 SQLite。这些输入多数在本地 `analysis_outputs/`，不随 Git 自动到达。找不到时报告具体缺项。

表中“no-CST”表示不启动 CST；仍可能读取此前从 CST 或人工审核取得的文件。“build”通常写入新的本地产物；不要把它当纯读取。

## 2. RF-CEM 当前 no-CST 命令

以下模块均由 `workflow/rf-cem-literature-review` 维护。

| 模块（`python -m` 后） | 子命令 / 用途 | 主要源码 |
| --- | --- | --- |
| `rf_cem.literature_semantics` | validate、draft-prior、merge-prior、audit；arxiv-search/fetch、render-evidence、corpus-audit、review-gui | `literature_semantics/cli.py` |
| `rf_cem.family_profile` | build、validate；保留两个实例的各自原生参数 | `family_profile/` |
| `rf_cem.semantic` | build、validate、diff；R1 已审核拓扑 | `semantic/cli.py`、`contracts.py`、`adapters.py` |
| `rf_cem.compiler` | build、validate；两个已有实例的 R2 编译 | `compiler/cli.py`、`core.py`、`adapters.py` |
| `rf_cem.semantic.induction` | build、build-ablation、validate；R3 结构提案与 proof | `semantic/induction/` |
| `rf_cem.observation` | build、validate；R4 描述符及约束示例 | `observation/` |
| `rf_cem.semantic_acquisition` | **a0-coverage**；当前仅此探针 | `semantic_acquisition/cli.py`、`a0_coverage.py`、`boundary_signals.py` |
| `rf_cem.workbench` | status、rebuild、serve；派生索引及只读 Web | `workbench/profile.py`、`indexer.py`、`server.py` |
| `rf_cem.workbench.desktop` | 固定动作桌面启动器，支持 --self-test | `workbench/desktop.py` |

源码路径在 `src/rf_cem/` 下。A0.5、A1–A3、LLM provider、原型检索目前没有可调用入口。

### 常用读取与校验

先执行第 1 节初始化；以下命令消费 profile 中的已有输入：

```powershell
& $py -m rf_cem.semantic validate --grammar $taskRecipe.family_grammar --graph $taskRecipe.instance_boundary_graphs[0] --graph $taskRecipe.instance_boundary_graphs[1]
& $py -m rf_cem.semantic diff --left $taskRecipe.instance_boundary_graphs[0] --right $taskRecipe.instance_boundary_graphs[1]
$taskCompileRoot = Split-Path (Split-Path $taskRecipe.compile_records[0])
& $py -m rf_cem.compiler validate --bundle-root $taskCompileRoot --record $taskRecipe.compile_records[0] --record $taskRecipe.compile_records[1]
& $py -m rf_cem.semantic.induction validate --bundle $taskRecipe.family_induction_bundle
& $py -m rf_cem.observation validate --root . --bundle $taskRecipe.observation_contract_bundle
```

这些校验检查结构、引用或文件身份；不验证标签是否科学正确。R4 当前 proof 对 roadmap 正文有字节绑定，兼容限制见状态入口。

### A0 覆盖探针

已有报告：

```text
analysis_outputs/rf_cem_acquisition_a0/
  a0_landmark_coverage.f23faf606b9652e4/
    a0_coverage_report.v0.json
    a0_coverage_report.md
    landmark_coverage.png
    source_binding_manifest.v0.json
```

需要实际再做实验时，使用新的 output root：

```powershell
& $py -m rf_cem.semantic_acquisition a0-coverage --root . --compile-record $taskRecipe.compile_records[0] --instance-graph $taskRecipe.instance_boundary_graphs[0] --output-root analysis_outputs/rf_cem_acquisition_experiments
```

默认采样数 512/2048，merge/stability 容差 `u=0.005`，覆盖容差 `u=0.02`；其余阈值见 `SignalParameters` 或 `a0-coverage --help`。长度 mm、曲率 1/mm、切向角 deg、`u=s/L` 无量纲。目标已存在会拒绝覆盖。

**解释限制：**A0 从 R2 landmark binding 取得参考坐标；其中一些是适配器的参数等分约定。4/8 表示对当前分区的覆盖，不是自动语义识别准确率。

### Workbench / Desktop

```powershell
& $py -m rf_cem.workbench status --repo-root . --profile config/rf_cem_workbench_profile.v0.json
& $py -m rf_cem.workbench rebuild --repo-root . --profile config/rf_cem_workbench_profile.v0.json
& $py -m rf_cem.workbench serve --repo-root . --profile config/rf_cem_workbench_profile.v0.json --port 0
```

status 是读取；rebuild 替换派生 SQLite；serve 打印随机 token 的 loopback URL。Web 是固定 GET 路由，不保存审核意见。前台服务用 Ctrl+C 结束。

```powershell
& $py -m rf_cem.workbench.desktop --self-test --repo-root . --no-browser
& $py -m rf_cem.workbench.desktop --repo-root .
```

Windows 打包使用 `scripts/build_rf_cem_workbench_desktop.ps1`，需要当前环境中的 PyInstaller，生成 ignored `dist/RF-CEM-Workbench.exe`。普通查看无需重新打包。Desktop 自检可能启动自己拥有的本地 Web 子进程；只想读状态时用 Workbench status。

### 文献/几何审核 GUI

这与 Workbench 是不同服务。实际 session 路径从原启动记录或已有会话定位；下例中的占位符必须替换：

```powershell
& $py -m rf_cem.literature_semantics review-gui --bundle-root '<PILOT_BUNDLE_ROOT>' --manifest corpus_manifest.json --paper-id sls2 --session-root '<EXISTING_OR_NEW_SESSION_ROOT>' --port 0
```

功能：Evidence 原页、Semantic candidates 的确认/拒绝/待证据、SLS-2 六参数投影、baseline/previous/current 比较、Helper2 face/feature/UDSG 审核。审核会写 session；GUI 不启动 CST，不自动改生产 prior。

`merge-prior` 是另一个显式命令，会生成合并后的 prior；不能由“打开 GUI”推导出执行它。常温/超导物理先验按 regime 区分；当前 SLS-2 几何投影只覆盖其既有模型。

### 需要重新构造 R1–R4 时

先看对应 build 的 `--help`，再用集中输入路径组装命令，避免复制陈旧 proof 路径。实际参数摘要：

| 构造 | 必要输入 |
| --- | --- |
| R1 build | --repo-root、--family-profile、--sls2-generation、--sls2-semantics、--sls2-review、--output-root |
| R2 build | --repo-root、--family-profile、--family-grammar、两个 --instance-boundary-graph、--sls2-generation、--sls2-baseline-step、--output-root |
| R3 build-ablation | grammar、两个 training graph、LEReC 两篇 PDF、实际审核决定及 output root；精确参数查 help |
| R4 build | --root、两个 --compile-record、两个 --instance-graph、--output-root；可指定 --architecture-document |

这些构造命令是当前两个实例的集成演示，不是任意新实例的通用 ingestion API。重用已有 proof 足以回答的问题，不必重建。

## 3. 代码职责与关键数据

| 路径 | 找什么 |
| --- | --- |
| `src/rf_cem/semantic/ontology.py` | 六类 region、三类 landmark 的当前定义 |
| `src/rf_cem/semantic/contracts.py` | FamilyGrammar、InstanceBoundaryGraph、图合法性与准入 |
| `src/rf_cem/semantic/adapters.py` | SLS-2/RF500 标签、source ref 和审核绑定如何进入图 |
| `src/rf_cem/representation/core.py` | Line/CircularArc/EllipseArc/SplineApprox/Composite、RegionGeometry、GeometryPatch |
| `src/rf_cem/compiler/adapters.py` | 原生曲线与 region 绑定，含多 owner 参数等分 |
| `src/rf_cem/compiler/core.py`、`contracts.py` | ProfileCompiler、连续性与实现约束、compile_record v0/v1/v2 |
| `src/rf_cem/semantic/induction/engine.py`、`alignment.py` | 已知类型残差、公共骨架与固定检测器 |
| `src/rf_cem/semantic/induction/blind.py`、`review.py` | LEReC 手工序列适配、提案审核与 grammar patch |
| `src/rf_cem/observation/observer.py`、`descriptors.py`、`constraints.py` | 形状观察、描述符及不修改几何的约束求值 |
| `src/rf_cem/semantic_acquisition/` | 当前 A0，信号提取与对既有分区的评分 |
| `src/rf_cem/workbench/indexer.py` | 派生实体、固定能力/阶段目录 |
| `src/rf_cem/literature_semantics/` | PDF/arXiv、语义 package、prior draft、review app/server/session |

`family_profile.v0` 保存原生来源，不是通用几何参数向量；`family_grammar.v0` 描述允许结构；`instance_boundary_graph.v0` 描述已标注实例；`compile_record.v2` 保存编译/连续性/产物关联。R4 的 exact、shape、scalar 各司其职，采样与标量不能替代几何生成输入。

这些边界目前有用：semantic 不依赖 CAD/CST；representation 不依赖具体 family；compiler 组合两侧；observation 读取几何；Workbench 派生展示。共享代码提级到 main 仍以真实复用为依据。

## 4. 共享工具与其他工作流

共享 owner 为 `main`：

| 入口 / 路径 | 用途 |
| --- | --- |
| `python -m cst_history_extractor` | 从宏或工程 history 提取命令和 recipe；额外 probe 行为先查 help |
| `python -m step_feature_assistant` | STEP 几何事实、Feature 候选及 HTML 审核 |
| `python -m step_feature_assistant.calibration_cli` | 基于审核案例的规则建议 |
| `python -m step_feature_assistant.classifier_cli` | 数据导出与建议型分类器；不等于 RF-CEM 的开放语义获取 |
| `src/cst_optimization/core/` | connection、project、solver、results、retry/timeout/cleanup |
| `src/cst_optimization/evaluation/` | evaluation DB、复用、失败与重试 |
| `src/cst_optimization/optimization/` | SAO/SAEA、acquisition、sampling、bounds |
| `src/cst_optimization/objectives/`、`parameters/`、`physics/` | 目标、参数及有单位的物理计算 |
| `factory.py`、`runner.py`、`checkpoint.py`（共享包内） | 构造器、BaseRunner、CheckpointManager |

具体 workflow 只在各自 canonical 分支维护：WF1/2/3/4 分别通过 `run_workflow_1.py` 到 `run_workflow_4.py` 及分支内模块运行；缺少入口时先核对 owner，不把另一分支的代码复制过来。

旧 RF500 工具在本分支仍有继承代码，live/campaign 的 canonical owner 是 `workflow/rf-cem-500mhz`：

| 模块（`python -m` 后） | 作用 / CST 要求 |
| --- | --- |
| `rf_cem` / `rf_cem.build_500mhz_baseline` | no-CST 基线 UDSG 与 Translator 产物 |
| `rf_cem.build_500mhz_parametric_geometry` | no-CST 参数化几何生成 |
| `workflows.rf_cem_500mhz_parametric_opt.runner` | no-CST 扫描 |
| `rf_cem.live_500mhz_diagnostic` | live 导入/设置 |
| `rf_cem.live_500mhz_parametric_diagnostic` | live 单包诊断，可求解 |
| `rf_cem.live_500mhz_postprocessing_diagnostic` | live 模板、求解与结果回读 |
| `workflows.rf_cem_500mhz_parametric_opt.live_campaign` | live 批量/SAO |

这里只提供定位，不代表当前授权执行 live。CST API 和模板/项目内部文件依据见 [接口手册](CST_AUTOMATION_INTERFACES.md)。

补充入口：`scripts/cst_help_automation_scan.py` 查官方 Help；`scripts/package_rf_cem_workstation.ps1` 和 `scripts/rf_cem_workstation_bootstrap.ps1` 用于工作站打包/环境准备。运行前查看本地路径和副作用，普通代码阅读不需要它们。

## 5. 验证入口

按范围选择已有测试；完整策略见根目录 AGENTS。当前研究核心的一次针对性检查：

```powershell
& $py -m pytest -q -m 'not cst_required' tests/test_sa_a0_landmark_coverage.py tests/test_rf_cem_semantic_core.py tests/test_rf_cem_family_induction.py tests/test_rf_cem_boundary_compiler.py tests/test_rf_cem_observation_contract.py tests/test_rf_cem_workbench.py tests/test_rf_cem_workbench_desktop.py tests/test_rf_cem_architecture_boundaries.py
```

2026-09-05 本地实测 74 passed；不要将它标成全分支回归。全分支命令：

```powershell
& $py -m pytest -q -m 'not cst_required'
```

文献/GUI 测试以 `test_rf_cem_literature_*`、`test_rf_cem_arxiv_ingest.py`、`test_rf_cem_pdf_evidence.py` 命名；共享 DB/retry 在 `tests/core/`，history/STEP 在相应 `test_history_*`、`test_feature_*` 等文件。先用 `rg --files tests` 找当前实际文件。

部分真实案例测试需要 ignored 输入，缺失会 skip；结果需带上这一限制。测试通过说明实现满足其测试断言；外部语义正确性、泛化和 RF 性能需要各自的实验依据。
