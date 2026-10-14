"""Working-mode RF loss from shared-pole time-domain field amplitudes.

SI units: seconds, Hz, E V/m, H A/m, surface m^2, voltage V, power W.
Peak phasors use exp(+i*omega*t); power is 0.5*Re(Zs)*integral(|Ht|^2).
The same isolated mode is extracted from E and H, including half-step times.
This is 500 kV peak CW fundamental metal loss, not bunch/HOM heating.
"""
from dataclasses import dataclass
import numpy as np
from scipy.constants import c, mu_0
from scipy.optimize import least_squares


@dataclass(frozen=True)
class Pole:
    """Damped working-mode pole fitted from the simulated electric field."""
    frequency_hz: float
    decay_per_s: float
    reference_time_s: float
    relative_residual: float


def design(t_s: np.ndarray, pole: Pole) -> np.ndarray:
    """Real damped sinusoid and two nuisance drift columns."""
    tau = np.asarray(t_s)-pole.reference_time_s
    theta = 2*np.pi*pole.frequency_hz*tau
    envelope = np.exp(-pole.decay_per_s*tau)
    return np.column_stack((envelope*np.cos(theta),envelope*np.sin(theta),
                            np.ones(len(tau)),tau/max(float(np.ptp(tau)),1e-15)))


def project(t_s: np.ndarray, fields: np.ndarray, pole: Pole, window: str='hann') -> tuple:
    """Fit peak phasors independently in space with one shared complex pole."""
    b = design(t_s,pole)
    weight = np.sqrt(np.hanning(len(t_s))) if window=='hann' else np.ones(len(t_s))
    operator = np.linalg.pinv(b*weight[:,None])*weight[None,:]
    coef = operator@np.asarray(fields)
    return coef[0]-1j*coef[1],coef


def fit_pole(t_s: np.ndarray, electric: np.ndarray) -> Pole:
    """Find the dominant isolated 490--510 MHz pole without CST amplitudes/frequency.

The dominant spatial SVD projection is valid only when the working mode
dominates this axis-field signal. Residuals and independent windows are
reported rather than treating the assumption as guaranteed.
"""
    data = np.asarray(electric,dtype='f8')
    u,sv,_ = np.linalg.svd(data-data.mean(axis=0),full_matrices=False)
    signal = u[:,0]*sv[0]
    scale = np.linalg.norm(signal)
    ref = float(t_s[0])
    weight = np.sqrt(np.hanning(len(t_s)))
    def residual(x):
        pole=Pole(x[0]*1e6,x[1]*1e9,ref,0.)
        b=design(t_s,pole)
        coef=np.linalg.lstsq(b*weight[:,None],signal*weight,rcond=None)[0]
        return (b@coef-signal)*weight/scale
    result=least_squares(residual,[500.,.00001],bounds=([490.,0.],[510.,.02]),
                         x_scale=[1.,.0001],ftol=1e-12,xtol=1e-12,gtol=1e-12,max_nfev=300)
    if not result.success:
        raise RuntimeError('Working mode fit failed: '+result.message)
    rel=float(np.linalg.norm(residual(result.x))/np.linalg.norm(signal*weight/scale))
    return Pole(float(result.x[0]*1e6),float(result.x[1]*1e9),ref,rel)


def voltage(phasor: np.ndarray,z_mid_m: np.ndarray,dz_m: np.ndarray,frequency_hz: float) -> complex:
    """Beta=1 transit-time voltage from midpoint Ez samples, exp(+iwt).

Integrate only physical edges within the same +/-235.050544 mm CST path;
last Wakis padding/ghost edge has zero weight. A sinc factor integrates the
transit phase exactly assuming constant E on each edge.
"""
    lo,hi=-.235050544,.235050544
    a=np.maximum(z_mid_m-dz_m/2,lo)
    b=np.minimum(z_mid_m+dz_m/2,hi)
    width=np.maximum(0,b-a)
    center=(a+b)/2
    k=2*np.pi*frequency_hz/c
    weights=width*np.sinc(k*width/(2*np.pi))*np.exp(1j*k*center)
    return complex(np.sum(phasor*weights))


def power_w(h_peak: np.ndarray,area_m2: np.ndarray,rs_ohm: float,
            voltage_peak_v: float,target_peak_v: float=500000.) -> float:
    """Time-averaged CW component metal loss with peak field convention."""
    if voltage_peak_v<=0 or rs_ohm<=0 or not np.isfinite(h_peak).all():
        raise ValueError('Invalid mode normalization or surface field')
    h=np.asarray(h_peak).reshape(-1,3)
    return float(.5*rs_ohm*np.sum(area_m2*np.sum(abs(h)**2,axis=1))*(target_peak_v/voltage_peak_v)**2)


def copper_resistance(frequency_hz: float,conductivity: float=5.8e7) -> float:
    """Good-conductor Rs [ohm], nonmagnetic thick copper with sigma [S/m]."""
    return float(np.sqrt(np.pi*frequency_hz*mu_0/conductivity))
