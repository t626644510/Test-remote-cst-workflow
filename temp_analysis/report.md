# Tolerance Sweep Analysis Report

**Campaign**: `wf3_tolerance`  |  **Parameter**: `tolerance_abs`  |  **Levels**: 9 (3um, 5um, 7um, 10um, 12um, 15um, 20um, 25um, 30um)

## 1. Data Overview

| Level | Source | Accepted | Failed | Success Rate |
|-------|--------|----------|--------|-------------|
| 3 um | 3um | 62 | 0 | 100.0% |
| 5 um | 5um | 60 | 0 | 100.0% |
| 7 um | 7um | 59 | 1 | 98.3% |
| 10 um | 10um | 60 | 0 | 100.0% |
| 12 um | 12um | 58 | 2 | 96.7% |
| 15 um | 15um | 52 | 16 | 76.5% |
| 20 um | 20um | 44 | 16 | 73.3% |
| 25 um | 25um | 42 | 18 | 70.0% |
| 30 um | 30um | 26 | 69 | 27.4% |

## 2. Coefficient of Variation (CV%)

| Metric | 3um | 5um | 7um | 10um | 12um | 15um | 20um | 25um | 30um | Monotonic | Knee |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|-----------|------|
| resonant_freq | 71.7 | 67.3 | 77.1 | 64.8 | 74.3 | 57.2 | 55.7 | 66.7 | 59.2 | non_monotonic | 12um |
| coupling_beta | 7.0 | 11.2 | 13.4 | 21.9 | 23.5 | 33.2 | 41.7 | 41.9 | 42.4 | increasing | 12um |
| q0 | 0.4 | 0.7 | 0.8 | 1.3 | 1.5 | 2.0 | 5.2 | 10.1 | 22.7 | increasing | 25um |
| peak_e_field | 5.5 | 5.3 | 50.3 | 10.1 | 67.3 | 14.7 | 18.9 | 78.6 | 31.0 | non_monotonic | 20um |
| field_flatness | 59.8 | 58.9 | 49.7 | 59.9 | 48.4 | 55.1 | 51.6 | 40.7 | 40.3 | non_monotonic | 10um |
| max_modified_poynting | 0.3 | 0.4 | 9.6 | 8.0 | 25.1 | 21.8 | 38.8 | 59.9 | 63.0 | non_monotonic | 20um |
| pulsed_heating | 2.7 | 0.4 | 8.5 | 7.4 | 22.7 | 38.6 | 35.9 | 58.2 | 59.9 | non_monotonic | 20um |

## 3. Mean Values by Tolerance Level

| Metric | 3um | 5um | 7um | 10um | 12um | 15um | 20um | 25um | 30um | Monotonic |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|-----------|
| resonant_freq | 1.048 | 1.679 | 1.859 | 3.319 | 3.159 | 4.122 | 4.722 | 4.032 | 4.789 | non_monotonic |
| coupling_beta | 1.91 | 1.91 | 2.008 | 1.908 | 2.034 | 1.864 | 1.866 | 2.186 | 2.033 | non_monotonic |
| q0 | 1.854e+04 | 1.854e+04 | 1.859e+04 | 1.854e+04 | 1.861e+04 | 1.853e+04 | 1.893e+04 | 1.916e+04 | 2.193e+04 | non_monotonic |
| peak_e_field | 9.037e+04 | 9.097e+04 | 4.635e+04 | 9.076e+04 | 3.429e+04 | 9.134e+04 | 9.14e+04 | 2.651e+04 | 8.825e+04 | non_monotonic |
| field_flatness | 0.05038 | 0.07696 | 0.1524 | 0.141 | 0.2345 | 0.2075 | 0.2686 | 0.3499 | 0.395 | non_monotonic |
| max_modified_poynting | 4.087e+12 | 4.09e+12 | 4.263e+12 | 4.202e+12 | 4.761e+12 | 4.467e+12 | 4.87e+12 | 6.271e+12 | 5.97e+12 | non_monotonic |
| pulsed_heating | 24.86 | 24.75 | 25.62 | 25.37 | 28.09 | 28.03 | 28.91 | 36.51 | 35.19 | non_monotonic |

## 4. Parameter Sensitivity (Spearman |score| >= 0.2)

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

*Verdict: Dominant = rank-1 in >=80% levels; Strong = >=50%; Consistent top-3 = in top-3 >=50%; Moderate = mean |rho| >=0.3.*

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
and metric averages computed per bin. **All 22 parameters vary
simultaneously** �� values reflect combined effects, not isolated impact.
Compare rows within a column to see degradation trends.
`n` = number of samples in that perturbation bin.

### `offset1` (nominal=0.0000 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.32 (89%) | 1.86 (17%) | 0.112 (98%) | 8.3e+04 (28%) | 173 |
| 3-5 | 2.76 (82%) | 1.99 (22%) | 0.163 (81%) | 7.24e+04 (41%) | 74 |
| 5-10 | 3.33 (73%) | 2.02 (27%) | 0.212 (56%) | 6.28e+04 (52%) | 122 |
| 10-15 | 3.48 (75%) | 1.9 (37%) | 0.262 (48%) | 7.26e+04 (44%) | 48 |
| 15-20 | 4.37 (61%) | 2.06 (40%) | 0.321 (42%) | 5.88e+04 (60%) | 23 |
| 20-30 | 4.07 (69%) | 2.36 (41%) | 0.395 (34%) | 5.18e+04 (75%) | 23 |

### `offset2` (nominal=0.0000 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.66 (87%) | 1.95 (16%) | 0.121 (82%) | 7.81e+04 (32%) | 203 |
| 3-5 | 2.73 (89%) | 2.04 (27%) | 0.185 (73%) | 6.58e+04 (49%) | 73 |
| 5-10 | 3 (73%) | 1.99 (32%) | 0.226 (64%) | 6.58e+04 (52%) | 92 |
| 10-15 | 3.49 (70%) | 1.87 (34%) | 0.248 (54%) | 7.08e+04 (50%) | 49 |
| 15-20 | 4.47 (55%) | 1.92 (50%) | 0.314 (54%) | 6.82e+04 (57%) | 26 |
| 20-30 | 3.55 (84%) | 1.91 (40%) | 0.36 (40%) | 7.22e+04 (47%) | 20 |

### `offset3` (nominal=0.0000 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.16 (92%) | 1.92 (16%) | 0.111 (93%) | 8.18e+04 (27%) | 158 |
| 3-5 | 2.58 (87%) | 1.94 (25%) | 0.156 (82%) | 7.19e+04 (41%) | 78 |
| 5-10 | 3.05 (74%) | 1.92 (26%) | 0.2 (58%) | 6.71e+04 (48%) | 112 |
| 10-15 | 3.98 (65%) | 1.96 (34%) | 0.263 (52%) | 7.05e+04 (50%) | 66 |
| 15-20 | 4.64 (58%) | 2.11 (35%) | 0.301 (44%) | 5.8e+04 (64%) | 24 |
| 20-30 | 4.58 (54%) | 2.33 (46%) | 0.387 (43%) | 5.27e+04 (79%) | 25 |

### `a` (nominal=10.6155 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.18 (93%) | 1.91 (17%) | 0.121 (86%) | 7.93e+04 (31%) | 188 |
| 3-5 | 2.7 (85%) | 2 (23%) | 0.167 (76%) | 7.05e+04 (43%) | 75 |
| 5-10 | 3.39 (74%) | 2.04 (30%) | 0.214 (63%) | 6.59e+04 (50%) | 109 |
| 10-15 | 4.08 (53%) | 1.99 (40%) | 0.283 (49%) | 6.56e+04 (55%) | 53 |
| 15-20 | 4.3 (65%) | 1.89 (41%) | 0.292 (55%) | 7.63e+04 (44%) | 20 |
| 20-30 | 4.97 (52%) | 1.87 (43%) | 0.386 (39%) | 5.69e+04 (78%) | 18 |

### `length1` (nominal=1.0290 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.31 (90%) | 1.99 (19%) | 0.115 (99%) | 8.06e+04 (29%) | 155 |
| 3-5 | 2.3 (84%) | 1.92 (20%) | 0.132 (75%) | 6.97e+04 (44%) | 75 |
| 5-10 | 3.24 (74%) | 1.92 (29%) | 0.201 (59%) | 6.72e+04 (48%) | 121 |
| 10-15 | 4.04 (63%) | 1.98 (33%) | 0.255 (49%) | 6.94e+04 (51%) | 59 |
| 15-20 | 3.95 (75%) | 1.82 (39%) | 0.322 (49%) | 6.75e+04 (55%) | 30 |
| 20-30 | 4.13 (63%) | 2.26 (42%) | 0.42 (26%) | 6.24e+04 (65%) | 23 |

### `PickUpDeep` (nominal=0.2620 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.27 (86%) | 1.92 (23%) | 0.142 (85%) | 8.04e+04 (31%) | 194 |
| 3-5 | 2.89 (79%) | 1.95 (26%) | 0.183 (85%) | 6.87e+04 (48%) | 80 |
| 5-10 | 3.31 (78%) | 1.96 (26%) | 0.195 (62%) | 6.56e+04 (50%) | 106 |
| 10-15 | 4.22 (57%) | 1.92 (33%) | 0.235 (56%) | 7.23e+04 (47%) | 47 |
| 15-20 | 4.39 (65%) | 2.05 (39%) | 0.282 (52%) | 6.25e+04 (56%) | 20 |
| 20-30 | 4.07 (74%) | 2.49 (38%) | 0.423 (36%) | 4.37e+04 (78%) | 16 |

### `R_cell_1` (nominal=11.2565 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.25 (91%) | 1.94 (20%) | 0.125 (89%) | 8.19e+04 (29%) | 184 |
| 3-5 | 2.68 (74%) | 1.99 (24%) | 0.157 (74%) | 7.38e+04 (39%) | 74 |
| 5-10 | 3.55 (67%) | 1.92 (26%) | 0.212 (62%) | 6.77e+04 (49%) | 118 |
| 10-15 | 3.86 (78%) | 1.94 (35%) | 0.267 (51%) | 6.43e+04 (52%) | 48 |
| 15-20 | 4.72 (53%) | 2.03 (42%) | 0.341 (41%) | 5.33e+04 (82%) | 20 |
| 20-30 | 3.32 (83%) | 2.24 (51%) | 0.373 (47%) | 3.82e+04 (71%) | 19 |

### `R_cell_2` (nominal=11.0049 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.81 (89%) | 1.94 (15%) | 0.1 (82%) | 8.3e+04 (23%) | 167 |
| 3-5 | 2.47 (82%) | 1.96 (21%) | 0.152 (66%) | 7.12e+04 (41%) | 81 |
| 5-10 | 3.69 (64%) | 1.9 (29%) | 0.213 (55%) | 6.63e+04 (53%) | 124 |
| 10-15 | 4.55 (59%) | 1.96 (38%) | 0.313 (47%) | 6.58e+04 (57%) | 54 |
| 15-20 | 4.57 (61%) | 2.27 (47%) | 0.348 (49%) | 4.89e+04 (75%) | 23 |
| 20-30 | 4.54 (63%) | 2.26 (42%) | 0.425 (34%) | 6.31e+04 (58%) | 14 |

### `R_cell_3` (nominal=10.7820 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.78 (93%) | 1.98 (12%) | 0.113 (91%) | 7.55e+04 (33%) | 179 |
| 3-5 | 2.79 (73%) | 1.99 (20%) | 0.158 (70%) | 7.15e+04 (42%) | 92 |
| 5-10 | 3.8 (65%) | 1.98 (29%) | 0.209 (57%) | 6.51e+04 (52%) | 109 |
| 10-15 | 4.44 (53%) | 1.93 (47%) | 0.31 (43%) | 7.19e+04 (50%) | 51 |
| 15-20 | 4.84 (63%) | 1.67 (60%) | 0.368 (33%) | 7.88e+04 (52%) | 20 |
| 20-30 | 5.15 (55%) | 1.95 (54%) | 0.473 (27%) | 8.2e+04 (51%) | 12 |

### `R_bend_cell1` (nominal=1.5270 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.99 (94%) | 1.91 (19%) | 0.131 (90%) | 7.57e+04 (36%) | 175 |
| 3-5 | 2.48 (78%) | 1.97 (20%) | 0.146 (79%) | 7.07e+04 (44%) | 81 |
| 5-10 | 3.91 (66%) | 2.01 (27%) | 0.213 (62%) | 6.6e+04 (52%) | 114 |
| 10-15 | 3.56 (68%) | 1.8 (39%) | 0.251 (53%) | 7.69e+04 (39%) | 44 |
| 15-20 | 4.23 (54%) | 2.14 (40%) | 0.295 (48%) | 7.26e+04 (46%) | 30 |
| 20-30 | 4.97 (57%) | 2.22 (45%) | 0.395 (43%) | 7.12e+04 (57%) | 19 |

### `R_bend_cell2_left` (nominal=1.4423 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.25 (88%) | 1.98 (19%) | 0.139 (87%) | 7.55e+04 (38%) | 176 |
| 3-5 | 2.52 (80%) | 1.89 (21%) | 0.147 (82%) | 7.73e+04 (36%) | 79 |
| 5-10 | 3.48 (71%) | 1.94 (30%) | 0.192 (63%) | 6.85e+04 (47%) | 113 |
| 10-15 | 4.04 (67%) | 1.87 (32%) | 0.248 (54%) | 7e+04 (48%) | 52 |
| 15-20 | 3.97 (67%) | 2.2 (43%) | 0.358 (44%) | 6.4e+04 (57%) | 24 |
| 20-30 | 4.18 (72%) | 2.12 (43%) | 0.377 (40%) | 5.83e+04 (65%) | 19 |

### `R_bend_cell3_left` (nominal=2.4460 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.98 (94%) | 1.89 (20%) | 0.129 (94%) | 7.84e+04 (35%) | 174 |
| 3-5 | 2.71 (79%) | 1.89 (19%) | 0.146 (76%) | 7.72e+04 (35%) | 84 |
| 5-10 | 3.36 (69%) | 1.96 (29%) | 0.214 (62%) | 6.81e+04 (47%) | 110 |
| 10-15 | 4.61 (54%) | 2.14 (33%) | 0.278 (51%) | 6.45e+04 (53%) | 56 |
| 15-20 | 4.77 (56%) | 1.93 (42%) | 0.268 (50%) | 6.06e+04 (60%) | 25 |
| 20-30 | 3.91 (80%) | 2.52 (39%) | 0.41 (34%) | 4.73e+04 (73%) | 14 |

### `R_between_cell_1_2` (nominal=4.0253 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.03 (92%) | 1.98 (21%) | 0.121 (92%) | 8.11e+04 (27%) | 181 |
| 3-5 | 2.6 (84%) | 1.93 (25%) | 0.167 (76%) | 6.9e+04 (46%) | 76 |
| 5-10 | 3.35 (71%) | 1.87 (27%) | 0.207 (60%) | 6.72e+04 (51%) | 114 |
| 10-15 | 4.44 (56%) | 2.01 (37%) | 0.276 (50%) | 6.52e+04 (54%) | 52 |
| 15-20 | 4.99 (54%) | 2.04 (40%) | 0.333 (52%) | 6.84e+04 (54%) | 28 |
| 20-30 | 4.63 (51%) | 2.34 (36%) | 0.37 (36%) | 4.4e+04 (87%) | 12 |

### `R_between_cell_2_3` (nominal=3.2820 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.23 (89%) | 1.97 (21%) | 0.134 (89%) | 7.75e+04 (34%) | 192 |
| 3-5 | 2.69 (81%) | 1.95 (24%) | 0.166 (73%) | 7.1e+04 (43%) | 69 |
| 5-10 | 3.68 (69%) | 1.93 (27%) | 0.204 (67%) | 6.69e+04 (50%) | 114 |
| 10-15 | 3.67 (71%) | 1.92 (39%) | 0.26 (55%) | 7.1e+04 (47%) | 49 |
| 15-20 | 4.73 (56%) | 1.93 (46%) | 0.29 (48%) | 7.21e+04 (54%) | 20 |
| 20-30 | 3.45 (77%) | 2.24 (39%) | 0.389 (37%) | 5.69e+04 (63%) | 19 |

### `R_between_cell_3_cutoff` (nominal=4.0380 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.06 (87%) | 1.96 (17%) | 0.12 (83%) | 7.93e+04 (31%) | 180 |
| 3-5 | 2.74 (83%) | 1.95 (27%) | 0.163 (81%) | 7.24e+04 (43%) | 73 |
| 5-10 | 3.53 (69%) | 1.92 (27%) | 0.211 (62%) | 6.83e+04 (48%) | 114 |
| 10-15 | 4.02 (62%) | 1.95 (38%) | 0.256 (50%) | 6.7e+04 (53%) | 49 |
| 15-20 | 4.28 (70%) | 1.82 (45%) | 0.318 (51%) | 6.66e+04 (55%) | 26 |
| 20-30 | 4.39 (65%) | 2.4 (40%) | 0.385 (43%) | 4.99e+04 (79%) | 21 |

### `cell_1_vertical_length` (nominal=1.4338 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.15 (87%) | 1.99 (20%) | 0.126 (90%) | 7.7e+04 (33%) | 209 |
| 3-5 | 3.43 (82%) | 1.87 (21%) | 0.162 (72%) | 6.94e+04 (48%) | 69 |
| 5-10 | 3.39 (65%) | 2.01 (30%) | 0.214 (61%) | 6.61e+04 (49%) | 104 |
| 10-15 | 4.13 (67%) | 1.97 (39%) | 0.281 (44%) | 7.06e+04 (49%) | 46 |
| 15-20 | 4.28 (66%) | 1.61 (44%) | 0.351 (40%) | 7.2e+04 (58%) | 18 |
| 20-30 | 4 (67%) | 2.05 (47%) | 0.431 (26%) | 6.6e+04 (64%) | 17 |

### `cell_2_vertical_left` (nominal=0.7719 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.16 (91%) | 1.95 (18%) | 0.124 (92%) | 7.71e+04 (35%) | 180 |
| 3-5 | 2.55 (75%) | 1.98 (23%) | 0.152 (78%) | 7.28e+04 (40%) | 72 |
| 5-10 | 3.5 (69%) | 1.91 (29%) | 0.215 (60%) | 6.84e+04 (48%) | 122 |
| 10-15 | 3.91 (69%) | 1.99 (35%) | 0.251 (52%) | 7.16e+04 (46%) | 49 |
| 15-20 | 4.92 (57%) | 1.93 (48%) | 0.329 (46%) | 7.21e+04 (50%) | 19 |
| 20-30 | 4.29 (68%) | 2.25 (43%) | 0.393 (37%) | 5.08e+04 (76%) | 21 |

### `cell_2_vertical_right` (nominal=0.5761 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.19 (85%) | 1.97 (21%) | 0.133 (87%) | 7.72e+04 (33%) | 207 |
| 3-5 | 3.59 (75%) | 1.92 (23%) | 0.183 (74%) | 7.26e+04 (44%) | 84 |
| 5-10 | 3.2 (79%) | 1.98 (29%) | 0.21 (61%) | 6.47e+04 (52%) | 93 |
| 10-15 | 3.78 (60%) | 1.91 (35%) | 0.243 (55%) | 7.35e+04 (45%) | 38 |
| 15-20 | 4.17 (68%) | 2.02 (48%) | 0.339 (44%) | 6.03e+04 (61%) | 25 |
| 20-30 | 4.58 (53%) | 2 (46%) | 0.385 (44%) | 6.31e+04 (70%) | 16 |

### `cell_3_vertical_left` (nominal=0.9300 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2.26 (95%) | 1.92 (16%) | 0.118 (87%) | 7.78e+04 (35%) | 160 |
| 3-5 | 2.28 (76%) | 1.89 (22%) | 0.154 (74%) | 7.29e+04 (43%) | 77 |
| 5-10 | 3.37 (70%) | 1.94 (28%) | 0.199 (66%) | 6.78e+04 (48%) | 117 |
| 10-15 | 3.76 (68%) | 2.08 (33%) | 0.243 (51%) | 6.87e+04 (46%) | 61 |
| 15-20 | 4.8 (54%) | 1.98 (45%) | 0.338 (48%) | 7.37e+04 (46%) | 26 |
| 20-30 | 3.97 (78%) | 2.2 (44%) | 0.395 (41%) | 5.97e+04 (61%) | 22 |

### `cell_3_vertical_right` (nominal=0.9310 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.96 (97%) | 1.87 (21%) | 0.128 (90%) | 7.82e+04 (33%) | 173 |
| 3-5 | 2.77 (78%) | 1.96 (20%) | 0.158 (80%) | 6.82e+04 (46%) | 85 |
| 5-10 | 3.67 (68%) | 1.99 (27%) | 0.215 (65%) | 6.66e+04 (51%) | 114 |
| 10-15 | 3.77 (61%) | 2.02 (32%) | 0.243 (52%) | 7.46e+04 (41%) | 46 |
| 15-20 | 4.53 (59%) | 2.03 (43%) | 0.312 (46%) | 7.14e+04 (52%) | 27 |
| 20-30 | 4.72 (57%) | 2.39 (41%) | 0.373 (41%) | 6.26e+04 (59%) | 18 |

### `bend1` (nominal=1.5570 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 2 (92%) | 1.99 (19%) | 0.117 (89%) | 7.83e+04 (31%) | 175 |
| 3-5 | 2.71 (72%) | 1.97 (24%) | 0.154 (69%) | 7.06e+04 (41%) | 83 |
| 5-10 | 3.74 (70%) | 1.9 (26%) | 0.209 (60%) | 6.53e+04 (53%) | 116 |
| 10-15 | 4.02 (64%) | 1.89 (38%) | 0.284 (52%) | 7.22e+04 (50%) | 53 |
| 15-20 | 4.37 (66%) | 1.95 (47%) | 0.367 (40%) | 6.72e+04 (55%) | 23 |
| 20-30 | 4.05 (64%) | 2.4 (44%) | 0.412 (37%) | 6.89e+04 (61%) | 13 |

### `e_x` (nominal=1.7820 mm)

| Perturb (um) | resonant_freq (CV%) | coupling_beta (CV%) | field_flatness (CV%) | peak_e_field (CV%) | n |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-3 | 1.86 (102%) | 2 (19%) | 0.113 (92%) | 7.88e+04 (31%) | 134 |
| 3-5 | 2.11 (80%) | 1.94 (18%) | 0.137 (79%) | 7.29e+04 (39%) | 83 |
| 5-10 | 3.21 (67%) | 1.94 (27%) | 0.204 (66%) | 7.01e+04 (46%) | 132 |
| 10-15 | 4.52 (54%) | 1.96 (40%) | 0.269 (54%) | 6.74e+04 (53%) | 68 |
| 15-20 | 4.58 (64%) | 1.98 (43%) | 0.307 (52%) | 7.11e+04 (52%) | 28 |
| 20-30 | 5.02 (56%) | 1.85 (35%) | 0.344 (37%) | 5.34e+04 (74%) | 18 |


## 8. Failure Rate by Level

| Level | Failure Rate |
|-------|-------------|
| 3 um | 0/62 (0.0%) |
| 5 um | 0/60 (0.0%) |
| 7 um | 1/60 (1.7%) |
| 10 um | 0/60 (0.0%) |
| 12 um | 2/60 (3.3%) |
| 15 um | 16/68 (23.5%) |
| 20 um | 16/60 (26.7%) |
| 25 um | 18/60 (30.0%) |
| 30 um | 69/95 (72.6%) |

---
*Report generated from 9 tolerance levels, 585 total records.*
