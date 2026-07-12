# RF-CEM 文献语义与几何审阅 GUI：中文总使用说明

## 1. 这套工具解决什么问题

本工具把以下内容集中到一个本机浏览器界面中，同时严格限制为“一篇论文、一个 RF 运行体制、一个审核会话”：

- 当前所选论文的文字证据、图片证据和论文摘要；
- 从论文抽取的 RF-CEM 语义候选；
- 人工审核状态与中文备注；
- SLS-2 单腔的论文近似几何；
- 基于几何参数即时生成的 STEP、网格和 BRep 检查结果；
- Helper2 自动生成的 Geometry、Features 和 UDSG 候选层。

它的定位是“文献证据 -> 语义候选 -> 几何假设”的人工审计闭环，而不是 CST 求解器或 RF 性能复现工具。常温腔与超导腔共享数据协议和审核组件，但不共享审核页面、会话状态或领域先验。

当前实现位于：

```text
C:\Users\lau\cst_ver3_rf_cem_review_gui
```

Git 工作分支：

```text
branch: codex/rf-cem-literature-review-gui
```

## 2. 重要边界

使用前请先明确以下边界：

1. GUI 不会启动 CST，也不会连接 live CST。
2. GUI 不会修改生产 `expert_prior`、campaign 配置或工作流基线。
3. 有效 STEP、有效 BRep 和外形相似，只能说明几何构造成功，不能证明论文中的谐振频率、分路阻抗、峰值场、HOM 或其他 RF 指标得到复现。
4. Helper2 的 Features 和 UDSG 是自动候选，默认仍需人工审核。
5. 语义的 OK、Reject 或 Add 会触发模型刷新，但 v1 不会擅自把自然语言语义翻译成数值几何变化。需要改变外形时，应明确修改 `L/l/r/R/a/b`。
6. 所有运行产物都放在被 Git 忽略的 `analysis_outputs/` 中，不应提交到仓库。
7. `Sls2LiteratureReviewApp` 只接受 `normal_conducting` 语义包；超导论文必须使用独立的语义审核会话，不能套用 SLS-2 几何生成器。
8. 常温经验可以迁移语义模板、证据协议和审核结构，但不能直接迁移材料损耗、峰值场、低温、Q0、cell coupling 等超导领域先验。

## 3. 目录与依赖

### 3.1 代码目录

```text
C:\Users\lau\cst_ver3_rf_cem_review_gui
```

### 3.2 Python 环境

这个隔离 worktree 不一定有自己的 `.venv`。当前验证使用主项目的虚拟环境：

```text
C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe
```

### 3.3 文献试点数据

```text
C:\Users\lau\cst_ver3_rf_cem_review_gui\analysis_outputs\rf_cem_literature_pilot_20260710
```

其中包括 TESLA、SLS-2 的 PDF、语义包、摘要、图片证据和 corpus manifest。

### 3.4 主要运行依赖

- Python 3.9；
- PyYAML；
- Plotly 5.24.1，用于离线三维模型和 r-z 轮廓显示；
- CadQuery 2.5.2 / OCP，用于无 seed STEP 的几何生成；
- 项目内的 `step_feature_assistant`，用于 Helper2 Geometry、Features 和 UDSG 候选。

本功能没有新增生产依赖。

## 4. 启动 GUI

### 4.1 推荐：前台启动

打开 PowerShell，执行：

```powershell
Set-Location C:\Users\lau\cst_ver3_rf_cem_review_gui
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')

& C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe `
  -m rf_cem.literature_semantics review-gui `
  --bundle-root analysis_outputs\rf_cem_literature_pilot_20260710 `
  --manifest corpus_manifest.json `
  --paper-id sls2 `
  --session-root analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui
```

程序会输出类似地址：

```text
http://127.0.0.1:<随机端口>/?token=<随机令牌>
```

复制并打开完整地址。端口和 token 每次启动都可能变化。

不要直接双击 HTML，也不要使用 `file://` 打开。页面与 API 被设计为必须来自同一个本机回环地址。

### 4.2 分别生成常温腔与超导腔静态审计 HTML

不要再生成混合 TESLA/SLS-2 的人工 OK/Reject 页面。使用同一 corpus manifest 时，通过 `--paper-id` 分别输出：

```powershell
& C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe `
  -m rf_cem.literature_semantics corpus-audit `
  --bundle-root analysis_outputs\rf_cem_literature_pilot_20260710 `
  --manifest analysis_outputs\rf_cem_literature_pilot_20260710\corpus_manifest.json `
  --paper-id sls2 `
  --out analysis_outputs\rf_cem_literature_pilot_20260710\audits\normal_conducting_sls2.html

& C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe `
  -m rf_cem.literature_semantics corpus-audit `
  --bundle-root analysis_outputs\rf_cem_literature_pilot_20260710 `
  --manifest analysis_outputs\rf_cem_literature_pilot_20260710\corpus_manifest.json `
  --paper-id tesla `
  --out analysis_outputs\rf_cem_literature_pilot_20260710\audits\superconducting_tesla.html
```

这两份 HTML 可以共享样式和 schema，但内容、语义状态和领域适用范围完全隔离。组合 corpus 报告只适合完整性统计或研究对比，不作为人工接受/拒绝入口。

### 4.3 继续使用已有最终会话

现有最终会话目录为：

```text
C:\Users\lau\cst_ver3_rf_cem_review_gui\analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui_final
```

如果对应服务仍在运行，可以从 `review_launch.json` 读取最新地址：

```powershell
$launchPath = 'C:\Users\lau\cst_ver3_rf_cem_review_gui\analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui_final\review_launch.json'
$launch = Get-Content -Raw -Encoding UTF8 $launchPath | ConvertFrom-Json
$launch.review_url
```

若地址已经失效，使用 4.1 的命令重新启动。若希望保留旧审核会话，给 `--session-root` 换一个新目录，不要删除旧会话。

### 4.4 停止服务

前台运行时，在对应 PowerShell 窗口按 `Ctrl+C`。

如果服务在后台运行，可先读取并核对进程：

```powershell
$launch = Get-Content -Raw -Encoding UTF8 'C:\Users\lau\cst_ver3_rf_cem_review_gui\analysis_outputs\rf_cem_literature_pilot_20260710\review_sessions\sls2_gui_final\review_launch.json' | ConvertFrom-Json
Get-Process -Id $launch.pid
```

确认它确实是本次 RF-CEM review Python 服务后，再执行：

```powershell
Stop-Process -Id $launch.pid
```

## 5. 页面总体布局

页面左侧有三个可切换工作区：

- `模型对比`：上方三维网格，下方 r-z 轮廓，图例区分 `baseline`、`previous` 和 `current`；
- `论文证据`：显示 evidence 对应的论文原页，可进一步切换到本地校验过的 PDF 同页；
- `Helper2 面审核`：逐面显示 Geometry、Features 或 UDSG 着色，并支持点击选面。

页面右侧是三层审核区：

1. `Layer 1 - Evidence`：论文证据；
2. `Layer 2 - Semantic candidates`：语义候选；
3. `Layer 3 - Geometry projection`：几何投影。

页面顶栏显示：

- 当前单论文审核范围，例如 `sls2 / normal_conducting / elliptical`；
- 当前 review revision；
- 本机 API 连接状态；
- “重新生成模型”按钮。

## 6. 审核状态的含义

每个可审核项都使用统一状态词：

| 状态 | GUI 按钮 | 建议含义 |
| --- | --- | --- |
| `pending` | 初始状态 | 尚未人工判断 |
| `accepted` | OK / 接受 | 证据、语义或几何投影可接受 |
| `accepted_as_soft_only` | Soft OK / 仅软建议 | 只能作为软提示，不能作为硬约束或生产事实 |
| `rejected` | Reject / 拒绝 | 当前项不应继续使用 |
| `needs_more_evidence` | Needs evidence / 补证据 | 暂不接受，需要更多文献或复现证据 |

实际建议：

- 单篇论文给出的数值范围，通常优先使用 `accepted_as_soft_only`；
- 论文图与当前几何 grammar 存在推导或近似时，优先使用 `needs_more_evidence` 或 `accepted_as_soft_only`；
- 只有在定义、单位、适用范围和来源都清楚时，才使用 `accepted`；
- `accepted` 不代表已经通过 CST 或实验验证。

每个卡片都有中文备注框。可记录：

- 为什么接受或拒绝；
- 定义或单位差异；
- 只适用于哪一种腔体；
- 下一步需要补什么证据；
- 与当前 RF-CEM 参数的映射关系。

## 7. Layer 1：Evidence 的使用方法

Evidence 层只汇总当前 `--paper-id` 所选论文的：

- 文本证据；
- 图片证据元数据；
- 嵌入的论文页；
- 页码、Figure/Table 编号和 evidence refs。

当前还额外补入了 SLS-2 Figure 3，即对称 `L/l/R/r/a/b` 几何定义图。该图片是 GUI 审计补充渲染，不会静默改写原始语义 JSON。

建议审核顺序：

1. 点击“定位到论文原页”，先确认论文、版本、页码和章节；
2. 确认图片或文字确实支持卡片中的表述；
3. 必要时点击“PDF 原文同页”，回到本地校验过的 source PDF；
4. 检查物理机制和适用范围；
5. 写中文备注；
6. 选择 OK、Soft OK、Reject 或补证据。

当前证据 schema 能可靠定位到页和章节。只有带 `bbox` 或 `text_anchor` 的新证据才能精确高亮段落或图中局部区域；没有这些定位字段时，GUI 不会假装知道精确文本边界。

Evidence 层的审核只评价“证据是否可靠、是否支持该表述”，不直接表示该证据可以进入生产 prior。

## 8. Layer 2：Semantic candidates 的使用方法

这一层包含：

- `classification`；
- `named_features`；
- `shape_motifs`；
- `curve_priors`；
- `parameter_ranges`；
- `optimization_objectives`；
- `physical_constraints`；
- draft-prior patch 项。

GUI 使用 `literature_semantic_candidate_view.v1` 统一显示每个候选：Subject、Claim/Predicate、Value、Applicability、Confidence、Geometry binding 和 Evidence。缺失值使用 JSON `null`，界面显示 `N/A`；不会用非标准 `NaN` 表示缺失。

同一主语会被分组，例如 `equator` 下分别显示存在性、形状模式、曲线策略和参数值。draft-prior patch 被放在单独的“配置应用建议”组，不再和论文事实混排。

### 8.1 审核语义候选

重点检查：

1. 语义名称是否准确；
2. `source_refs` 是否真正支持该结论；
3. 单位和 RF 定义是否清楚；
4. `operating_regime`、`cavity_family`、`cell_count` 等适用范围是否正确；
5. 是否把单篇论文数值误当成通用硬边界；
6. 是否把 beam-pipe radius、iris radius 等不同参数静默改名；
7. 当前页面的 `operating_regime` 是否和启动时选择的论文一致；若出现另一运行体制的候选，应视为载荷隔离错误并停止审核。

### 8.2 新增结构化语义

展开 `Add structured semantic / 新增结构化语义`，选择 section、填写唯一 ID，并输入 JSON 对象。

示例：

```json
{
  "motif_name": "broad_symmetric_equator",
  "description": "对称单腔的宽赤道轮廓候选",
  "source_refs": ["sls2_p8_spline"],
  "confidence": 0.7,
  "scope": "SLS-2 geometry review",
  "applicability": {
    "operating_regime": "normal_conducting",
    "cavity_family": "elliptical",
    "cell_count": "single"
  }
}
```

新增项始终以 `pending` 开始，不会因为被添加就自动进入生产 prior。

### 8.3 全局中文备注

全局备注适合记录本轮审核结论，例如：

- 本轮只审核几何语义；
- RF 指标尚未复现；
- 当前会话只接受 SLS-2 `normal_conducting` 候选；
- SLS-2 数值只允许进入 `nc_elliptical` 的软候选。

## 9. Layer 3：Geometry projection 的使用方法

Geometry projection 内部有三个子页：

1. `Geometry`：参数、生成结果和 BRep/STEP 检查；
2. `Features`：Helper2 自动识别的 RF 几何特征候选；
3. `UDSG`：特征到几何节点的候选绑定与验证信息。

### 9.1 SLS-2 论文候选 1

当前基准使用下列尺寸，单位全部为 mm：

| 参数 | 数值 | 含义 |
| --- | ---: | --- |
| `L` | 680.0 | 总轴向长度 |
| `l` | 188.671 | 每侧直线 beam-pipe 长度 |
| `r` | 50.0 | beam-pipe 半径 |
| `R` | 249.901 | 论文 cavity 1 的赤道半径 |
| `a` | 125.232 | 赤道侧椭圆轴向半轴 |
| `b` | 70.2322 | 赤道侧椭圆径向半轴 |

定义：

```text
h = L/2 - l
```

当前重建假设使用四段 90 度椭圆弧，第二组椭圆半轴为：

```text
轴向半轴 = h - a
径向半轴 = R - r - b
```

几何保护条件为：

```text
L > 2l
0 < a < h
0 < b < R - r
r > 0
```

第二组椭圆半轴是明确标记的重建假设，不应表述成论文直接给出的 STEP 公式。

### 9.2 STEP 近似方式

生成器将解析椭圆上的采样点交给 CadQuery `Workplane.splineApprox`，最高阶数为 5。

因此：

- 采样点位于解析椭圆上；
- STEP 内部曲线是 spline 近似；
- 它们不是精确 conic entity；
- 几何近似误差与 RF 网格/求解误差是不同问题。

### 9.3 参数迭代

在 Geometry 子页修改 `L/l/r/R/a/b`，点击：

```text
Render parameters / 按参数渲染
```

系统会生成一个新的 content-addressed STEP，并同时显示：

- `baseline`：论文候选；
- `previous`：上一版生成模型；
- `current`：当前人工编辑模型。

例如，可以把：

```text
R = 249.901 mm
```

临时改为：

```text
R = 251.0 mm
```

然后观察三维模型和 r-z 轮廓差异。

人工编辑后的 tuple 会被标记为：

```text
origin = human_preview_edit
source_refs = []
published_value_claim = false
```

论文原值保留在 `paper_baseline`，当前变体通过 lineage hash 绑定其直接父候选。因此人工值不会冒充论文值。

### 9.4 几何审核注意事项

对每个新几何变体都应重新判断。上一版的接受状态不会静默传播到下一版。

建议检查：

- 参数是否满足保护条件；
- 左右是否对称；
- beam-pipe、赤道和过渡段是否连续；
- BRep 是否有效；
- STEP 轴向范围是否与 `L` 一致；
- 最大径向范围是否与 `R` 一致；
- 是否出现异常尖角、自交或局部塌陷；
- 新模型是否仍符合当前语义候选。

## 10. Features 和 UDSG 的审核方法

### 10.1 Features

当前 Helper2 会给出候选，例如：

- RFVacuumVolume；
- BeamPipeLeft / BeamPipeRight；
- ConductingWall；
- Iris；
- EquatorRegion；
- TransitionBlend。

检查每个候选的：

- `geometry_refs`；
- confidence；
- evidence；
- status；
- 是否漏面、重叠或绑定到错误面。

所有自动候选默认 `requires_review`。当前 normal-conducting 500 MHz profile 是启发式分类器，不是论文事实。

Features 子页复用旧 Helper2 的审核结构，可以：

- 按 Feature type 分组查看；
- 在左侧高亮候选所引用的面；
- Confirm、Requires review 或 Reject；
- 编辑 Feature type；
- 从候选中删除错误面；
- 把左侧已选面加入候选；
- 建立人工 Feature group。

每次修改都会写入当前 `projection_id` 对应的 `helper2_reviews` 命名空间，不会转换成 literature review 状态。

### 10.2 UDSG

UDSG 子页展示：

- geometry nodes；
- feature candidates；
- topology graph；
- feature-to-geometry bindings；
- warnings 和 validation status。

Bindings 按 Feature 分组，并支持：

- 高亮绑定面；
- 编辑 `feature_id` 与 `geometry_node_id`；
- Accept、Requires review、Reject；
- Delete 和 Restore；
- 保存 Helper2 总备注。

`partial_ok` 只表示几何层候选绑定没有阻塞性错误，不代表完整 RF-CEM UDSG 已完成，也不代表 CST recipe 已验证。

## 11. 会话保存与恢复

会话目录包含：

| 文件或目录 | 作用 |
| --- | --- |
| `review_session.v1.json` | 当前审核状态，原子替换写入 |
| `review_events.jsonl` | append-only 审核事件日志 |
| `rf_cem_literature_review_<paper-id>.html` | 当前单论文本机 GUI HTML |
| `review_launch.json` | 当前端口、token、PID 和路径 |
| `geometry_previews/<hash>/cavity.step` | 对应候选的 STEP |
| `generation.core.json` | 几何生成与验证报告 |
| `*.review_snapshot.json` | 绑定人工审核状态的候选快照 |
| `helper2_face_mesh.json` | Helper2 面级网格 |

`review_session.v1.json` 内部把两类审核状态分开保存：

- `review_decisions`：Evidence、Semantic、Geometry projection 的文献状态；
- `helper2_reviews.<projection_id>`：逐面 Geometry、Feature、Binding、人工组和 Helper2 备注。

审核事件使用 optimistic revision。如果两个页面同时修改同一会话，其中一个可能收到 revision conflict。此时刷新页面，确认最新状态后再操作。

参数输入框中尚未提交的草稿不会跨刷新保存；已经提交并生成的模型报告会保存在 content-addressed 目录中。

## 12. 安全设计

本机服务具备以下限制：

- 只绑定 `127.0.0.1`；
- 每次启动生成随机 token；
- 检查 Host 和 Origin；
- API 不开放 CORS；
- 限制请求体大小；
- API 使用 token header；
- HTML 只能从同源本机服务访问 API；
- 不提供 shell、CST、生产 prior merge 或 campaign 接口。

不要把带 token 的 URL 发送给无关人员，也不要把 `review_launch.json` 或会话目录提交到 Git。

## 13. Windows 注意事项

### 13.1 `L` 与 `l`

PowerShell 5.1 的 `ConvertFrom-Json` 把 JSON 键名按大小写不敏感处理，无法解析同时包含 `L` 和 `l` 的参数对象。

参数 JSON 本身合法。查看这类报告时，应使用 GUI 或 Python：

```powershell
@'
import json
from pathlib import Path

path = Path(r'C:\path\to\generation.core.json')
data = json.loads(path.read_text(encoding='utf-8'))
print(data['parameter_tuple']['values'])
'@ | C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe -
```

### 13.2 中文与编码

- Markdown、JSON 和 YAML 均按 UTF-8 读取；
- 不要使用 PowerShell 默认编码重写中文语义文件；
- 不要用终端一行替换命令批量修改中文 JSON/YAML；
- 修改语义包后，应重新验证 hash 和 schema。

### 13.3 本机 Python 偶发异常

该工作站的 Python 3.9 环境曾偶发出现 PyYAML/SciPy `SystemError: unknown opcode` 或一次性 socket 抖动。同一测试在全新 Python 进程中通常可通过。

处理方式：

1. 关闭失败的 Python 进程；
2. 使用全新解释器重跑同一个目标测试；
3. 如果同一失败稳定复现，再按代码问题处理；
4. 不要因为一次解释器异常而删除会话、STEP 或审核记录。

## 14. 常见问题排查

### 14.1 页面显示 403 或未授权

原因通常是 URL 中 token 过期或使用了旧端口。

处理：重新读取最新 `review_launch.json` 中的 `review_url`。

### 14.2 直接打开 HTML 后按钮无效

原因：使用了 `file://`，同源 API 被安全策略阻止。

处理：通过 `http://127.0.0.1:<port>/?token=...` 打开。

### 14.3 模型区提示 Plotly 未安装

先检查当前环境：

```powershell
& C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe -c "import plotly; print(plotly.__version__)"
```

当前已验证版本为 5.24.1。不要在未确认环境前随意安装或升级生产依赖。

### 14.4 STEP 生成失败

依次检查：

1. 六个参数是否都是有限数值，单位是否为 mm；
2. 是否满足 `L > 2l`、`0 < a < h`、`0 < b < R-r`、`r > 0`；
3. CadQuery 是否可导入；
4. `review_server.stderr.log`；
5. 对应 content-hash 目录中的 generation report。

### 14.5 页面刷新后参数草稿消失

尚未点击“按参数渲染”的输入不会保存，这是 v1 的已知限制。已经生成的候选报告和 STEP 仍在 `geometry_previews/` 中。

### 14.6 会话提示绑定到不同 source payload

说明 corpus、语义包、证据图片或几何投影已经改变，而旧会话仍绑定旧 hash。

处理：使用新的 `--session-root`，保留旧会话用于审计，不要覆盖或删除旧记录。

## 15. no-CST 验证

本功能只需要 no-CST 验证。

### 15.1 目标测试

```powershell
Set-Location C:\Users\lau\cst_ver3_rf_cem_review_gui
$env:PYTHONPATH = (Join-Path (Resolve-Path '.') 'src')

& C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe -m pytest -q `
  tests\test_rf_cem_literature_geometry_candidate.py `
  tests\test_rf_cem_literature_interactive_reviewer.py `
  tests\test_rf_cem_literature_review_server.py `
  tests\test_rf_cem_literature_review_bundle.py `
  tests\test_rf_cem_literature_review_app.py
```

### 15.2 分支全量 no-CST

```powershell
& C:\Users\lau\cst_ver3_project\.venv\Scripts\python.exe -m pytest -q -m 'not cst_required'
```

当前分支最近一次完整结果：

```text
696 passed, 11 skipped
```

其中 live-CST 验证未运行，也不属于本 GUI 的验收范围。

## 16. 推荐的实际审核流程

建议按以下顺序工作：

1. 启动新会话并保存本轮 session-root；
2. 确认顶栏只显示一个 paper 和一个 operating regime；
3. 在 Evidence 层逐项打开论文原页，审核文字、图片和 Figure 3 补充证据；
4. 在按 Subject 分组的 Semantic candidates 中审核 claim、适用范围、参数、目标和约束；
5. 将单篇论文数值优先标记为 Soft OK，除非已有独立复现；
6. 在 Geometry 层确认论文 baseline；
7. 修改一个或少量参数，生成 current，并与 baseline/previous 对比；
8. 对每个新几何变体单独写中文备注并审核；
9. 切换到 Helper2 面审核，检查 Features 的 face refs、confidence 和 overlap；
10. 按 Feature 分组检查 UDSG bindings，完成必要编辑后保存；
11. 只有在几何、定义、单位和来源全部明确后，才考虑把稳定契约提级；
12. RF 指标仍需独立的 no-CST 数值检查或后续 live-CST campaign，不能由本 GUI 代替。

## 17. 当前可交付状态

当前实现已经完成：

- 常温腔与超导腔的单论文、单运行体制隔离载荷；
- `corpus-audit --paper-id` 分别生成 SLS-2 与 TESLA 审计 HTML；
- Evidence、Semantics、Geometry 三层审核；
- Evidence 回到论文原页及本地 PDF 同页；
- 统一的 `literature_semantic_candidate_view.v1` 与按 Subject 分组；
- draft patch 与论文事实分组隔离；
- 逐项和全局中文备注；
- OK、Soft OK、Reject、补证据；
- 结构化 Add；
- SLS-2 六参数几何生成；
- baseline、previous、current 对比；
- 无 seed STEP 的 CadQuery 生成；
- BRep、mesh 和边界范围验证；
- 可编辑、可高亮、可持久化的 Helper2 Geometry、Features 和 UDSG；
- token 化本机回环服务；
- 原子 session 与 append-only event log；
- no-CST 全量测试通过。

仍然需要人工或后续阶段完成：

- 对常温腔当前审核项逐项给出正式结论；
- 对人工几何变体进行工程筛选；
- 建立语义到数值参数变更的显式、可审核映射；
- 用未参与模板开发的超导论文建立迁移基准，量化“八九不离十”的实际准确率；
- 使用独立求解流程复现 RF 指标；
- 在明确授权后，才考虑进入 live CST 或生产 prior 合并。
