"""Partial-observation, cost-aware sequential GP search in normalized coordinates."""
from __future__ import annotations
import warnings
import numpy as np
from scipy.special import ndtr
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel,Matern,WhiteKernel
from .config import Config,NAMES
from .geometry import Geometry
from .screening import search_view

METRICS=('longitudinal','transverse','power5','power6')


def axis_observed(candidate:dict)->bool:
    """Count trustworthy categorical exceedances toward initial coverage, not GP data."""
    if 'longitudinal' in candidate.get('metrics',{}):return True
    d=candidate.get('details',{}).get('longitudinal',{}).get('diagnostics',{})
    fits=d.get('fits',[])
    return bool('axis' in candidate.get('stages',{}) and d.get('decision')=='exceeds' and fits and all(f.get('valid') for f in fits))


class Controller:
    """Four independent GPs; numerical failures and unobserved metrics never become penalties."""
    def __init__(self,config: Config,state: dict):
        self.config=config;self.state=state;self.geometry=Geometry(config)
        self.rng=np.random.default_rng(config.search.seed)
        if state.get('rng'):self.rng.bit_generator.state=state['rng']
        self.lower=np.array([config.bounds[n][0] for n in NAMES]);self.width=np.array([config.bounds[n][1]-config.bounds[n][0] for n in NAMES])
        self.limits=np.array([config.physics.longitudinal_limit,config.physics.transverse_limit,*([config.physics.power_reference_w]*2)])
        self.models={}

    @property
    def candidates(self):
        return [search_view(self.config,c) for c in self.state['candidates']]

    def training_rows(self,metric):
        """Metric-wise native replacement of audited common-band historical proxies.

        Historical wakes (ohm or ohm/m) inform regression only, never current
        feasibility, stage quotas, budget, or radius changes. Thermal watts
        use native noise because the validated CW working-mode physics is shared.
        """
        rows={}
        def add(candidate,historical):
            value=candidate.get('metrics',{}).get(metric)
            if not isinstance(value,(int,float)) or not np.isfinite(value) or value<0:return
            if self.geometry.violations(candidate['parameters']):return
            key=tuple(np.round(self.encode(candidate['parameters']),10))
            noise=self.config.search.history_relative_noise if historical and metric in METRICS[:2] else self.config.search.native_relative_noise
            rows[key]=(candidate,float(value),noise,historical)
        if self.config.search.observation_mode=='finite_tail_screening':
            for c in self.state.get('historical_observations',[]):
                if (c.get('source_kind')!='common_band_history' or not c.get('evidence_verified')
                    or list(c.get('band_hz',[]))!=list(self.config.physics.band_hz)
                    or c.get('wake_length_m')!=self.config.physics.wake_length_m):continue
                add(c,True)
        for c in self.candidates:add(c,False)
        return list(rows.values())

    def encode(self,p):return (np.array([p[n] for n in NAMES])-self.lower)/self.width
    def decode(self,x):return dict(zip(NAMES,map(float,self.lower+self.width*np.asarray(x))))

    def pool(self,center=None):
        result=[]
        for _ in range(100):
            x=self.rng.random((self.config.search.pool,12))
            if center is not None:
                n=len(x)//2;x[:n]=np.clip(center+self.rng.uniform(-self.state['radius'],self.state['radius'],(n,12)),0,1)
            for row in x:
                if not self.geometry.violations(self.decode(row)):result.append(row)
            if len(result)>=self.config.search.pool:break
        if not result:raise ValueError('No feasible points found in configured domain')
        return np.asarray(result[:self.config.search.pool])

    def fit(self):
        self.models={}
        for k,limit in zip(METRICS,self.limits):
            rows=self.training_rows(k)
            if len(rows)<self.config.search.gp_min_samples:continue
            x=np.array([self.encode(c['parameters']) for c,_,_,_ in rows]);ratio=np.array([v/limit for _,v,_,_ in rows]);y=np.log1p(ratio)
            # alpha is variance in normalized log1p units, not ohm^2 or W^2.
            # Convert configured relative uncertainty before sklearn normalizes y.
            relative=np.array([noise for _,_,noise,_ in rows])
            uncertainty=np.maximum(np.log1p(ratio*(1+relative))-y,1e-6)
            scale=float(np.std(y));scale=scale if scale>1e-15 else 1.
            alpha=(uncertainty/scale)**2
            try:
                kernel=ConstantKernel(1.,(.01,100.))*Matern(np.ones(12),(.03,5.),nu=2.5)+WhiteKernel(1e-5,(1e-8,.05))
                model=GaussianProcessRegressor(kernel=kernel,alpha=alpha,normalize_y=True,random_state=self.config.search.seed,n_restarts_optimizer=0)
                with warnings.catch_warnings():warnings.simplefilter('ignore');model.fit(x,y)
                self.models[k]=model
            except (ValueError,np.linalg.LinAlgError):continue

    def predictions(self,x):
        result={}
        for k in METRICS:
            if k in self.models:result[k]=self.models[k].predict(x,return_std=True)
            else:result[k]=(np.full(len(x),np.log(2.)),np.ones(len(x)))
        return result

    def score(self,x,cost,observed=None):
        """MC heat EI × impedance feasibility / remaining seconds, else worst violation."""
        pred=self.predictions(x)
        if observed:
            for k,v in observed.items():pred[k]=(np.full(len(x),np.log1p(v/self.limits[METRICS.index(k)])),np.zeros(len(x)))
        feasible=[c for c in self.candidates if c.get('feasible') and all(k in c['metrics'] for k in METRICS)]
        probability=np.ones(len(x))
        for k in METRICS[:2]:
            mean,std=pred[k];probability*=ndtr((np.log(2.)-mean)/np.maximum(std,1e-9))
        if feasible:
            best=min(max(c['metrics']['power5'],c['metrics']['power6'])/self.limits[2] for c in feasible)
            samples=[]
            for k in METRICS[2:]:
                mean,std=pred[k];samples.append(np.expm1(np.clip(mean[None,:]+std[None,:]*self.rng.standard_normal((64,len(x))),-10,20)))
            improvement=np.maximum(0,best-np.maximum(*samples)).mean(axis=0)
            return (improvement+1e-4)*probability/max(cost,1.)
        # Lower confidence bound rewards both likely improvement and uncertainty.
        lower=np.maximum(*(pred[k][0]-.7*pred[k][1] for k in METRICS[:2]))
        return np.exp(-np.clip(lower,-10,20))/max(cost,1.)

    def propose(self):
        existing=self.candidates;ranked=sorted(existing,key=lambda c:max(c.get('metrics',{}).get(k,float('inf'))/self.limits[i] for i,k in enumerate(METRICS[:2])))
        hot=sorted((c for c in existing if c.get('feasible') and all(k in c['metrics'] for k in METRICS)),
                   key=lambda c:(max(c['metrics']['power5'],c['metrics']['power6']),c['metrics']['power5']+c['metrics']['power6']))
        if hot:ranked=hot+[c for c in ranked if c not in hot]
        # Valuable partial transverse results remain centers despite a poor L gate.
        centers=[c for c in existing if c.get('metrics')]
        center=self.encode((centers[int(self.rng.integers(len(centers)))] if centers and self.rng.random()<.35 else ranked[0])['parameters']) if ranked else None
        initial=sum(axis_observed(c) for c in existing)<=self.config.search.initial_points
        pool=self.pool(center if not initial else None)
        if existing:
            old=np.array([self.encode(c['parameters']) for c in existing]);dist=np.min(np.linalg.norm(pool[:,None,:]-old[None,:,:],axis=2),axis=1)
            pool=pool[dist>1e-6];dist=dist[dist>1e-6]
        else:dist=np.ones(len(pool))
        if not len(pool):raise ValueError('Feasible candidate pool exhausted by deduplication')
        if initial or len(self.models)<2:index=int(np.argmax(dist));source='global_maximin'
        else:index=int(np.argmax(self.score(pool,1.)));source='gp_cost_ei'
        self.state['rng']=self.rng.bit_generator.state
        return self.decode(pool[index]),source

    def update_radius(self,old: dict,new: dict):
        """Only compare fully observed same-level objectives, never failure/missing data."""
        keys=METRICS if all(k in old and k in new for k in METRICS) else METRICS[:2]
        if not all(k in old and k in new for k in keys):return
        def objective(m):
            violation=max(m[k]/self.limits[i] for i,k in enumerate(METRICS[:2]))
            return (max(1.,violation),max(m['power5'],m['power6'])) if len(keys)==4 else (violation,)
        improve=objective(new)<objective(old)
        self.state['improving']=self.state['improving']+1 if improve else 0
        self.state['not_improving']=0 if improve else self.state['not_improving']+1
        if self.state['improving']>=3:self.state['radius']=min(self.config.search.max_radius,self.state['radius']*1.3);self.state['improving']=0
        if self.state['not_improving']>=6:self.state['radius']=max(self.config.search.min_radius,self.state['radius']*.7);self.state['not_improving']=0
