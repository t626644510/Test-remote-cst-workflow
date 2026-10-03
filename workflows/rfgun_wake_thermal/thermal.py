"""Working-mode component losses at peak 500 kV, CW, beta=1.

QFactor ASCII and VectorPlot3D APIs verified in WF5 and loss_field_probe_20260923.
No port power or HOM heating is added; exported losses already are time averages.
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
from .config import Physics
from .reconstruction import C


def quote(value:object)->str:
    s=str(value)
    if '\n' in s or '\r' in s:raise ValueError('Invalid VBA string')
    return '"'+s.replace('"','""')+'"'


def voltage_vba(mode:int,out:Path,p:Physics)->str:
    """Collect complex axial Ez (V/m), on global z in model millimetres."""
    n=p.thermal_z_samples;z0,z1=p.thermal_z_range_mm
    return '\n'.join(['Option Explicit','Sub Main','Dim j As Long,fo As Integer',
        'Dim xr As Double,yr As Double,zr As Double,xi As Double,yi As Double,zi As Double,ok As Boolean',
        f'If Not SelectTreeItem("2D/3D Results\\Modes\\Mode {mode}\\e") Then Err.Raise 1001',
        'VectorPlot3D.Reset',f'For j=0 To {n-1}',f'VectorPlot3D.AddListItem 0,0,{z0:.15g}+{z1-z0:.15g}*j/{n-1}',
        'Next j','VectorPlot3D.CalculateList',f'If VectorPlot3D.GetListLength <> {n} Then Err.Raise 1002',
        'fo=FreeFile',f'Open {quote(out)} For Output As #fo','Print #fo,"Ez_real,Ez_imag,valid"',
        f'For j=0 To {n-1}','ok=VectorPlot3D.GetListItem(j,xr,yr,zr,xi,yi,zi)',
        'Print #fo,Trim$(Str$(zr)) & "," & Trim$(Str$(zi)) & "," & CStr(CInt(ok))',
        'Next j','Close #fo','VectorPlot3D.Reset','End Sub'])


def losses_vba(mode:int,out:Path,p:Physics)->str:
    """Use verified QFactor solid loss export; do not enable expensive 3D loss field."""
    return '\n'.join(['Option Explicit','Sub Main','With QFactor','.Reset',
        f'.SetHField "2D/3D Results\\Modes\\Mode {mode}\\h"',
        *[f'.SetConductivity {quote(k)}, {quote(format(v,".15g"))}' for k,v in p.conductivity_s_per_m.items()],
        '.UseNewMethod True','.Save3DData False','.Calculate',f'.ASCIIExport {quote(out)}','End With','End Sub'])


def analyze_thermal(folder:Path,frequency_hz:float,p:Physics)->dict:
    """Validate frequency/energy evidence and normalize all solids per component."""
    text=(folder/'losses.txt').read_text(encoding='utf-8-sig',errors='replace')
    meta={}
    for k in ('Frequency/Hz','Energy/J'):
        m=re.search(re.escape(k)+r'\s+([\d.Ee+\-]+)',text)
        if not m:raise ValueError('Missing QFactor metadata: '+k)
        meta[k]=float(m.group(1))
    if not np.isfinite(list(meta.values())).all() or meta['Energy/J']<=0 or abs(meta['Frequency/Hz']/frequency_hz-1)>1e-6:
        raise ValueError('Mismatched field/loss normalization')
    lines={}
    for line in text.splitlines():
        m=re.match(r'\s+(.+?:.+?)\s+([\d.Ee+\-]+)\s+([\d.Ee+\-]+)\s*$',line)
        if m:
            if m.group(1) in lines:raise ValueError('Duplicate loss solid')
            lines[m.group(1)]=float(m.group(2))
    losses={c:{k:v for k,v in lines.items() if k.rsplit(':',1)[0]==c} for c in p.components}
    if any(not v for v in losses.values()) or not np.isfinite(list(lines.values())).all() or any(v<0 for v in lines.values()):
        raise ValueError('Missing or invalid antenna component losses')
    data=np.loadtxt(folder/'voltage.csv',delimiter=',',skiprows=1,ndmin=2)
    if data.shape!=(p.thermal_z_samples,3) or not np.isfinite(data).all() or not np.all(data[:,2]!=0):
        raise ValueError('Invalid voltage samples')
    z=np.linspace(*p.thermal_z_range_mm,p.thermal_z_samples)*1e-3
    integrand=(data[:,0]+1j*data[:,1])*np.exp(2j*np.pi*frequency_hz*z/C)
    voltage=abs(np.trapz(integrand,z));half=abs(np.trapz(integrand[::2],z[::2]))
    if voltage<=1e-12 or abs(voltage-half)/voltage>.01:raise ValueError('Voltage integration unstable or zero')
    factor=(p.voltage_peak_v/voltage)**2
    powers=[sum(losses[c].values())*factor for c in p.components]
    return dict(status='valid',frequency_hz=frequency_hz,voltage_peak_v=voltage,target_voltage_peak_v=p.voltage_peak_v,
                scale=factor,power5=powers[0],power6=powers[1],components=losses,energy_j=meta['Energy/J'],
                voltage_half_error=abs(voltage-half)/voltage,assumptions='CW; peak cavity voltage; beta=1; fundamental metal losses only')
