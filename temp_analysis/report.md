# Tolerance Sweep Analysis Report

**Campaign**: `wf3_tolerance`  |  **Parameter**: `tolerance_abs`  |  **Levels**: 9 (3um, 5um, 10um, 15um, 20um, 30um, 7um, 12um, 25um)

## 1. Data Overview

| Level | Source | Accepted | Failed | Success Rate |
|-------|--------|----------|--------|-------------|
| 3 um | 3um | 62 | 0 | 100.0% |
| 5 um | 5um | 60 | 0 | 100.0% |
| 10 um | 10um | 60 | 0 | 100.0% |
| 15 um | 15um | 52 | 16 | 76.5% |
| 20 um | 20um | 44 | 16 | 73.3% |
| 30 um | 30um | 26 | 69 | 27.4% |
| 7 um | 7um | 59 | 1 | 98.3% |
| 12 um | 12um | 58 | 2 | 96.7% |
| 25 um | 25um | 42 | 18 | 70.0% |

## 2. Coefficient of Variation (CV%)

| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic | Knee |
|--------|-----|-----|------|------|------|------|-----------|------|
| resonant_freq | 71.7 | 67.3 | 77.1 | 64.8 | 74.3 | 57.2 | 55.7 | 66.7 | 59.2 | non_monotonic | 12um |
| coupling_beta | 7.0 | 11.2 | 13.4 | 21.9 | 23.5 | 33.2 | 41.7 | 41.9 | 42.4 | increasing | 12um |
| q0 | 0.4 | 0.7 | 0.8 | 1.3 | 1.5 | 2.0 | 5.2 | 10.1 | 22.7 | increasing | 25um |
| peak_e_field | 5.5 | 5.3 | 50.3 | 10.1 | 67.3 | 14.7 | 18.9 | 78.6 | 31.0 | non_monotonic | 20um |
| field_flatness | 59.8 | 58.9 | 49.7 | 59.9 | 48.4 | 55.1 | 51.6 | 40.7 | 40.3 | non_monotonic | 10um |
| max_modified_poynting | 0.3 | 0.4 | 9.6 | 8.0 | 25.1 | 21.8 | 38.8 | 59.9 | 63.0 | non_monotonic | 20um |
| pulsed_heating | 2.7 | 0.4 | 8.5 | 7.4 | 22.7 | 38.6 | 35.9 | 58.2 | 59.9 | non_monotonic | 20um |

## 3. Mean Values by Tolerance Level

| Metric | 3um | 5um | 10um | 15um | 20um | 30um | Monotonic |
|--------|-----|-----|------|------|------|------|-----------|
| resonant_freq | 1.048 | 1.679 | 1.859 | 3.319 | 3.159 | 4.122 | 4.722 | 4.032 | 4.789 | non_monotonic |
| coupling_beta | 1.91 | 1.91 | 2.008 | 1.908 | 2.034 | 1.864 | 1.866 | 2.186 | 2.033 | non_monotonic |
| q0 | 1.854e+04 | 1.854e+04 | 1.859e+04 | 1.854e+04 | 1.861e+04 | 1.853e+04 | 1.893e+04 | 1.916e+04 | 2.193e+04 | non_monotonic |
| peak_e_field | 9.037e+04 | 9.097e+04 | 4.635e+04 | 9.076e+04 | 3.429e+04 | 9.134e+04 | 9.14e+04 | 2.651e+04 | 8.825e+04 | non_monotonic |
| field_flatness | 0.05038 | 0.07696 | 0.1524 | 0.141 | 0.2345 | 0.2075 | 0.2686 | 0.3499 | 0.395 | non_monotonic |
| max_modified_poynting | 4.087e+12 | 4.09e+12 | 4.263e+12 | 4.202e+12 | 4.761e+12 | 4.467e+12 | 4.87e+12 | 6.271e+12 | 5.97e+12 | non_monotonic |
| pulsed_heating | 24.86 | 24.75 | 25.62 | 25.37 | 28.09 | 28.03 | 28.91 | 36.51 | 35.19 | non_monotonic |

## 4. Parameter Sensitivity (Spearman |score| �� 0.2)

### 3 um

**resonant_freq** (n=62):
  - `R_cell_2`: -0.451 (rank=1)
  - `R_cell_3`: -0.363 (rank=2)
  - `R_cell_1`: -0.309 (rank=3)
  - `R_bend_cell1`: -0.290 (rank=4)
  - `length1`: -0.270 (rank=5)

**coupling_beta** (n=62):
  - `R_cell_3`: -0.820 (rank=1)
  - `R_cell_2`: +0.391 (rank=2)
  - `R_between_cell_1_2`: -0.298 (rank=3)
  - `R_bend_cell3_left`: +0.218 (rank=4)
  - `cell_2_vertical_right`: +0.209 (rank=5)

**q0** (n=62):
  - `R_cell_3`: -0.814 (rank=1)
  - `R_cell_2`: +0.338 (rank=2)
  - `R_between_cell_1_2`: -0.326 (rank=3)
  - `R_bend_cell3_left`: +0.233 (rank=4)

**peak_e_field** (n=62):
  - `R_cell_3`: +0.761 (rank=1)
  - `R_bend_cell3_left`: -0.308 (rank=2)
  - `R_cell_2`: -0.243 (rank=3)
  - `R_between_cell_1_2`: +0.217 (rank=4)

**field_flatness** (n=62):
  - `PickUpDeep`: +0.250 (rank=1)
  - `R_between_cell_1_2`: +0.233 (rank=2)
  - `cell_1_vertical_length`: -0.220 (rank=3)

**max_modified_poynting** (n=62):
  - `R_cell_1`: +0.395 (rank=1)
  - `e_x`: +0.340 (rank=2)
  - `offset1`: -0.234 (rank=3)
  - `R_cell_2`: -0.212 (rank=4)
  - `R_between_cell_1_2`: +0.205 (rank=5)

**pulsed_heating** (n=62):
  - `R_cell_1`: +0.391 (rank=1)
  - `e_x`: +0.268 (rank=2)
  - `R_cell_2`: -0.219 (rank=3)


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

**resonant_freq** (n=26):
  - `length1`: -0.343 (rank=1)
  - `PickUpDeep`: +0.333 (rank=2)
  - `cell_2_vertical_left`: +0.310 (rank=3)
  - `R_between_cell_2_3`: +0.279 (rank=4)
  - `R_bend_cell2_left`: +0.266 (rank=5)

**coupling_beta** (n=26):
  - `R_cell_3`: -0.615 (rank=1)
  - `R_cell_2`: +0.566 (rank=2)
  - `R_cell_1`: +0.286 (rank=3)
  - `bend1`: +0.277 (rank=4)
  - `R_between_cell_2_3`: -0.257 (rank=5)

**q0** (n=26):
  - `cell_1_vertical_length`: -0.489 (rank=1)
  - `R_cell_3`: +0.437 (rank=2)
  - `R_between_cell_1_2`: +0.330 (rank=3)
  - `R_bend_cell3_left`: -0.261 (rank=4)
  - `cell_3_vertical_left`: -0.254 (rank=5)

**peak_e_field** (n=26):
  - `R_cell_3`: +0.763 (rank=1)
  - `R_cell_1`: -0.584 (rank=2)
  - `bend1`: -0.535 (rank=3)
  - `R_cell_2`: -0.485 (rank=4)
  - `R_between_cell_1_2`: +0.457 (rank=5)

**field_flatness** (n=26):
  - `a`: +0.428 (rank=1)
  - `cell_1_vertical_length`: -0.394 (rank=2)
  - `R_bend_cell2_left`: -0.303 (rank=3)
  - `cell_2_vertical_left`: -0.282 (rank=4)
  - `R_cell_3`: +0.281 (rank=5)

**max_modified_poynting** (n=26):
  - `R_cell_1`: +0.717 (rank=1)
  - `R_cell_3`: -0.563 (rank=2)
  - `R_between_cell_1_2`: -0.498 (rank=3)
  - `bend1`: +0.479 (rank=4)
  - `R_between_cell_3_cutoff`: -0.406 (rank=5)

**pulsed_heating** (n=26):
  - `R_cell_1`: +0.716 (rank=1)
  - `R_cell_3`: -0.536 (rank=2)
  - `R_between_cell_1_2`: -0.483 (rank=3)
  - `bend1`: +0.444 (rank=4)
  - `R_between_cell_3_cutoff`: -0.424 (rank=5)


### 7 um

**resonant_freq** (n=59):
  - `cell_2_vertical_left`: -0.253 (rank=1)
  - `R_between_cell_1_2`: -0.219 (rank=2)
  - `bend1`: -0.214 (rank=3)

**coupling_beta** (n=59):
  - `R_cell_3`: -0.790 (rank=1)
  - `R_cell_2`: +0.370 (rank=2)
  - `length1`: -0.347 (rank=3)
  - `a`: -0.268 (rank=4)
  - `R_cell_1`: +0.250 (rank=5)

**q0** (n=59):
  - `R_cell_3`: -0.801 (rank=1)
  - `R_cell_1`: +0.325 (rank=2)
  - `length1`: -0.322 (rank=3)
  - `R_cell_2`: +0.301 (rank=4)
  - `a`: -0.252 (rank=5)

**peak_e_field** (n=59):
  - `R_between_cell_1_2`: +0.366 (rank=1)
  - `PickUpDeep`: +0.265 (rank=2)
  - `R_cell_3`: -0.263 (rank=3)
  - `R_cell_2`: -0.209 (rank=4)

**field_flatness** (n=59):
  - `R_cell_2`: +0.383 (rank=1)
  - `e_x`: +0.252 (rank=2)
  - `bend1`: -0.251 (rank=3)
  - `cell_2_vertical_left`: +0.221 (rank=4)
  - `R_cell_1`: +0.213 (rank=5)

**max_modified_poynting** (n=59):
  - `R_cell_1`: +0.781 (rank=1)
  - `bend1`: -0.249 (rank=2)
  - `PickUpDeep`: +0.207 (rank=3)

**pulsed_heating** (n=59):
  - `R_cell_1`: +0.811 (rank=1)
  - `bend1`: -0.214 (rank=2)
  - `R_between_cell_1_2`: +0.213 (rank=3)


### 12 um

**resonant_freq** (n=58):
  - `R_between_cell_1_2`: -0.288 (rank=1)
  - `bend1`: -0.281 (rank=2)
  - `PickUpDeep`: -0.252 (rank=3)
  - `cell_2_vertical_left`: -0.243 (rank=4)

**coupling_beta** (n=58):
  - `R_cell_3`: -0.797 (rank=1)
  - `R_cell_2`: +0.369 (rank=2)
  - `length1`: -0.308 (rank=3)
  - `R_cell_1`: +0.281 (rank=4)
  - `a`: -0.231 (rank=5)

**q0** (n=58):
  - `R_cell_3`: -0.818 (rank=1)
  - `R_cell_1`: +0.349 (rank=2)
  - `length1`: -0.296 (rank=3)
  - `R_cell_2`: +0.293 (rank=4)
  - `a`: -0.210 (rank=5)

**peak_e_field** (n=58):
  - `R_between_cell_1_2`: +0.352 (rank=1)
  - `R_cell_3`: -0.332 (rank=2)
  - `PickUpDeep`: +0.272 (rank=3)
  - `bend1`: +0.244 (rank=4)
  - `R_cell_2`: -0.242 (rank=5)

**field_flatness** (n=58):
  - `bend1`: -0.254 (rank=1)
  - `R_cell_2`: +0.225 (rank=2)
  - `R_cell_1`: +0.205 (rank=3)

**max_modified_poynting** (n=58):
  - `R_cell_1`: +0.676 (rank=1)
  - `R_cell_2`: +0.427 (rank=2)
  - `cell_1_vertical_length`: +0.241 (rank=3)
  - `cell_2_vertical_left`: +0.210 (rank=4)
  - `bend1`: -0.200 (rank=5)

**pulsed_heating** (n=58):
  - `R_cell_1`: +0.774 (rank=1)
  - `R_cell_2`: +0.298 (rank=2)
  - `bend1`: -0.261 (rank=3)
  - `cell_2_vertical_left`: +0.200 (rank=4)


### 25 um

**resonant_freq** (n=42):
  - `R_between_cell_1_2`: -0.326 (rank=1)
  - `R_between_cell_2_3`: -0.309 (rank=2)
  - `R_cell_1`: -0.225 (rank=3)
  - `cell_2_vertical_left`: -0.220 (rank=4)
  - `PickUpDeep`: -0.209 (rank=5)

**coupling_beta** (n=42):
  - `R_cell_3`: -0.869 (rank=1)
  - `R_cell_2`: +0.553 (rank=2)
  - `length1`: -0.314 (rank=3)
  - `R_bend_cell1`: -0.275 (rank=4)
  - `R_cell_1`: +0.272 (rank=5)

**q0** (n=42):
  - `R_cell_3`: -0.573 (rank=1)
  - `bend1`: -0.365 (rank=2)
  - `R_cell_1`: +0.330 (rank=3)
  - `R_cell_2`: +0.314 (rank=4)
  - `a`: -0.257 (rank=5)

**peak_e_field** (n=42):
  - `R_between_cell_1_2`: +0.389 (rank=1)
  - `e_x`: -0.265 (rank=2)
  - `R_bend_cell2_left`: -0.263 (rank=3)
  - `PickUpDeep`: +0.258 (rank=4)
  - `R_cell_3`: -0.256 (rank=5)

**field_flatness** (n=42):
  - `offset1`: +0.329 (rank=1)
  - `R_cell_3`: -0.316 (rank=2)
  - `length1`: -0.243 (rank=3)
  - `R_cell_1`: +0.226 (rank=4)

**max_modified_poynting** (n=42):
  - `R_cell_3`: -0.548 (rank=1)
  - `R_cell_1`: +0.515 (rank=2)
  - `R_cell_2`: +0.441 (rank=3)
  - `R_bend_cell1`: -0.402 (rank=4)
  - `cell_1_vertical_length`: +0.283 (rank=5)

**pulsed_heating** (n=42):
  - `R_cell_1`: +0.556 (rank=1)
  - `R_cell_3`: -0.554 (rank=2)
  - `R_bend_cell1`: -0.425 (rank=3)
  - `R_cell_2`: +0.408 (rank=4)
  - `cell_1_vertical_length`: +0.253 (rank=5)


## 5. Cross-Level Parameter Rank Stability

For each core metric, which parameters consistently dominate
across all 6 tolerance levels?

| Metric | Parameter | |��| mean | Rank=1 % | Top-3 % | Mean Rank | Verdict |
|--------|-----------|:-------:|:--------:|:-------:|:---------:|---------|
| resonant_freq | `length1` | 0.20 | 33% (9 lvls) | 56% | 7.4 | Consistent top-3 |
| resonant_freq | `R_cell_3` | 0.18 | 22% (9 lvls) | 33% | 9.8 | Weak / noise-level |
| resonant_freq | `R_between_cell_1_2` | 0.12 | 22% (9 lvls) | 33% | 12.9 | Weak / noise-level |
| resonant_freq | `R_cell_2` | 0.15 | 11% (9 lvls) | 11% | 10.4 | Weak / noise-level |
| resonant_freq | `cell_2_vertical_left` | 0.19 | 11% (9 lvls) | 33% | 8.2 | Weak / noise-level |

| coupling_beta | `R_cell_3` | 0.80 | 100% (9 lvls) | 100% | 1.0 | **Dominant** |
| coupling_beta | `offset1` | 0.09 | 0% (9 lvls) | 0% | 13.4 | Weak / noise-level |
| coupling_beta | `offset2` | 0.06 | 0% (9 lvls) | 0% | 16.0 | Weak / noise-level |
| coupling_beta | `offset3` | 0.05 | 0% (9 lvls) | 0% | 17.6 | Weak / noise-level |
| coupling_beta | `a` | 0.09 | 0% (9 lvls) | 0% | 14.1 | Weak / noise-level |

| field_flatness | `a` | 0.23 | 44% (9 lvls) | 56% | 6.7 | Consistent top-3 |
| field_flatness | `PickUpDeep` | 0.16 | 22% (9 lvls) | 33% | 7.9 | Weak / noise-level |
| field_flatness | `offset1` | 0.10 | 11% (9 lvls) | 11% | 12.7 | Weak / noise-level |
| field_flatness | `R_cell_2` | 0.10 | 11% (9 lvls) | 22% | 13.4 | Weak / noise-level |
| field_flatness | `bend1` | 0.11 | 11% (9 lvls) | 22% | 11.2 | Weak / noise-level |

*Verdict: Dominant = rank-1 in ��80% levels; Strong = ��50%; Consistent top-3 = in top-3 ��50%; Moderate = mean |��| ��0.3.*

## 6. Tolerance Recommendation

**Overall recommended max tolerance**: **10.0 um**

**Limiting metrics**: pulsed_heating

| Metric | Recommended Max | First Warning | First Failure | Knee Candidate |
|--------|----------------|---------------|---------------|----------------|
| resonant_freq | N/A um | N/A um | 3.0 um | 10.0 um |
| coupling_beta | N/A um | N/A um | 15.0 um | 25.0 um |
| q0 | 25.0 um | N/A um | 30.0 um | 30.0 um |
| field_flatness | N/A um | N/A um | 3.0 um | 12.0 um |
| max_modified_poynting | 15.0 um | N/A um | 20.0 um | 25.0 um |
| pulsed_heating | 10.0 um | N/A um | 12.0 um | 25.0 um |
| peak_e_field | N/A um | N/A um | N/A um | N/A um |

## 7. Per-Parameter Tolerance Budget

For each parameter, actual perturbation values are binned,
and metric averages computed per bin. This shows how metrics
degrade as THIS parameter deviates (with others also varying).

### `offset1` (nominal=0.0000 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.3e+04 (28%) | 2.32 (89%) | 4.13e+12 (7%) | 173 |
| 3-5 | 7.24e+04 (41%) | 2.76 (82%) | 4.53e+12 (32%) | 74 |
| 5-10 | 6.28e+04 (52%) | 3.33 (73%) | 4.77e+12 (45%) | 122 |
| 10-15 | 7.26e+04 (44%) | 3.48 (75%) | 4.87e+12 (36%) | 48 |
| 15-20 | 5.88e+04 (60%) | 4.37 (61%) | 5.38e+12 (39%) | 23 |
| 20-30 | 5.18e+04 (75%) | 4.07 (69%) | 6.67e+12 (58%) | 23 |

### `offset2` (nominal=0.0000 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.81e+04 (32%) | 2.66 (87%) | 4.22e+12 (13%) | 203 |
| 3-5 | 6.58e+04 (49%) | 2.73 (89%) | 4.77e+12 (36%) | 73 |
| 5-10 | 6.58e+04 (52%) | 3 (73%) | 4.92e+12 (50%) | 92 |
| 10-15 | 7.08e+04 (50%) | 3.49 (70%) | 4.73e+12 (35%) | 49 |
| 15-20 | 6.82e+04 (57%) | 4.47 (55%) | 5.68e+12 (61%) | 26 |
| 20-30 | 7.22e+04 (47%) | 3.55 (84%) | 5.35e+12 (45%) | 20 |

### `offset3` (nominal=0.0000 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.18e+04 (27%) | 2.16 (92%) | 4.16e+12 (10%) | 158 |
| 3-5 | 7.19e+04 (41%) | 2.58 (87%) | 4.56e+12 (35%) | 78 |
| 5-10 | 6.71e+04 (48%) | 3.05 (74%) | 4.44e+12 (22%) | 112 |
| 10-15 | 7.05e+04 (50%) | 3.98 (65%) | 4.8e+12 (30%) | 66 |
| 15-20 | 5.8e+04 (64%) | 4.64 (58%) | 5.49e+12 (39%) | 24 |
| 20-30 | 5.27e+04 (79%) | 4.58 (54%) | 7.36e+12 (70%) | 25 |

### `a` (nominal=10.6155 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.93e+04 (31%) | 2.18 (93%) | 4.17e+12 (9%) | 188 |
| 3-5 | 7.05e+04 (43%) | 2.7 (85%) | 4.41e+12 (19%) | 75 |
| 5-10 | 6.59e+04 (50%) | 3.39 (74%) | 4.95e+12 (44%) | 109 |
| 10-15 | 6.56e+04 (55%) | 4.08 (53%) | 5.21e+12 (41%) | 53 |
| 15-20 | 7.63e+04 (44%) | 4.3 (65%) | 5.54e+12 (70%) | 20 |
| 20-30 | 5.69e+04 (78%) | 4.97 (52%) | 5.65e+12 (63%) | 18 |

### `length1` (nominal=1.0290 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.06e+04 (29%) | 2.31 (90%) | 4.38e+12 (30%) | 155 |
| 3-5 | 6.97e+04 (44%) | 2.3 (84%) | 4.41e+12 (40%) | 75 |
| 5-10 | 6.72e+04 (48%) | 3.24 (74%) | 4.53e+12 (39%) | 121 |
| 10-15 | 6.94e+04 (51%) | 4.04 (63%) | 4.95e+12 (35%) | 59 |
| 15-20 | 6.75e+04 (55%) | 3.95 (75%) | 5.24e+12 (47%) | 30 |
| 20-30 | 6.24e+04 (65%) | 4.13 (63%) | 5.92e+12 (45%) | 23 |

### `PickUpDeep` (nominal=0.2620 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.04e+04 (31%) | 2.27 (86%) | 4.36e+12 (23%) | 194 |
| 3-5 | 6.87e+04 (48%) | 2.89 (79%) | 4.5e+12 (34%) | 80 |
| 5-10 | 6.56e+04 (50%) | 3.31 (78%) | 4.48e+12 (22%) | 106 |
| 10-15 | 7.23e+04 (47%) | 4.22 (57%) | 4.76e+12 (44%) | 47 |
| 15-20 | 6.25e+04 (56%) | 4.39 (65%) | 5.58e+12 (65%) | 20 |
| 20-30 | 4.37e+04 (78%) | 4.07 (74%) | 7.99e+12 (56%) | 16 |

### `R_cell_1` (nominal=11.2565 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.19e+04 (29%) | 2.25 (91%) | 4.28e+12 (19%) | 184 |
| 3-5 | 7.38e+04 (39%) | 2.68 (74%) | 4.42e+12 (26%) | 74 |
| 5-10 | 6.77e+04 (49%) | 3.55 (67%) | 4.5e+12 (25%) | 118 |
| 10-15 | 6.43e+04 (52%) | 3.86 (78%) | 5.1e+12 (37%) | 48 |
| 15-20 | 5.33e+04 (82%) | 4.72 (53%) | 5.52e+12 (47%) | 20 |
| 20-30 | 3.82e+04 (71%) | 3.32 (83%) | 7.55e+12 (74%) | 19 |

### `R_cell_2` (nominal=11.0049 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.3e+04 (23%) | 1.81 (89%) | 4.19e+12 (10%) | 167 |
| 3-5 | 7.12e+04 (41%) | 2.47 (82%) | 4.4e+12 (21%) | 81 |
| 5-10 | 6.63e+04 (53%) | 3.69 (64%) | 4.51e+12 (24%) | 124 |
| 10-15 | 6.58e+04 (57%) | 4.55 (59%) | 5.16e+12 (47%) | 54 |
| 15-20 | 4.89e+04 (75%) | 4.57 (61%) | 7.17e+12 (68%) | 23 |
| 20-30 | 6.31e+04 (58%) | 4.54 (63%) | 6.12e+12 (52%) | 14 |

### `R_cell_3` (nominal=10.7820 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.55e+04 (33%) | 1.78 (93%) | 4.25e+12 (17%) | 179 |
| 3-5 | 7.15e+04 (42%) | 2.79 (73%) | 4.5e+12 (28%) | 92 |
| 5-10 | 6.51e+04 (52%) | 3.8 (65%) | 4.66e+12 (30%) | 109 |
| 10-15 | 7.19e+04 (50%) | 4.44 (53%) | 5.64e+12 (58%) | 51 |
| 15-20 | 7.88e+04 (52%) | 4.84 (63%) | 5.16e+12 (53%) | 20 |
| 20-30 | 8.2e+04 (51%) | 5.15 (55%) | 5.93e+12 (74%) | 12 |

### `R_bend_cell1` (nominal=1.5270 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.57e+04 (36%) | 1.99 (94%) | 4.24e+12 (19%) | 175 |
| 3-5 | 7.07e+04 (44%) | 2.48 (78%) | 4.36e+12 (19%) | 81 |
| 5-10 | 6.6e+04 (52%) | 3.91 (66%) | 4.84e+12 (46%) | 114 |
| 10-15 | 7.69e+04 (39%) | 3.56 (68%) | 4.59e+12 (26%) | 44 |
| 15-20 | 7.26e+04 (46%) | 4.23 (54%) | 5.57e+12 (46%) | 30 |
| 20-30 | 7.12e+04 (57%) | 4.97 (57%) | 6.7e+12 (65%) | 19 |

### `R_bend_cell2_left` (nominal=1.4423 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.55e+04 (38%) | 2.25 (88%) | 4.42e+12 (23%) | 176 |
| 3-5 | 7.73e+04 (36%) | 2.52 (80%) | 4.31e+12 (25%) | 79 |
| 5-10 | 6.85e+04 (47%) | 3.48 (71%) | 4.53e+12 (31%) | 113 |
| 10-15 | 7e+04 (48%) | 4.04 (67%) | 4.55e+12 (28%) | 52 |
| 15-20 | 6.4e+04 (57%) | 3.97 (67%) | 6.78e+12 (67%) | 24 |
| 20-30 | 5.83e+04 (65%) | 4.18 (72%) | 5.96e+12 (60%) | 19 |

### `R_bend_cell3_left` (nominal=2.4460 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.84e+04 (35%) | 1.98 (94%) | 4.44e+12 (35%) | 174 |
| 3-5 | 7.72e+04 (35%) | 2.71 (79%) | 4.2e+12 (12%) | 84 |
| 5-10 | 6.81e+04 (47%) | 3.36 (69%) | 4.54e+12 (35%) | 110 |
| 10-15 | 6.45e+04 (53%) | 4.61 (54%) | 5.11e+12 (36%) | 56 |
| 15-20 | 6.06e+04 (60%) | 4.77 (56%) | 5.14e+12 (48%) | 25 |
| 20-30 | 4.73e+04 (73%) | 3.91 (80%) | 7.43e+12 (59%) | 14 |

### `R_between_cell_1_2` (nominal=4.0253 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 8.11e+04 (27%) | 2.03 (92%) | 4.38e+12 (32%) | 181 |
| 3-5 | 6.9e+04 (46%) | 2.6 (84%) | 4.52e+12 (38%) | 76 |
| 5-10 | 6.72e+04 (51%) | 3.35 (71%) | 4.41e+12 (18%) | 114 |
| 10-15 | 6.52e+04 (54%) | 4.44 (56%) | 5.12e+12 (39%) | 52 |
| 15-20 | 6.84e+04 (54%) | 4.99 (54%) | 5.85e+12 (67%) | 28 |
| 20-30 | 4.4e+04 (87%) | 4.63 (51%) | 6.2e+12 (41%) | 12 |

### `R_between_cell_2_3` (nominal=3.2820 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.75e+04 (34%) | 2.23 (89%) | 4.39e+12 (31%) | 192 |
| 3-5 | 7.1e+04 (43%) | 2.69 (81%) | 4.47e+12 (28%) | 69 |
| 5-10 | 6.69e+04 (50%) | 3.68 (69%) | 4.65e+12 (37%) | 114 |
| 10-15 | 7.1e+04 (47%) | 3.67 (71%) | 5.02e+12 (55%) | 49 |
| 15-20 | 7.21e+04 (54%) | 4.73 (56%) | 5.21e+12 (46%) | 20 |
| 20-30 | 5.69e+04 (63%) | 3.45 (77%) | 5.92e+12 (48%) | 19 |

### `R_between_cell_3_cutoff` (nominal=4.0380 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.93e+04 (31%) | 2.06 (87%) | 4.24e+12 (13%) | 180 |
| 3-5 | 7.24e+04 (43%) | 2.74 (83%) | 4.51e+12 (32%) | 73 |
| 5-10 | 6.83e+04 (48%) | 3.53 (69%) | 4.61e+12 (29%) | 114 |
| 10-15 | 6.7e+04 (53%) | 4.02 (62%) | 4.96e+12 (46%) | 49 |
| 15-20 | 6.66e+04 (55%) | 4.28 (70%) | 5.18e+12 (45%) | 26 |
| 20-30 | 4.99e+04 (79%) | 4.39 (65%) | 7.08e+12 (70%) | 21 |

### `cell_1_vertical_length` (nominal=1.4338 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.7e+04 (33%) | 2.15 (87%) | 4.34e+12 (23%) | 209 |
| 3-5 | 6.94e+04 (48%) | 3.43 (82%) | 4.38e+12 (20%) | 69 |
| 5-10 | 6.61e+04 (49%) | 3.39 (65%) | 4.82e+12 (44%) | 104 |
| 10-15 | 7.06e+04 (49%) | 4.13 (67%) | 5.1e+12 (39%) | 46 |
| 15-20 | 7.2e+04 (58%) | 4.28 (66%) | 5.04e+12 (76%) | 18 |
| 20-30 | 6.6e+04 (64%) | 4 (67%) | 6.27e+12 (60%) | 17 |

### `cell_2_vertical_left` (nominal=0.7719 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.71e+04 (35%) | 2.16 (91%) | 4.31e+12 (19%) | 180 |
| 3-5 | 7.28e+04 (40%) | 2.55 (75%) | 4.52e+12 (41%) | 72 |
| 5-10 | 6.84e+04 (48%) | 3.5 (69%) | 4.61e+12 (36%) | 122 |
| 10-15 | 7.16e+04 (46%) | 3.91 (69%) | 4.7e+12 (26%) | 49 |
| 15-20 | 7.21e+04 (50%) | 4.92 (57%) | 5.21e+12 (43%) | 19 |
| 20-30 | 5.08e+04 (76%) | 4.29 (68%) | 7.19e+12 (65%) | 21 |

### `cell_2_vertical_right` (nominal=0.5761 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.72e+04 (33%) | 2.19 (85%) | 4.36e+12 (28%) | 207 |
| 3-5 | 7.26e+04 (44%) | 3.59 (75%) | 4.48e+12 (24%) | 84 |
| 5-10 | 6.47e+04 (52%) | 3.2 (79%) | 4.81e+12 (45%) | 93 |
| 10-15 | 7.35e+04 (45%) | 3.78 (60%) | 4.82e+12 (34%) | 38 |
| 15-20 | 6.03e+04 (61%) | 4.17 (68%) | 5.36e+12 (45%) | 25 |
| 20-30 | 6.31e+04 (70%) | 4.58 (53%) | 6.32e+12 (70%) | 16 |

### `cell_3_vertical_left` (nominal=0.9300 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.78e+04 (35%) | 2.26 (95%) | 4.26e+12 (16%) | 160 |
| 3-5 | 7.29e+04 (43%) | 2.28 (76%) | 4.3e+12 (18%) | 77 |
| 5-10 | 6.78e+04 (48%) | 3.37 (70%) | 4.7e+12 (47%) | 117 |
| 10-15 | 6.87e+04 (46%) | 3.76 (68%) | 4.89e+12 (29%) | 61 |
| 15-20 | 7.37e+04 (46%) | 4.8 (54%) | 5.16e+12 (46%) | 26 |
| 20-30 | 5.97e+04 (61%) | 3.97 (78%) | 6.8e+12 (61%) | 22 |

### `cell_3_vertical_right` (nominal=0.9310 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.82e+04 (33%) | 1.96 (97%) | 4.24e+12 (19%) | 173 |
| 3-5 | 6.82e+04 (46%) | 2.77 (78%) | 4.47e+12 (28%) | 85 |
| 5-10 | 6.66e+04 (51%) | 3.67 (68%) | 4.79e+12 (44%) | 114 |
| 10-15 | 7.46e+04 (41%) | 3.77 (61%) | 4.79e+12 (28%) | 46 |
| 15-20 | 7.14e+04 (52%) | 4.53 (59%) | 5.27e+12 (44%) | 27 |
| 20-30 | 6.26e+04 (59%) | 4.72 (57%) | 6.72e+12 (69%) | 18 |

### `bend1` (nominal=1.5570 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.83e+04 (31%) | 2 (92%) | 4.31e+12 (23%) | 175 |
| 3-5 | 7.06e+04 (41%) | 2.71 (72%) | 4.41e+12 (26%) | 83 |
| 5-10 | 6.53e+04 (53%) | 3.74 (70%) | 4.55e+12 (27%) | 116 |
| 10-15 | 7.22e+04 (50%) | 4.02 (64%) | 5.04e+12 (53%) | 53 |
| 15-20 | 6.72e+04 (55%) | 4.37 (66%) | 6.06e+12 (59%) | 23 |
| 20-30 | 6.89e+04 (61%) | 4.05 (64%) | 6.71e+12 (63%) | 13 |

### `e_x` (nominal=1.7820 mm)

| Perturb (um) | peak_e_field (CV%) | resonant_freq (CV%) | max_modified_poynting (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 7.88e+04 (31%) | 1.86 (102%) | 4.36e+12 (32%) | 134 |
| 3-5 | 7.29e+04 (39%) | 2.11 (80%) | 4.23e+12 (9%) | 83 |
| 5-10 | 7.01e+04 (46%) | 3.21 (67%) | 4.55e+12 (26%) | 132 |
| 10-15 | 6.74e+04 (53%) | 4.52 (54%) | 5.18e+12 (46%) | 68 |
| 15-20 | 7.11e+04 (52%) | 4.58 (64%) | 5.67e+12 (71%) | 28 |
| 20-30 | 5.34e+04 (74%) | 5.02 (56%) | 5.36e+12 (44%) | 18 |


## 8. Failure Rate by Level

| Level | Failure Rate |
|-------|-------------|
| 3 um | 0/62 (0.0%) |
| 5 um | 0/60 (0.0%) |
| 10 um | 0/60 (0.0%) |
| 15 um | 16/68 (23.5%) |
| 20 um | 16/60 (26.7%) |
| 30 um | 69/95 (72.6%) |
| 7 um | 1/60 (1.7%) |
| 12 um | 2/60 (3.3%) |
| 25 um | 18/60 (30.0%) |

---
*Report generated from 9 tolerance levels, 585 total records.*
