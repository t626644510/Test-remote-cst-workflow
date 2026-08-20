# 本项目 Git 与 Pull Request 协作指南

本文面向第一次参与本项目、已经了解少量 RF 和计算机基础，但还不熟悉 Git/GitHub 协作的同事。请按顺序操作，不要凭目录名或旧报告猜目标分支。

## 1. 最重要的五条规则

1. 不直接在 `main` 或任何 canonical `workflow/*` 分支上开发。
2. 每个任务从正确的 canonical 分支新建一个任务分支。
3. 一个任务只开一个 Pull Request（PR）；修改同一任务时继续 push，原 PR 会自动更新。
4. PR 的 no-CST CI 通过、自查完成后，才把 Draft PR 改为 Ready 并请求审核。
5. 不提交本地配置、CST 工程/结果、论文 PDF、STEP 输入、数据库、JSONL/NPZ、checkpoint、session、日志或临时脚本。

> **为什么：**Git 分支表示代码基线，电脑上的文件夹名不表示代码所有权。选错 PR 目标分支会把具体工作流带入严格共享核心，后续很难安全拆分。

## 2. 先理解六个名词

| 名词 | 本项目中的含义 |
| --- | --- |
| fork | 你在 GitHub 账号下的仓库副本，用来推送自己的任务分支。 |
| clone | 下载到你电脑上的工作目录。 |
| `origin` | 通常指向你自己的 fork。 |
| `upstream` | 指向项目维护者的主仓库。 |
| branch | 一条独立代码线；canonical 分支是受保护的正式基线。 |
| PR | 请求把你的任务分支合入指定 canonical 分支。 |

`commit` 是一次有说明的本地版本记录；`push` 才会把 commit 上传到 GitHub。PR 不是文件包，也不需要在每次修改后重开。

## 3. 第一次配置

### 3.1 fork 与 clone

先在 GitHub 页面 fork 主仓库，然后在 PowerShell 中执行：

```powershell
git clone https://github.com/<你的GitHub用户名>/Test-remote-cst-workflow.git
Set-Location Test-remote-cst-workflow
git remote add upstream https://github.com/t626644510/Test-remote-cst-workflow.git
git remote -v
```

预期结果：

- `origin` 指向你的 fork；
- `upstream` 指向 `t626644510/Test-remote-cst-workflow`。

如果 `upstream` 已存在，不要重复添加；先运行 `git remote -v` 核对。

### 3.2 建立本机 Python 环境

从仓库根目录执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[dev,cad,review]'
```

每份 clone 使用自己的 `.venv`。不要引用维护者电脑或另一个 worktree 的绝对路径。

验证安装：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m 'not cst_required'
```

这项测试不会主动启动 CST。live-CST 验证是另一类操作，需要单独授权和记录。

## 4. 如何选择目标分支

| 改动内容 | PR 目标分支 |
| --- | --- |
| 通用 CST wrapper、evaluation DB、retry、通用参数/目标/优化器 | `main` |
| 通用 CST history 提取或通用 STEP Feature Assistant | `main` |
| RF gun SAO | `workflow/1-rfgun-sao` |
| HOM 天线与 wake PSO | `workflow/2-rfgun-hom-antenna` |
| recovery 或 tolerance | `workflow/3-rfgun-recovery-tolerance` |
| HOM eigenmode campaign | `workflow/4-rfgun-hom-eigenmode` |
| 500 MHz 常温单腔参数化几何或 live campaign | `workflow/rf-cem-500mhz` |
| 文献获取、语义审核、几何投影、Helper2 审核 GUI、family profile、R1 语义拓扑、R2 边界表示/编译、R3 腔族归纳/盲测、Workbench W0–W3 与 R0B–R5 架构 | `workflow/rf-cem-literature-review` |

`main` 是严格共享核心，不能接收具体 workflow 包、入口、campaign 配置或 workflow-only 测试。无法确定所有权时，先在任务中说明拟修改文件和目标分支，不要先写代码再决定。

## 5. 每个任务的标准流程

以下示例假设任务属于文献审核 GUI；其他任务替换目标分支即可。

### 5.1 获取最新远端状态

```powershell
git fetch upstream --prune
git status --short --branch
```

开始新任务时，优先从最新 upstream canonical 分支新建任务分支，不要复用上一个任务的旧分支：

```powershell
git switch -c contrib/<你的名字>/<简短任务名> upstream/workflow/rf-cem-literature-review
```

例如：

```powershell
git switch -c contrib/student/evidence-page-link upstream/workflow/rf-cem-literature-review
```

### 5.2 小步修改和检查

随时查看当前状态：

```powershell
git status --short
git diff --stat
git diff
```

只暂存本任务文件，避免无意提交整个目录：

```powershell
git add path\to\changed_file.py path\to\test_file.py
git diff --cached
git commit -m "feat: add evidence page navigation"
```

提交信息应说明完成了什么，不使用 `update`、`fix stuff` 等无法追溯的描述。

### 5.3 提交前验证

至少运行：

```powershell
git diff --check
.\.venv\Scripts\python.exe -m pytest -q -m 'not cst_required'
git status --short
```

如果改动涉及 GUI，还要人工确认：

- 页面能启动；
- Evidence、Semantic、Geometry/Helper2 目标功能可操作；
- 刷新后需要持久化的状态仍存在；
- 没有把论文、session 或生成结果提交进 Git；
- PR 中附上必要截图和复现步骤。

如果涉及频率、Q、R/Q、场强、功率、梯度、wake、阻抗或目标函数，代码注释/文档必须写明单位和假设。

### 5.4 push 并创建一个 Draft PR

```powershell
git push -u origin HEAD
```

在 GitHub 创建 PR 时：

- base repository 选择维护者主仓库；
- base branch 选择第 4 节对应的 canonical 分支；
- compare branch 选择你刚 push 的任务分支；
- 工作未完成时选择 Draft PR；
- 按 PR 模板填写范围、测试和风险。

Draft PR 可以尽早触发 CI，但不要立即请求维护者审核。CI 通过、自查完成、范围稳定后，再改为 Ready for review 并请求一次审核。

## 6. 收到审核意见后怎么做

继续在原任务分支修改、commit 和 push：

```powershell
git add <修改过的文件>
git commit -m "fix: address review feedback"
git push
```

原 PR 会自动更新。不要：

- 为同一批审核意见重新开 PR；
- 每条评论单独开 PR；
- 关闭旧 PR 后复制到新分支；
- 在 GitHub 网页和本地同时进行相互覆盖的大段修改。

完成修改并重新测试后，在原 PR 中集中回复“改了什么、测试结果是什么”。只有确实处理完成后再 resolve conversation。

## 7. 如何减少冲突

- 一个 PR 只解决一个明确问题。
- 尽量让 PR 生命周期短，不把互不相关的重构、文档和功能混在一起。
- 新任务永远重新从最新 upstream 目标分支建分支。
- 不把 `main` 合入具体工作流来“碰碰运气”；工作流基线调整由维护者统一安排。
- PR 开发期间如果目标分支发生较大变化，先联系维护者再 rebase。

维护者确认需要 rebase 时：

```powershell
git fetch upstream
git rebase upstream/<目标分支>
git push --force-with-lease
```

只允许对你自己的任务分支使用 `--force-with-lease`。不要使用普通 `git push --force`，不要对 canonical 分支改写历史。

## 8. 提交前文件卫生

以下内容默认不得提交：

- `config.local.yaml`、`.env` 和带本机绝对路径/密钥的配置；
- `.cst`、CST 解包目录、solver 输出和结果缓存；
- `analysis_outputs/`、`runs/`、campaign 目录；
- `.db`、`.sqlite*`、`.jsonl`、`.npz`、`.h5`、checkpoint 和日志；
- 论文 PDF、未经授权的数据、STEP 输入和审阅 session；
- `.venv/`、`__pycache__/`、IDE 设置和临时脚本。

提交前执行：

```powershell
git status --short
git diff --cached --name-status
```

看到不认识的文件就先停止，不要用清理命令删除；它可能是用户或 campaign 的本地证据。

## 9. 常见错误与安全恢复

### 改了文件但还没 commit，发现分支不对

在当前改动仍完整时新建正确任务分支：

```powershell
git switch -c contrib/<你的名字>/<正确任务名>
```

然后再次核对目标 base。不要用 `git reset --hard`。

### 不小心暂存了不该提交的文件

只取消暂存，不删除工作区文件：

```powershell
git restore --staged <文件>
```

### 不清楚发生了什么

只读检查：

```powershell
git status --short --branch
git log -8 --oneline --decorate
git reflog -12 --date=iso
```

把输出发给维护者。不要先 reset、clean、删除锁或移动结果目录。

## 10. Worktree 是可选进阶功能

初学阶段推荐“一份 clone + 一个当前任务分支”。只有确实需要同时维护多个 canonical 分支时再使用 `git worktree`。

查看已有 worktree：

```powershell
git worktree list --porcelain
```

工作目录名称可以自由选择，仓库文档不会把任何人的绝对路径当成标准。

## 11. 请求审核前的最终检查

- [ ] PR 的 base 分支正确。
- [ ] 一个 PR 只有一个主题。
- [ ] 已说明改动动机、范围和明确不包含的内容。
- [ ] 已运行并记录完整 no-CST 命令与结果。
- [ ] live-CST 未运行，或已单独记录授权、版本、输入和结果。
- [ ] 科学量的单位与假设完整。
- [ ] GUI 改动有复现步骤和必要截图。
- [ ] 没有本地配置、数据、论文、CST 输出、数据库或 session。
- [ ] `git diff --check` 通过。
- [ ] CI 通过，所有模板项已填写。
- [ ] Draft 已转为 Ready 后才请求审核。

如果其中任何一项不满足，先继续在同一个 Draft PR 中修正，不需要新开 PR。
