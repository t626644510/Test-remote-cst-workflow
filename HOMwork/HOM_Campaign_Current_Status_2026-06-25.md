# Workflow 4 HOM 本征模 campaign 现状交接

记录日期：2026-06-25
campaign 快照：`C:\Users\lau\cst_ver3_HOMwork\hom_campaign_20260621T064755Z`

## 1. 当前结论

本轮 Workflow 4 campaign 已经收束到终态，可作为后续 HOM 处理项目的初始候选输入。

但它不是最终 HOM 模式清单。后续项目需要继续解决：

- 测量目标与仿真模式的多候选匹配歧义；
- 3 模模板导致的模式枚举截断；
- 传播端口警告下的物理解释；
- 横向量和模式分类的人工/算法复核。

原始 campaign CSV 和 JSON 建议保持不可变。不要手工修改顶层输出表；如需下游专用输入，应另行生成派生 CSV，并在 manifest 或交接文档中记录筛选口径。

## 2. 工作区、代码和输入

- 工作区：`C:\Users\lau\cst_ver3_HOMwork`
- Git 分支：`codex/HOMwork`
- 当前代码 commit：`2394006b17e50164f494b93c0e02f3af347f5254`
- Workflow 4 入口：`run_workflow_4.py`
- Workflow 4 包：`workflows/rfgun_hom_eigenmode/`
- CST 模板路径：`D:\workflow4\F2F.cst`
- campaign 输入 CSV：`HOMwork\eigenmode_frequency_targets.csv`
- campaign 输入行数：60 条测量可疑 HOM 频率目标
- campaign 聚类后 target cluster：39 个

重要原则仍然有效：

- `eigenmode_frequency_targets.csv` 是测量目标输入，不是最终物理结果，禁止覆盖。
- CST API fidelity 是硬约束，只使用已验证封装或用户提供的官方 CST 文档。
- 仿真 R/Q 与测量 Q 必须分开保存和解释。
- 不使用 S21 峰值幅度直接计算束流阻抗。
- 无可靠离散模式或模式枚举不完整时，不做排除性结论。

## 3. campaign 顶层输出文件

campaign 根目录包含：

- `campaign_state.json`：状态机和 attempt 历史，最权威的运行状态来源。
- `hom_solver_manifest.json`：模板、输入、配置、公式、CST 版本和限制说明。
- `result_contract_audit.json`：结果树和导出契约审计。
- `hom_target_clusters.csv`：60 条测量输入聚类后的 39 个目标 cluster。
- `hom_solver_windows.csv`：所有求解窗口及 `fHOM` 计划。
- `hom_eigenmode_results.csv`：主候选模式表，323 条模式。
- `hom_valid_seed.csv`：旧口径下的有效 seed，218 条。
- `hom_mode_target_map.csv`：模式与 target cluster 的多候选频率映射。
- `hom_mode_condition_results.csv`：模式与每条测量工况/Q 的组合结果。
- `hom_unmatched_targets.csv`：未匹配目标；本轮为空。
- `workflow_4_runtime.log`：运行日志。

下游优先读取：

1. `hom_solver_manifest.json`
2. `hom_eigenmode_results.csv`
3. `hom_mode_target_map.csv`
4. `hom_mode_condition_results.csv`
5. `campaign_state.json`

不要只读取 `hom_valid_seed.csv`，原因见第 6 节。

## 4. 运行状态摘要

`campaign_state.json` 统计：

| 项目 | 数量 |
|---|---:|
| state schema version | 3 |
| window 总数 | 116 |
| `postprocessed` | 49 |
| `mode_enumeration_incomplete` | 63 |
| `avoid_retry` | 2 |
| `avoid_retry_legacy` | 2 |
| attempt 总数 | 193 |
| attempt success | 112 |
| attempt failed | 77 |
| attempt interrupted | 3 |
| attempt running 记录残留 | 1 |

失败类型统计：

- `long_solve`：41
- `init_fast`：36
- `external_interrupt`：3

当前没有 `pending` 或需要普通 resume 继续执行的窗口。

## 5. 结果覆盖摘要

顶层 CSV 统计：

| 输出 | 数量 |
|---|---:|
| target clusters | 39 |
| solver windows | 116 |
| eigenmode result rows | 323 |
| old valid seed rows | 218 |
| mode-target map rows | 576 |
| condition result rows | 995 |
| unmatched target rows | 0 |

覆盖情况：

- 60 条原始测量 source row 全部进入 `hom_mode_condition_results.csv`。
- 60 条原始测量 source row 都至少有一个 `derived_valid=true` 的 condition 组合。
- 39 个 target cluster 都至少有一个候选模式。
- `hom_unmatched_targets.csv` 为空。

这说明 campaign 对输入目标的覆盖是完整的；问题主要在候选唯一性和枚举完整性，而不是目标遗漏。

## 6. crosscheck 口径更新

Workflow 4 当前代码把离线 Ez 线积分结果与 CST native `Voltage` / `R over Q` 做 2% 相对误差交叉验证：

- `native_voltage_crosscheck_failed`
- `native_r_over_q_crosscheck_failed`

本轮结果中：

| `data_availability_reason` | 模式数 |
|---|---:|
| 空，即旧口径 `derived_valid=true` | 218 |
| `native_r_over_q_crosscheck_failed` | 58 |
| `native_voltage_crosscheck_failed;native_r_over_q_crosscheck_failed` | 47 |

用户已明确新的解释口径：

- 纵向 `Voltage` 以 CST native 输出为准。
- 纵向 `R/Q` 以 CST native `R over Q beta=1` 为准。
- 离线 Ez 积分受当前导出 Ez 精度、采样范围和路径设置限制，不应优先于 CST native 标量。
- 因此这两类 crosscheck failure 应降级为诊断 warning，不应作为排除模式的硬条件。

实际下游建议：

- 不手动修改原始 CSV。
- 下游若构建 HOM 候选池，应从 `hom_eigenmode_results.csv` 取 323 条完整候选。
- 对 `data_availability_reason` 仅为上述 crosscheck failure 的模式，不要直接剔除其 CST native 频率、Voltage、R/Q。
- 横向派生量仍来自五点 Ez 线场，若某个横向结论很关键，应单独提高场导出精度或用 CST native 偏轴 R/Q 复核。

## 7. 匹配歧义

当前匹配规则是频率窗口匹配：

- 对每个 target cluster，在 ±10 MHz 内找仿真模式。
- 找到 1 个模式则 `matched`。
- 找到多个模式则 `ambiguous`。
- 找不到则 `unmatched`。

本轮 `hom_mode_target_map.csv`：

| `match_status` | 数量 |
|---|---:|
| `matched` | 2 |
| `ambiguous` | 574 |

含义：

- 这不是 CST 求解失败。
- 这表示大多数测量目标附近存在多个仿真候选模式，不能只按频率唯一认领。
- 后续具体 HOM 处理需要结合场型、极化方向、R/Q、端口/吸收结构、传播背景、测量工况等继续筛选。

本轮结果适合作为“候选地图”，不适合作为“最终唯一映射表”。

## 8. 模式枚举截断

当前模板每个窗口最多导出 3 个模式。Workflow 4 语义为：

- 返回 1–2 个模式：未触及模板上限；
- 返回恰好 3 个模式：`mode_count_censored=true`，表示“至少 3 个”，不能证明窗口内只有 3 个。

本轮结果：

| 字段 | 数量 |
|---|---:|
| `mode_count_censored=true` | 316 |
| `mode_count_censored=false` | 7 |
| `mode_enumeration_incomplete` window | 63 |

Workflow 4 已做过自动补救：

1. 多 cluster 饱和窗口拆成单 cluster；
2. 单 cluster 仍饱和时增加 `fHOM-5 MHz` 和 `fHOM+5 MHz` 探测窗口；
3. 探测仍触顶时标记 `mode_enumeration_incomplete`。

后续解释口径：

- 可以使用已找到的候选模式。
- 不能用本轮结果证明某频段“没有其他模式”。
- 关键频段若需要完整枚举，应改模板策略，例如更窄频窗、增加导出模式数、按极化/边界分组，或辅助 driven-mode / wakefield 分析。

## 9. 传播端口警告

所有 323 条模式均有 `boundary_sensitive=true`。

警告分布：

| `warning_codes` | 模式数 |
|---|---:|
| `propagating_port_modes_not_considered:1_4_5_6` | 313 |
| `propagating_port_modes_not_considered:1` | 10 |

用户当前认为可在本阶段暂时忽略该项，由后续具体 HOM 处理中解释。

仍需保留的物理提醒：

- 传播通道遗漏可能低估泄漏、抬高 Q，也可能因反射改变频率、场型和极化。
- 2.7–3.0 GHz 区域尤其不宜把 `QL/Qext/radiated-Q` 当作最终阻抗结论。

## 10. 模板 revision 混合

campaign 使用了模板 revision 继承机制。

模式表中：

| template revision | `hom_eigenmode_results.csv` | `hom_valid_seed.csv` |
|---|---:|---:|
| `TR_81424d512315` | 41 | 34 |
| `TR_64cca13c2716` | 282 | 184 |

当前 active template revision：

```text
TR_64cca13c2716
```

用户已表示该项暂时可忽略。

若后续需要全量同模板一致性，优先关注这些没有 active-template seed 的 cluster：

- `TC_0001`
- `TC_0002`
- `TC_0004`
- `TC_0005`

有效 seed 数较少、后续也可重点复核：

- `TC_0037`
- `TC_0039`

## 11. 失败/未产出窗口

顶层结果中无模式的窗口包括：

- `WIN_0002_C2`
- `WIN_0003_M5`
- `WIN_0005`
- `WIN_0018_C1_P5`

这些窗口对应的目标或频段在其他窗口已有候选覆盖，因此 campaign 整体没有 unmatched target。

若需要进一步审计失败原因，优先索取这些窗口的：

- `attempt_metadata.json`
- `cst_messages.txt`
- `Model.log`
- `output.txt` / `output.json`
- `simulation_overview.json`
- 文件清单，不必先传大体积场文件。

## 12. 给下游项目的推荐用法

下游如果需要 HOM 初始候选输入：

1. 读取 `hom_eigenmode_results.csv` 作为完整候选池。
2. 读取 `hom_mode_target_map.csv` 保留多候选映射，不要自动唯一选模。
3. 读取 `hom_mode_condition_results.csv` 获取每条测量 Q 下的组合阻抗。
4. 对 `native_*_crosscheck_failed` 只作为 Ez 线积分诊断 warning，不作为 native Voltage/R/Q 剔除条件。
5. 保留 `mode_count_censored`、`match_status`、`boundary_sensitive`、`warning_codes`。
6. 对关键 HOM 再按场型、极化、R/Q、端口/吸收结构和测量工况做物理筛选。

如果下游必须要一个单独 CSV，建议另行生成派生表，例如：

```text
hom_candidate_seed_native_voltage.csv
```

该派生表可包含全部 323 条模式，并新增字段说明：

- `native_longitudinal_quantities_authoritative=true`
- `ez_crosscheck_warning=true/false`
- `candidate_pool_status=usable_candidate`

但不要覆盖现有 campaign 输出。
