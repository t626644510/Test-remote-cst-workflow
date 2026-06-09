# Tolerance Sweep Analysis Report

**Campaign**: `wf3_tolerance_6x60`  |  **Parameter**: `tolerance_abs`  |  **Levels**: 3, 5, 10, 15, 20, 30 um

## 1. Data Overview

| Level | Source | Accepted | Failed | Success Rate |
|-------|--------|----------|--------|-------------|
| 3 um | 3um | 60 | 0 | 100.0% |
| 5 um | 5um | 60 | 0 | 100.0% |
| 10 um | 10um | 60 | 0 | 100.0% |
| 15 um | 15um | 52 | 8 | 86.7% |
| 20 um | 20um | 44 | 16 | 73.3% |
| 30 um | 30um | 25 | 35 | 41.7% |

## 2. Coefficient of Variation (CV%)

| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic | Knee |
|--------|-----|-----|------|------|------|------|-----------|------|
| resonant_freq | 71.8 | 67.3 | 64.8 | 57.2 | 55.7 | 59.8 | non_monotonic | 10um |
| coupling_beta | 7.1 | 11.2 | 21.9 | 33.2 | 41.7 | 43.3 | increasing | 10um |
| q0 | 0.5 | 0.7 | 1.3 | 2.0 | 5.2 | 22.9 | increasing | 20um |
| peak_e_field | 3.4 | 5.3 | 10.1 | 14.7 | 18.9 | 24.1 | increasing | 20um |
| field_flatness | 60.4 | 58.9 | 59.9 | 55.1 | 51.6 | 41.0 | non_monotonic | 20um |
| max_modified_poynting | 0.3 | 0.4 | 8.0 | 21.8 | 38.8 | 62.3 | increasing | 20um |
| pulsed_heating | 2.7 | 0.4 | 7.4 | 38.6 | 35.9 | 59.1 | non_monotonic | 10um |

## 3. Mean Values by Tolerance Level

| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic |
|--------|-----|-----|------|------|------|------|-----------|
| resonant_freq | 1.046 | 1.679 | 3.319 | 4.122 | 4.722 | 4.626 | non_monotonic |
| coupling_beta | 1.912 | 1.91 | 1.908 | 1.864 | 1.866 | 2.006 | non_monotonic |
| q0 | 1.854e+04 | 1.854e+04 | 1.854e+04 | 1.853e+04 | 1.893e+04 | 2.204e+04 | non_monotonic |
| peak_e_field | 9.104e+04 | 9.097e+04 | 9.076e+04 | 9.134e+04 | 9.14e+04 | 9.153e+04 | non_monotonic |
| field_flatness | 0.04985 | 0.07696 | 0.141 | 0.2075 | 0.2686 | 0.389 | increasing |
| max_modified_poynting | 4.087e+12 | 4.09e+12 | 4.202e+12 | 4.467e+12 | 4.87e+12 | 5.685e+12 | increasing |
| pulsed_heating | 24.86 | 24.75 | 25.37 | 28.03 | 28.91 | 33.6 | non_monotonic |

## 4. Parameter Sensitivity (Spearman |score| �� 0.2)

### 3 um

**resonant_freq** (n=60):
  - `R_cell_2`: -0.420 (rank=1)
  - `R_cell_3`: -0.381 (rank=2)
  - `R_cell_1`: -0.353 (rank=3)
  - `length1`: -0.283 (rank=4)
  - `R_bend_cell1`: -0.273 (rank=5)

**coupling_beta** (n=60):
  - `R_cell_3`: -0.816 (rank=1)
  - `R_cell_2`: +0.387 (rank=2)
  - `R_between_cell_1_2`: -0.289 (rank=3)
  - `R_bend_cell3_left`: +0.246 (rank=4)
  - `cell_2_vertical_right`: +0.203 (rank=5)

**q0** (n=60):
  - `R_cell_3`: -0.809 (rank=1)
  - `R_cell_2`: +0.345 (rank=2)
  - `R_between_cell_1_2`: -0.313 (rank=3)
  - `R_bend_cell3_left`: +0.264 (rank=4)

**peak_e_field** (n=60):
  - `R_cell_3`: +0.803 (rank=1)
  - `R_between_cell_1_2`: +0.329 (rank=2)
  - `R_cell_2`: -0.265 (rank=3)
  - `R_bend_cell3_left`: -0.250 (rank=4)

**field_flatness** (n=60):
  - `PickUpDeep`: +0.261 (rank=1)
  - `R_between_cell_1_2`: +0.206 (rank=2)

**max_modified_poynting** (n=60):
  - `R_cell_1`: +0.374 (rank=1)
  - `e_x`: +0.318 (rank=2)
  - `offset1`: -0.226 (rank=3)
  - `R_between_cell_1_2`: +0.210 (rank=4)
  - `cell_3_vertical_right`: -0.210 (rank=5)

**pulsed_heating** (n=60):
  - `R_cell_1`: +0.362 (rank=1)
  - `e_x`: +0.236 (rank=2)


### 5 um

**resonant_freq** (n=60):
  - `R_cell_3`: -0.373 (rank=1)
  - `R_cell_1`: -0.312 (rank=2)
  - `length1`: -0.265 (rank=3)
  - `R_bend_cell1`: -0.248 (rank=4)
  - `cell_1_vertical_length`: +0.215 (rank=5)

**coupling_beta** (n=60):
  - `R_cell_3`: -0.830 (rank=1)
  - `R_cell_2`: +0.398 (rank=2)
  - `R_between_cell_1_2`: -0.302 (rank=3)
  - `R_bend_cell3_left`: +0.233 (rank=4)

**q0** (n=60):
  - `R_cell_3`: -0.837 (rank=1)
  - `R_cell_2`: +0.350 (rank=2)
  - `R_between_cell_1_2`: -0.315 (rank=3)
  - `R_bend_cell3_left`: +0.260 (rank=4)

**peak_e_field** (n=60):
  - `R_cell_3`: +0.810 (rank=1)
  - `R_between_cell_1_2`: +0.349 (rank=2)
  - `R_cell_2`: -0.283 (rank=3)
  - `R_bend_cell3_left`: -0.230 (rank=4)

**field_flatness** (n=60):
  - `PickUpDeep`: +0.272 (rank=1)
  - `a`: +0.254 (rank=2)
  - `cell_1_vertical_length`: -0.221 (rank=3)

**max_modified_poynting** (n=60):
  - `R_cell_1`: +0.510 (rank=1)
  - `R_cell_2`: -0.232 (rank=2)
  - `R_cell_3`: -0.211 (rank=3)

**pulsed_heating** (n=60):
  - `R_cell_1`: +0.478 (rank=1)
  - `R_cell_2`: -0.319 (rank=2)
  - `cell_3_vertical_left`: -0.277 (rank=3)
  - `R_cell_3`: -0.237 (rank=4)
  - `R_bend_cell1`: -0.201 (rank=5)


### 10 um

**resonant_freq** (n=60):
  - `R_cell_3`: -0.335 (rank=1)
  - `length1`: -0.256 (rank=2)
  - `R_cell_1`: -0.234 (rank=3)
  - `R_bend_cell1`: -0.224 (rank=4)
  - `bend1`: +0.211 (rank=5)

**coupling_beta** (n=60):
  - `R_cell_3`: -0.843 (rank=1)
  - `R_cell_2`: +0.404 (rank=2)
  - `R_between_cell_1_2`: -0.295 (rank=3)
  - `R_bend_cell3_left`: +0.235 (rank=4)

**q0** (n=60):
  - `R_cell_3`: -0.843 (rank=1)
  - `R_cell_2`: +0.359 (rank=2)
  - `R_between_cell_1_2`: -0.316 (rank=3)
  - `R_bend_cell3_left`: +0.239 (rank=4)

**peak_e_field** (n=60):
  - `R_cell_3`: +0.815 (rank=1)
  - `R_between_cell_1_2`: +0.354 (rank=2)
  - `R_cell_2`: -0.289 (rank=3)
  - `R_bend_cell3_left`: -0.229 (rank=4)

**field_flatness** (n=60):
  - `a`: +0.283 (rank=1)
  - `PickUpDeep`: +0.234 (rank=2)
  - `R_between_cell_1_2`: +0.229 (rank=3)
  - `cell_1_vertical_length`: -0.222 (rank=4)

**max_modified_poynting** (n=60):
  - `R_cell_1`: +0.561 (rank=1)
  - `R_cell_3`: -0.344 (rank=2)
  - `cell_3_vertical_left`: -0.319 (rank=3)
  - `R_bend_cell1`: -0.248 (rank=4)
  - `PickUpDeep`: +0.234 (rank=5)

**pulsed_heating** (n=60):
  - `R_cell_1`: +0.529 (rank=1)
  - `R_bend_cell1`: -0.334 (rank=2)
  - `R_cell_3`: -0.295 (rank=3)
  - `cell_3_vertical_left`: -0.274 (rank=4)
  - `R_bend_cell2_left`: -0.265 (rank=5)


### 15 um

**resonant_freq** (n=52):
  - `length1`: -0.280 (rank=1)
  - `bend1`: +0.229 (rank=2)
  - `cell_2_vertical_left`: +0.221 (rank=3)
  - `cell_1_vertical_length`: +0.218 (rank=4)
  - `R_bend_cell3_left`: +0.206 (rank=5)

**coupling_beta** (n=52):
  - `R_cell_3`: -0.846 (rank=1)
  - `R_cell_2`: +0.545 (rank=2)
  - `R_between_cell_1_2`: -0.312 (rank=3)
  - `R_bend_cell3_left`: +0.222 (rank=4)

**q0** (n=52):
  - `R_cell_3`: -0.806 (rank=1)
  - `R_cell_2`: +0.443 (rank=2)
  - `R_between_cell_1_2`: -0.287 (rank=3)
  - `cell_2_vertical_right`: +0.213 (rank=4)
  - `cell_3_vertical_left`: -0.210 (rank=5)

**peak_e_field** (n=52):
  - `R_cell_3`: +0.815 (rank=1)
  - `R_cell_2`: -0.393 (rank=2)
  - `R_between_cell_1_2`: +0.375 (rank=3)
  - `R_cell_1`: -0.352 (rank=4)
  - `R_bend_cell3_left`: -0.212 (rank=5)

**field_flatness** (n=52):
  - `a`: +0.317 (rank=1)
  - `cell_1_vertical_length`: -0.247 (rank=2)
  - `R_between_cell_1_2`: +0.226 (rank=3)
  - `cell_2_vertical_left`: -0.215 (rank=4)
  - `offset3`: +0.209 (rank=5)

**max_modified_poynting** (n=52):
  - `R_cell_1`: +0.656 (rank=1)
  - `R_cell_3`: -0.424 (rank=2)
  - `cell_3_vertical_right`: -0.227 (rank=3)
  - `PickUpDeep`: +0.221 (rank=4)
  - `cell_3_vertical_left`: -0.218 (rank=5)

**pulsed_heating** (n=52):
  - `R_cell_1`: +0.656 (rank=1)
  - `R_cell_3`: -0.372 (rank=2)
  - `PickUpDeep`: +0.304 (rank=3)
  - `cell_3_vertical_left`: -0.260 (rank=4)


### 20 um

**resonant_freq** (n=44):
  - `length1`: -0.351 (rank=1)
  - `R_bend_cell3_left`: +0.296 (rank=2)
  - `cell_2_vertical_right`: -0.265 (rank=3)
  - `cell_2_vertical_left`: +0.264 (rank=4)
  - `cell_1_vertical_length`: +0.258 (rank=5)

**coupling_beta** (n=44):
  - `R_cell_3`: -0.825 (rank=1)
  - `R_cell_2`: +0.589 (rank=2)
  - `R_between_cell_1_2`: -0.410 (rank=3)
  - `offset1`: +0.220 (rank=4)
  - `R_bend_cell3_left`: +0.211 (rank=5)

**q0** (n=44):
  - `cell_2_vertical_left`: -0.292 (rank=1)
  - `R_cell_3`: -0.263 (rank=2)

**peak_e_field** (n=44):
  - `R_cell_3`: +0.835 (rank=1)
  - `R_between_cell_1_2`: +0.463 (rank=2)
  - `R_cell_2`: -0.411 (rank=3)
  - `R_cell_1`: -0.370 (rank=4)
  - `offset1`: -0.250 (rank=5)

**field_flatness** (n=44):
  - `a`: +0.364 (rank=1)
  - `cell_1_vertical_length`: -0.286 (rank=2)
  - `R_bend_cell3_left`: -0.211 (rank=3)

**max_modified_poynting** (n=44):
  - `R_cell_1`: +0.596 (rank=1)
  - `R_cell_3`: -0.521 (rank=2)
  - `R_between_cell_1_2`: -0.353 (rank=3)
  - `cell_3_vertical_right`: -0.238 (rank=4)
  - `R_between_cell_2_3`: +0.230 (rank=5)

**pulsed_heating** (n=44):
  - `R_cell_1`: +0.604 (rank=1)
  - `R_cell_3`: -0.521 (rank=2)
  - `R_between_cell_1_2`: -0.340 (rank=3)
  - `cell_3_vertical_right`: -0.238 (rank=4)
  - `R_between_cell_2_3`: +0.234 (rank=5)


### 30 um

**resonant_freq** (n=25):
  - `length1`: -0.377 (rank=1)
  - `cell_3_vertical_left`: +0.296 (rank=2)
  - `cell_2_vertical_left`: +0.267 (rank=3)
  - `PickUpDeep`: +0.254 (rank=4)
  - `R_cell_2`: -0.252 (rank=5)

**coupling_beta** (n=25):
  - `R_cell_3`: -0.598 (rank=1)
  - `R_cell_2`: +0.522 (rank=2)
  - `R_between_cell_2_3`: -0.304 (rank=3)
  - `R_cell_1`: +0.293 (rank=4)
  - `cell_1_vertical_length`: -0.278 (rank=5)

**q0** (n=25):
  - `cell_1_vertical_length`: -0.503 (rank=1)
  - `R_cell_3`: +0.447 (rank=2)
  - `R_between_cell_1_2`: +0.333 (rank=3)
  - `R_bend_cell3_left`: -0.275 (rank=4)
  - `R_cell_2`: -0.275 (rank=5)

**peak_e_field** (n=25):
  - `R_cell_3`: +0.792 (rank=1)
  - `R_cell_1`: -0.615 (rank=2)
  - `bend1`: -0.513 (rank=3)
  - `R_between_cell_1_2`: +0.508 (rank=4)
  - `R_cell_2`: -0.436 (rank=5)

**field_flatness** (n=25):
  - `cell_1_vertical_length`: -0.466 (rank=1)
  - `a`: +0.422 (rank=2)
  - `R_bend_cell2_left`: -0.345 (rank=3)
  - `cell_2_vertical_left`: -0.316 (rank=4)
  - `R_cell_3`: +0.297 (rank=5)

**max_modified_poynting** (n=25):
  - `R_cell_1`: +0.748 (rank=1)
  - `R_cell_3`: -0.568 (rank=2)
  - `R_between_cell_1_2`: -0.534 (rank=3)
  - `bend1`: +0.442 (rank=4)
  - `R_between_cell_3_cutoff`: -0.375 (rank=5)

**pulsed_heating** (n=25):
  - `R_cell_1`: +0.748 (rank=1)
  - `R_cell_3`: -0.542 (rank=2)
  - `R_between_cell_1_2`: -0.517 (rank=3)
  - `bend1`: +0.404 (rank=4)
  - `R_between_cell_3_cutoff`: -0.395 (rank=5)


## 5. Cross-Level Parameter Rank Stability

For each core metric, which parameters consistently dominate
across all 6 tolerance levels?

| Metric | Parameter | |��| mean | Rank=1 % | Top-3 % | Mean Rank | Verdict |
|--------|-----------|:-------:|:--------:|:-------:|:---------:|---------|
| resonant_freq | `length1` | 0.30 | 50% (6 lvls) | 83% | 2.0 | Strong |
| resonant_freq | `R_cell_3` | 0.23 | 33% (6 lvls) | 50% | 8.7 | Consistent top-3 |
| resonant_freq | `R_cell_2` | 0.20 | 17% (6 lvls) | 17% | 7.8 | Weak / noise-level |
| resonant_freq | `offset1` | 0.11 | 0% (6 lvls) | 0% | 13.7 | Weak / noise-level |
| resonant_freq | `offset2` | 0.10 | 0% (6 lvls) | 0% | 14.3 | Weak / noise-level |

| coupling_beta | `R_cell_3` | 0.79 | 100% (6 lvls) | 100% | 1.0 | **Dominant** |
| coupling_beta | `offset1` | 0.07 | 0% (6 lvls) | 0% | 15.7 | Weak / noise-level |
| coupling_beta | `offset2` | 0.07 | 0% (6 lvls) | 0% | 15.8 | Weak / noise-level |
| coupling_beta | `offset3` | 0.06 | 0% (6 lvls) | 0% | 16.0 | Weak / noise-level |
| coupling_beta | `a` | 0.03 | 0% (6 lvls) | 0% | 18.0 | Weak / noise-level |

| field_flatness | `a` | 0.30 | 50% (6 lvls) | 83% | 1.8 | Strong |
| field_flatness | `PickUpDeep` | 0.19 | 33% (6 lvls) | 50% | 5.3 | Consistent top-3 |
| field_flatness | `cell_1_vertical_length` | 0.27 | 17% (6 lvls) | 83% | 2.5 | Consistent top-3 |
| field_flatness | `offset1` | 0.04 | 0% (6 lvls) | 0% | 17.0 | Weak / noise-level |
| field_flatness | `offset2` | 0.13 | 0% (6 lvls) | 0% | 8.5 | Weak / noise-level |

*Verdict: Dominant = rank-1 in ��80% levels; Strong = ��50%; Consistent top-3 = in top-3 ��50%; Moderate = mean |��| ��0.3.*

## 6. Tolerance Recommendation

**Overall recommended max tolerance**: **10.0 um**

**Limiting metrics**: pulsed_heating

| Metric | Recommended Max | First Warning | First Failure | Knee Candidate |
|--------|----------------|---------------|---------------|----------------|
| resonant_freq | N/A um | N/A um | 3.0 um | 10.0 um |
| coupling_beta | N/A um | N/A um | 15.0 um | 30.0 um |
| q0 | 20.0 um | N/A um | 30.0 um | 30.0 um |
| field_flatness | N/A um | N/A um | 3.0 um | 30.0 um |
| max_modified_poynting | 15.0 um | N/A um | 20.0 um | 30.0 um |
| pulsed_heating | 10.0 um | N/A um | 15.0 um | 30.0 um |
| peak_e_field | N/A um | N/A um | N/A um | N/A um |

## 7. Per-Parameter Tolerance Budget

For each parameter, actual perturbation values are binned,
and metric averages computed per bin. This shows how metrics
degrade as THIS parameter deviates (with others also varying).

### `offset1` (nominal=0.0000 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.22 (93%) | 4.1e+12 (2%) | 0.094 (103%) | 140 |
| 3-5 | 2.82 (79%) | 4.29e+12 (22%) | 0.139 (88%) | 46 |
| 5-10 | 3.96 (58%) | 4.6e+12 (41%) | 0.198 (60%) | 58 |
| 10-15 | 4.01 (67%) | 4.9e+12 (40%) | 0.275 (48%) | 33 |
| 15-20 | 4.48 (68%) | 5.41e+12 (46%) | 0.304 (48%) | 13 |
| 20-30 | 3.57 (83%) | 5.6e+12 (53%) | 0.396 (35%) | 11 |

### `offset2` (nominal=0.0000 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.73 (90%) | 4.13e+12 (6%) | 0.0969 (89%) | 151 |
| 3-5 | 2.44 (87%) | 4.54e+12 (33%) | 0.147 (85%) | 40 |
| 5-10 | 3.15 (67%) | 4.54e+12 (28%) | 0.211 (67%) | 49 |
| 10-15 | 3.55 (70%) | 4.55e+12 (28%) | 0.252 (54%) | 31 |
| 15-20 | 4.11 (60%) | 5.59e+12 (68%) | 0.29 (58%) | 18 |
| 20-30 | 4.42 (62%) | 5.1e+12 (47%) | 0.376 (40%) | 12 |

### `offset3` (nominal=0.0000 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.05 (94%) | 4.15e+12 (10%) | 0.0892 (96%) | 125 |
| 3-5 | 2.55 (78%) | 4.31e+12 (29%) | 0.12 (86%) | 48 |
| 5-10 | 3.76 (64%) | 4.31e+12 (14%) | 0.198 (62%) | 61 |
| 10-15 | 4.44 (60%) | 4.54e+12 (27%) | 0.254 (55%) | 40 |
| 15-20 | 4.23 (62%) | 5.61e+12 (46%) | 0.279 (52%) | 15 |
| 20-30 | 4.37 (67%) | 6.4e+12 (71%) | 0.421 (36%) | 12 |

### `a` (nominal=10.6155 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.07 (97%) | 4.14e+12 (6%) | 0.104 (93%) | 141 |
| 3-5 | 2.8 (76%) | 4.39e+12 (21%) | 0.142 (93%) | 44 |
| 5-10 | 3.82 (63%) | 4.88e+12 (51%) | 0.197 (73%) | 60 |
| 10-15 | 4.33 (52%) | 4.84e+12 (40%) | 0.256 (56%) | 33 |
| 15-20 | 4.95 (58%) | 4.29e+12 (9%) | 0.261 (55%) | 14 |
| 20-30 | 4.93 (58%) | 4.64e+12 (30%) | 0.396 (31%) | 9 |

### `length1` (nominal=1.0290 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.27 (90%) | 4.3e+12 (31%) | 0.101 (107%) | 125 |
| 3-5 | 2.28 (83%) | 4.13e+12 (4%) | 0.103 (66%) | 44 |
| 5-10 | 3.78 (66%) | 4.35e+12 (19%) | 0.181 (63%) | 64 |
| 10-15 | 4.09 (63%) | 4.81e+12 (40%) | 0.245 (58%) | 39 |
| 15-20 | 4.07 (70%) | 4.76e+12 (36%) | 0.281 (54%) | 17 |
| 20-30 | 3.8 (75%) | 5.41e+12 (53%) | 0.442 (24%) | 12 |

### `PickUpDeep` (nominal=0.2620 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.21 (90%) | 4.33e+12 (24%) | 0.124 (95%) | 150 |
| 3-5 | 2.75 (80%) | 4.33e+12 (32%) | 0.148 (101%) | 47 |
| 5-10 | 3.83 (68%) | 4.31e+12 (20%) | 0.182 (69%) | 56 |
| 10-15 | 4.62 (52%) | 4.71e+12 (51%) | 0.231 (63%) | 32 |
| 15-20 | 5.13 (51%) | 4.74e+12 (25%) | 0.285 (50%) | 11 |
| 20-30 | 4.27 (74%) | 6.76e+12 (54%) | 0.424 (34%) | 5 |

### `R_cell_1` (nominal=11.2565 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.15 (95%) | 4.22e+12 (17%) | 0.106 (92%) | 151 |
| 3-5 | 2.8 (68%) | 4.49e+12 (31%) | 0.154 (88%) | 47 |
| 5-10 | 4.24 (57%) | 4.45e+12 (31%) | 0.21 (70%) | 65 |
| 10-15 | 4.76 (60%) | 4.69e+12 (30%) | 0.271 (49%) | 24 |
| 15-20 | 3.86 (74%) | 5e+12 (53%) | 0.332 (46%) | 10 |
| 20-30 | 3.82 (71%) | 7.91e+12 (81%) | 0.404 (51%) | 4 |

### `R_cell_2` (nominal=11.0049 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.89 (89%) | 4.16e+12 (8%) | 0.0871 (85%) | 130 |
| 3-5 | 2.79 (82%) | 4.36e+12 (24%) | 0.14 (76%) | 49 |
| 5-10 | 4.16 (58%) | 4.26e+12 (19%) | 0.195 (65%) | 68 |
| 10-15 | 4.26 (65%) | 4.87e+12 (50%) | 0.279 (56%) | 34 |
| 15-20 | 5.16 (50%) | 5.65e+12 (48%) | 0.333 (48%) | 10 |
| 20-30 | 3.85 (72%) | 6.52e+12 (57%) | 0.411 (40%) | 10 |

### `R_cell_3` (nominal=10.7820 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.72 (91%) | 4.11e+12 (4%) | 0.0714 (73%) | 119 |
| 3-5 | 2.77 (76%) | 4.21e+12 (12%) | 0.118 (68%) | 59 |
| 5-10 | 4.1 (63%) | 4.43e+12 (26%) | 0.182 (58%) | 62 |
| 10-15 | 4.32 (51%) | 5.1e+12 (36%) | 0.295 (38%) | 37 |
| 15-20 | 4.75 (67%) | 5.31e+12 (60%) | 0.407 (25%) | 15 |
| 20-30 | 5.23 (50%) | 5.58e+12 (80%) | 0.511 (17%) | 9 |

### `R_bend_cell1` (nominal=1.5270 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.86 (100%) | 4.14e+12 (7%) | 0.102 (104%) | 118 |
| 3-5 | 2.42 (76%) | 4.16e+12 (12%) | 0.116 (94%) | 50 |
| 5-10 | 4.24 (59%) | 4.34e+12 (20%) | 0.178 (65%) | 65 |
| 10-15 | 3.81 (66%) | 4.69e+12 (28%) | 0.239 (55%) | 32 |
| 15-20 | 4.46 (51%) | 5.44e+12 (50%) | 0.282 (53%) | 22 |
| 20-30 | 4.61 (59%) | 5.93e+12 (71%) | 0.37 (47%) | 14 |

### `R_bend_cell2_left` (nominal=1.4423 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.91 (91%) | 4.23e+12 (17%) | 0.098 (100%) | 124 |
| 3-5 | 2.75 (76%) | 4.27e+12 (27%) | 0.138 (90%) | 56 |
| 5-10 | 4.04 (62%) | 4.38e+12 (28%) | 0.185 (66%) | 64 |
| 10-15 | 4.48 (59%) | 4.49e+12 (21%) | 0.243 (56%) | 32 |
| 15-20 | 4.14 (68%) | 5.42e+12 (49%) | 0.333 (46%) | 16 |
| 20-30 | 4.54 (66%) | 6.31e+12 (70%) | 0.398 (38%) | 9 |

### `R_bend_cell3_left` (nominal=2.4460 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.74 (96%) | 4.1e+12 (3%) | 0.0888 (96%) | 131 |
| 3-5 | 2.93 (76%) | 4.1e+12 (2%) | 0.132 (84%) | 58 |
| 5-10 | 3.96 (59%) | 4.35e+12 (16%) | 0.228 (58%) | 59 |
| 10-15 | 4.95 (44%) | 5.3e+12 (39%) | 0.283 (50%) | 35 |
| 15-20 | 5.72 (45%) | 5.08e+12 (49%) | 0.255 (55%) | 13 |
| 20-30 | 4.12 (82%) | 9.53e+12 (62%) | 0.488 (24%) | 5 |

### `R_between_cell_1_2` (nominal=4.0253 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.04 (94%) | 4.19e+12 (13%) | 0.0985 (94%) | 139 |
| 3-5 | 2.7 (83%) | 4.33e+12 (34%) | 0.146 (83%) | 43 |
| 5-10 | 3.59 (67%) | 4.31e+12 (16%) | 0.198 (65%) | 64 |
| 10-15 | 4.54 (52%) | 5.19e+12 (45%) | 0.27 (58%) | 33 |
| 15-20 | 5.51 (42%) | 5.37e+12 (63%) | 0.305 (61%) | 18 |
| 20-30 | 5.46 (51%) | 4.82e+12 (20%) | 0.348 (39%) | 4 |

### `R_between_cell_2_3` (nominal=3.2820 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.03 (94%) | 4.26e+12 (20%) | 0.11 (99%) | 141 |
| 3-5 | 2.7 (77%) | 4.3e+12 (22%) | 0.14 (82%) | 43 |
| 5-10 | 4.32 (56%) | 4.39e+12 (39%) | 0.184 (76%) | 63 |
| 10-15 | 4.15 (62%) | 4.73e+12 (38%) | 0.234 (57%) | 30 |
| 15-20 | 4.66 (64%) | 4.98e+12 (37%) | 0.301 (43%) | 15 |
| 20-30 | 3.46 (71%) | 5.86e+12 (56%) | 0.412 (35%) | 9 |

### `R_between_cell_3_cutoff` (nominal=4.0380 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.93 (88%) | 4.18e+12 (10%) | 0.101 (93%) | 136 |
| 3-5 | 2.6 (81%) | 4.34e+12 (28%) | 0.134 (87%) | 48 |
| 5-10 | 4.34 (56%) | 4.4e+12 (22%) | 0.199 (67%) | 64 |
| 10-15 | 4.31 (62%) | 5.08e+12 (55%) | 0.269 (54%) | 29 |
| 15-20 | 5.19 (52%) | 4.95e+12 (47%) | 0.287 (61%) | 15 |
| 20-30 | 3.7 (85%) | 5.74e+12 (57%) | 0.373 (48%) | 9 |

### `cell_1_vertical_length` (nominal=1.4338 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.08 (90%) | 4.26e+12 (20%) | 0.105 (97%) | 155 |
| 3-5 | 3.51 (81%) | 4.22e+12 (13%) | 0.138 (81%) | 41 |
| 5-10 | 3.92 (54%) | 4.58e+12 (30%) | 0.192 (67%) | 56 |
| 10-15 | 4.49 (62%) | 5.05e+12 (46%) | 0.275 (50%) | 29 |
| 15-20 | 4.26 (69%) | 4.1e+12 (2%) | 0.311 (35%) | 11 |
| 20-30 | 4.11 (58%) | 5.59e+12 (80%) | 0.471 (26%) | 9 |

### `cell_2_vertical_left` (nominal=0.7719 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.91 (94%) | 4.22e+12 (16%) | 0.0982 (101%) | 135 |
| 3-5 | 2.56 (66%) | 4.32e+12 (19%) | 0.125 (81%) | 45 |
| 5-10 | 4.1 (59%) | 4.5e+12 (35%) | 0.203 (64%) | 68 |
| 10-15 | 4.43 (60%) | 4.6e+12 (30%) | 0.256 (56%) | 31 |
| 15-20 | 4.92 (60%) | 5.12e+12 (47%) | 0.329 (45%) | 14 |
| 20-30 | 5.36 (56%) | 5.93e+12 (79%) | 0.398 (42%) | 8 |

### `cell_2_vertical_right` (nominal=0.5761 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.17 (87%) | 4.3e+12 (29%) | 0.106 (99%) | 150 |
| 3-5 | 3.57 (77%) | 4.28e+12 (18%) | 0.155 (78%) | 57 |
| 5-10 | 3.61 (71%) | 4.47e+12 (29%) | 0.204 (62%) | 47 |
| 10-15 | 4.16 (55%) | 4.74e+12 (34%) | 0.244 (55%) | 26 |
| 15-20 | 4.03 (63%) | 5.19e+12 (47%) | 0.319 (50%) | 13 |
| 20-30 | 5.19 (55%) | 5.29e+12 (64%) | 0.448 (33%) | 8 |

### `cell_3_vertical_left` (nominal=0.9300 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.17 (100%) | 4.11e+12 (3%) | 0.0936 (93%) | 122 |
| 3-5 | 2.18 (77%) | 4.1e+12 (2%) | 0.127 (83%) | 47 |
| 5-10 | 3.76 (63%) | 4.28e+12 (14%) | 0.177 (68%) | 62 |
| 10-15 | 4.01 (58%) | 4.91e+12 (33%) | 0.238 (57%) | 39 |
| 15-20 | 4.92 (55%) | 4.93e+12 (42%) | 0.305 (54%) | 19 |
| 20-30 | 4.17 (72%) | 7.22e+12 (65%) | 0.413 (38%) | 12 |

### `cell_3_vertical_right` (nominal=0.9310 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.95 (100%) | 4.1e+12 (3%) | 0.102 (96%) | 123 |
| 3-5 | 2.65 (78%) | 4.23e+12 (11%) | 0.113 (86%) | 51 |
| 5-10 | 3.88 (64%) | 4.53e+12 (34%) | 0.19 (70%) | 66 |
| 10-15 | 4.18 (56%) | 4.67e+12 (26%) | 0.241 (56%) | 32 |
| 15-20 | 4.6 (55%) | 4.97e+12 (47%) | 0.303 (52%) | 18 |
| 20-30 | 4.77 (58%) | 6.63e+12 (67%) | 0.398 (39%) | 11 |

### `bend1` (nominal=1.5570 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.9 (90%) | 4.23e+12 (21%) | 0.0896 (93%) | 125 |
| 3-5 | 2.85 (73%) | 4.22e+12 (10%) | 0.131 (75%) | 53 |
| 5-10 | 4.19 (63%) | 4.3e+12 (17%) | 0.183 (67%) | 62 |
| 10-15 | 4.09 (66%) | 4.6e+12 (34%) | 0.265 (51%) | 37 |
| 15-20 | 4.52 (55%) | 5.38e+12 (41%) | 0.346 (43%) | 15 |
| 20-30 | 3.66 (70%) | 6.82e+12 (75%) | 0.434 (41%) | 9 |

### `e_x` (nominal=1.7820 mm)

| Perturb (um) | resonant_freq (CV%) | max_modified_poynting (CV%) | field_flatness (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.64 (104%) | 4.14e+12 (7%) | 0.0799 (90%) | 100 |
| 3-5 | 2.05 (74%) | 4.11e+12 (3%) | 0.0994 (85%) | 51 |
| 5-10 | 3.64 (59%) | 4.38e+12 (19%) | 0.195 (66%) | 78 |
| 10-15 | 4.67 (53%) | 5.15e+12 (49%) | 0.268 (57%) | 46 |
| 15-20 | 5.39 (53%) | 4.98e+12 (65%) | 0.279 (59%) | 17 |
| 20-30 | 4.55 (67%) | 4.86e+12 (29%) | 0.339 (44%) | 9 |


## 8. Failure Rate by Level

| Level | Failure Rate |
|-------|-------------|
| 3 um | 0/60 (0.0%) |
| 5 um | 0/60 (0.0%) |
| 10 um | 0/60 (0.0%) |
| 15 um | 8/60 (13.3%) |
| 20 um | 16/60 (26.7%) |
| 30 um | 35/60 (58.3%) |

---
*Report generated from 6 tolerance levels, 360 total records.*
