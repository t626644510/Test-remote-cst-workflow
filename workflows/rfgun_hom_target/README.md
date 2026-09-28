# WF5：横向 HOM 快速达标优化

本分支 `workflow/5-rfgun-hom-target` 从共享核心 `main` 建立。共享核心没有修改；
WF1/WF2/WF4 仅作为已验证控制次序的参考，没有跨分支运行时导入。

目标是 1030–1060 MHz 内每个已解析模式最强实极化方向的横向阻抗 ≤100 kΩ/m。
六变量依次为 selfangle2、UpperHeight2、DownHeight2、Lin2、inner_angle3、inner_r2。
默认范围见配置示例，弯曲半径上限为25 mm。频窗外不施加阻抗目标。

## 配置与运行

复制 `config.example.yaml` 为同目录被 Git 忽略的 `config.local.yaml`。
填写工程 `.cst`、输出目录、CST Python 库目录，以及明确的束流积分范围 `z_range_mm`。
工程必须带有同名配套目录和已保存参数、历史信息。路径相对于 YAML 文件解析；
空库路径读取 `CST_PYTHON_LIB`，不猜测开发站路径。支持 CST 参数名称映射。
示例中的积分范围为 null，因此填写前验证会失败，不能静默采用另一个腔体的范围。

```powershell
.venv\Scripts\python.exe run_workflow_5.py --config workflows\rfgun_hom_target\config.local.yaml --validate-config
.venv\Scripts\python.exe run_workflow_5.py --config workflows\rfgun_hom_target\config.local.yaml --baseline-only
.venv\Scripts\python.exe run_workflow_5.py --config workflows\rfgun_hom_target\config.local.yaml --resume
```

新 campaign 可直接使用 `--optimize`，其中首点仍为当前模板的真实参数。
`--resume` 延续同一预算；它也用于基线完成后的优化、已保存求解后的后处理恢复。
`--max-solves N` 只用于新 campaign，默认40，重试和频窗覆盖补算都计数。
模板、代码或配置发生变化时拒绝复用，请新建输出目录。输出目录有操作系统独占锁，
同一 campaign 不能同时运行两份；进程退出后锁自动释放，锁文件本身保留。

Python 崩溃后，其 CST 会话可能继续运行。恢复会先只读检查已有 session：
新记录使用 UUID 关联 cleanup，旧记录始终查询精确 PID。仍存活或无法确认时返回
`orphan_session_pending`，保留 pending 与已消耗预算，不创建新 CST、不自动清理。
确认旧会话退出后可再次恢复；PID 被复用也保守阻止恢复，不操作该进程。
此门禁不替代代码指纹校验：旧 campaign 的代码身份不匹配时仍拒绝自动复用。

离线重算已保存的 `postprocess_NNN` 数据包：

```powershell
.venv\Scripts\python.exe run_workflow_5.py --analyze-only PATH_TO_BUNDLE
```

此入口不加载本机 CST 库、不打开工程，也不改写输入包。缺失窗内模式的场文件会明确失败。

用户选择仅优化两个最大单模时，设置 `physics.mode_policy: largest_two`。
该策略关闭低 Q 和模态线宽重叠两项阻断，按当前点的 `Qloaded × (R/Q)principal`
从大到小选取最多两个窗内模式，不固定模式编号。两者均需低于阈值，优化量仍是
`log1p(max(Zi/threshold))`。其含义是用户认可的单模阻抗评分，不是重建重叠模的总宽带谱。
所有窗内模式仍提取并保存，缺场、储能/频率不匹配、非有限值和数值交叉检查仍会阻止验收；
简表只列选中的两个模式。`strict_all` 保持原来的严格策略。

仅修改上述验收策略时，可用 `--seed-campaign OLD_CAMPAIGN` 配合新配置的
`--baseline-only` 或 `--optimize`，从已停止、仅含一个完整基线的 campaign 导入原始场。
必须使用与旧 campaign 完全一致的模板快照、参数/求解/采样设置，并保留剩余预算。
导入会锁定旧 campaign、核对工程及储存能量证据、重新计算全部场数据；不启动 CST，
不修改旧状态或工程，不把旧失败记录直接改成成功。新目录保留来源与字段哈希。
导入完成后可按新目录常规 `--resume`，旧 campaign 的代码指纹约束保持不变。

## 数值与几何约定

几何长度使用 mm，角度 degree；原工程使用其他受支持长度单位时显式换算。
束流沿 Z、β=1，复场使用 peak 振幅；其他 β 或场约定在配置阶段拒绝。
`V=∫Ez exp(+iωz/c) dz`，`g=∇⊥V`，
`M=c*g*gᴴ/(2*ω²*U)`，`Zprincipal=Qloaded*λmax(Re M)`，单位 Ω/m。
不是矩阵迹、不是复极化方向，也不是多个模式的总谱峰。Total-Q 不再叠加壁损 Q。

使用13条对称偏移轨迹，默认三次拟合和内层五点梯度差≤2%，半采样积分差≤1%。
储能取当前模式 QFactor 数据并核对频率与归一化，不假定 U=1 J；材料取配置或 Model.qfi。
缺场、无效采样、低Q或明显线宽重叠均不能报告有效单模达标。求解警告保留在每次尝试中。
轨迹签名匹配使用公共相位不变相关性及一对一分配，仅作为模式身份的辅助证据；
优化始终包含全部窗内模式，匹配模糊不会漏掉强模。

单弯几何使用圆截面扫掠的精确径向包络，包含整个圆弧；不套用旧双弯公式。
解析过滤要求 Lin2-DownHeight2≥间隙、弯曲半径大于导体半径并满足间隙、
导体投影位于法兰内。倒角半径保留作来源约定，不人为强制 R≥导体半径+倒角半径。
解析预筛不证明面编号、倒角或布尔运算一定成功，后续必须通过副本重建。

## 搜索、求解与恢复

基线加最多11个初始点，每点检查阈值。之后用 sklearn GP 和共享 EI，
输入归一化到[0,1]，有效目标 `log1p(max(Zi/100000))` 再标准化；
80%局部候选、20%全域候选。失败是状态，不是阻抗或巨大罚值。
连续两次改善扩大局部范围，连续四次无改善缩小；所有边界和预算可配置。
达到目标立即停止，不做用户已取消的额外复核或网格加密。

每次使用不可变模板的完整独立副本，重建并保存无结果版本，再用新的自有 CST 会话求解。
只设置本征模搜索参数，不 Reset 网格、材料或端口设置。General (Lossy) 不能使用
JDM专用的全频窗开关；从频段下限求6个模式，必要时加至12、24个。
General (Lossy) 只返回全局求解频率上限以内的模式，因此求解上限单独配置，
默认1070 MHz，验收上限仍为1060 MHz。要求原生模式表编号连续、频率升序，
并实际找到超过验收上限的模式；频窗内不完整的表不能通过。补算也消耗预算。
已覆盖但无窗内模式时可判为空窗；读不到模式表绝不等同于空窗。

默认覆盖策略为 `solver.coverage_policy: upper_sentinel`。用户确认有限模式数足够时，
可显式选择 `fixed_window`，同时设置 `upper_frequency_mhz: 1060`、`mode_count: 6`、
`max_mode_count: 6`、`coverage_retries: 0`。该策略接受用户指定的搜索范围，
不要求窗外哨兵，也不自动增加模式数；结果记录 `coverage_verified: false` 和
`coverage_basis: user_accepted_fixed_window`，不宣称已经自动证明谱完整性。
原生表必须非空、编号连续、频率有序且位于求解范围内；所有窗内已返回模式仍须通过
完整场提取和物理质量检查。空表、缺场、低 Q 或线宽重叠不会因此成为有效达标结果。

求解前持久化预算预留，异常退出也不会返还已预留次数。只对瞬时 RPC/连接故障
尝试一次新副本。几何确定失败不反复跑；基线失败停止整个启动阶段。
求解成功证据、工程及配套结果指纹用于恢复，后处理失败不重跑求解。
成功保存后与主 journal 写入之间的中断可从 solved.json 恢复。
仅关闭记录到的自有 PID；绝不调用可回退全局清理的通用 connection.close()。
自有资源清理失败时停止 campaign，保留证据供诊断。

## 输出与验证

- `report.md`、`summary.json`、`best.json`：状态、预算、最佳参数与候选工程位置。
- `modes.csv`：最佳有效点的窗内模态阻抗表；没有有效点时仅输出明确标注的诊断表，缺值不填零。
- `state.json`、`campaign.ckpt`、`evaluations.sqlite`：权威恢复状态和共享持久化格式。
- `template/`：验证过的完整模板快照；`evaluations/`：每次几何、求解和后处理证据。
- `native.json`、`fields/`、`analysis.json`：可离线重算的场、储能与各方向阻抗。

候选工程保留在最佳记录指向的独立目录，不用额外复制巨型结果。所有运行产物与本地配置
不提交 Git。退出码0表示达标或基线完成；2表示预算耗尽、基线失败或需要恢复后处理。

```powershell
.venv\Scripts\python.exe -m pytest -m "not cst_required" -q
```

no-CST 测试与 live-CST 验证单独报告，详见 `VALIDATION.md`。纯数值方法与 VBA 来源为
`cst-hom-audit` 2026-09-28 版本，已纳入本包，不依赖个人 skills 目录。
控制接口来源为仓库 wrappers；求解器语义依据用户安装提供的 CST 官方
`special_vbasolver_eigenmodesolver_object.htm`；场导出依据官方 VectorPlot3D/QFactor 文档。
