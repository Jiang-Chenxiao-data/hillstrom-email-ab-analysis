"""Recompute published effects from archived sufficient statistics; no raw data needed."""
from pathlib import Path
import json, math
import pandas as pd
from scipy.stats import norm, t, ttest_ind_from_stats
from statsmodels.stats.proportion import test_proportions_2indep

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/analysis_output'
g=pd.read_csv(OUT/'report_group_summary.csv').set_index('segment')
assert g.customer_cnt.sum()==64000 and g.buyer_cnt.sum()==578
assert math.isclose(g.spend_s.sum(),67258.13,abs_tol=1e-8)

def wilson(b,n,alpha):
    z=norm.ppf(1-alpha/2);p=b/n;v=1+z*z/n
    c=(p+z*z/(2*n))/v;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/v
    return c-h,c+h

def check_effect(row,alpha,multiplier):
    a,b=g.loc[row.treatment],g.loc[row.baseline]
    p1,p0=a.buyer_cnt/a.customer_cnt,b.buyer_cnt/b.customer_cnt
    l1,u1=wilson(a.buyer_cnt,a.customer_cnt,alpha)
    l0,u0=wilson(b.buyer_cnt,b.customer_cnt,alpha)
    diff=p1-p0
    lo=diff-math.hypot(p1-l1,u0-p0);hi=diff+math.hypot(u1-p1,p0-l0)
    va,vb=a.spend_std**2/a.customer_cnt,b.spend_std**2/b.customer_cnt
    df=(va+vb)**2/(va**2/(a.customer_cnt-1)+vb**2/(b.customer_cnt-1))
    d=a.spend_s/a.customer_cnt-b.spend_s/b.customer_cnt
    h=t.ppf(1-alpha/2,df)*math.sqrt(va+vb)
    expected={'rate_diff':diff,'rate_ci_low':lo,'rate_ci_high':hi,
              'spend_diff':d,'spend_ci_low':d-h,'spend_ci_high':d+h}
    for key,v in expected.items():assert math.isclose(v,float(row[key]),abs_tol=1e-10),(key,v,row[key])
    rate_p=test_proportions_2indep(a.buyer_cnt,a.customer_cnt,b.buyer_cnt,b.customer_cnt,method='score',compare='diff',correction=True).pvalue
    spend_p=ttest_ind_from_stats(a.spend_s/a.customer_cnt,a.spend_std,a.customer_cnt,b.spend_s/b.customer_cnt,b.spend_std,b.customer_cnt,equal_var=False).pvalue
    assert math.isclose(rate_p,float(row.rate_p_raw),rel_tol=1e-8,abs_tol=1e-15)
    assert math.isclose(spend_p,float(row.spend_p_raw),rel_tol=1e-8,abs_tol=1e-15)
    if multiplier==2:
        assert math.isclose(min(rate_p*2,1),float(row.rate_p_adjusted),rel_tol=1e-8)
        assert math.isclose(min(spend_p*2,1),float(row.spend_p_adjusted),rel_tol=1e-8)

for _,r in pd.read_csv(OUT/'report_effects.csv').iterrows():check_effect(r,0.025,2)
for _,r in pd.read_csv(OUT/'report_direct_comparison.csv').iterrows():check_effect(r,0.05,1)
for _,r in g.iterrows():
    assert math.isclose(r.purchase_rate,r.buyer_cnt/r.customer_cnt,abs_tol=1e-12)
    assert math.isclose(r.mean_spend,r.spend_s/r.customer_cnt,abs_tol=1e-12)
print(json.dumps({'status':'passed','scope':'3 groups; 2 corrected comparisons and 1 exploratory comparison; rates, means, intervals and p-values'},ensure_ascii=False))
