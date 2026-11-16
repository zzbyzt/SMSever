"""Two fixed, convex full-RNA-scale count models; no target truth interface."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import numpy as np
from scipy.optimize import minimize,brentq

ARMS=('FULL_DONOR_PRECISION','PANEL_OUTSIDE_PRECISION')
GAP_TOL=1e-8

def prepare(F,counts,panel):
    F=np.asarray(F,float);counts=np.asarray(counts,float);panel=np.asarray(panel,int)
    assert F.shape==counts.shape and np.all(F>=0) and np.all(counts>=0)
    assert np.allclose(F.sum(0),1,atol=1e-12)
    assert len(set(panel))==len(panel) and len(panel)<len(F)
    depth=float(np.median(counts.sum(0)));G=len(F)
    epsilon=1/(depth+1)
    P=(1-epsilon)*F+epsilon/G
    mask=np.ones(G,bool);mask[panel]=False
    A=np.vstack([P[panel],P[mask].sum(0)])
    assert P.min()>0 and A.min()>0 and np.allclose(A.sum(0),1,atol=1e-12)
    return {'FULL_COUNT':P,'PANEL_OUTSIDE_COUNT':A},dict(reference_depth=depth,uniform_background_mass=epsilon,raw_reference_zero_genes=int(np.sum(np.all(F==0,axis=1))),panel=panel,mask=mask)

def solve(P,q,weights=None):
    P=np.asarray(P,float,order='F');q=np.asarray(q,float)
    assert P.min()>0 and q.min()>=0 and np.isclose(q.sum(),1)
    weights=np.ones(len(q)) if weights is None else np.asarray(weights,float)
    assert weights.shape==q.shape and np.all(weights>0) and np.all(weights<=1)
    active=q>0;Pa=P[active];qa=(q*weights)[active]
    colsum=weights@P; n=P.shape[1]
    def fun(x):
        mu=Pa@x
        return float(colsum@x-qa@np.log(mu))
    def jac(x):return colsum-Pa.T@(qa/(Pa@x))
    x=np.ones(n)/n
    r=minimize(fun,x,jac=jac,method='SLSQP',bounds=[(0.,1.)]*n,
      constraints={'type':'eq','fun':lambda x:x.sum()-1.,'jac':lambda x:np.ones(n)},options={'ftol':1e-13,'maxiter':2000})
    x=np.maximum(r.x,0);x/=x.sum()
    initial_gap=float(jac(x)@x-jac(x).min())
    # Solve the equality-constrained Newton system on the active face before
    # coordinate polishing. This changes only convergence, not the objective.
    for ni in range(100):
        g=jac(x)
        if float(g@x-g.min())<=GAP_TOL*.25:break
        ids=np.flatnonzero(x>1e-13)
        j=int(np.argmin(g))
        if j not in ids:ids=np.r_[ids,j]
        mu=Pa@x;B=Pa[:,ids]
        H=B.T@((qa/mu**2)[:,None]*B)
        k=len(ids);mat=np.block([[H,np.ones((k,1))],[np.ones((1,k)),np.zeros((1,1))]])
        sol=np.linalg.lstsq(mat,np.r_[-g[ids],0.],rcond=1e-13)[0][:k]
        direction=np.zeros(n);direction[ids]=sol
        if g@direction>=-1e-18:break
        negatives=direction<0
        upper=min(1.,float(np.min(-x[negatives]/direction[negatives]))) if np.any(negatives) else 1.
        if upper<=1e-15:break
        md=Pa@direction;linear=float(colsum@direction)
        derivative=lambda t:float(linear-qa@(md/(mu+t*md)))
        step=upper if derivative(upper)<=0 else brentq(derivative,0,upper,xtol=1e-15,rtol=1e-14)
        x+=step*direction;x[np.abs(x)<1e-14]=0.;x=np.maximum(x,0.);x/=x.sum()
    for it in range(3000):
        g=jac(x);gap=float(g@x-g.min())
        if gap<=GAP_TOL*.5:break
        j=int(np.argmin(g));support=np.flatnonzero(x>1e-14)
        i=int(support[np.argmax(g[support])])
        if i==j:break
        direction=Pa[:,j]-Pa[:,i];mu=Pa@x
        linear=colsum[j]-colsum[i]
        def deriv(t):return float(linear-qa@(direction/(mu+t*direction)))
        upper=float(x[i])
        if deriv(upper)<=0:step=upper
        else:step=brentq(deriv,0,upper,xtol=1e-15,rtol=1e-14)
        if step<=1e-16:break
        x[i]-=step;x[j]+=step
    g=jac(x);feas=max(abs(x.sum()-1),max(0,-float(x.min())))
    gap=max(0.,float(g@x-g.min()))+64*np.finfo(float).eps*(1+np.max(abs(g)))
    return x,{'numeric_certified':bool(gap<=GAP_TOL and feas<=1e-10),'global_simplex_gap':gap,'feasibility':feas,'slsqp_success':bool(r.success),'slsqp_iterations':int(r.nit),'newton_iterations':ni,'polish_iterations':it,'initial_gap':initial_gap,'objective':fun(x)}

def forward(F,counts,panel,Y,column_type,K):
    models,info=prepare(F,counts,panel)
    Y=np.asarray(Y,float);Q=Y/Y.sum(0)
    qs={'FULL_COUNT':Q,'PANEL_OUTSIDE_COUNT':np.vstack([Q[info['panel']],Q[info['mask']].sum(0)])}
    outputs={}
    for mode,arm in zip(('FULL_COUNT','PANEL_OUTSIDE_COUNT'),ARMS):
        P=models[mode]
        centres=np.column_stack([P[:,column_type==k].mean(1) for k in range(K)])
        variances=np.zeros_like(centres);support=np.bincount(column_type,minlength=K)
        for k in range(K):
            if support[k]>=2:variances[:,k]=P[:,column_type==k].var(1,ddof=1)/support[k]
        predictions=[];diagnostics=[];coeff=[]
        for n,q in enumerate(qs[mode].T):
            initial,initial_diag=solve(P,q)
            pi=np.bincount(column_type,weights=initial,minlength=K)
            mean=centres@pi
            variance=variances@(pi*pi)
            precision=mean/(mean+Y[:,n].sum()*variance)
            x,d=solve(P,q,precision)
            d['initial_certified']=initial_diag['numeric_certified']
            d['initial_gap']=initial_diag['global_simplex_gap']
            d['numeric_certified']=d['numeric_certified'] and initial_diag['numeric_certified']
            d['precision_min']=float(precision.min());d['precision_median']=float(np.median(precision));d['precision_max']=float(precision.max())
            d['variance_unsupported_types']=np.flatnonzero(support<2).tolist()
            predictions.append(np.bincount(column_type,weights=x,minlength=K));diagnostics.append(d);coeff.append(x)
        outputs[arm]={'prediction':np.asarray(predictions),'coefficients':np.asarray(coeff),'diagnostics':diagnostics}
    info={k:v for k,v in info.items() if k not in {'panel','mask'}}
    info['observed_reference_zero_RNA_mass']=(Q[np.all(F==0,axis=1)].sum(0)).tolist()
    return outputs,info
