# 2026-10-24 Git 分类与 WF8.1 提级

状态：本地整合与归档完成；下一步推送、逐 SHA 核验后退役临时分支。
本分支仅维护恢复目录，不合并到 main 或 workflow。此前 2026-07-13 的完整记录保留在下方。

## 正式归属

main 严格共享核心；每个 workflow 只有一个正式分支。所有 workflow 共同基于 main，
共享核心目录逐项比对一致；最后一次 docs/忽略规则同步未改变已测试代码 blob。
WF6 收录 station-recovery 并保持 WF6.1 独立；WF8 保留 PIC，WF8.1 独立承载 TRK。
RF-CEM 500 MHz 收录 provenance 修复；literature-review 收录 A0 与现有文档。
R5 独有的 cc46d22 / 33dc8d0 **仅归档，未合入**。旧工作区与仿真结果均保留。

| 正式分支 | 提交 | 完整 no-CST |
|---|---|---|
| `main` | `590705d6fac2dd4c3d5732bf1aa15e3bdffb2ba3` | 591 passed, 1 skipped |
| `workflow/1-rfgun-sao` | `da2fb9f2e412096faa737782c16331c040cbb3cc` | 1098 passed, 1 skipped |
| `workflow/2-rfgun-hom-antenna` | `b04f4f66a26ee5466886e07c4c415f1e3470e259` | 735 passed, 1 skipped |
| `workflow/3-rfgun-recovery-tolerance` | `696884485d6afbec5d3f1478ef206ae4b1d41648` | 703 passed, 1 skipped |
| `workflow/4-rfgun-hom-eigenmode` | `0ef029011331b4e5908ee1a8bf0ff2b96561c61d` | 626 passed, 2 skipped |
| `workflow/5-rfgun-hom-target` | `a6aa03184efcd1b03851018fc2f154eb530da417` | 947 passed, 1 skipped |
| `workflow/6-rfgun-wake-thermal` | `707ad2cd125a0f79bb22a4bbc80bf267e03f2913` | 795 passed, 1 skipped |
| `workflow/6.1-longitudinal-heat` | `ad15616bb3dd2c16af1ae051a3911f7cfe80fca0` | 805 passed, 1 skipped |
| `workflow/7-wakis-hom` | `186de311267ab228ead489cd206de855a34e7a9f` | 693 passed, 1 skipped |
| `workflow/8-pic-multipacting` | `8c9a6a8bbf0521f287c2157e839ff7edddaf24fc` | 606 passed, 1 skipped |
| `workflow/8.1-trk-multipacting` | `ef56a47745db735b4903621e274a6c8cd208d8d1` | 686 passed, 1 skipped |
| `workflow/rf-cem-500mhz` | `d7351cbf08c7aad177c56282ff7b713647b2edb1` | 617 passed, 1 skipped |
| `workflow/rf-cem-literature-review` | `3d741857885540dd98ea8d785aeb9b25216dff45` | 811 passed, 11 skipped |

WF8.1 使用 MP5、MP5-5、MP6-3 已导出数据回归；输入指纹不变。
MP5-5 另用 VTK 从端点/STL 重建 688349 个事件，0 未解析，原生统计核对通过。
未启动 CST 求解，未做 live export 验证。验证说明在 WF8.1 包的 VALIDATION.md。

## 离线恢复

本机备份目录：`C:/Users/lau/cst_ver3/.codex_tmp/git_reorg_20261024/`。
`all-refs-before.bundle` 已通过 git bundle verify；SHA-256：
`6022d1c935132e53ab9775726dc354fce1f095b94c300deafe959befca3ae294`。
`backup_manifest.json`、逐工作区 staged/unstaged patch 与未跟踪源码 ZIP、
`artifact-scripts.zip` 和 SHA 清单保留整理前来源；ZIP CRC 已全部通过。
临时部署、接管和补丁脚本只在备份中保存，不是正式运行入口。
另建 `all-refs-consolidated-before-retirement.bundle` 保存整合后、删除前的完整 refs。
两份 bundle、仿真输入和报告均不提交 Git。

恢复使用 `git switch -c recovery/<name> <archive-tag>^{}` 或在新目录 clone bundle；
不要覆盖既有工作区和结果。WF5/WF8/RF-CEM 状态文档冲突均保留完整历史副本再合并。

## 2026-10-24 归档标签

pre-reorg 为原分支 HEAD；source 为收录未提交源码后的保存点；retired 为退役前最终 HEAD。

| 归档标签 | Commit |
|---|---|
| `archive/snapshot/pre-reorg-20261024-archive--backup-catalog` | `40c56df2a8f6e8496e15968471849f451d4d0131` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-acquisition-a0-landmark-coverage` | `d17d95f08ba2ff705cf9dbe0d6219b1c409c7437` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-family-profile-v0` | `61534a896ef50052e0d645c421e99f7066231fe6` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r0b-workbench` | `f69bd8d58711c79ed73c2a90ed8476e79f616281` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r1-semantic-core` | `65d8d52350b9e536f3b2a0d30a0b18f24d447fdb` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r2-boundary-compiler` | `f6df4c5589cf3c952c177e02dc053c6b7970b4d5` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r3-family-induction` | `ceb1d9a9851cffeb91adc328c3f42c9209d3010b` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r4-observation-contract` | `6cd58604a63e4db81a7485d9a9939261178676f9` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-r5-rf-result-field` | `33dc8d00046e42306640bd8ecd8f69f7697249e9` |
| `archive/snapshot/pre-reorg-20261024-codex--rf-cem-td1-td3-workbench-desktop` | `efda2b51976c506d26aed7ff97c3c7d5e7ee45f5` |
| `archive/snapshot/pre-reorg-20261024-codex--rf500-variant-index-provenance-fix` | `3cb928c750a6b76a6a20a786a2a1a0b209ac6ee9` |
| `archive/snapshot/pre-reorg-20261024-codex--sls2-r149-closeout` | `f9c895d7332275d5f4762d59a165342e5772d970` |
| `archive/snapshot/pre-reorg-20261024-main` | `dedc5fcabfa1bde0be49726d14488baea6f7cea0` |
| `archive/snapshot/pre-reorg-20261024-workflow--1-rfgun-sao` | `63207ba5a992d44823a19b8b848a4f542e1f0b6a` |
| `archive/snapshot/pre-reorg-20261024-workflow--2-rfgun-hom-antenna` | `6a6c99d484362ce02c08589d0b3bd0e2793ce9e0` |
| `archive/snapshot/pre-reorg-20261024-workflow--3-rfgun-recovery-tolerance` | `5ba5e1f4a2c505dcdbf82eb55b45c7ca5c924430` |
| `archive/snapshot/pre-reorg-20261024-workflow--4-rfgun-hom-eigenmode` | `7226c0fa01b3e913ca88a4272b22ad54846fc709` |
| `archive/snapshot/pre-reorg-20261024-workflow--5-rfgun-hom-target` | `6e69c68f3fd402edc13b6cecf61f85e3362321a4` |
| `archive/snapshot/pre-reorg-20261024-workflow--6-rfgun-wake-thermal` | `dc4cc40780cfdf6c4184ae92cfacc2412539105f` |
| `archive/snapshot/pre-reorg-20261024-workflow--6.1-longitudinal-heat` | `dc4cc40780cfdf6c4184ae92cfacc2412539105f` |
| `archive/snapshot/pre-reorg-20261024-workflow--7-wakis-hom` | `5e1bfd2e52a4ed12d10ca3ba179cd3d3eb4343c8` |
| `archive/snapshot/pre-reorg-20261024-workflow--8-pic-multipacting` | `aa4bf9200240d96e8d65f4cd71daa98e4a784356` |
| `archive/snapshot/pre-reorg-20261024-workflow--rf-cem-500mhz` | `af690d5d946406e2876679d62489574d4fa3807d` |
| `archive/snapshot/pre-reorg-20261024-workflow--rf-cem-literature-review` | `c42c3df5cb45a2cdb87beaa88b558d286968a1e2` |
| `archive/snapshot/retired-20261024-codex--rf-cem-acquisition-a0-landmark-coverage` | `923470c965be040cb5287816c724d0b959cfec09` |
| `archive/snapshot/retired-20261024-codex--rf-cem-family-profile-v0` | `61534a896ef50052e0d645c421e99f7066231fe6` |
| `archive/snapshot/retired-20261024-codex--rf-cem-r0b-workbench` | `f69bd8d58711c79ed73c2a90ed8476e79f616281` |
| `archive/snapshot/retired-20261024-codex--rf-cem-r1-semantic-core` | `65d8d52350b9e536f3b2a0d30a0b18f24d447fdb` |
| `archive/snapshot/retired-20261024-codex--rf-cem-r2-boundary-compiler` | `f6df4c5589cf3c952c177e02dc053c6b7970b4d5` |
| `archive/snapshot/retired-20261024-codex--rf-cem-r3-family-induction` | `ceb1d9a9851cffeb91adc328c3f42c9209d3010b` |
| `archive/snapshot/retired-20261024-codex--rf-cem-r4-observation-contract` | `6cd58604a63e4db81a7485d9a9939261178676f9` |
| `archive/snapshot/retired-20261024-codex--rf-cem-r5-rf-result-field` | `33dc8d00046e42306640bd8ecd8f69f7697249e9` |
| `archive/snapshot/retired-20261024-codex--rf-cem-td1-td3-workbench-desktop` | `efda2b51976c506d26aed7ff97c3c7d5e7ee45f5` |
| `archive/snapshot/retired-20261024-codex--rf500-variant-index-provenance-fix` | `3cb928c750a6b76a6a20a786a2a1a0b209ac6ee9` |
| `archive/snapshot/retired-20261024-codex--sls2-r149-closeout` | `f9c895d7332275d5f4762d59a165342e5772d970` |
| `archive/snapshot/retired-20261024-codex--workflow-git-reorg` | `590705d6fac2dd4c3d5732bf1aa15e3bdffb2ba3` |
| `archive/snapshot/source-20261024-codex--rf-cem-acquisition-a0-landmark-coverage` | `a635ef99d38158b7d06b09dcbbe0e8a8dfbead58` |
| `archive/snapshot/source-20261024-wf6-station-recovery` | `27138d6ccd084e20dadfca15144a7df9c732d87d` |
| `archive/snapshot/source-20261024-workflow--5-rfgun-hom-target` | `49c09d2ed364fd6c115dbb37ab5f6ca0687aa1b6` |
| `archive/snapshot/source-20261024-workflow--6-rfgun-wake-thermal` | `27091565c7bed265e09846df9a173e116e2df84f` |
| `archive/snapshot/source-20261024-workflow--6.1-longitudinal-heat` | `774498d24e40f1ff1fc84047be6c38dfa67834c6` |
| `archive/snapshot/source-20261024-workflow--7-wakis-hom` | `b7fa37255c8b4e60bddefea0a532ac123f44d33a` |

---

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
