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
| resonant_freq | 211.6 | 331.2 | 487.3 | 9281.6 | 3359.3 | 489.9 | non_monotonic | 10um |
| coupling_beta | 7.1 | 11.2 | 21.9 | 33.2 | 41.7 | 43.3 | increasing | 10um |
| q0 | 0.5 | 0.7 | 1.3 | 2.0 | 5.2 | 22.9 | increasing | 20um |
| peak_e_field | 3.4 | 5.3 | 10.1 | 14.7 | 18.9 | 24.1 | increasing | 20um |
| field_flatness | 60.4 | 58.9 | 59.9 | 55.1 | 51.6 | 41.0 | non_monotonic | 20um |
| max_modified_poynting | 0.3 | 0.4 | 8.0 | 21.8 | 38.8 | 62.3 | increasing | 20um |
| pulsed_heating | 2.7 | 0.4 | 7.4 | 38.6 | 35.9 | 59.1 | non_monotonic | 10um |

## 3. Mean Values by Tolerance Level

| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic |
|--------|-----|-----|------|------|------|------|-----------|
| resonant_freq | 0.5523 | 0.588 | 0.7993 | 0.05154 | -0.1623 | 1.094 | non_monotonic |
| coupling_beta | 1.912 | 1.91 | 1.908 | 1.864 | 1.866 | 2.006 | non_monotonic |
| q0 | 1.854e+04 | 1.854e+04 | 1.854e+04 | 1.853e+04 | 1.893e+04 | 2.204e+04 | non_monotonic |
| peak_e_field | 9.104e+04 | 9.097e+04 | 9.076e+04 | 9.134e+04 | 9.14e+04 | 9.153e+04 | non_monotonic |
| field_flatness | 0.04985 | 0.07696 | 0.141 | 0.2075 | 0.2686 | 0.389 | increasing |
| max_modified_poynting | 4.087e+12 | 4.09e+12 | 4.202e+12 | 4.467e+12 | 4.87e+12 | 5.685e+12 | increasing |
| pulsed_heating | 24.86 | 24.75 | 25.37 | 28.03 | 28.91 | 33.6 | non_monotonic |

## 4. Parameter Sensitivity (Spearman |score| �� 0.2)

### 3 um

**resonant_freq** (n=60):
  - `R_cell_2`: -0.655 (rank=1)
  - `R_cell_3`: -0.637 (rank=2)
  - `R_cell_1`: -0.556 (rank=3)

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
  - `R_cell_3`: -0.648 (rank=1)
  - `R_cell_2`: -0.648 (rank=2)
  - `R_cell_1`: -0.550 (rank=3)

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
  - `R_cell_2`: -0.650 (rank=1)
  - `R_cell_3`: -0.650 (rank=2)
  - `R_cell_1`: -0.528 (rank=3)

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
  - `R_cell_2`: -0.588 (rank=1)
  - `R_cell_3`: -0.511 (rank=2)
  - `R_cell_1`: -0.379 (rank=3)
  - `e_x`: +0.279 (rank=4)

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
  - `R_cell_2`: -0.570 (rank=1)
  - `R_cell_3`: -0.398 (rank=2)
  - `PickUpDeep`: +0.322 (rank=3)
  - `R_cell_1`: -0.294 (rank=4)
  - `cell_2_vertical_left`: -0.261 (rank=5)

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
  - `R_cell_2`: -0.651 (rank=1)
  - `e_x`: +0.471 (rank=2)
  - `cell_3_vertical_left`: -0.271 (rank=3)
  - `R_bend_cell2_left`: -0.206 (rank=4)

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


## 5. Tolerance Recommendation

**Overall recommended max tolerance**: **3.0 um**

**Limiting metrics**: peak_e_field

| Metric | Recommended Max | First Warning | First Failure | Knee Candidate |
|--------|----------------|---------------|---------------|----------------|
| resonant_freq | N/A um | N/A um | 3.0 um | 30.0 um |
| field_flatness | N/A um | N/A um | 3.0 um | 30.0 um |
| pulsed_heating | 10.0 um | N/A um | 15.0 um | 30.0 um |
| max_modified_poynting | 10.0 um | N/A um | 15.0 um | 30.0 um |
| coupling_beta | N/A um | N/A um | 15.0 um | 30.0 um |
| q0 | 20.0 um | N/A um | 30.0 um | 30.0 um |
| peak_e_field | 3.0 um | N/A um | 5.0 um | 15.0 um |

## 7. Per-Parameter Tolerance Budget

Analysis: for each parameter, compute max perturbation (um) before
key metrics cross thresholds. Based on pooled data across all levels.

| Parameter | Max Perturb (um) | resonant_freq | coupling_beta | field_flatness | peak_e_field | q0 | pulsed_heating |
|-----------|:----------------:|:-------------:|:------------:|:-------------:|:------------:|:--:|:-------------:|
| `offset1` | 29 | +0.337 | +0.392 | +1.92e+12 | -7.83e+03 | +9.49 | +2.7e+03 | -0.981 |
| `offset2` | 28 | -0.239 | +0.339 | +1.39e+12 | +5.19e+03 | +6.94 | +2.22e+03 | +1.55 |
| `offset3` | 30 | +0.325 | +0.39 | +2.34e+12 | -4.01e+03 | +11.8 | +2.3e+03 | -0.258 |
| `a` | 30 | -0.309 | +0.344 | +8.18e+11 | +7.25e+03 | +3.8 | +2.55e+03 | +1.39 |
| `length1` | 30 | -0.293 | +0.36 | +1.04e+12 | +5.82e+03 | +5.88 | +2.9e+03 | -1.01 |
| `PickUpDeep` | 25 | +0.111 | +0.258 | +1.1e+12 | -2.99e+03 | +8.08 | +1.83e+03 | +0.151 |
| `R_cell_1` | 26 | -0.023 | +0.369 | +1.72e+12 | -1.73e+03 | +9.72 | +2.86e+03 | +0.263 |
| `R_cell_2` | 29 | +0.247 | +0.449 | +2.45e+12 | -6.16e+03 | +14.2 | +3.72e+03 | +3.24 |
| `R_cell_3` | 30 | -0.352 | +0.581 | +2.01e+12 | +1.2e+04 | +10.2 | +5.23e+03 | +0.507 |
| `R_bend_cell1` | 30 | +0.236 | +0.313 | +2.15e+12 | -2.69e+03 | +10.8 | +1.31e+03 | -1.02 |
| `R_bend_cell2_left` | 28 | +0.144 | +0.37 | +1.75e+12 | -3.76e+03 | +10.3 | +2.49e+03 | +2.58 |
| `R_bend_cell3_left` | 28 | +0.683 | +0.402 | +3.23e+12 | -1.36e+04 | +19.5 | +1.7e+03 | -1.72 |
| `R_between_cell_1_2` | 28 | +0.179 | +0.378 | +1.92e+12 | -2.28e+03 | +9.64 | +2.9e+03 | +3.08 |
| `R_between_cell_2_3` | 30 | +0.104 | +0.335 | +1.51e+12 | +372 | +7.79 | +2.55e+03 | -3.64 |
| `R_between_cell_3_cutoff` | 30 | -0.0266 | +0.339 | +1.57e+12 | +1.32e+03 | +10.1 | +2.36e+03 | -1.43 |
| `cell_1_vertical_length` | 29 | -0.513 | +0.44 | +1.18e+12 | +1.32e+04 | +7.95 | +3.54e+03 | +1.9 |
| `cell_2_vertical_left` | 29 | -0.288 | +0.389 | +1.37e+12 | +4.23e+03 | +7.22 | +3.18e+03 | +1.76 |
| `cell_2_vertical_right` | 29 | -0.104 | +0.386 | +1.21e+12 | +4.32e+03 | +6.24 | +3.42e+03 | -1.71 |
| `cell_3_vertical_left` | 30 | +0.396 | +0.371 | +2.54e+12 | -6.79e+03 | +14.3 | +2.41e+03 | -1.37 |
| `cell_3_vertical_right` | 30 | +0.311 | +0.358 | +2.27e+12 | -5.1e+03 | +11.6 | +2.36e+03 | +1.13 |
| `bend1` | 29 | -0.0287 | +0.431 | +2.06e+12 | +3.8e+03 | +10.7 | +3.32e+03 | +2.29 |
| `e_x` | 30 | -0.0397 | +0.365 | +1.43e+12 | +931 | +8.5 | +2.04e+03 | +0.502 |

*Values show estimated metric change at max perturbation (linear regression slope �� max ��m).*

## 6. Failure Rate by Level

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
