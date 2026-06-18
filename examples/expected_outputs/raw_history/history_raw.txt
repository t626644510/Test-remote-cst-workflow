' History Item: set project units
With Units
     .SetUnit "Length", "mm"
     .SetUnit "Frequency", "GHz"
     .SetUnit "Time", "ns"
     .SetUnit "Temperature", "K"
End With

' History Item: store cavity parameters
StoreParameter "cavity_radius", "42.0"
StoreParameter "cell_length", "115.0"

' History Item: define copper material
With Material
     .Reset
     .Name "OFHC_Copper"
     .Folder "CavityMaterials"
     .Type "Normal"
     .Epsilon "1.0"
     .Mu "1.0"
     .Sigma "5.8e7"
     .Create
End With

' History Item: import baseline geometry
With STEP
     .Reset
     .FileName "baseline_cavity.step"
     .ScaleToUnit "False"
     .ImportToActiveCoordinateSystem "True"
     .Import
End With

' History Item: create vacuum cylinder
With Cylinder
     .Reset
     .Name "rf_vacuum"
     .Component "vacuum"
     .Material "Vacuum"
     .OuterRadius "20"
     .Zrange "-50", "50"
     .Create
End With

' History Item: global boundary conditions
With Boundary
     .Xmin "electric"
     .Xmax "electric"
     .Ymin "electric"
     .Ymax "electric"
     .Zmin "magnetic"
     .Zmax "open"
     .ApplyInAllDirections "False"
End With

' History Item: waveguide input port
With WaveguidePort
     .Reset
     .PortNumber "1"
     .Label "input_coupler"
     .NumberOfModes "1"
     .AdjustPolarization "False"
     .Create
End With

' History Item: global mesh setup
With Mesh
     .Reset
     .LinesPerWavelength "20"
     .MinimumStepNumber "5"
     .UseRatioLimit "True"
End With

' History Item: eigenmode solver settings
ChangeSolverType "Eigenmode"
With EigenmodeSolver
     .Reset
     .Modes "5"
     .Accuracy "1e-6"
     .StoreResultsInCache "False"
End With

' History Item: e field monitor
With Monitor
     .Reset
     .Name "E-field 1.3GHz"
     .Domain "Frequency"
     .FieldType "Efield"
     .Frequency "1.3"
     .Create
End With

' History Item: result template q factor
With ResultTemplate
     .Reset
     .Name "Q Factor"
     .Type "0D"
     .Evaluate
End With

' History Item: export 3d fields
With FieldExport
     .Reset
     .FileName "exports/e_field_mode1.h5"
     .Mode "FixedNumber"
     .Step "1"
     .Execute
End With
