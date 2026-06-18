# STEP Feature Detection Rules

All rules are candidate heuristics.  They never confirm a feature without human
review.

## Beam Pipe

Candidate evidence:

- cylindrical face;
- axisymmetric with respect to the requested beam axis;
- located near `z_min` or `z_max`;
- radius smaller than the largest cavity radius.

Outputs: `BeamPipeLeft`, `BeamPipeRight`, `BeamAperture`, `BeamExit`.

## Conducting Wall / Main Cavity Wall

Candidate evidence:

- axisymmetric cylindrical, toroidal, conical, surface-of-revolution, or
  spline-like face;
- large radius relative to the model;
- connected to other wall-like faces.

Output: `ConductingWall` with `default_boundary_role=electric`.

## Iris And Equator

Iris candidates are axisymmetric interior faces with small radius relative to
the largest cavity radius.  Equator candidates are axisymmetric interior faces
with large radius.

Outputs: `Iris`, `EquatorRegion`.

## Cathode And Nose Cone

For `xband_2.3cell_gun`, planar faces near `z_min` become cathode candidates.
Conical, toroidal, or spline-like near-axis transitions near cathode/iris
regions should be reviewed as nose-cone candidates.  v0 keeps these conservative
and expects user hints for reliable cathode/nose-cone separation.

Outputs: `CathodeSurface`, `TransitionBlend`; future versions may promote a
dedicated `NoseCone` rule after more labeled examples.

## Fillet / Chamfer / Transition Blend

Candidate evidence:

- toroidal, conical, spline-like, or small-radius cylindrical face;
- radius small relative to main cavity radius;
- adjacent to at least two other faces.

Output: `TransitionBlend`.

## Coupler / Side Port

Candidate evidence:

- not axisymmetric with respect to the beam axis;
- located away from the beam axis on the side wall;
- normal estimate not parallel to the beam axis.

Output: `UnknownSidePort`.  Humans should refine it to `InputCouplerPort`,
`WaveguidePort`, or `CoaxialPort` where appropriate.

## Hints

Useful hints include:

- known cathode or beam-exit approximate location;
- expected features for a model family;
- manually confirmed face refs from a prior review;
- whether a side opening is a coupler, pickup, pump port, or artifact.
