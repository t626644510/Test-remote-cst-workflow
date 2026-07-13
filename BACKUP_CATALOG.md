# Git 归档快照目录

状态：`COMPLETE`（归档标签和目录分支已在远端验证；旧引用已安全退役）

更新日期：2026-07-13（Asia/Shanghai）

## 1. 目的与边界

本分支是历史恢复入口，不是开发基线。它只维护快照目录和恢复方法，不承载任何具体工作流，也不应合并到 `main` 或任一 `workflow/*` 分支。

- 开发基线以 `main` 和规范 `workflow/*` 分支为准。
- `archive/snapshot/*` 是不可变 annotated tags；需要恢复时从标签创建新分支，不要移动或复用旧标签。
- 历史 backup 分支来自不同工作流和时间线，不通过 merge commit 强行拼接。
- 当前代码、测试和 Git diff 始终高于历史快照中的说明文档。

## 2. 删除前离线备份

本次整理前已创建全 refs Git bundle：

| 字段 | 值 |
|---|---|
| 文件名 | `pre-git-archive-consolidation-20260713-235206.bundle` |
| 当前工作站位置 | `C:\Users\lau\cst_ver3_backups\pre-git-archive-consolidation-20260713-235206.bundle` |
| SHA-256 | `A4AC7A34D15C651BE2A5509B97CE6D806F1D36379FE191C199362FA28C1867C1` |
| 大小 | `28,517,092` bytes |
| `git bundle verify` | 通过；记录完整历史与 48 个 refs |

绝对路径只记录本次备份在当前工作站的位置，不是仓库规范路径。换机后请用文件名和 SHA-256 定位、校验备份。

退役 semantics 工作树前，还发现了未进入 Git 的 ignored artifacts，并进行了独立备份：

| 字段 | 值 |
|---|---|
| 目录名 | `rf-cem-semantics-local-artifacts-20260713-235827` |
| 当前工作站位置 | `C:\Users\lau\cst_ver3_backups\rf-cem-semantics-local-artifacts-20260713-235827` |
| 文件数 | `198` |
| 总大小 | `17,494,431` bytes |
| 校验 | 所有源文件与备份文件逐项进行 SHA-256 比对，全部一致 |

其中包括 `analysis_outputs/`、`tmp/`、pytest cache 和 Python bytecode。前两类可能有人工复核价值；cache/bytecode 仅为完整保留，不应回写仓库。

## 3. 归档标签

以下 14 个标签保留了 13 个原 backup 快照，以及被退役的 literature-semantics staging 分支。

| 归档标签（省略 `archive/snapshot/`） | Commit | 原来源 | 保留原因 |
|---|---|---|---|
| `cst-step-assistants-before-main-rebase-20260705` | `bb9e4f90b7a0e157119383c5a1c249eef075251f` | local backup branch | CST/STEP assistant 主线重排前快照；当前 main 中有 patch-equivalent 内容 |
| `post-backup-cst-step-assistant-changes-20260710` | `f46e8b2bfd38bf41f6727b8e210f3ccb3bae1385` | remote backup branch | CST/STEP assistant 后续备份；当前 main 中有 patch-equivalent 内容 |
| `pre-strict-reorg-20260710-cst-step` | `fa8ae5182b7514477b415f088316b45b51ed4d71` | local + remote backup branch | strict reorg 前 CST/STEP 快照 |
| `pre-strict-reorg-20260710-main` | `ce70b8fe94f81876fb580322155e84c8437083ff` | local + remote backup branch | strict reorg 前 main 快照；是当前规范分支历史祖先 |
| `pre-strict-reorg-20260710-stale-workflows` | `263822e454a2393f41960bdf6100719b552871c6` | remote backup branch | 清理旧 workflow refs 前的历史证据 |
| `raw-main-before-cleanup-20260618` | `ff08279569349467dca742473c48b6fc0b652c44` | local backup branch | 旧混合 main；含清理前独有历史，只用于恢复和考古 |
| `pre-clean-wf2-closure-20260710` | `5aea50b6ce57c6920bd2eea16a85746ec58a1e2a` | local + remote backup branch | WF2 收口与重建前历史 |
| `pre-strict-reorg-20260710-wf2-closure` | `3e56e1a7cf655ae82c7400294b5360538bc84106` | local + remote backup branch | strict reorg 前 WF2 closure 历史 |
| `pre-strict-reorg-20260710-wf2-worktree` | `a303bebfca79160e2b20128ced2b7d3be17eb210` | remote backup branch | WF2 worktree 旧状态；保留独有测试提交证据 |
| `pre-strict-reorg-20260710-homwork` | `2394006b17e50164f494b93c0e02f3af347f5254` | local + remote backup branch | WF4/HOM worktree 重排前历史 |
| `rf-cem-literature-review-pre-handoff-20260713-144716` | `0a675df8714564e03ce305959095183524238850` | backup tag | literature review 交接前快照 |
| `rf-cem-literature-review-pre-canonical-rebase-20260713-145915` | `16f4a2b6ed7d8ae49ba4cf49f6c339d263b4ee53` | backup tag | literature review 规范 rebase 前快照 |
| `rf-cem-literature-review-pre-pandas-sync-20260713-162709` | `f97557bc6ee540d06de9a7115af0598707a577a9` | backup tag | pandas/CI 同步前快照 |
| `rf-cem-literature-semantics-hardening-retired-20260713` | `38039219bdce73ef9aaf490d911ba0a1dffe758a` | retired staging branch | semantics hardening 已 patch-equivalent 地进入 literature-review；保留退役点 |

## 4. 恢复方法

只读查看某个快照：

```powershell
git show --stat archive/snapshot/<snapshot-name>
```

从快照建立隔离恢复分支：

```powershell
git switch --create recovery/<purpose> archive/snapshot/<snapshot-name>^{}
```

校验离线 bundle：

```powershell
git bundle verify <BACKUP_ROOT>\pre-git-archive-consolidation-20260713-235206.bundle
Get-FileHash -Algorithm SHA256 <BACKUP_ROOT>\pre-git-archive-consolidation-20260713-235206.bundle
```

在独立目录完整恢复删除前仓库：

```powershell
git clone <BACKUP_ROOT>\pre-git-archive-consolidation-20260713-235206.bundle <RECOVERY_DIR>
```

恢复动作必须先创建新 `recovery/*` 分支并审计差异；不得直接强推 `main` 或规范工作流分支。

## 5. 本次收口记录

执行顺序固定如下：

1. 创建并验证全 refs bundle；
2. 创建并校验 14 个 annotated tags；
3. 推送本目录分支与标签并从远端逐项核验；
4. 删除旧 `backup/*` 分支、旧 `backup/*` 标签与已被覆盖的 semantics staging 分支；
5. 运行全工作树状态、远端 refs、`git fsck` 和 bundle 完整性复核。

本次执行结果：

- `archive/backup-catalog` 在删除前已推送并核验；初始目录提交为 `f057af6fd9f79fc043378986eaf64f3781aa0e53`；
- 14 个 `archive/snapshot/*` 标签的远端 peeled commit 已逐项匹配；
- 删除 8 个远端和 7 个本地 `backup/*` 分支，以及本地、远端各 3 个旧 `backup/*` 标签；数量不同是因为部分旧快照原本只存在于一端；
- 删除 `cst_ver3_rf_cem_semantics` 工作树和 `codex/rf-cem-literature-semantics-hardening` 本地、远端分支；退役 commit 仍由归档标签保护；
- 最终旧 backup refs 数量为 0，8 个保留工作树全部干净并跟踪远端；
- 离线 bundle SHA-256 复核一致，`git bundle verify` 与 `git fsck --full --no-dangling` 均通过。
