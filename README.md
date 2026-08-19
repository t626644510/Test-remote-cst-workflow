# CST 自动化与 RF-CEM 项目：中文背景、现状与交接说明

更新日期：2026-08-19
适合读者：懂一些 RF/加速器腔和 Python，但尚未熟悉本项目架构、CST 自动化细节或代理模型优化的研究生同事。

## 先说结论

这是一个围绕 CST Studio Suite 的微波加速器腔自动化项目。它已经不只是“批量改参数并运行 CST”，而是逐步形成了四类可复用能力：

1. 安全地打开、修改、求解和读取 CST 工程；
2. 从 STEP 与 CST history 中提取几何和仿真语义；
3. 用代理模型、恢复机制和评估数据库组织不同工作流；
4. 在 RF-CEM 路线上，把论文证据、人工语义审核、参数化几何、STEP、CSTTranslator 和本征模结果连成可审计链路。

当前最成熟的新路线是 500 MHz 常温单腔 RF-CEM：工作站已完成 60 次连续 campaign，60/60 得到有效结果。规范分支 `workflow/rf-cem-literature-review` 还完成了常温/超导论文隔离审阅、语义候选审核、SLS-2 六参数几何即时生成、Helper2 面级 Feature/UDSG 审核，以及 Stage C 两个真实实例的 `family_profile.v0`。当前按 R0B–R5 路线推进；R0B Workbench W0 只提供 no-CST 派生视图，不替代任何源数据或物理验收。

> **RF 备注：**“几何生成成功”只说明模型能被构造，不等于频率、R/Q、Q 或峰值场已经复现。最终物理结论仍要由明确的求解器设置、材料、边界、网格和结果定义支持。
>
> **软件工程备注：**项目采用严格分支隔离。`main` 只放共享核心；每个具体工作流只能在自己的 `workflow/*` 分支中存在。不要为了方便把工作流代码复制回 `main`。

## 1. 项目在解决什么问题

传统 CST 工作常见三个困难：

- 工程设置隐含在 GUI、history 和本机目录中，换人后很难复现；
- 优化 campaign 时间长，崩溃、重复计算、输出覆盖和错误重试都很昂贵；
- STEP 的“面 17”或论文中的“equator”并不是稳定、统一的工程语义。

本项目把问题拆成若干层：

```text
论文 / 人工知识 / 既有 STEP / 既有 CST 工程
                    |
                    v
       证据、Feature、Expert Prior、Recipe
                    |
                    v
       参数化几何 / CSTTranslator / Workflow
                    |
                    v
            CST 求解与结果标准化
                    |
                    v
       优化、恢复、审计和人工决策
```

> **RF 备注：**Feature 是“这部分几何在 RF 上是什么”，例如 beam pipe、iris、equator；Recipe 是“本次仿真怎样使用它”，例如材料、边界、本征模求解器和后处理。
>
> **软件工程备注：**这些层之间使用 JSON/YAML 和稳定类接口连接。这样可以替换一层而不静默改变其他层，也能给每个结论保留来源和版本。

## 2. 需要先认识的几个名词

| 名词 | 在本项目中的含义 |
| --- | --- |
| CST history | CST 记录的重要建模/设置操作，常表现为 VBA 命令块。 |
| CSTTranslator | 把已审核几何语义和 recipe 编译为确定性的 CST VBA action、脚本和映射表。 |
| FeatureGraph | 描述 solid/face 的工程语义及几何引用。 |
| Expert Prior | 人工确认的领域规则，例如某组面如何定义 equator radius、某设计族允许哪些曲线。 |
| UDSG | Unified Design State Graph；把证据、几何、Feature、仿真设置和映射关系组织成可追溯图。 |
| Helper2 | 当前仓库中的 STEP Feature Assistant；负责面级几何事实、Feature 候选和部分 UDSG 审核。 |
| SAO | Surrogate-Assisted Optimization；用代理模型减少昂贵 CST 求解次数。 |
| no-CST test | 不启动 CST、不占许可证的自动测试。 |
| live-CST | 真正连接 CST、建模或求解；成本和风险都更高。 |

> **RF 备注：**R/Q 的单位是 ohm，Q 无量纲，项目中的派生分路阻抗采用 `R = (R/Q) * Q`，单位仍为 ohm。频率字段必须明确 Hz、MHz 或 GHz。
>
> **软件工程备注：**“schema 能通过”只代表结构有效；“no-CST 测试通过”只代表离线逻辑有效；“live-CST 成功”才说明指定 CST 环境下的真实链路工作。三种证据不能互相替代。

## 3. 仓库、分支与工作目录

这些分支属于同一个 Git 仓库。每个人的 clone/worktree 目录都可以不同，目录名不是项目契约；需要确认本机目录时运行 `git worktree list`。

| Canonical 分支 | 主要责任 |
| --- | --- |
| `main` | 严格共享核心、CST history 工具、STEP Feature Assistant |
| `workflow/1-rfgun-sao` | RF gun 单/双 pass SAO |
| `workflow/2-rfgun-hom-antenna` | 双工程 HOM 天线与 wake 拟合 |
| `workflow/3-rfgun-recovery-tolerance` | recovery 与 tolerance |
| `workflow/4-rfgun-hom-eigenmode` | HOM eigenmode campaign |
| `workflow/rf-cem-500mhz` | 500 MHz 常温单腔参数化几何与 live campaign |
| `workflow/rf-cem-literature-review` | 文献获取、语义审核、几何投影和 Helper2 GUI；新同事在此分支工作 |

`workflow/rf-cem-literature-review` 从 `workflow/rf-cem-500mhz` 的已验证能力发展而来，但现在是文献语义与审阅 GUI 的唯一 canonical owner。它不会整体并回 `workflow/rf-cem-500mhz`；只有契约稳定、确有复用价值的通用组件，才按所有权规则单独提级。

> **RF 备注：**常温腔与超导腔可以共享证据 schema、审核控件和几何术语，但不能直接共享材料损耗、Q0、低温、峰值场和 cell coupling 等物理先验。
>
> **软件工程备注：**同一功能只应有一个 canonical owner。实验分支验证完成后应合并或重建到 canonical 分支，不要让两个 worktree 长期各自演化同一模块。

## 4. 当前各路线做到哪一步

### 4.1 `main`：共享核心

`main` 已包含：

- CST connection、project、solver、results、retry、timeout 和 cleanup 封装；
- SQLite evaluation DB、去重、warm start、成功复用、失败分类与 retry；
- 通用参数、目标函数、SAO/SAEA、物理公式和 checkpoint；
- `cst_history_extractor`；
- `step_feature_assistant`。

`main` 不应包含任何具体 workflow 包、入口、campaign 配置或 workflow-only 测试。

> **RF 备注：**共享公式和结果容器必须写明单位与假设，尤其是频率、Q、场强、功率、wake 和阻抗。
>
> **软件工程备注：**只有至少两个真实工作流复用、契约稳定且失败语义清楚的实现，才适合提级到 `main`。

### 4.2 WF1：RF gun SAO

已有默认 single-pass、可选 two-pass calibration/measurement、metric role、gate、staged search、adaptive bounds、checkpoint、evaluation DB、warm start 和 retry。live-CST 路径必须由本地配置显式启用。

### 4.3 WF2：双工程 HOM 天线优化

已收口到独立分支，顺序管理 frequency-domain 与 wakefield 工程，支持工程副本、heartbeat、crash recovery、warmup bundle、天线/阻抗目标和 unknown longitudinal HOM 的有界频率拟合。

其科学限制是：单次 PSO 的 HOM 参数反演通常不是唯一解，必须结合多 seed residual、相关性和稳定性判断。

### 4.4 WF3：恢复与容差

包含单工程 recovery 优化，以及 tolerance sampling、单数据库分析和跨 tolerance level 汇总。数据库和报告是本地产物，不能提交或把不完整失败记录当成有效样本。

### 4.5 WF4：HOM eigenmode campaign

已有 plan、resume preview、offline audit 和结果审计。历史 campaign 存在 mode enumeration 截断与大量 ambiguous mapping；只有用户明确要求时才可恢复或启动 CST。

### 4.6 RF-CEM 500 MHz 常温单腔

当前已验证链路：

```text
reviewed labels / expert prior
  -> 12D curve controls
  -> parametric_geometry.v0.json
  -> generated_vacuum.step
  -> CSTTranslator
  -> Copper (annealed) background + Vacuum body
  -> Tetrahedral eigenmode
  -> Frequency / R over Q / Q
```

工作站第一轮 seeded SAO campaign 为 60/60 `SUCCESS`。当前重点候选：

- candidate 039：历史记录中 R/Q 最高，约 427.13 ohm；
- candidate 046：历史记录中 `R=(R/Q)*Q` 最高，约 19.49 Mohm。

它们仍需完整检查 STEP、几何验证、审计 HTML、CST 工程和 mode 形态，不能只凭三个标量接受。

当前主要缺口：

- objective 仍过度奖励贴近 500 MHz；更符合当前意图的是把 490–510 MHz 作为低/零频率惩罚窗口，主要提高 R/Q 与 R，Q 只设 soft floor；
- live runner 尚不能从任意 `live_records.jsonl` record 作为 seed；
- 12D 物理边界、曲率和形状 hard gate 尚未正式收口；
- multi-cell、非轴对称、coupler、HOM、thermal、structural、cooling、multipacting 不属于当前完成范围。

> **RF 备注：**已验证的单点示例为 505.584 MHz、R/Q 约 428.09 ohm、Q 约 45867。它证明自动链路可工作，不代表它就是最终最佳腔。
>
> **软件工程备注：**几何真值源是 `parametric_geometry.v0.json` 和生成链路，不是 CST `StoreParameter`。每个候选必须有独立目录、项目名和记录，避免错号与覆盖。

### 4.7 文献语义与审阅 GUI

当前规范工作流分支已实现：

- arXiv 检索候选与显式版本 PDF 固定；
- PDF SHA-256、证据选页与图片渲染；
- `literature_semantics.v0` 校验；
- integrity-bound `expert_prior.draft.v0`；
- 单篇或 corpus 静态审计 HTML；
- 常温与超导论文的页面、状态和 prior 隔离；
- Evidence、Semantic candidates、Geometry projection 三层审核；
- Evidence 回到论文原页与本地 PDF 同页；
- OK、Soft OK、Reject、Needs evidence、结构化 Add 和中文备注；
- SLS-2 `L/l/r/R/a/b` 六参数几何即时生成；
- baseline / previous / current 模型对比；
- Helper2 Geometry / Features / UDSG 面级高亮、编辑和持久化；
- 仅绑定 `127.0.0.1`、随机 token、Host/Origin 检查与原子 session。

重要限制：

- GUI 不启动 CST，不修改生产 prior，不自动发起 campaign；
- SLS-2 几何生成器只接受 `normal_conducting / elliptical / single-cell`；
- OK/Reject 语义会刷新审核状态，但不会把自然语言静默转换成数值几何；
- 有效 STEP/BRep 不能证明 RF 指标；
- 当前 pilot 数据在被 Git 忽略的 `analysis_outputs/` 中。

> **RF 备注：**先把常温腔语义学扎实，再用未参与模板开发的超导论文做迁移测试，是合理路线；但“迁移准确”必须用独立论文和明确评分标准量化。
>
> **软件工程备注：**组合 corpus 页面适合完整性统计，不适合作为人工接受入口。人工审核应保持“一篇论文、一个 operating regime、一个 session”。

### 4.8 Stage C 与 R0B Workbench W0

Stage C 已通过 PR #4 合入 `workflow/rf-cem-literature-review`，形成 `nc_axisymmetric_single_cell_rf_vacuum` 的 source-lossless 两实例 profile：`sls2.r149.6593e02e` 与 `rf500.2c27faee.b1r3`。该契约保存两者原生 schema、参数名、分组、单位、维数和来源哈希，但明确不声称它们共享 RF 指标定义；`live_cst` 与 `physical_acceptance` 也仍是独立、未建立的状态。

R0B 新增了 `semantic`、`representation`、`compiler`、`observation` 四个依赖边界，以及一个可删除、可重建的本地 Workbench W0。W0 从显式输入重建 SQLite 索引，显示 Families、Instances、Semantics、Representations、Algorithms、Reviews、Validation、Roadmap/Gates、Capability Coverage 与有限的 legacy compile placeholders。它只绑定 `127.0.0.1`，需要随机 token，并且没有 shell、任意文件浏览、CST 控制或写入 API。使用方法见 `docs/FUNCTIONS_AND_ENTRYPOINTS.md`，架构和各阶段出门条件见 `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`。

## 5. 新同事如何开始

### 5.1 只读熟悉

先阅读：

1. 本文；
2. `CONTRIBUTING.md`，按其中流程配置 fork、upstream、任务分支和 PR；
3. `docs/PROJECT_STATUS_CONTEXT.md`；
4. `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md`；
5. `docs/FUNCTIONS_AND_ENTRYPOINTS.md`；
6. 需要恢复工作时再读 `docs/AGENT_CONTEXT_RECOVERY.md`；
7. 涉及 CST 时必须读 `docs/CST_AUTOMATION_INTERFACES.md`。

然后检查本机状态：

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $RepoRoot
git status --short --branch
git worktree list
```

### 5.2 Python 与 no-CST 验证

每个 clone/worktree 使用自己的 `.venv`。首次安装步骤见 `CONTRIBUTING.md`。

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'

& $Python `
  -m pytest -q -m 'not cst_required'
```

这条命令不会主动启动 CST。

### 5.3 启动 SLS-2 文献审阅 GUI

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
$BundleRoot = '<LOCAL_LITERATURE_BUNDLE_ROOT>'
$SessionRoot = Join-Path $BundleRoot 'review_sessions\sls2_gui'

& $Python `
  -m rf_cem.literature_semantics review-gui `
  --bundle-root $BundleRoot `
  --manifest corpus_manifest.json `
  --paper-id sls2 `
  --session-root $SessionRoot
```

程序会输出带随机 token 的 `http://127.0.0.1:<port>/...` 地址。必须打开完整 URL，不能直接双击 HTML。

`<LOCAL_LITERATURE_BUNDLE_ROOT>` 是未提交到 Git 的本地论文包目录。新同事需要单独接收经授权的论文/审计数据，或者按功能入口文档重新生成；不能假设 clone 后自动存在 `analysis_outputs/`。

> **RF 备注：**建议先逐条检查论文证据与定义，再审核语义，最后才看几何投影。单篇数值通常先标 Soft OK。
>
> **软件工程备注：**不要复用已经绑定不同 source hash 的 session。输入变更后新建 `--session-root`，保留旧会话作为审计记录。

## 6. 数据、输出与安全边界

以下内容通常是本地输入或运行产物，不应提交：

- `Appendix/`、`StepData/` 和论文 PDF；
- `analysis_outputs/`、`runs/`、CST `.cst` 与解包目录；
- SQLite/JSONL/NPZ、checkpoint、日志和 session；
- `config.local.yaml` 与本机绝对路径配置；
- 临时脚本和一次性人工导出。

任何 live-CST 操作前：

1. 使用工程副本；
2. 确认 CST Python library、项目路径、输出目录和许可证；
3. 明确本次是否允许求解、恢复、kill、删锁或清理结果；
4. 记录 no-CST 与 live-CST 分别运行了什么；
5. 不根据方法名猜测 CST API。

> **RF 备注：**材料、边界、solver、mesh 和 result definition 共同决定物理含义。只换 STEP 而不核对这些项，可能得到数值正常但物理错误的结果。
>
> **软件工程备注：**“用户允许运行 CST”不自动等于“允许 kill 所有 CST 进程、删除锁或覆盖 campaign”。这些是独立的高风险动作。

## 7. 建议的近期工作顺序

1. 完成 R0B hard gate：架构边界、Workbench W0、完整 no-CST 回归、文档与单一 canonical owner；
2. R1 建立与表示方法无关的 RF 真空边界语义核心；
3. R2 建立与腔族无关的边界表示，并在唯一 compiler 边界实现 Compiler v0；
4. R3 做有证据门禁的腔族归纳与扩展；
5. R4 建立带单位、验证层和工程约束的公共 observation contract；
6. R5 先离线建立 RF result/mode/field contract；只有用户明确授权后才做 live-CST 验证；
7. 原有 candidate、objective、seed 与 campaign 工作继续由 `workflow/rf-cem-500mhz` 所有，不与此路线静默混合；
8. 只有出现第二个真实消费者和稳定契约后，才讨论把通用组件提级到 `main`。

## 8. 以后只维护哪些说明文档

| 文件 | 读者与用途 |
| --- | --- |
| `README.md` | 人类中文背景、现状、入门与交接；就是本文。 |
| `CONTRIBUTING.md` | 中文 Git/PR 协作流程、分支路由和提交前自查。 |
| `docs/PROJECT_STATUS_CONTEXT.md` | Agent 使用的完整、机械化项目状态真值。 |
| `docs/AGENT_CONTEXT_RECOVERY.md` | Agent 中断、死机、换任务后的恢复与维护步骤。 |
| `docs/FUNCTIONS_AND_ENTRYPOINTS.md` | 全部主要功能、CLI、输入输出和分支入口。 |
| `docs/CST_AUTOMATION_INTERFACES.md` | CST 官方接口、仓库封装与直接项目文件证据。 |
| `docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md` | RF-CEM 架构决策、Workbench W0 以及 R0B–R5 阶段门禁。 |
| `.agent/goals/RF-CEM_Codex_Goal_R0B-R5.md` | 当前 R0B–R5 的执行范围、阶段顺序与收口约束。 |

根 `AGENTS.md` 是 Codex 自动读取的短治理入口，只保留不可违反的规则和上述文档索引；`.github/` 中的 PR 模板与 CI 是协作基础设施，不是项目状态报告。

收口前的 25 份 Markdown 原件已整体归档为：

```text
documentation_archive\markdown_before_consolidation_20260712_HEAD-0663994.zip
SHA-256: 342f999e67bc10ccf6a8d7d6685ca57a93bc27fb666c9c5c61516b0c5e986ab6
```

历史内容只用于追溯，不再单独维护；出现冲突时，以当前代码、测试、Git 状态和以上八份文档为准。
