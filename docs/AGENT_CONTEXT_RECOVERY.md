# Agent 上下文恢复

更新：2026-09-05。当前状态入口：[PROJECT_STATUS_CONTEXT.md](PROJECT_STATUS_CONTEXT.md)。

目标是恢复到能继续一个具体动作，不是重新审计整个项目。

## 1. 几分钟开始

在用户指定的工作目录执行：

```powershell
git status --short --branch
git log -5 --oneline
git worktree list
```

然后读状态入口，按任务查 [命令与源码索引](FUNCTIONS_AND_ENTRYPOINTS.md)。涉及 CST 才查 [接口手册](CST_AUTOMATION_INTERFACES.md)。`RF_CEM_ROADMAP_AND_ARCHITECTURE.md` 保留的是详细历史合同与运行兼容快照，不必每次通读。

核对三件事：当前用户想完成什么、哪些文件在开始时已有改动、下一步依赖哪些本地输入。不要仅按目录名判断分支，也不要按旧 goal 的“下一步”自动启动工作。

当前已知差异：A0 分支基于 PR #10 合并 `ab4a55c`，本地 `workflow/rf-cem-literature-review` ref 仍较旧。具体 owner 列表见状态入口。接续当前任务不必为整理文档切换分支、同步全部 worktree 或重新开 PR。

## 2. 代码任务中断

```powershell
git diff --stat
git diff --check
git diff -- path/to/relevant_file.py
```

读改动涉及的代码和测试，找最后完成的行为，再继续剩余部分。未知 dirty/untracked 文件先保留。大幅改动前备份相应文件；已有备份可用时不重复做整库 bundle 或逐文件 hash。

本机文档整理前备份：`C:/Users/lau/cst_ver3_backups/rf-cem-docs-before-simplification-20260905-141400.zip`，含当时 docs 内八份 Markdown。恢复时先取到另一个目录核对，不覆盖用户后续修改。

## 3. 本地证据与 Workbench

`config/rf_cem_workbench_profile.v0.json` 是常用源路径的集中索引。PDF、STEP、review session、proof 和 SQLite 通常在 ignored 目录；Git 干净不代表它们不存在或可以清理。

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py -m rf_cem.workbench status --repo-root . --profile config/rf_cem_workbench_profile.v0.json
```

- 缺源：查看返回的具体路径，找原始输入或备份；不要创建空文件来凑齐。
- SQLite 过期：需要使用 Workbench 时，可用既有 rebuild 命令重建派生索引。
- proof 已存在：读已有结果。确需新实验时用新的 output root，保留原结果。
- 文档与 proof 不一致：先判断是否只是历史正文变动，避免为了“全 fresh”重做整条实验链。

**现有耦合：**R4 当前 bundle 绑定 roadmap 原文字节。只改 roadmap 会使当前 R4 loader 拒绝加载，并阻断默认 W4 重建。此次保留该文件；当前研究判断写在状态入口。不要据此把每次文档修改都升级成实验重建任务。

## 4. GUI 中断

文献证据审核 GUI 与 Workbench 是两个服务：前者保存审核 session，后者展示派生索引。不要拿一个服务的端口或状态推断另一个。

从该服务上次启动输出找地址、PID、repo root 和 session 路径；必要时只读核对进程命令行。旧记录只表示曾经运行。需要重启时使用 [入口索引](FUNCTIONS_AND_ENTRYPOINTS.md) 的对应命令和原 session。重开后核对论文、审核 revision 和几何实例，避免进入另一个会话。

Workbench Desktop 使用固定动作，可以管理自己启动的 Web 子进程；不要顺手清理其他 Python、浏览器或 CST 进程。

## 5. 验证

一律从当前 worktree 根目录使用它自己的 `.venv\Scripts\python.exe`。

```powershell
& $py -m pytest -q tests/test_sa_a0_landmark_coverage.py
```

按改动范围选择现有测试；共享核心、运行入口、持久化、恢复、schema、配置所有权或 review session 逻辑改变时，运行全分支 no-CST：

```powershell
& $py -m pytest -q -m 'not cst_required'
```

文档整理做链接、路径和 diff 检查即可；若文档被运行时读取，再做对应功能检查。记录本次结果，不反复重跑已通过检查。单次解释器故障可重试一次确认；持续失败则检查具体原因，不无限重试。

## 6. live-CST 或 campaign 中断

本轮文档任务未授权新的 live 操作。继续 campaign 前先只读检查配置、checkpoint、记录、输出目录和具体进程归属。只有用户明确指定后才启动 CST、恢复求解、终止进程、删锁或清理结果；这些动作的授权互不替代。

保留候选目录、CST 工程、`parametric_geometry.v0.json`、STEP、记录和结果之间的对应关系。发现缺失或编号不符时先定位原因，不通过删除文件掩盖问题。

## 7. 给下一次接续留下什么

在本任务的最终回复或已有状态入口写清：完成的行为、实际验证、尚未解决的问题、下一步需要的输入。只有发生变化时才更新；无需新增日期版 handoff/status Markdown，也无需复述整段提交历史。
