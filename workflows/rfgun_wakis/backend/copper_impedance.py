"""Passive causal good-conductor surface impedance; SI units.

For a nonmagnetic thick conductor, Z(s)=sqrt(mu/sigma)*sqrt(s). Under exp(+iwt),
Z(iw)=(1+i)*sqrt(w*mu/(2*sigma)) ohm. Positive quadrature of
sqrt(s)=(2/pi)*integral_0^infinity s/(s+t^2) dt gives stable real negative
poles and positive residues. No cavity frequency/decay is used for fitting.
This is a boundary constitutive law, not a volume conductivity in S/m.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from scipy.constants import mu_0

@dataclass
class CopperSurfaceImpedance:
    conductivity_S_per_m:float=5.8e7
    mu_H_per_m:float=mu_0
    terms:int=96
    pole_min_Hz:float=1e-6
    pole_max_Hz:float=1e22

    def coefficients(self):
        lo,hi=.5*np.log(2*np.pi*np.array([self.pole_min_Hz,self.pole_max_Hz]))
        du=(hi-lo)/self.terms
        t=np.exp(lo+(np.arange(self.terms)+.5)*du)
        poles=t*t
        resistances=2/np.pi*np.sqrt(self.mu_H_per_m/self.conductivity_S_per_m)*t*du
        return poles,resistances

    def frequency_response(self,f_Hz):
        p,r=self.coefficients();s=2j*np.pi*np.asarray(f_Hz)
        return np.sum(r[:,None]*s[None,:]/(s[None,:]+p[:,None]),axis=0)

    def recurrence(self,dt_s):
        p,r=self.coefficients();v=p*dt_s
        # For piecewise-linear H, w=H-lowpass(H):
        # w_next=alpha*w_old+beta*(H_next-H_old), E=sum R*w_next.
        return np.exp(-v),-np.expm1(-v)/v,r

def validate():
    root=Path(__file__).absolute().parent
    model=CopperSurfaceImpedance()
    f=np.geomspace(1e5,5e9,2000)
    ideal=(1+1j)*np.sqrt(np.pi*f*mu_0/5.8e7)
    actual=model.frequency_response(f)
    p,r=model.coefficients()
    assert np.all(p>0) and np.all(r>0)
    assert np.all(actual.real>=0)
    error=float(np.max(abs(actual/ideal-1)))
    assert error<1e-4
    curves=np.load(root/'curves.npz')
    cf=curves['curve_6_x']*1e6
    keep=cf>0
    cideal=curves['curve_6_y']+1j*curves['curve_8_y']
    cerr=float(np.max(abs(model.frequency_response(cf[keep])/cideal[keep]-1)))
    # Transfer-function check of the actual finite-time recurrence in float32.
    # Applied H is sinusoidal, 500 MHz; measure settled E/H complex amplitude.
    dt=4e-12;freq=500e6
    alpha,beta,R=model.recurrence(dt)
    alpha,beta,R=alpha.astype('f4'),beta.astype('f4'),R.astype('f4')
    memory=np.zeros(model.terms,dtype='f4');old=np.float32(0)
    tt=np.arange(60000)*dt;field=np.zeros_like(tt)
    for i,t in enumerate(tt):
        h=np.float32(np.sin(2*np.pi*freq*t))
        memory=alpha*memory+beta*(h-old);old=h
        field[i]=np.dot(R,memory)
    chosen=tt>tt[-1]-40e-9
    basis=np.column_stack([np.sin(2*np.pi*freq*tt[chosen]),np.cos(2*np.pi*freq*tt[chosen]),np.ones(chosen.sum())])
    fit=np.linalg.lstsq(basis,field[chosen],rcond=None)[0]
    target=(1+1j)*np.sqrt(np.pi*freq*mu_0/5.8e7)
    recurrence_error=float(abs((fit[0]+1j*fit[1])/target-1))
    assert recurrence_error<.003
    result=dict(status='constitutive_law_validated_not_yet_spatial_boundary',terms=model.terms,
        sigma_S_per_m=5.8e7,validation_band_Hz=[1e5,5e9],maximum_complex_relative_error=error,
        maximum_relative_error_against_saved_CST_theory=cerr,
        float32_recurrence_500MHz_dt4ps_relative_error=recurrence_error,
        all_poles_stable=True,all_residues_positive=True,
        formula='Z(s)=sqrt(mu/sigma)*sqrt(s); E_t=Z(s)*(H_t cross n)',
        limitations='Constitutive test only. Spatial coupling, energy and reflection still require verification.')
    (root/'copper_constitutive_validation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':validate()
