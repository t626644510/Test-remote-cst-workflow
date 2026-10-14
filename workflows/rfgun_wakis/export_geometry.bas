Sub Main
Dim i As Long, n As Long, k As Long
Dim fullname As String, cname As String, sname As String, mat As String
Open "MANIFEST" For Output As #1
Print #1, "index" & vbTab & "name" & vbTab & "material"
n = Solid.GetNumberOfShapes
For i = 0 To n
    fullname = Solid.GetNameOfShapeFromIndex(i)
    If Len(fullname) > 0 Then
        k = InStrRev(fullname, ":")
        If k = 0 Then Err.Raise 1001, , "Missing component in solid name"
        cname = Left(fullname, k-1)
        sname = Mid(fullname, k+1)
        mat = Solid.GetMaterialNameForShape(fullname)
        With STL
            .Reset
            .FileName "OUTDIR/solid_" & CStr(i) & ".stl"
            .Name sname
            .Component cname
            .ExportFromActiveCoordinateSystem False
            .ExportFileUnits "m"
            .NormalTolerance "10"
            .SurfaceTolerance "0.02"
            .WriteCAD
        End With
        Print #1, CStr(i) & vbTab & fullname & vbTab & mat
    End If
Next i
Close #1
End Sub
