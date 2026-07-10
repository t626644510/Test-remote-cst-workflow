# RF-CEM 500 MHz 工作站本地 Agent 交接说明

更新日期：2026-07-09

## 1. 项目当前状态

RF-CEM 500 MHz 当前已经具备一条可运行的参数化几何到 live-CST 回读链路：

```text
expert prior / 12D curve controls
  -> parametric_geometry.v0.json
  -> generated_vacuum.step
  -> CSTTranslator setup
  -> CST eigenmode solver
  -> 0D result tree readback: Frequency / R over Q / Q
```

当前工作基线是：

```text
free_equator_smooth
```

优化参数预设是：

```text
exploratory_12d
```

这 12 个参数控制 equator crown、左右 shoulder、左右 nose NURBS 内部控制点、左右 blend arc radius。几何参数不会直接写 CST StoreParameter，而是写入本轮 expert prior override，再重新生成 STEP。

已验证的 CST 设置路径：

- 背景材料：`Copper (annealed)`，导电率 `5.8e7 S/m`
- 导入实体材料：`Vacuum`
- Solver：`HF Eigenmode`
- Mesh：Tetrahedral
- 后处理模板：从 `D:\ModelData\bare\Model\3D\Model.rpp` 和对应 `.r0d` 文件注册
- 结果树路径：
  - `Tables\0D Results\Frequency (Mode 1)`
  - `Tables\0D Results\R over Q (Mode 1)`
  - `Tables\0D Results\Q-Factor (Perturbation) (Mode 1)`

注意：不要默认调用 `--evaluate-templates`。显式 `EvaluateResultTemplates` 可能触发非致命的 `HEX mesh is invalid`，但 result tree readback 已经足够用于优化。

## 2. 工作站侧已知目录

工作站包根目录示例：

```text
G:\500MHzTest\rf_cem_workstation_package_smoke
```

第一次 seeded SAO campaign 目录：

```text
G:\500MHzTest\rf_cem_workstation_package_smoke\runs\rf_cem_500mhz_sao_seed004_budget60
```

用户只拷回了轻量汇总文件，完整 `candidates/` 和 `cst_projects/` 太大，应在工作站本地审计：

```text
live_records.jsonl
live_summary.json
sao_result.json
candidates\candidate_###\...
cst_projects\candidate_###_postprocess_solver.cst
```

## 3. 第一次 campaign 审计结论

第一次 campaign 命令语义：

```text
mode = sao
seed_candidate_index = 4
local_bounds_scale = 0.45
n_initial = 24
n_iterations = 36
max_evals = 60
```

总体执行结果：

```text
record_count = 60
success_count = 60
status = SUCCESS for all records
search_semantics = seeded_local_sao
```

这说明 live-CST 求解与结果回读链路稳定。

重要发现：

1. `candidate_004` seed 本身不是好腔型。

```text
candidate_001 in campaign, i.e. seed004 vector:
Frequency = 765.176529789666 MHz
R/Q       = 2.782529258126 Ohm
Q         = 40173.2150634
R         = 111783.1463 Ohm
```

2. SAO 在 seed004 附近找回了 500 MHz 附近的有效腔型。

当前按原 scalar objective 最优：

```text
candidate_014
Frequency = 500.001480360380 MHz
R/Q       = 425.046393100986 Ohm
Q         = 45274.2454731786
R         = 19,243,654.7387 Ohm
objective = -0.64984200568
```

当前最高 R/Q：

```text
candidate_039
Frequency = 503.196373350478 MHz
R/Q       = 427.129785470058 Ohm
Q         = 45413.9015328536
R         = 19,397,630.0191 Ohm
objective = 2.54115462148
```

当前最高综合 R：

```text
candidate_046
Frequency = 501.756334899666 MHz
R/Q       = 425.830522740434 Ohm
Q         = 45770.9945658718
R         = 19,490,686.5423 Ohm
objective = 1.09446834346
```

结论：campaign 执行成功，但当前 objective 过度偏向频率精确贴近 `500 MHz`。用户真实偏好是：

```text
频率在 500 MHz 附近即可，初始允许 490-510 MHz；
R/Q 尽量高；
Q 不要太低；
R = R/Q * Q 尽量高；
允许更奇怪的形状。
```

因此下一步应调整 objective，而不是只沿用当前 scalar objective。

## 4. 下一步建议

### 4.1 先在工作站本地完整审计 candidate_039 和 candidate_046

重点打开：

```text
runs\rf_cem_500mhz_sao_seed004_budget60\candidates\candidate_039
runs\rf_cem_500mhz_sao_seed004_budget60\candidates\candidate_046
```

检查：

- `metadata\parametric_geometry.v0.json`
- `metadata\geometry_validation.json`
- `audit\parametric_geometry_audit.html`
- `geometry\generated_vacuum.step`
- `live_postprocessing\live_postprocessing_diagnostic_report.json`
- 对应 CST project

确认这些形状是否视觉上可接受、没有不合理尖角/自交/过度细颈。

### 4.2 调整 objective

建议把频率惩罚改为窗口式：

```text
if 490 <= frequency_mhz <= 510:
    frequency_penalty = 0
else:
    frequency_penalty = distance_to_window
```

然后更重视：

```text
- normalized R/Q gain
- normalized shunt impedance R gain
- Q soft floor penalty
- novelty reward, optional and small
```

可以先采用：

```text
objective = frequency_penalty
            - 0.01 * normalized_r_over_q_gain
            - 0.01 * normalized_shunt_impedance_gain
            + q_soft_floor_penalty
            - 0.05 * novelty_score
```

具体权重可以由本地 agent 根据 budget60 的统计量标定。

### 4.3 以 candidate_039 或 candidate_046 为新 seed 继续 local SAO

由于当前 CLI 支持 `--seed-candidate-index` 读取 quick-scan candidate，而不是读取上一次 campaign 的任意 candidate，下一步有两种实现方式：

1. 快速做法：新增 `--seed-record-index 39` 或 `--seed-record-path ...`，从 `live_records.jsonl` 读取 candidate_039 的参数向量作为 warm start。
2. 临时做法：把 candidate_039 的参数手动写成一个新 config seed。

推荐实现方式 1。

新一轮建议：

```text
seed = candidate_039 或 candidate_046
local_bounds_scale = 0.30-0.45
n_initial = 36
n_iterations = 84
max_evals = 120
```

如果几何失败率仍低，可以提高到：

```text
max_evals = 200
local_bounds_scale = 0.55
```

## 5. 本地 Agent Prompt

请将以下 prompt 交给工作站本地 Codex agent：

```text
你是工作站本地执行 agent，工作目录为：
G:\500MHzTest\rf_cem_workstation_package_smoke

任务背景：
RF-CEM 500 MHz 参数化几何和 live-CST 回读链路已经跑通。当前优化工作基线是 free_equator_smooth，参数预设为 exploratory_12d。第一次 seeded SAO campaign 位于：
runs\rf_cem_500mhz_sao_seed004_budget60

该 campaign 的执行结果为 60/60 SUCCESS，证明 live-CST solver 和结果树回读稳定。关键结果：
- candidate_014: f=500.001480 MHz, R/Q=425.046393 Ohm, Q=45274.245, R=19.2437M, 当前 scalar objective 最优。
- candidate_039: f=503.196373 MHz, R/Q=427.129785 Ohm, Q=45413.902, R=19.3976M, 当前 R/Q 最高。
- candidate_046: f=501.756335 MHz, R/Q=425.830523 Ohm, Q=45770.995, R=19.4907M, 当前 R=R/Q*Q 最高。
- seed004 本身很差：f=765.176530 MHz, R/Q=2.782529 Ohm。

用户真实偏好：
频率只需在 500 MHz 附近，初始接受 490-510 MHz；优先提高 R/Q 和 R=R/Q*Q；Q 只做 soft floor，不要太低；允许生成更奇怪但几何合法的形状。

你的任务：
1. 只读审计 runs\rf_cem_500mhz_sao_seed004_budget60 的完整目录，重点看 candidate_039 和 candidate_046 的 generated STEP、parametric_geometry、geometry_validation、audit HTML、live diagnostic JSON 和 CST project。
2. 判断 candidate_039 / candidate_046 是否适合作为下一轮 seed。
3. 修改 live campaign objective：频率在 490-510 MHz 内应为零或很低惩罚，不要压过 R/Q 与 R 的优化；R/Q 和 R 应成为主要优化方向；Q 维持 soft floor。
4. 实现从上一轮 live_records.jsonl 读取任意 seed record 的功能，例如：
   --seed-record-index 39
   或 --seed-record-path runs\...\live_records.jsonl --seed-record-index 39
   使下一轮 SAO 可以围绕 candidate_039 或 candidate_046 继续局部优化。
5. 不新增未经验证的 CST API。继续复用已验证入口：
   rf_cem.live_500mhz_postprocessing_diagnostic
   不默认传 --evaluate-templates。
6. 先做 no-CST / dry-run 级别测试，确认 seed 参数向量读取和 objective 计算正确；然后启动下一轮小预算 live-CST，例如 max_evals=20；稳定后再扩大到 120 或 200。

注意：
- 不要盲目复制整个 runs 目录回主机，文件很大。
- 所有重要结论写入本地 markdown 状态文档。
- 每个 campaign 必须保留 live_records.jsonl、live_summary.json、sao_result.json。
- 每条记录必须能追溯 parameter_values、objective_values、candidate_dir、project_path、diagnostic_report。
```

## 6. 需要避免的问题

- 不要把单点 `rf_cem.live_500mhz_postprocessing_diagnostic` 误认为 campaign。
- 不要把 `project_path` 的编号当作几何 candidate 编号；真正几何来源是 `package-dir` 或 campaign record 的 `parameter_values`。
- 不要因为 `EvaluateResultTemplates` 的 `HEX mesh is invalid` 误判失败；以 result tree scalar readback 为准。
- 不要把 `candidate_004` 继续当好 seed；它只是一个能让 SAO 找回有效区域的起点，性能本身很差。
- 不要过度追求频率精确等于 500 MHz。窗口内应主要比较 R/Q、Q 和 R。
