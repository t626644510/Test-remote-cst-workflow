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
python.exe : Traceback (most recent call last):
At line:1 char:99
+ ... \cst_ver3"; & $python temp_analysis\analyze_tolerance.py 2>&1 | Out-F ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (Traceback (most recent call last)::String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
  File "C:\Users\lau\cst_ver3\temp_analysis\analyze_tolerance.py", line 353, in <module>
    main()
  File "C:\Users\lau\cst_ver3\temp_analysis\analyze_tolerance.py", line 272, in main
    cfg = _yaml.safe_load(fh)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\__init__.py", line 125, in safe_load
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


## 5. Tolerance Recommendation

    return load(stream, SafeLoader)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\__init__.py", line 81, in load
    return loader.get_single_data()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\constructor.py", line 49, in get_single_data
    node = self.get_single_node()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 36, in get_single_node
    document = self.compose_document()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 55, in compose_document
    node = self.compose_node(None, None)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 84, in compose_node
    node = self.compose_mapping_node(anchor)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 133, in compose_mapping_node
    item_value = self.compose_node(node, item_key)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 84, in compose_node
    node = self.compose_mapping_node(anchor)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 133, in compose_mapping_node
    item_value = self.compose_node(node, item_key)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 82, in compose_node
    node = self.compose_sequence_node(anchor)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 111, in compose_sequence_node
    node.value.append(self.compose_node(node, index))
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 84, in compose_node
    node = self.compose_mapping_node(anchor)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 133, in compose_mapping_node
    item_value = self.compose_node(node, item_key)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\composer.py", line 64, in compose_node
    if self.check_event(AliasEvent):
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\parser.py", line 98, in check_event
    self.current_event = self.state()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\parser.py", line 449, in parse_block_mapping_value
    if not self.check_token(KeyToken, ValueToken, BlockEndToken):
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\scanner.py", line 116, in check_token
    self.fetch_more_tokens()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\scanner.py", line 255, in fetch_more_tokens
    return self.fetch_plain()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\scanner.py", line 679, in fetch_plain
    self.tokens.append(self.scan_plain())
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\scanner.py", line 1305, in scan_plain
    spaces = self.scan_plain_spaces(indent, start_mark)
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\scanner.py", line 1332, in scan_plain_spaces
    self.forward()
  File "C:\Users\lau\cst_ver3\.venv\lib\site-packages\yaml\reader.py", line 106, in forward
    if ch in '\n\x85\u2028\u2029'  \
TypeError: 'in <string>' requires string as left operand, not int
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

