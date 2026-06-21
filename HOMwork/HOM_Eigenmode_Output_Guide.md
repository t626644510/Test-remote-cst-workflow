# HOM 本征模自动计算输出说明

## 1. 分析目标

自动优化/电磁仿真框架读取：

```text
outputs/eigenmode_frequency_targets.csv
```

以测量识别出的可疑 HOM 频率作为搜索目标，计算模式的频率、场型、`R/Q`、损耗和各类 Q 值。随后将仿真的 `R/Q` 与测量得到的加载 Q 结合，估算实际测量工况下的有效阻抗：

```text
R_parallel = (R_parallel / Q)_simulation * QL_measurement
R_transverse = (R_transverse / Q)_simulation * QL_measurement
```

需要明确区分：

- 仿真主要提供模式的 `R/Q` 和物理分类。
- 测量主要提供实际端口和吸收结构加载下的 `QL`。
- S21 峰值幅度不能直接等同于束流阻抗。

## 2. `hom_target_clusters.csv`

### 作用

将不同测量工况中频率相近、可能属于同一物理模式的峰聚合，减少重复仿真，同时保留所有原始测量来源。

### 主要字段

#### `target_cluster_id`

频率目标组的唯一编号，例如：

```text
TC_0001
```

#### `target_freq_ghz`

该组的代表频率。建议使用组内测量频率的中位数，避免单个异常峰拉偏中心。

#### `freq_min_ghz` / `freq_max_ghz`

该组所有测量峰的最低和最高频率，用来反映工况间的频率漂移。

#### `search_min_ghz` / `search_max_ghz`

本征模仿真的搜索范围。建议：

```text
half_span = max(
    suggested_span_mhz,
    10 MHz,
    0.5% * target_frequency
)
```

搜索区间为：

```text
target_frequency +/- half_span
```

#### `source_conditions`

检测到该频率峰的全部测量工况。一个峰被多个独立工况重复检测，通常会提高其真实性。

#### `source_row_ids`

原始 `eigenmode_frequency_targets.csv` 的行号或稳定记录 ID，用于结果追溯。

#### `measurement_q_min` / `measurement_q_median` / `measurement_q_max`

同一频率组在不同工况下的测量 Q 范围。不要在本阶段用平均值覆盖不同工况的 Q。

#### `propagation_background`

表示目标是否来自传播背景明显的频段。只要任一来源被标记为传播背景，就应保留该标志。

### 聚类方法

两个目标可以先归入同一候选组，当：

```text
frequency_difference <= max(
    target_1.suggested_span_mhz,
    target_2.suggested_span_mhz,
    0.5% * center_frequency
)
```

如果仿真在同一个搜索窗口内找到多个模式，必须重新拆分模式映射，不能强制认为它们是同一个模式。

## 3. `hom_eigenmode_results.csv`

### 作用

这是本征模仿真的主结果表。每一行代表一个独立仿真模式，而不是一个测量峰。

## 3.1 频率和匹配字段

#### `mode_id`

仿真模式唯一编号。不能只使用频率作为 ID，因为可能存在简并模或频率非常接近的不同模式。

#### `target_cluster_id`

该模式对应的测量频率目标组。

#### `target_freq_ghz`

测量目标组的中心频率。

#### `freq_sim_ghz`

本征模求解器给出的模式频率。

#### `delta_freq_mhz`

测量和仿真的频率偏差：

```text
delta_freq_mhz =
    (freq_sim_hz - target_freq_hz) / 1e6
```

#### `match_status`

建议使用以下状态：

- `matched`：存在唯一且可信的仿真模式。
- `ambiguous`：窗口内有多个可能模式，无法唯一对应。
- `unmatched`：没有找到可信模式。
- `propagating`：更像开放束管传播态，不适合作为普通离散本征模处理。

#### `match_confidence`

用于排序和人工复核的工程评分，不是物理量。可按以下权重构建：

```text
60% 频率接近程度
20% 多工况重复检测情况
20% 场型和端口耦合是否符合测量
```

评分公式和阈值必须写入 `hom_solver_manifest.json`。

## 3.2 模式分类字段

#### `mode_family`

建议分类：

- `monopole`
- `dipole`
- `quadrupole`
- `higher_multipole`

可在束流轴附近对纵向场进行方位傅里叶分解：

```text
Ez(r, phi) = sum(Em(r) * exp(i * m * phi))
```

其中：

- `m = 0`：monopole
- `m = 1`：dipole
- `m = 2`：quadrupole

#### `mode_localization`

建议分类：

- `trapped`：能量高度局限在腔体内，外泄功率很小。
- `cavity_localized`：能量主要位于腔体，但存在一定端口或束管外泄。
- `beam_pipe_propagating`：能量和功率主要沿束管传播。
- `HOM_waveguide`：场或损耗主要位于 HOM 波导或吸收结构。

可计算区域储能比例：

```text
cavity_energy_fraction = U_cavity / U_total
beam_pipe_energy_fraction = U_beam_pipe / U_total
HOM_waveguide_energy_fraction = U_HOM_waveguide / U_total
```

同时结合端口辐射功率判断，不能只看单张场图。

#### `polarization`

用于 dipole 模，描述主要横向踢束方向，例如：

```text
x
y
rotated_32deg
```

可根据横向 kick vector、场偶极矩或横向电压的方向确定。

#### `degenerate_group`

标识一组频率近似相同、场型正交的简并模式。判断需要同时检查：

- 频率接近程度
- 场分布正交性
- 极化方向
- 几何对称性

#### `propagation_background`

首先继承测量目标中的标记，再根据仿真场和端口功率确认。如果模式主要沿束管传播，应保留该标志。

## 3.3 纵向和横向 `R/Q`

#### `longitudinal_R_over_Q_ohm`

对超相对论束流，先计算带 transit-time 相位因子的有效纵向电压：

```text
V_parallel =
    integral Ez(0, 0, z) * exp(i * omega * z / c) dz
```

常见定义：

```text
R_parallel / Q =
    |V_parallel|^2 / (omega * U)
```

不同求解器可能使用额外的 2 倍因子。必须在 manifest 中记录求解器采用的公式。

#### `transverse_R_over_Q`

横向模式可通过横向 kick 或 Panofsky-Wenzel 关系计算：

```text
V_transverse =
    -(i * c / omega) * gradient_transverse(V_parallel)
```

横向 `R/Q` 的定义在不同软件中可能输出：

- `ohm`
- `ohm/m`
- `ohm/m^2`

因此必须同时输出：

- `transverse_R_over_Q`
- `transverse_R_over_Q_unit`
- `reference_offset_mm`
- 使用的数学定义

没有单位和参考偏移量的横向 `R/Q` 不可直接比较。

## 3.4 储能和损耗

#### `stored_energy_j`

模式总储能。常见相量定义：

```text
U =
    1/4 * integral(
        epsilon * |E|^2
        + mu * |H|^2
    ) dV
```

需要记录求解器的场归一化方式。

#### `wall_loss_w`

金属表面损耗：

```text
P_wall =
    1/2 * integral Rs * |H_t|^2 dS
```

其中 `Rs` 为表面电阻，`H_t` 为切向磁场。

#### `absorber_loss_w`

铁氧体、陶瓷或其他有损材料中的体损耗。通常由材料复介电常数或复磁导率的虚部进行积分。

#### `radiated_power_w`

通过束管端口、HOM 波导端口或开放边界流出的平均 Poynting 功率。

该值对区分局域 HOM 和传播模非常重要。

## 3.5 各类 Q 值

Q 的统一定义为：

```text
Q = omega * U / P_loss
```

#### `Q_wall`

```text
Q_wall = omega * U / P_wall
```

#### `Q_material`

```text
Q_material = omega * U / P_absorber
```

#### `Q_external`

```text
Q_external = omega * U / P_radiated
```

#### `Q_loaded_simulated`

综合所有损耗：

```text
1 / Q_loaded =
    1 / Q_wall
    + 1 / Q_material
    + 1 / Q_external
```

若还存在其他独立损耗，应继续加入倒数项。

#### `complex_eigenfrequency`

开放本征模求解器可能输出复频率：

```text
f_complex = f_real + i * f_imag
```

相应 Q 常写为：

```text
Q = f_real / (2 * abs(f_imag))
```

虚部正负号取决于求解器的时间相量约定。

#### `Q_measurement`

来自测量峰。当前 `eigenmode_frequency_targets.csv` 中的 Q 来源于 rolling-baseline residual 曲线的 3 dB 带宽：

```text
Q_measurement = f_peak / bandwidth_3dB
```

该 Q 可用于第一版计算，但更可靠的方法是对原始复数 S 参数进行“谐振极点 + 平滑复数背景”拟合。

## 3.6 有效阻抗

#### `R_parallel_from_measured_Q_ohm`

```text
R_parallel =
    longitudinal_R_over_Q_ohm
    * Q_measurement
```

#### `R_transverse_from_measured_Q`

```text
R_transverse =
    transverse_R_over_Q
    * Q_measurement
```

结果单位取决于横向 `R/Q` 的定义。

同一个仿真模式在不同测量工况下可能具有不同 `QL`，因此应分别计算有效阻抗，不能提前平均。

## 3.7 求解质量和可追溯性

#### `solver_status`

建议状态：

- `converged`
- `not_converged`
- `mode_lost`
- `boundary_sensitive`
- `propagating_no_discrete_mode`

#### `mesh_cells`

最终网格单元数量，用于判断计算规模和复现求解设置。

#### `frequency_error`

最后两次网格迭代的相对频率误差：

```text
frequency_error =
    abs(f_n - f_previous) / f_n
```

#### `RQ_error`

最后两次网格迭代的 `R/Q` 相对误差：

```text
RQ_error =
    abs(RQ_n - RQ_previous) / RQ_n
```

#### `convergence_error`

可使用：

```text
convergence_error =
    max(frequency_error, RQ_error)
```

但建议同时保留两个原始误差字段。

#### `field_map_path`

求解器导出的三维复数 E/H 场文件路径，用于后处理和模式比较。

#### `field_image_path`

人工检查用的场图路径，例如轴向 `Ez`、束管截面场和损耗分布。

## 4. `hom_mode_condition_results.csv`

### 作用

把一个仿真模式与各个测量工况分别组合。主模式表中的 `R/Q` 只保存一次，本表记录不同工况下的 `QL` 和有效阻抗。

每一行对应：

```text
一个 mode_id + 一个 condition
```

### 主要字段

- `mode_id`
- `condition`
- `measurement_freq_ghz`
- `Q_measurement`
- `Q_source`
- `longitudinal_R_over_Q_ohm`
- `R_parallel_from_measured_Q_ohm`
- `transverse_R_over_Q`
- `R_transverse_from_measured_Q`
- `measurement_match_quality`

### `Q_source`

建议明确标记 Q 的来源：

- `raw_3db`
- `baseline_residual_3db`
- `reference_corrected_3db`
- `complex_pole_fit`

推荐优先级：

```text
complex_pole_fit
> reference-corrected or baseline cross-check
> raw 3 dB estimate
```

## 5. `hom_unmatched_targets.csv`

### 作用

记录没有找到可信仿真模式的测量峰，防止目标被静默丢弃。

### 建议原因字段

- `no_mode_in_window`
- `multiple_ambiguous_modes`
- `solver_not_converged`
- `likely_noise_peak`
- `likely_port_or_fixture_resonance`
- `beam_pipe_continuum`
- `reference_correction_sensitive`

这张表可用于决定是否扩大搜索窗口、修改边界条件、改用 driven-mode/wakefield，或者回查测量数据。

## 6. `hom_solver_manifest.json`

### 作用

记录结果的生成条件，是复现、审计和比较不同优化轮次的依据。

至少应包含：

- 几何模型路径及文件哈希
- 参数名称和实际值
- 腔体、束管和端口尺寸
- 求解器名称及版本
- 材料、电导率、铁氧体参数
- 边界条件
- waveguide port 模式数量
- 开放边界或 PML 设置
- 网格策略和收敛阈值
- `R/Q` 公式及单位约定
- 横向 `R/Q` 的参考偏移
- 场归一化方式
- 输入 CSV 的哈希
- 代码版本或 Git commit
- 仿真任务 ID 和运行时间

如果缺少 manifest，不同计算批次的 `R/Q` 可能因定义、归一化或边界差异而无法比较。

## 7. `fields/`

### 作用

保存模式场证据，用于确认数值结果对应的物理模式。

建议目录结构：

```text
fields/<mode_id>/E_complex.*
fields/<mode_id>/H_complex.*
fields/<mode_id>/axis_Ez.csv
fields/<mode_id>/beam_pipe_cross_section.png
fields/<mode_id>/cavity_cross_section.png
fields/<mode_id>/loss_distribution.png
```

这些文件主要用于判断：

- 模式是否局域在腔体；
- 模式是否沿束管传播；
- 模式属于 monopole、dipole 还是更高多极；
- 是否存在简并极化；
- 损耗是否进入 HOM 吸收材料；
- 高 `R/Q` 是否来自错误的封闭束管驻波。

## 8. 束管截止频率以上的特殊处理

束管半径约 50 mm 时，参考截止频率约为：

```text
TE11: 约 1.76 GHz
TM01: 约 2.30 GHz
TE21: 约 2.91 GHz
```

截止频率以上，封闭 eigenmode solver 可能把传播连续谱离散成随束管长度变化的驻波模式。判断方法包括：

1. 改变束管长度后频率明显漂移。
2. 场能量主要位于束管。
3. 开放端口功率较大。
4. 模式数量随计算域长度明显增加。
5. 使用开放边界后模式变成复频率或不再作为离散模式出现。

这些模式应优先使用：

- 开放边界或 PML 本征模；
- waveguide port driven-mode；
- wakefield 阻抗计算；
- complex eigenfrequency。

不能仅依赖普通封闭本征模的 Q 和 `R/Q` 判断危险程度。

## 9. 最终数据流

推荐完整流程：

```text
测量复数 S21
    -> 背景处理和候选峰识别
    -> 复数谐振拟合得到 QL
    -> eigenmode_frequency_targets.csv
    -> 频率目标聚类
    -> 本征模/开放模/驱动模计算
    -> 模式分类和 R/Q
    -> 与每个工况的 QL 分别组合
    -> 计算有效纵向/横向阻抗
    -> 输出危险 HOM 排序及场型证据
```

其中最重要的原则是：

```text
R/Q 决定束流与模式的耦合强度；
QL 决定实际加载条件下模式能量衰减速度；
二者结合后才能得到有意义的有效阻抗。
```
