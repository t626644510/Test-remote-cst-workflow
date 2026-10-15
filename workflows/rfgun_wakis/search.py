"""Robust partial-observation GP search for the fifteen-dimensional domain.

Each GP learns a reconstructed RF peak or CW power, never a direct-FT proxy.
All six metrics keep their own observed coordinates and sensitivity noise.
The acquisition is an explicit engineering utility, not a physical bound.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Sequence
import warnings
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern
from .config import Config
from .geometry import Geometry
from .observations import METRICS, Observation
from .trust import reference

@dataclass
class Sample:
    """One independent geometry with any subset of valid search observations."""
    parameters: dict[str,float]
    observations: dict[str,Observation]

def utility(values: np.ndarray, config: Config) -> np.ndarray:
    """Dimensionless search utility, lower is better; heat has no stop target.

    Longitudinal excess is weighted first, leakage is a basic constraint,
    while heat and X transverse continue improving inside the L threshold.
    These soft weights rank acquisition draws, never certify feasibility.
    """
    p=config.physics
    scale=np.array([p.longitudinal_limit,p.transverse_limit,p.power_reference_w,
                    p.power_reference_w,p.leakage_limit_w,p.leakage_limit_w])
    v=np.maximum(values,0)/scale
    return (8*np.maximum(v[...,0]-1,0) + 6*np.maximum(v[...,4:6]-1,0).sum(axis=-1)
            + np.maximum(v[...,1]-1,0) + .5*v[...,1] + np.max(v[...,2:4],axis=-1))

class Proposer:
    """Independent heteroscedastic GPs with deterministic reproducible proposals."""
    def __init__(self,config:Config):
        self.config=config;self.geometry=Geometry(config)

    def scales(self) -> dict[str,float]:
        """Physical reference scales: ohm, ohm/metre, then four CW watts."""
        p=self.config.physics
        return dict(zip(METRICS,(p.longitudinal_limit,p.transverse_limit,p.power_reference_w,
                                p.power_reference_w,p.leakage_limit_w,p.leakage_limit_w)))

    def training_reason(self,obs:Observation) -> str | None:
        """Quarantine unsupported scales without deleting or changing evidence.

        An unbounded peak may guide a noisy trend only when its finite lower
        envelope still identifies the same order of magnitude (factor <=4).
        This engineering policy is explicit, not an invented physical bound.
        """
        if not obs.search_eligible:return 'reference_or_incomplete'
        if obs.contradictory:return 'contradictory_evidence'
        if obs.upper is None:
            if (obs.lower is None or obs.lower<=0 or
                obs.estimate/obs.lower>self.config.search.unbounded_max_scale_ratio or
                obs.relative_uncertainty>self.config.search.unbounded_max_relative):
                return 'unbounded_scale_unidentified'
        return None

    def training(self,samples:Sequence[Sample],metric:str) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
        rows={}
        for sample in samples:
            obs=sample.observations.get(metric)
            if obs is None or self.training_reason(obs) or self.geometry.violations(sample.parameters):continue
            key=tuple(sample.parameters[n] for n in self.config.active_names)
            rows[key]=(sample,obs)
        x=[];y=[];noise=[]
        for sample,obs in rows.values():
            x.append(self.geometry.normalize(sample.parameters))
            y.append(np.log1p(obs.estimate))
            rel=max(obs.relative_uncertainty,self.config.search.native_relative_noise)
            # Delta in log1p(value), divided by the measured y scale at fit time.
            relative=np.log1p(obs.estimate*(1+rel))-np.log1p(obs.estimate)
            absolute=np.log1p(obs.estimate+self.scales()[metric]*self.config.search.absolute_noise_fraction)-np.log1p(obs.estimate)
            quality=(0. if obs.qualified else self.config.search.uncertain_log_noise
                     if obs.upper is not None else self.config.search.unbounded_log_noise)
            noise.append(max(relative,absolute,quality))
        return np.asarray(x),np.asarray(y),np.asarray(noise)

    def choose(self,samples:Sequence[Sample],*,sequence:int,radius:float,
               explore:bool,excluded:Sequence[Mapping[str,float]]=(),trust_generation:int=0) -> tuple[dict,dict]:
        rng=np.random.default_rng(self.config.search.seed+sequence)
        g=self.geometry;n=self.config.search.pool
        supported=[s for s in samples if reference(s.observations) and not g.violations(s.parameters)]
        center=None;center_sample=None
        if supported and not explore:
            # A useful axis-only candidate may be a center. Unknown metrics
            # receive an explicit ranking prior, never fake training values.
            ranked=[utility(np.array([s.observations[k].ranking_value if k in s.observations
                       and self.training_reason(s.observations[k]) is None else 2*v
                       for k,v in self.scales().items()]),self.config) for s in supported]
            center_sample=supported[int(np.argmin(ranked))];center=center_sample.parameters
        candidates=g.sample(rng,n//2,center,radius) + g.sample(rng,n-n//2)
        seen=[g.normalize(p) for p in list(excluded)+[s.parameters for s in samples]]
        if seen:
            old=np.asarray(seen)
            candidates=[p for p in candidates if np.min(np.linalg.norm(old-g.normalize(p),axis=1))>1e-7]
        if not candidates:raise RuntimeError('No nonduplicate proposal')
        x=np.array([g.normalize(p) for p in candidates]);models={};audit={}
        for metric in METRICS:
            train,y,noise=self.training(samples,metric)
            quarantined=[dict(parameters=s.parameters,reason=self.training_reason(s.observations[metric]))
                         for s in samples if metric in s.observations and self.training_reason(s.observations[metric])]
            audit[metric]={'independent_points':len(y),'quarantined':quarantined}
            if len(y)<self.config.search.gp_min_samples:continue
            scale=max(float(np.std(y)),1e-6)
            alpha=np.maximum((noise/scale)**2,1e-10)
            gp=GaussianProcessRegressor(kernel=ConstantKernel(1.,(.05,20.))*Matern(
                length_scale=np.ones(len(self.config.active_names)),length_scale_bounds=(.05,5.),nu=2.5),
                alpha=alpha,normalize_y=True,n_restarts_optimizer=0,random_state=sequence)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',ConvergenceWarning);gp.fit(train,y)
            mean,std=gp.predict(x,return_std=True);models[metric]=(mean,std)
            audit[metric].update(noise_log_std_min=float(noise.min()),alpha_min=float(alpha.min()),kernel=str(gp.kernel_))
        effective_points=sum(any(self.training_reason(o) is None for o in sample.observations.values()) for sample in samples)
        if effective_points<self.config.search.initial_points or 'longitudinal' not in models:
            chosen=int(rng.integers(len(candidates)));method='feasible_global_initial_design'
        else:
            # Smooth pointwise confidence-bound utility avoids selecting the
            # most extreme of thousands of independent random draws. Constraint
            # metrics use upper predictive quantiles; X/heat use lower ones.
            # These are acquisition scores only, never qualification bounds.
            scales=[self.config.physics.longitudinal_limit,self.config.physics.transverse_limit,
                    self.config.physics.power_reference_w,self.config.physics.power_reference_w,
                    self.config.physics.leakage_limit_w,self.config.physics.leakage_limit_w]
            draws=[]
            for k,s in zip(METRICS,scales):
                mu,sd=models.get(k,(np.full(len(x),np.log1p(s)),np.full(len(x),1.)))
                sign=1 if k in ('longitudinal','leak_2','leak_3') else -1
                draws.append(np.maximum(0,np.expm1(np.clip(mu+sign*self.config.search.acquisition_beta*sd,-20,35))))
            score=utility(np.array(draws).T,self.config)
            if explore:
                # Forced global proposals remain unconstrained by the current
                # longitudinal gate. Prefer novelty, retain partial observations.
                distance=np.min(np.linalg.norm(x[:,None,:]-np.array(seen)[None,:,:],axis=2),axis=1) if seen else np.ones(len(x))
                chosen=int(np.argmax(distance));method='global_cross_gate_exploration'
            else:chosen=int(np.argmin(score));method='robust_partial_GP_confidence_utility'
        is_local=center is not None and bool(np.all(abs(g.normalize(candidates[chosen])-g.normalize(center))<=radius+1e-12))
        return candidates[chosen],dict(method=method,sequence=sequence,radius=radius,local_proposal=is_local,
            forced_transverse=explore,training=audit,reference_records_used=False,
            center_parameters=center,trust_generation=trust_generation,
            trust_reference=reference(center_sample.observations) if is_local else None)

def comparable_improvement(old:Observation,new:Observation) -> bool:
    """Only disjoint finite envelopes count; failure/overlap cannot shrink radius."""
    return bool(old.lower is not None and old.upper is not None and new.lower is not None
                and new.upper is not None and not old.contradictory and not new.contradictory
                and new.upper < old.lower)
