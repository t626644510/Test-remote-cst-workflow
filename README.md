# RF-CEM：知识与经验学习

当前分支：`workflow/rf-cem-literature-review`。更新：2026-10-24。

本分支负责 RF-CEM 的知识输入、几何语义与人工审核。当前研究重点是**文字经验驱动的腔体区域划分与学习**，计划将其作为 RF-CEM 更上游的输入，逐步整合原有文献审核流程；现有模块仍保留，分支名暂沿用。

## 当前进度

拟实现的学习闭环：

```text
轮廓观测＋文字经验 → LLM 划分 → 人工修正 → 经验更新 → 下一实例
```

- **已完成实验：**六条基础经验、SLS-2 / RF500 两例的 Luna 有无经验对照，以及人工复评。有经验 run2 的 wall/blend 划分得到认可；稳定复现、nose/blend 细分和跨新实例学习仍待验证。
- **尚未实现：**经验库、`partition / learn` 服务和自动反馈更新闭环。当前正式 `semantic_acquisition` 入口仍只有 A0 几何信号覆盖探针。
- **已有基础：**文献证据与审核 GUI、语义拓扑、边界表示与几何编译、腔族归纳、几何观测，以及只读 Workbench / Desktop。它们可供后续整合，不代表学习闭环已经接通。

完整方案、六条经验和实验结论见[项目状态](docs/PROJECT_STATUS_CONTEXT.md)。

## 开始使用

从当前工作区根目录运行，使用已配置的 `.venv`；安装与协作流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -m rf_cem.semantic_acquisition --help
.\.venv\Scripts\python.exe -m rf_cem.workbench --help
.\.venv\Scripts\python.exe -m pytest -q -m 'not cst_required'
```

文献审核 GUI、Workbench / Desktop 的启动方式、所需输入与具体参数，统一查[命令与源码入口](docs/FUNCTIONS_AND_ENTRYPOINTS.md)。本地输入不随 Git 克隆，缺少时先定位原始数据。

## 文档导航

| 文档 | 用途 |
|---|---|
| [项目状态与当前方案](docs/PROJECT_STATUS_CONTEXT.md) | 当前重点、文字经验方案、实验结论和未完成工作 |
| [命令与源码入口](docs/FUNCTIONS_AND_ENTRYPOINTS.md) | 已有 CLI、输入输出和模块位置 |
| [正式分支目录](docs/WORKFLOW_BRANCHES.md) | 各 workflow 的代码归属 |
| [协作流程](CONTRIBUTING.md) / [上下文恢复](docs/AGENT_CONTEXT_RECOVERY.md) | 提交、验证与中断后的接续 |
| [历史架构](docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md) | R0B–R4 等既有设计与兼容约定；当前研究安排以项目状态和用户最新指令为准 |

## 代码与数据边界

- `main` 维护共享核心；`workflow/rf-cem-500mhz` 负责既有 RF 参数化优化与 live campaign。本分支的几何或 no-CST 验证不等于 RF 物理验收。
- 文字经验方案与结论已提交；实验输入、原始输出和临时实验脚本仍在本地 `analysis_outputs/`，组会材料在 `PPT/`，两者均被 Git 忽略，尚未作为可复现实验收录。
- R5 独有实现仅归档、未合入。本轮重点是上游经验学习，不自动推进旧阶段计划或启动 CST。
