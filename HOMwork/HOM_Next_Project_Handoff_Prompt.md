# HOM campaign 下一项目快速恢复 prompt

将下面 prompt 粘贴给新的 Codex 线程或下一个项目代理使用。

```text
你现在接手 RF 常温腔 HOM 本征模 campaign 结果的后续处理。

工作区：
C:\Users\lau\cst_ver3_HOMwork

Git 分支：
codex/HOMwork

当前参考 commit：
2394006b17e50164f494b93c0e02f3af347f5254

核心 campaign 快照：
C:\Users\lau\cst_ver3_HOMwork\hom_campaign_20260621T064755Z

开始前只读检查并确认 cwd、分支、git status。不要删除、覆盖或移动以下原始 HOM 输入文件：

1. HOMwork\eigenmode_frequency_targets.csv
2. HOMwork\HOM_Eigenmode_Output_Guide.md
3. HOMwork\HOM_Eigenmode_Implementation_Plan.md
4. HOMwork\HOM_Campaign_Current_Status_2026-06-25.md

按顺序阅读：

- AGENTS.md
- reports\project_context_capsule.md
- _docs\FRAMEWORK.md
- HOMwork\HOM_Eigenmode_Implementation_Plan.md
- HOMwork\HOM_Eigenmode_Output_Guide.md
- HOMwork\HOM_Campaign_Current_Status_2026-06-25.md
- HOMwork\eigenmode_frequency_targets.csv 的表头和行数
- campaign 根目录下的 hom_solver_manifest.json、campaign_state.json、result_contract_audit.json

重要原则：

- CST API fidelity 是硬约束。若需要 CST 交互，只能使用用户提供的官方 CST 文档或仓库已验证封装，不得猜测 API。
- 原始测量 CSV 是目标输入，不是最终物理结果，严禁覆盖。
- 原始 campaign 输出建议保持不可变；需要下游专用表时另行生成派生 CSV。
- 仿真 R/Q 和测量 Q 必须分开保存。
- 不使用 S21 峰值幅度直接计算束流阻抗。
- 无可靠完整枚举时不能做排除性结论。

当前 campaign 状态概要：

- 输入测量目标：60 条
- 聚类目标：39 个 target cluster
- solver windows：116 个
- 主结果模式：323 条
- 旧口径 valid seed：218 条
- mode-target map：576 条
- mode-condition results：995 条
- unmatched targets：0
- `postprocessed` windows：49
- `mode_enumeration_incomplete` windows：63
- `avoid_retry` / `avoid_retry_legacy` windows：4

当前解释口径：

1. campaign 可作为后续 HOM 处理的初始候选输入，但不是最终模式清单。
2. 匹配高度歧义：`hom_mode_target_map.csv` 中仅 2 条 `matched`，574 条 `ambiguous`。后续需要结合场型、极化、R/Q、端口/吸收结构、传播背景和测量工况进行物理筛选。
3. 模式枚举大量截断：模板每窗口最多导出 3 个模式，316/323 条模式为 `mode_count_censored=true`，63 个窗口为 `mode_enumeration_incomplete`。可使用已找到候选，但不能证明频段内没有其他模式。
4. crosscheck 口径已更新：CST native `Voltage` 和 native `R over Q beta=1` 是纵向量权威来源；离线 Ez 线积分受当前导出精度限制，只作为诊断 warning，不应把 `native_voltage_crosscheck_failed` 或 `native_r_over_q_crosscheck_failed` 当作剔除 native 纵向量的硬条件。
5. 传播端口警告和模板 revision 混合当前可暂时忽略，但必须保留 provenance 字段，不要从输出中删掉。

下游推荐读取：

1. hom_solver_manifest.json
2. campaign_state.json
3. result_contract_audit.json
4. hom_eigenmode_results.csv
5. hom_mode_target_map.csv
6. hom_mode_condition_results.csv

不要只用 hom_valid_seed.csv，因为它仍体现旧口径：把 Ez crosscheck 超 2% 的 105 条模式排除在 valid seed 外。按当前用户确认，这些模式的 CST native 频率、Voltage、R/Q 不应因此视为无效。

如果需要生成下游候选输入，请基于 hom_eigenmode_results.csv 另行生成派生表，例如 hom_candidate_seed_native_voltage.csv，并保留：

- mode_id
- solver_window_id
- target_cluster_ids 或匹配候选集合
- freq_sim_hz / freq_sim_ghz
- native longitudinal_R_over_Q_ohm
- native voltage_v
- Q_loaded_simulated / Q0_simulated / regional_q_json
- 横向 R/Q 派生量及其 Ez-line 来源说明
- match_status / candidate_rank / delta_freq_mhz
- mode_count_censored
- boundary_sensitive
- warning_codes
- data_availability_reason
- template_revision_id / template_hash

当前不要重新运行 campaign，除非用户明确要求。第一步应只读审计上述文件，复述当前状态和下游处理计划。
```
