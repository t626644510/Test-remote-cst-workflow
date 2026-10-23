# Workflow 正式分支目录

更新：2026-10-24（Asia/Shanghai）。一个 workflow 只有一个长期正式分支。
分支名称决定代码归属；本地目录只是工作区。以下路径是本机登记，不是运行配置。

| 正式分支 | 内容 | 当前工作区 | no-CST 验证 |
|---|---|---|---|
| `main` | 共享核心、CST history / STEP 通用工具 | `C:/Users/lau/cst_ver3` | 591 passed, 1 skipped |
| `workflow/1-rfgun-sao` | WF1 SAO | `C:/Users/lau/cst_ver3_wf1` | 1098 passed, 1 skipped |
| `workflow/2-rfgun-hom-antenna` | WF2 HOM 天线 | `C:/Users/lau/cst_ver3_wf2_major_refactor` | 735 passed, 1 skipped |
| `workflow/3-rfgun-recovery-tolerance` | WF3 recovery / tolerance | `C:/Users/lau/cst_ver3_wf3` | 703 passed, 1 skipped |
| `workflow/4-rfgun-hom-eigenmode` | WF4 HOM eigenmode | `C:/Users/lau/cst_ver3_HOMwork` | 626 passed, 2 skipped |
| `workflow/5-rfgun-hom-target` | WF5 HOM 目标与异步优化 | `C:/Users/lau/.codex/worktrees/wf5-hom-target/cst_ver3` | 947 passed, 1 skipped |
| `workflow/6-rfgun-wake-thermal` | WF6 wake / thermal 与 station recovery | `C:/Users/lau/.codex/worktrees/wf6-wake-thermal/cst_ver3` | 795 passed, 1 skipped |
| `workflow/6.1-longitudinal-heat` | WF6.1 纵向约束低损耗 | `C:/Users/lau/cst_ver3/artifacts/wf61_20261011/code` | 805 passed, 1 skipped |
| `workflow/7-wakis-hom` | WF7 Wakis HOM | `C:/Users/lau/.codex/worktrees/wf7-wakis/cst_ver3` | 693 passed, 1 skipped |
| `workflow/8-pic-multipacting` | WF8 PIC multipacting | `C:/Users/lau/.codex/worktrees/wf8-pic-multipacting/cst_ver3` | 606 passed, 1 skipped |
| `workflow/8.1-trk-multipacting` | WF8.1 TRK multipacting / 后处理 | `C:/Users/lau/.codex/worktrees/wf81-trk-multipacting/cst_ver3` | 见 WF8.1 VALIDATION.md |
| `workflow/rf-cem-500mhz` | RF-CEM 500 MHz 参数化优化 | `C:/Users/lau/cst_ver3_project` | 617 passed, 1 skipped |
| `workflow/rf-cem-literature-review` | RF-CEM 文献 / 语义 / A0 审核工作台 | `C:/Users/lau/cst_ver3_rf_cem_review_gui` | 811 passed, 11 skipped |

`archive/backup-catalog` 仅保存历史恢复目录，不作为开发分支，也不合并到 main。
`codex/*` 用于短期任务；完成后并入正确的 workflow，再用归档标签保存原提交并退役。

## 本次收口

- WF5/WF7 的未提交实现已收录；WF6 纳入 station-recovery 工作区的恢复阶梯、STOP 传递及证据保护；WF6.1 保持独立。
- WF8 保留 PIC。TRK 扫描、监督、正常 abort、续跑、加权 SEY、轨迹数和逐固体后处理提级为 WF8.1；入口 `run_workflow_8_1.py`，仅存在于该分支。
- RF-CEM 500 MHz 纳入 provenance 修复；literature-review 收口到 A0 路线和当前文档。
- R5 独有的 `cc46d22` / `33dc8d0` **未合入** literature-review，完整保存在 `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r5-rf-result-field`。
- 通用进程退出检查、私有会话清理、reviewer payload 在 main；workflow 不保留第二份共享实现。
- Python / Markdown 使用 LF 行尾，避免 Windows checkout 改变原始源码 SHA。历史证据的哈希检查未放宽。

## 验证与边界

全部使用项目 `.venv\Scripts\python.exe -m pytest -q -m "not cst_required"`。
表中 skipped 项为本地可选依赖或 fixture；不表示通过 live-CST 测试。
WF8.1 使用 MP5、MP5-5、MP6-3 的既有导出数据做离线回归；原始输入指纹不变。
本次不启动 CST 求解，不改写 campaign、工程和仿真结果。临时代码归档后才忽略根目录 artifacts。

## 恢复

整理前所有 refs 已保存到 `all-refs-before.bundle`，并通过 `git bundle verify`。
本机完整备份：`C:/Users/lau/cst_ver3/.codex_tmp/git_reorg_20261024/`。
其中 `backup_manifest.json`、各 worktree 的 patch/源码 ZIP 和 `artifact-scripts.zip`
保留未提交来源；ZIP CRC 已核对。另有 `archive/snapshot/source-20261024-*`
保存收录前源码提交，`archive/snapshot/retired-20261024-*` 保存退役分支最终 HEAD。
从标签新建恢复分支，不能将旧快照覆盖当前结果目录。

旧 detached station-recovery 工作区保留作来源快照；今后 WF6 开发使用上表正式工作区。
