# CST Optimization Framework — 架构总结

> 全自动 CST Studio Suite 微波加速器腔体电磁仿真与代理模型优化框架
> 版本: 0.5.0 | 更新: 2026-05-30

---

## 1. 项目概述

本框架通过 COM 接口自动化 CST Studio Suite，实现加速器腔体（X-band RF gun / HOM 天线）的几何参数化 → 电磁仿真 → 物理量提取 → 贝叶斯优化全流程闭环。

### 依赖

`numpy scipy matplotlib scikit-learn pymoo pyyaml openpyxl`
CST Python 库 (`cst.interface` + `cst.results`)，要求 CST 2025+ 且 Python 3.9-3.13 64-bit。

---

## 2. 分层架构

```
config/*.yaml  →  factory.py  →  orchestrator / recovery evaluator
                      │
         ┌────────────┼────────────────┐
    core/          physics/       parameters/
  CST 集成层      纯数学/物理      设计空间定义
         │
    objectives/    optimization/   sensitivity/
  目标函数+模式    贝叶斯优化算法   灵敏度+鲁棒性
                      │
              conditional_gate.py  (v0.5 新增)
               自适应条件门控
           (三阶段 + TCP 滑动窗口)

  checkpoint.py  watchdog.py  database.py  (跨层基础设施)
  断点续算        外部进程监控    1D曲线DB
```

### 2.1 Core 层 — CST 集成 (`src/cst_optimization/core/`)

| 模块 | 职责 |
|------|------|
| `connection.py` | `CSTConnection` — DesignEnvironment 生命周期管理 (connect/close/reconnect)，支持 new/any/any_or_new 三种模式 |
| `project.py` | `CSTProject` — .cst 文件包装器。`update_parameters()` 三级回退: 原生 StoreParameter → VBA add_to_history → raise |
| `solver.py` | `SolverRunner` — `model3d.run_solver()`，结构化错误分类: timeout/mesh/com/convergence |
| `results.py` | `ResultReader` — 通过 `cst.results.ProjectFile` 读取 0D标量/1D曲线/2D色图。`TREEPATH_S11/S21/S31` 类常量支持 multipin 端口默认。构造参数 `s11_treepath/s21_treepath/s31_treepath` 支持实例级覆盖（config 驱动）。`get_all_run_ids()` + `get_parameter_combination()` 读取参数扫描 |
| `messages.py` | `MessageLogger` — 捕获 CST 消息窗口，检测 VBA 历史回放失败 |
| `orchestrator.py` | `DualProjectOrchestrator` — 多项目串行编排 (单 `CSTConnection`): Phase 1(非条件求解) → [Inter-pass Reset: 杀旧DE+清条件项目结果+新建DE，防F2F残留致PBA矩阵竞态] → Phase 1.5(条件项目，`completed_labels` 门控) → Phase 2(目标评估，跨文件读取) → Phase 3(惩罚) → Phase 4(try/finally 清理)。Phase 1 频域 mesh 错误直接冒泡 Tier3；Phase 1.5 尾场 mesh 错误触发 rebuildlength 6→25 逐级 `full_history_rebuild()` 重试。每次评估终端日志同步落盘 `workflow_2_terminal.log`。 |
| `retry.py` | `EvaluationRetryHandler` — 三级 escalation 重试。Tier1: 同连接简单重试 → Tier2: 优雅关闭+清结果+重连 → Tier3: force kill+清结果+重连。v0.4 新增 `extra_result_paths` 支持多项目结果目录清理。Workflow 2 配置 `max_tier2=0` (跳过 Tier2，直接 Tier3)，无 `post_eval_recovery`。`force_reset()` 主动重置。`close_all()` 防孤儿 CST 进程 |
| `cleanup.py` | `force_kill_cst()`, `kill_all_cst_processes()` (双通道: 前缀扫描 + 精确名)，锁文件/结果文件夹清理。`CST_PROCESS_WHITELIST = {"cstd.exe"}` 保护许可证服务器不被误杀 |
| `errors.py` | 类型化异常体系 (`CSTConnectionLostError`, `SolverError` 子类) |
| `timeout.py` | `run_with_wall_clock_timeout()` — 守护线程超时保护，超时触发 Tier3 恢复 |

### 2.2 Physics 层 — 物理计算 (`src/cst_optimization/physics/`)

纯 numpy/scipy，无 CST 依赖，可单元测试。

| 模块 | 关键函数/类 |
|------|-----------|
| `formulas.py` | `half_power_bandwidth()`, `loaded_q_from_bandwidth()`, `coupling_beta()`, `intrinsic_q0()`, `power_scaling()`, `resonance_from_dip()` |
| `cavity.py` | `ResonantFrequency`, `LoadedQ`, `CouplingBeta`, `IntrinsicQ`, `PeakSurfaceField`, `InputPower`, `MinS11` (均为 `PhysicsQuantity` 子类) |
| `heating.py` | `pulsed_heating_delta_t()` — SRF 脉冲加热温升 (OFHC铜@77K)；`max_h_from_field_file()` |
| `poynting.py` | `max_modified_poynting()` — 修正坡印廷矢量缩放；`discover_field_files()` — 通配符自动定位 E/H 场导出文件 |
| `wakefield.py` | `read_beam_impedance()`, `compute_transverse_impedance()`, `scalarize()` (三种策略 + `square_exceedance`), `aggregate_over_beams()` |
| `quantities.py` | `PhysicsQuantity` ABC, `ResultBundle` 数据类 |

### 2.3 Parameters 层 — 设计空间 (`src/cst_optimization/parameters/`)

- `ParamRange(low, high, log_scale)` — 参数边界
- `GeometryParameter` — 映射到 CST `StoreParameter` 的具体几何参数
- `ParameterSet` — 有序参数集合，支持 normalize/denormalize、bounds 管理、shrink/expand
- `ConstraintSet` / `ParameterConstraint` — 几何约束框架 (支持 `gt` (参数间+字面量), `sin_times_r_lt/gt`)

### 2.4 Objectives 层 — 目标函数 (`src/cst_optimization/objectives/`)

| 模块 | 注册目标 | 物理含义 |
|------|---------|---------|
| `frequency.py` | `resonant_freq` | S11 dip 谐振频率 (GHz) |
| `quality.py` | `q0`, `q_loaded`, `coupling_beta`, `input_power` | 腔体品质因数 |
| `field.py` | `peak_e_field`, `field_flatness`, `max_modified_poynting`, `pulsed_heating` | 场分布 |
| `wakefield.py` | `z_longitudinal`, `z_transverse` | 束流耦合阻抗 |
| `antenna.py` | `antenna_absorption`, `antenna_absorption_db`, `s21_at_f0_db` | HOM 天线吸收 / 传输 (dB)。构造参数 `tree_path` 支持 config 级覆盖 (不依赖硬编码 multipin 路径) |

`OptimizationMode` 子类: `Minimize`, `Maximize`, `LessThan`, `GreaterThan`, `GaussianTolerance`, `SoftTolerance`, `SoftLessThan`, `SoftGreaterThan`。装饰器注册表 (`@register_objective` / `@register_mode`)。

### 2.5 Optimization 层 — 优化算法 (`src/cst_optimization/optimization/`)

- `SurrogateAssistedOptimizer` (SAO) — GP 贝叶斯优化，EI/UCB/PI 采集函数，LHS/Sobol 初始采样。支持 `prior_data` 和 `n_initial_extra`
- `SurrogateAssistedEA` (SAEA) — GP 辅助 NSGA-II 多目标进化
- `AdaptiveBoundsController` — 边界收缩/扩展 (shrink_factor + expand_factor)
- `OptimizationLogger` — Excel 双工作表日志
- `InSituSensitivity` — GP-Sobol' 灵敏度 (零额外 CST 评估)

### 2.6 Sensitivity 层 (`src/cst_optimization/sensitivity/`)

- `SobolSensitivity` — Saltelli Sobol' 指数
- `RobustOptimizer` — 制造公差鲁棒性 (蒙特卡洛扰动)

### 2.7 基础设施 (`src/cst_optimization/`)

| 模块 | 职责 |
|------|------|
| `checkpoint.py` | `CheckpointManager` — pickle 持久化。三态: pending/completed/failed_permanent。Tier3 耗尽→permanent |
| `watchdog.py` | `WatchdogRunner` — 外部进程监控。崩溃→cooldown→重启 (max_restarts 次) |
| `database.py` | 1D 曲线数据库 — `RecordingResultReader` 拦截 CST 读取并录制成 `.npz`；`VirtualResultReader` 从 `.npz` 回放，使 objective.raw_value() 可在无 CST 环境下重算；`curves_to_warmup()` 加载历史曲线用当前惩罚算法重算 → SAO warmup |
| `factory.py` | YAML → 对象图构建。Workflow 2 支持 `EvaluationRetryHandler` 包装 + 适配器 (`_evaluate_for_retry`)，`post_eval_recovery` 可配置，`--warmup-from-db` 重载历史数据 |

---

## 3. 三个 Workflow

### Workflow 1: 单项目单通频域 SAO 优化 + 公差分析

**SAO 优化入口**: `python run_workflow_1.py` → `config/default.yaml` 根级
**公差分析入口**: `python examples/tolerance_analysis.py` → `config/default.yaml` `tolerance` 段

**SAO 优化特性**:
- 13 参数 ±3μm 窄范围，7 目标 (resonant_freq, coupling_beta, peak_e_field, q0, max_modified_poynting, field_flatness, pulsed_heating)
- 单通求解 (f_data=11.424 GHz)，无需校准/测量分离
- Three-tier retry + 每次评估后 Tier2 优雅重置 (正常关闭 → 清结果 → 重连)
- Checkpoint 断点续算

**公差分析特性**:
- 拉丁超立方采样 + 自适应加密 (min→max samples，按 batch_size 批增)
- 双通求解 (校准 f0 → 测量通 re-solve at f0)
- Three-tier retry: Tier1×0 → Tier2×2 (优雅) → Tier3×2 (force kill)
- 每次样本后 Tier2 优雅重置，保持 CST 状态干净
- 增量 Excel + JSON checkpoint + failed_permanent 追踪
- Watchdog: `python examples/run_tolerance_watchdog.py`

### Workflow 2: HOM 天线三项目自适应条件链 (v0.5 重构)

**入口**: `python run_workflow_2.py` → `config/default.yaml` `workflow_2` 段
**算法**: SAO (14 参数, 4 目标: z_longitudinal, z_transverse, antenna_absorption, antenna_absorption_db)
**恢复策略**: EvaluationRetryHandler (Tier1=0, Tier2=0, Tier3=2), 无 post_eval_recovery
**1D 曲线数据库**: RecordingResultReader/VirtualResultReader + `.npz` + `index.jsonl`
**新增 (v0.5)**: 自适应条件门控 `AdaptiveConditionalGate` — 三阶段 + TCP 滑动窗口

**三阶段自适应门控**:

```
Phase A (WARMUP)             Phase B (GP_GATED)              Phase C (FULL_4OBJ)
──────────────────           ────────────────────            ────────────────────
前 N_warmup 次无条件         GP 预测 z_long/z_trans          全 4 目标 BO
运行全部 F2W+F2WO             TCP 窗口调节 dB 阈值             默认跑 F2W
积累初始 GP 训练数据          ┌─验证通过→收紧窗口              GP 只跳过确信必差点
                             ├─验证失败→放松窗口              通过率骤降→回退 B
                             └─连续失败→重建 GP
```

**项目执行顺序** (单 CSTConnection, 串行):

```
iter N
  │
  ├─ [Pre-solve cleanup] (v0.5 新增)
  │    每次求解前删除同名结果文件夹 + ProjectDir.lock
  │    确保每次求解从干净状态起步
  │
  ├─ Phase 1: F2F.cst (frequency_domain, pre_filter)
  │    频域求解 → antenna_absorption 预过滤
  │    v0.5: > 阈值不再返回全 1.0 → 继续 Phase 2/3 计算真实 penalty（有梯度）
  │    条件项目因 trigger_penalty >= max_penalty 被 gate 跳过
  │    Phase 1 mesh/com/timeout 错误直接冒泡到 retry handler →
  │    Tier3 (force kill+清结果+重连) ×2
  │
  ├─ [Inter-pass Reset]
  │    杀当前 DE → kill_all_CST → 仅清 F2W/F2W_offset 结果文件夹
  │    (保留 F2F 结果供 Phase 1.5 读取 S 参数) → 新建 DE
  │
  ├─ Phase 1.5: 条件项目 (自适应门控)
  │   │
  │   ├─ wakefield (F2W.cst)
  │   │    trigger=antenna_absorption, max_penalty=0.35
  │   │    读 F2F S21 → 计算 trigger_penalty
  │   │    门控决策: AdaptiveConditionalGate.should_run_conditional()
  │   │      · WARMUP → 强制运行
  │   │      · GP_GATED → GP 预测好才跑 (保守)
  │   │      · FULL_4OBJ → GP 预测差才跳 (激进, 优先阻抗)
  │   │      · should_validate_next → 定期无条件抽样验证
  │   │    跳过时: penalty 用 GP 预测值 (而非硬编码 0.0)
  │   │    Phase 1.5 mesh 错误: rebuildlength 6→25 逐级重试
  │   │
  │   └─ wakefield_offset (F2W_offset.cst)
  │        trigger=z_longitudinal, max_penalty=0.35
  │        同上自适应门控
  │
  ├─ Phase 2: 评估目标 (ref_project_map 跨文件读取)
  │    antenna_absorption/antenna_absorption_db ← F2F.cst (S2,1/S3,1)
  │    z_longitudinal   ← F2W.cst    (ParticleBeam1.Z)
  │    z_transverse     ← F2W_offset.cst (ParticleBeam2.XY) + ref: F2W.cst (ParticleBeam1.XY)
  │    F2W 未运行时: z_long/z_trans → NaN → Phase 3 用 GP 预测填补
  │
  ├─ Phase 3: 惩罚
  │    已求解目标 → mode.compute(raw) → 真实连续 penalty (有梯度)
  │    门控跳过目标 → GP 预测 penalty (有梯度) / 回退 0.0 (中性)
  │    solver fail → 1.0
  │
  ├─ [Gate recording] (v0.5 新增)
  │    gate.record_evaluation(x, penalties, f2w_ran)
  │    gate.record_validation(predicted, measured)  ← 仅验证轮
  │    TCP 窗口调节 + Phase 转换检查
  │
  ├─ Phase 3.5: 日志 (Excel + 1D曲线.npz + checkpoint)
  │
  └─ Phase 4: try/finally 清理 (v0.5 简化)
       超时关闭所有 CSTProject 句柄 (10s daemon thread)
       DE 连接保留不杀 — 跨 evaluate() 复用
       (DE 只在 Inter-pass Reset 和最终退出时关闭)
```

**TCP 滑动窗口机制**:

```
连续验证通过 N_trust 次  →  收紧窗口: threshold -= Δ_dB (更严格)
                            threshold 不低于 db_min (-31 dB)

单次验证失败             →  放松窗口: threshold += Δ_dB (更宽容)
                            threshold 不高于 db_initial (-25 dB)

连续失败 N_max_fail 次   →  重建所有 GP 模型 → 返回 Phase B 起点
                            threshold 重置为 db_initial
```

**配置**: `config/default.yaml` → `workflow_2.adaptive_gate` 段 (全部参数可配)

**v0.5 关键修复**:
- `force_kill_cst()` 检查 `taskkill` 退出码，失败时 `kill_all_cst_processes()` 兜底
- `CSTConnection.close()`: force kill 后二次验证 + 重试 2 次 + kill_all 兜底
- Phase 4 不再每轮杀 DE — DE 跨评估存活，避免每次走 Tier2 恢复
- `retry_handler.close_all()` 在三处退出路径均被调用

**终端日志**: 所有 `print()` 同步追加写入 `D:/Results/workflow_2_terminal.log`。

**检测到的 CST 内部 bug**: F2W 尾场求解器在 PBA 矩阵计算阶段触发竞态条件 (`Caught unhandled exception (check for race conditions)` → `Error in calculating solver matrix`)。Inter-pass Reset (新建 DE) 显著降低触发概率。

### Workflow 3: 单项目双通恢复优化

**入口**: `python run_workflow_3.py` → `config/workflow_3.yaml`
**项目**: X-band gun PickupDesign，双通求解: calibration pass(猜频 11.424 GHz) → measurement pass(修正 f_data=f0)

**评估流程** (每次迭代):

```
1. 打开 project → update_parameters (全量重建)
2. Calibration solve: f_data=11.424 GHz → 读 S11 → half_power_bandwidth → f0
3. S11 depth gate (|S11|_min > -1.0 dB → PHYSICS_INVALID)
4. Frequency gate (|f0 - 11.424| > 20 MHz → FREQUENCY_GATE)
5. [inter_pass_recovery] 双通之间优雅重置: 正常关闭 → 5s冷却 → 清结果 → 5s冷却 → 重连 + 全量重建
6. Measurement solve: f_data=f0 → 读 S11 + E-field + 场导出 + S21
7. 计算所有目标 penalty → 加权标量
8. [post_eval_recovery] 评估后优雅重置 (Tier2: 正常关闭 + 清结果 + 重连)
```

**恢复链路** (评估失败时):

```
首次失败 → Tier1 (max=0, skip)
  → Tier2 ×2: 优雅关闭 + 清结果 + 重连 + 全量重建 + 重试
  → Tier3 ×2: force kill + 清结果 + 重连 + 全量重建 + 重试
  → 全部失败 → EXHAUSTED
```

**特性**: FrequencyGate 早拒, S11 深度门控, 多凹陷诊断, adaptive bounds, staged search(两阶段), `--resume-from` JSONL 续算, cooldown_s=5s 冷却, cstd.exe 白名单保护

**CST 崩溃诊断**: 多个 DMP 文件经 WinDbg 分析确认为 `Qt6CoreCST_AMD64.dll` 的 use-after-free / null-pointer-write。快速进程创建/销毁触发 Qt6 对象生命周期 bug。5s cooling + 优雅退出 (非 force kill) 显著缓解。

---

## 4. Recovery 架构总结

### 4.1 三级 Retry (EvaluationRetryHandler)

| 层级 | 策略 | 连接 | 结果文件夹 | 适用场景 |
|------|------|------|-----------|---------|
| Tier1 | 同连接简单重试 | 不变 | 不变 | 瞬态 COM 超时 |
| Tier2 | 优雅关闭 + 清结果 + 重连 | 正常关闭→新建 | 删除 | SOLVER_FAILED, 结果缓存损坏 |
| Tier3 | force kill + 清结果 + 重连 | 强制杀→新建 | 删除 | COM_LOST, 进程僵死, 超时 |

Tier2 与 Tier3 的唯一区别是 CST 退出方式 (正常 vs 强制)。

### 4.2 主动恢复 (Proactive Recovery)

两种主动重置场景，均使用 **优雅退出** (非 force kill):

| 场景 | 触发时机 | 方法 |
|------|---------|------|
| Inter-pass (Workflow 3) | 校准完成后，测量开始前 | `_do_inter_pass_reset()` → 正常关闭+清结果+重连 |
| Post-eval (Workflow 1/3) | 每次完整评估后 | `retry_handler.force_reset()` → `_graceful_clean_and_reconnect()` |
| Post-sample (Tolerance) | 每个公差样本评估后 | `retry_handler.force_reset()` |

### 4.3 进程白名单

`CST_PROCESS_WHITELIST = {"cstd.exe"}` — `kill_all_cst_processes()` 的双通道扫描 (前缀+精确名) 均跳过白名单进程，保护 CST 许可证服务器。

---

## 5. CST 结果树路径 (Multipin 端口)

CST 2026 不同项目的端口配置不同:

| 逻辑含义 | Multipin (默认) | 简单端口 (Workflow 2) |
|---------|-----------------|---------------------|
| S11 (反射) | `1D Results\S-Parameters\S1(2),1(2)` | `1D Results\S-Parameters\S1,1` |
| S21 (传输) | `1D Results\S-Parameters\S2(1),1(2)` | `1D Results\S-Parameters\S2,1` |
| S31 (传输) | `1D Results\S-Parameters\S3(1),1(2)` | `1D Results\S-Parameters\S3,1` |
| E-field 0D | `Tables\0D Results\MaxE_Z0` | (未变) |
| 场导出 3D | `Export/3d/e-field (f=f_data) (1(2)).txt` | |

**Config 驱动**: Workflow 2 在 `config/default.yaml` 中通过 `workflow_2.result_paths` 和 antenna objective 的 `obj_params.tree_path` 显式声明简单端口路径。`ResultReader` 构造参数 (`s11_treepath/s21_treepath/s31_treepath`) 支持实例级覆盖，默认保留 multipin 格式。

`discover_field_files()` 使用通配符 (`*e-field*`, `*h-field*`) 自适应匹配，无需代码修改。

---

## 6. 1D 曲线数据库

### 存储格式

```
D:/Results/raw_curves/
  eval_0000.npz        # 单次评估的全部 1D 曲线 (S参数+尾场阻抗)
  index.jsonl          # JSONL 索引: {iter, params, npz_file, solver_ok, has_f2f, has_f2w, has_f2wo}
  missing_f2f_params.jsonl  # 缺 F2F 数据的参数组补算清单
```

### 录制/回放机制

| 组件 | 职责 |
|------|------|
| `RecordingResultReader` | 包装 `ResultReader`，拦截 1D/0D 读取并记录原始数组 |
| `VirtualResultReader` | 从 `.npz` 加载，实现同接口，使 `raw_value()` 无修改回放 |
| `save_curves_npz()` | 压缩 dump 到 `.npz` |
| `curves_to_warmup()` | 加载全部 `.npz`，用当前 objectives 重算 raw+penalty → SAO warmup |

### 辅助脚本

| 脚本 | 功能 |
|------|------|
| `examples/extract_curves_to_db.py` | 从三项目 `.cst` 提取全部参数扫描 run，按参数分组合并 |
| `examples/recompute_f2f.py` | 补算缺失 F2F 的组，合并入数据库 |
| `examples/verify_database.py` | 诊断 .npz 内容 + warmup 功能验证 |

---

## 7. 数据流

```
YAML Config → factory.py
                │
    ┌───────────┼───────────┐
    v           v           v
CSTConnection  ParameterSet  Objectives
    │           │           │
    v           v           v
CSTProject ←→ normalize  ←→ OptimizationMode
    │           │
    v           v
SolverRunner  denormalize
    │
    v
ResultReader → PhysicsQuantity → ObjectiveFunction.raw_value()
                                      │
                                      v
                              OptimizationMode.compute() → penalty vector
                                      │
                                      v
                              BaseOptimizer ← GP Surrogate ← prior_data
                                      │
                                      v
                              OptimizationResult
                                      │
                              checkpoint_callback → CheckpointManager.save()
```

---

## 8. Watchdog + 断点续算

```
watchdog.py (外部进程)
  │ 子进程崩溃 → cooldown → 重启 (max_restarts 次)
  │ 退出前: kill_all_cst_processes() 兜底清理 (cstd.exe 白名单保护)
  │
  └─ subprocess → run_workflow_X.py / tolerance_analysis.py
        │
        ├─ 启动: CheckpointManager.load() → prior_data → SAO.optimize(prior_data=...)
        ├─ 每次评估后: checkpoint_callback → ckpt.save()
        ├─ 正常结束: ckpt.clear()
        └─ 崩溃: ckpt 保留 → watchdog 重启 → load → resume
```

**运行方式**:
```powershell
# Workflow 1 SAO (直接/带 watchdog)
python run_workflow_1.py
python run_watchdog.py --max-restarts 5 --cooldown 30 -- run_workflow_1.py

# Workflow 2 (直接/带 watchdog/带 warmup)
python run_workflow_2.py
python run_workflow_2.py --warmup-from-db D:/Results/raw_curves/index.jsonl
python run_watchdog.py --max-restarts 5 --cooldown 30 -- run_workflow_2.py
python run_watchdog.py --max-restarts 5 --cooldown 30 -- run_workflow_2.py --warmup-from-db D:/Results/raw_curves/index.jsonl

# Workflow 3 (直接/带 watchdog/带 resume)
python run_workflow_3.py
python run_watchdog.py --max-restarts 5 --cooldown 30 -- run_workflow_3.py
python run_watchdog.py --max-restarts 5 --cooldown 30 -- run_workflow_3.py --resume-from D:/Results/workflow3/resume/evaluation_records.jsonl

# 公差分析 (直接/带 watchdog)
python examples/tolerance_analysis.py
python examples/run_tolerance_watchdog.py --max-restarts 5 --cooldown 30
```

---

## 9. 关键文件路径

| 文件 | 作用 |
|------|------|
| `config/default.yaml` | Workflow 1+2 + 公差分析配置 |
| `config/workflow_3.yaml` | Workflow 3 配置 |
| `run_workflow_1.py` | Workflow 1 入口 (单通 SAO + checkpoint + Ctrl+C) |
| `run_workflow_2.py` | Workflow 2 入口 (多项目条件链 + checkpoint + Ctrl+C) |
| `run_workflow_3.py` | Workflow 3 入口 (staged search + resume + checkpoint + Ctrl+C) |
| `run_watchdog.py` | Watchdog 通用启动器 |
| `examples/tolerance_analysis.py` | 公差分析主脚本 (LHS采样 + 双通 + retry + 优雅重置) |
| `examples/run_tolerance_watchdog.py` | 公差分析 Watchdog 启动器 |
| `examples/list_result_tree.py` | CST 结果树路径诊断工具 |
| `examples/extract_curves_to_db.py` | 从 CST 项目文件提取全部参数扫描 run → 1D 曲线 `.npz` 数据库 |
| `examples/recompute_f2f.py` | 补算缺失 F2F S 参数的参数组 |
| `examples/verify_database.py` | 1D 曲线数据库诊断 + warmup 验证 |
| `src/cst_optimization/database.py` | `RecordingResultReader`/`VirtualResultReader`/`curves_to_warmup()` |
| `src/cst_optimization/factory.py` | YAML → 对象图构建。v0.5: Workflow 2 集成 `AdaptiveConditionalGate` + 暴露 `retry_handler` |
| `src/cst_optimization/core/retry.py` | 三级 escalation 重试 + `extra_result_paths` + `force_reset()` + `close_all()` |
| `src/cst_optimization/core/cleanup.py` | `force_kill_cst()` (v0.5: 检查 taskkill 退出码) + `kill_all_cst_processes()` + `CST_PROCESS_WHITELIST` |
| `src/cst_optimization/core/connection.py` | `CSTConnection` — v0.5: `close()` 检查 kill 结果 + 二次验证 + kill_all 兜底 |
| `src/cst_optimization/core/results.py` | `ResultReader` + 可配置树路径常量 + `get_all_run_ids()` / `get_parameter_combination()` |
| `src/cst_optimization/core/orchestrator.py` | `DualProjectOrchestrator` — v0.5: 自适应门控 + pre-solve cleanup + Phase 4 简化为只关 project (不杀 DE) |
| `src/cst_optimization/optimization/conditional_gate.py` | **v0.5 新增** — `AdaptiveConditionalGate`: 三阶段 + TCP 滑动窗口 + 多输出 GP |
| `examples/diagnose_cst_stability.py` | **v0.5 新增** — CST 稳定性诊断: 确定性回放 + 系统画像 |
| `src/cst_optimization/workflows/recovery.py` | Workflow 3 评估器 (双通 + 频率门控 + inter-pass 重置) |
| `src/cst_optimization/physics/poynting.py` | `discover_field_files()` 通配符场导出定位 |
| `src/cst_optimization/checkpoint.py` | `CheckpointManager` (三态追踪 + pickle 持久化) |
| `src/cst_optimization/watchdog.py` | `WatchdogRunner` (子进程监控 + 自动重启) |
| `_docs/FRAMEWORK.md` | 本文档 |
