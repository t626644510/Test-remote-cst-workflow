"""Regression of the later validated missing-tail method, with no CST needed."""
from dataclasses import replace
import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative
from workflows.rfgun_wake_thermal.measured_tail import (
    C,ProjectedResidual,TailFit,fit_tail,raw_transform,pencil_seeds)
from workflows.rfgun_wake_thermal.reconstruction import direct_spectrum,reconstruct
from workflows.rfgun_wake_thermal.config import Physics,Reconstruction

pytestmark=pytest.mark.no_cst


def test_joint_variable_projection_jacobian():
    s=np.linspace(1,30,901);p=np.array([800.,1200.,.02,.04])
    rng=np.random.default_rng(53)
    y=np.column_stack([np.sin(2*np.pi*8e8*s/C),np.cos(2*np.pi*1.2e9*s/C),np.sin(2*np.pi*1.2e9*s/C),np.cos(2*np.pi*8e8*s/C)])
    y+=rng.normal(0,.001,y.shape)
    model=ProjectedResidual(s,y)
    numerical=approx_derivative(lambda v:model.calculate(v)['residual'].ravel(),p,method='3-point',rel_step=1e-5)
    np.testing.assert_allclose(model.calculate(p)['jacobian'],numerical,atol=1e-6,rtol=2e-4)


@pytest.mark.parametrize('direction',['longitudinal','transverse'])
def test_full_measured_czt_matches_direct_with_nonzero_origin(direction):
    s=np.linspace(-.45,35,20001);w=np.column_stack([np.cos(2*np.pi*8e8*s/C),np.sin(2*np.pi*1.2e9*s/C)])
    f=np.linspace(550e6,2e9,97)
    np.testing.assert_allclose(raw_transform(s,w,f,.05,direction),direct_spectrum(s,w,f,.05,direction),rtol=1e-7,atol=1e-7)
    s=s+1e-5*np.sin(s)
    np.testing.assert_allclose(raw_transform(s,w,f[::11],.05,direction),direct_spectrum(s,w,f[::11],.05,direction),rtol=1e-10,atol=1e-8)


def test_missing_tail_matches_reference_formula_and_does_not_extend_dc():
    f=np.array([810e6,1294e6]);a=np.array([.003,.06]);co=np.array([[.03,-.1],[.04,.02],[.02,.04],[-.01,.01],[999.,-888.]])
    model=TailFit(f,a,co,3.,19.,np.zeros(2,dtype=bool),True,0.,1.)
    grid=np.array([810e6,812e6,1294e6]);k=2*np.pi*f/C;kf=2*np.pi*grid/C
    old=np.zeros((len(grid),2),complex)
    for j in range(2):
        residue=(co[j]-1j*co[2+j])*np.exp(a[j]*3-1j*k[j]*19)
        p=a[j]+1j*(kf-k[j]);pn=a[j]+1j*(kf+k[j])
        old+=.5*(residue*np.exp(-p*35)[:,None]/p[:,None]+residue.conj()*np.exp(-pn*35)[:,None]/pn[:,None])
    old*=-1e12/C/np.exp(-.5*(kf*.05)**2)[:,None]
    np.testing.assert_allclose(model.tail(35,grid,.05,'longitudinal'),old,rtol=1e-12)
    np.testing.assert_allclose(model.tail(35,grid,.05,'transverse'),-1j*old,rtol=1e-12)
    # Historical failure: extending a rapid-decay fit back to zero magnifies noise.
    rapid=replace(model,alpha=np.full(2,4.),start_m=3.)
    assert np.max(abs(rapid.tail(35,grid,.05,'longitudinal')))<1e-45


def test_free_phase_joint_poles_and_prefix_prediction():
    s=np.linspace(1,35,3001);f=np.array([800e6,1294e6]);a=np.array([.025,.06])
    co=np.array([[.2,-.1,.02,.4],[.1,.2,-.3,.05],[.1,.03,.07,.2],[-.1,.2,.2,.3],[.001,0,0,.002]])
    truth=TailFit(f,a,co,1.,18.,np.zeros(2,dtype=bool),True,0.,1.)
    w=truth.predict(s);seeds=pencil_seeds(s,w,(4,), (100e6,2e9),(1e-9,4.))[0]
    assert seeds[0]==pytest.approx(f,rel=1e-6)  # DC is a fifth, deliberately unseeded subspace column.
    cut=s<28;fit=fit_tail(s[cut],w[cut],*seeds,10e6,(1e-9,4.),100)
    assert fit.success and fit.error<1e-8
    np.testing.assert_allclose(fit.predict(s[~cut]),w[~cut],atol=1e-8)
    grid=np.linspace(700e6,1400e6,100)
    np.testing.assert_allclose(fit.tail(35,grid,.05,'transverse'),truth.tail(35,grid,.05,'transverse'),atol=1e-5)


def test_unresolved_window_cannot_supply_gp_or_success(monkeypatch):
    # One bound-controlled persistent pole must never be silently dropped.
    import workflows.rfgun_wake_thermal.tail_ensemble as module
    original=module.fit_tail
    def bounded(*args,**kwargs):
        result=original(*args,**kwargs);result.boundary[:]=True;return result
    monkeypatch.setattr(module,'fit_tail',bounded)
    s=np.linspace(-.2,35,12000);w=np.cos(2*np.pi*8e8*s/C)*np.exp(-.002*np.maximum(s,0));w[s<0]=0
    p=replace(Physics(),band_hz=(700e6,900e6),sigma_m=.01)
    r=replace(Reconstruction(),pencil_ranks=(2,2,2),pencil_rows=80,fit_points=1000,spectrum_points=300)
    result=reconstruct(s,w,p,r,'longitudinal',1e9)
    assert result.value is None and result.status=='uncertain'
    assert 'unresolved_peak_windows' in result.reasons
    assert result.diagnostics['decision']=='unresolved'


def test_baseline_admission_distinguishes_reliable_rejection_from_precise_metrics():
    from workflows.rfgun_wake_thermal.campaign import baseline_admission
    d=dict(status='uncertain',diagnostics=dict(decision='exceeds',fits=[dict(valid=True)]*6))
    c=dict(complete=True,metrics={'power5':180.,'power6':170.},
           details=dict(longitudinal=d,transverse=d,thermal=dict(status='valid')))
    assert baseline_admission(c)['ready']
    assert set(c['metrics'])=={'power5','power6'}  # no fictitious impedance samples
    assert baseline_admission(c)['evidence']['longitudinal']=='exceeds_without_scalar'
    c['details']['longitudinal']=dict(status='uncertain',diagnostics=dict(decision='unresolved',fits=[dict(valid=True)]*6))
    assert not baseline_admission(c)['ready']
    c['details']['longitudinal']=dict(status='uncertain',diagnostics=dict(decision='exceeds',fits=[dict(valid=False)]))
    assert not baseline_admission(c)['ready']
