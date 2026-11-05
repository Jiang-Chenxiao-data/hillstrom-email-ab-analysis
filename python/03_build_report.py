"""复算已有汇总、生成项目报告与静态图。运行：python python/03_build_report.py。

不连接或修改 MySQL，不修改原始数据。既有两项对照比较分别在指标内校正。
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import sqlite3
import sys

import numpy as np
import pandas as pd
import scipy
from scipy.stats import chisquare, norm, t, ttest_ind, ttest_ind_from_stats
import statsmodels
from statsmodels.stats.proportion import confint_proportions_2indep, test_proportions_2indep
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv'
REFERENCE_OUT = ROOT / 'data/analysis_output'
OUT = ROOT / 'reproduction_output/data' 
FIG = ROOT / 'reproduction_output/figures'
validation_path = OUT / 'report_validation.json'
previous_validation = json.loads(validation_path.read_text(encoding='utf-8')) if validation_path.exists() else {}
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)
SHA = hashlib.sha256(RAW.read_bytes()).hexdigest()
assert SHA == '0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece'
df = pd.read_csv(RAW)
ORDER = ['No E-Mail', 'Mens E-Mail', 'Womens E-Mail']
CN = dict(zip(ORDER, ['不发邮件', '男装邮件', '女装邮件']))
assert len(df) == 64000 and not df.isna().any().any()
assert set(df.segment) == set(ORDER)
assert all(df[c].isin([0,1]).all() for c in ['mens','womens','newbie','visit','conversion'])
assert df.recency.between(1,12).all()
assert ((df.conversion == 1) == (df.spend > 0)).all()
assert (df.conversion <= df.visit).all() and (df.spend >= 0).all()
summary = df.groupby('segment').agg(customer_cnt=('spend', 'size'), buyer_cnt=('conversion', 'sum'),
    visitor_cnt=('visit', 'sum'), spend_s=('spend', 'sum'), spend_std=('spend', 'std')).loc[ORDER]
summary['purchase_rate'] = summary.buyer_cnt / summary.customer_cnt
summary['mean_spend'] = summary.spend_s / summary.customer_cnt

# 设计可信性诊断：约三等分人数；只比较实验前特征，排除结果字段。
srm = chisquare(summary.customer_cnt, f_exp=np.repeat(len(df)/3,3))
features = pd.get_dummies(df[['recency','history','mens','womens','zip_code','newbie','channel']],dtype=float)
balance_rows = []
for arm in ORDER[1:]:
    for feature in features:
        a = features.loc[df.segment==arm,feature]
        b = features.loc[df.segment==ORDER[0],feature]
        pooled_sd = np.sqrt((a.var(ddof=1)+b.var(ddof=1))/2)
        balance_rows.append(dict(treatment=arm,feature=feature,smd=(a.mean()-b.mean())/pooled_sd if pooled_sd else np.nan))
balance = pd.DataFrame(balance_rows)
balance.to_csv(OUT/'report_baseline_balance.csv',index=False,encoding='utf-8-sig')
max_smd = balance.smd.abs().max()

# 与用户已有 SQL 导出逐组对账；不依赖它的舍入率或舍入均值计算推断。
old_group = pd.read_csv(REFERENCE_OUT / 'experiment_group_summary.csv').set_index('segment').loc[ORDER]
old_spend = pd.read_csv(REFERENCE_OUT / 'experiment_spend_summary.csv').set_index('segment').loc[ORDER]
for col in ['customer_cnt', 'buyer_cnt', 'visitor_cnt', 'spend_s']:
    np.testing.assert_allclose(summary[col], old_group[col], rtol=0, atol=1e-8)
for col in ['customer_cnt', 'spend_s', 'spend_std']:
    np.testing.assert_allclose(summary[col], old_spend[col], rtol=0, atol=1e-10)

# 独立路径：标准库 CSV + 整数美分 + SQLite 聚合，避免复用 pandas 分组结果。
with RAW.open(encoding='utf-8-sig', newline='') as f:
    records = [(r['segment'], int(r['conversion']), int(r['visit']),
                int(round(float(r['spend']) * 100))) for r in csv.DictReader(f)]
with sqlite3.connect(':memory:') as db:
    db.execute('CREATE TABLE customers(segment TEXT, buyer INTEGER, visitor INTEGER, cents INTEGER)')
    db.executemany('INSERT INTO customers VALUES(?,?,?,?)', records)
    sql_rows = db.execute('SELECT segment, COUNT(*), SUM(buyer), SUM(visitor), SUM(cents) FROM customers GROUP BY segment').fetchall()
for s, n, b, v, cents in sql_rows:
    r = summary.loc[s]
    assert (n, b, v, cents) == (int(r.customer_cnt), int(r.buyer_cnt), int(r.visitor_cnt), round(r.spend_s * 100))

def independent_newcombe(b1, n1, b0, n0, alpha):
    """Wilson 两个单比例区间组合，独立核对 statsmodels Newcombe 结果。"""
    z = norm.ppf(1-alpha/2)
    def wilson(b, n):
        p = b/n
        center = (p + z*z/(2*n))/(1+z*z/n)
        h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        return center-h, center+h
    p1, p0 = b1/n1, b0/n0
    l1, u1 = wilson(b1, n1)
    l0, u0 = wilson(b0, n0)
    return p1-p0-math.hypot(p1-l1,u0-p0), p1-p0+math.hypot(u1-p1,p0-l0)

def compare(s1, s0, alpha, multiplier, role):
    a, b = summary.loc[s1], summary.loc[s0]
    ci = confint_proportions_2indep(a.buyer_cnt, a.customer_cnt, b.buyer_cnt, b.customer_cnt,
        method='newcomb', compare='diff', alpha=alpha)
    np.testing.assert_allclose(ci, independent_newcombe(a.buyer_cnt,a.customer_cnt,b.buyer_cnt,b.customer_cnt,alpha),atol=1e-12)
    score = test_proportions_2indep(a.buyer_cnt,a.customer_cnt,b.buyer_cnt,b.customer_cnt,
        value=0,method='score',compare='diff',alternative='two-sided',correction=True)
    v1, v0 = a.spend_std**2/a.customer_cnt, b.spend_std**2/b.customer_cnt
    se = math.sqrt(v1+v0)
    dof = (v1+v0)**2/(v1*v1/(a.customer_cnt-1)+v0*v0/(b.customer_cnt-1))
    delta = a.mean_spend-b.mean_spend
    crit = t.ppf(1-alpha/2,dof)
    test = ttest_ind_from_stats(a.mean_spend,a.spend_std,a.customer_cnt,b.mean_spend,b.spend_std,b.customer_cnt,equal_var=False)
    independent = ttest_ind(df.loc[df.segment==s1,'spend'],df.loc[df.segment==s0,'spend'],equal_var=False)
    np.testing.assert_allclose(test.pvalue, independent.pvalue, rtol=1e-10)
    return dict(treatment=s1,baseline=s0,role=role,ci_level=1-alpha,
        rate_diff=a.purchase_rate-b.purchase_rate,rate_relative_lift=a.purchase_rate/b.purchase_rate-1,
        rate_ci_low=ci[0],rate_ci_high=ci[1],extra_buyers_per_1000=(a.purchase_rate-b.purchase_rate)*1000,
        rate_p_raw=float(score.pvalue),rate_p_adjusted=min(1,float(score.pvalue)*multiplier),
        spend_diff=delta,spend_relative_lift=a.mean_spend/b.mean_spend-1,
        spend_ci_low=delta-crit*se,spend_ci_high=delta+crit*se,
        spend_p_raw=float(test.pvalue),spend_p_adjusted=min(1,float(test.pvalue)*multiplier))

effects = pd.DataFrame([compare(s,'No E-Mail',.025,2,'two_control_comparisons') for s in ORDER[1:]])
direct = pd.DataFrame([compare('Mens E-Mail','Womens E-Mail',.05,1,'exploratory_direct_comparison')])
summary.to_csv(OUT/'report_group_summary.csv',encoding='utf-8-sig')
effects.to_csv(OUT/'report_effects.csv',index=False,encoding='utf-8-sig')
direct.to_csv(OUT/'report_direct_comparison.csv',index=False,encoding='utf-8-sig')

# Markdown 为静态图片目的地；区间用同一份 effects 数据，不另行估算。
import os
font_path = Path(os.environ.get('CJK_FONT', 'C:/Windows/Fonts/msyh.ttc'))
if font_path.exists():
    font = FontProperties(fname=str(font_path))
    plt.rcParams['font.family'] = font.get_name()
plt.rcParams.update({'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,
    'axes.spines.right':False,'figure.facecolor':'white','axes.facecolor':'white'})
colors = ['#3269A8','#BE681F']
fig, axes = plt.subplots(1,2,figsize=(11.8,4.6))
for ax, col, title, unit in [(axes[0],'purchase_rate','两周购买率','购买率（%）'),
                             (axes[1],'mean_spend','两周每客平均消费','美元 / 分配客户')]:
    values = summary[col].to_numpy()*(100 if col=='purchase_rate' else 1)
    ax.bar([CN[s] for s in ORDER],values,color=['#8591A0']+colors,width=.5)
    ax.set_ylim(0,max(values)*1.28)
    ax.set_title(title,pad=16,fontweight='bold')
    ax.set_ylabel(unit)
    for i,v in enumerate(values):
        ax.text(i,v+max(values)*.035,f'{v:.3f}'+('%' if col=='purchase_rate' else ''),ha='center')
    ax.grid(axis='y',alpha=.18)
    ax.set_axisbelow(True)
fig.text(.5,.025,'分母均为全部分配客户，包含未购买者；每组人数见报告表。来源：原始 CSV 全量复算。',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.07,1,1))
fig.savefig(FIG/'01_group_outcomes.png',dpi=180)
plt.close(fig)

fig, axes = plt.subplots(1,2,figsize=(11.8,4.8))
for ax, prefix, scale, title, unit in [
    (axes[0],'rate',100,'购买率增量及区间','相比不发邮件的差值（百分点）'),
    (axes[1],'spend',1,'每客消费增量及区间','相比不发邮件的差值（美元 / 分配客户）')]:
    for i,r in effects.iterrows():
        val,lo,hi = [float(r[f'{prefix}_{k}'])*scale for k in ['diff','ci_low','ci_high']]
        ax.errorbar(val,1-i,xerr=[[val-lo],[hi-val]],fmt='o',capsize=7,color=colors[i],markersize=7)
        ax.text(val,1-i+.19,f'{val:.3f} [{lo:.3f}, {hi:.3f}]',ha='center',fontsize=10)
    ax.set_yticks([1,0],[CN[s] for s in ORDER[1:]])
    ax.set_ylim(-.5,1.6)
    ax.axvline(0,color='#64748B',linestyle='--',linewidth=1)
    ax.set_title(title,pad=16,fontweight='bold')
    ax.set_xlabel(unit)
    ax.grid(axis='x',alpha=.18)
    ax.set_xlim(-.04,1.22) if prefix=='spend' else ax.set_xlim(-.04,1.01)
fig.text(.5,.025,'点为差值，横线为每项 97.5% 置信区间；各指标内两项比较分别作 Bonferroni 校正。来源同图1。',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.07,1,1))
fig.savefig(FIG/'02_increment_intervals.png',dpi=180)
plt.close(fig)

def pct(v): return f'{v*100:.3f}%'
def sci(v): return f'{v:.4g}'
m,w = [effects.iloc[i] for i in range(2)]
d = direct.iloc[0]
business = (ROOT/'业务问题说明.md').read_text(encoding='utf-8-sig').split('## 已确认版本')[1].split('## GitHub')[0].strip()
rows = '\n'.join(f'| {CN[s]} | {int(r.customer_cnt):,} | {int(r.buyer_cnt):,} | {pct(r.purchase_rate)} | {r.spend_s:,.2f} | {r.mean_spend:.3f} |' for s,r in summary.iterrows())
rate_rows = '\n'.join(f'| {CN[r.treatment]} − 不发邮件 | +{r.rate_diff*100:.3f} | [{r.rate_ci_low*100:.3f}, {r.rate_ci_high*100:.3f}] | +{r.rate_relative_lift*100:.2f}% | +{r.extra_buyers_per_1000:.2f} |' for r in effects.itertuples())
spend_rows = '\n'.join(f'| {CN[r.treatment]} − 不发邮件 | +{r.spend_diff:.3f} | [{r.spend_ci_low:.3f}, {r.spend_ci_high:.3f}] | +{r.spend_relative_lift*100:.2f}% |' for r in effects.itertuples())
test_rows = '\n'.join(f'| {CN[r.treatment]} − 不发邮件 | {sci(r.rate_p_adjusted)} | {sci(r.spend_p_adjusted)} | 各指标内乘 2 校正 |' for r in effects.itertuples())
test_rows += f'\n| 男装邮件 − 女装邮件 | {sci(d.rate_p_raw)} | {sci(d.spend_p_raw)} | 探索性，未校正 |'
context = dict(business=business, rows=rows, rate_rows=rate_rows, spend_rows=spend_rows, test_rows=test_rows,
    control_rate=pct(summary.loc['No E-Mail','purchase_rate']),
    mens_rate=pct(summary.loc['Mens E-Mail','purchase_rate']), womens_rate=pct(summary.loc['Womens E-Mail','purchase_rate']),
    srm_p=f'{srm.pvalue:.3f}', srm_stat=f'{srm.statistic:.6f}', max_smd=f'{max_smd:.3f}',
    total_spend=f'{summary.spend_s.sum():,.2f}',raw_name=RAW.name,raw_sha=SHA)
for name,r in [('mens',m),('womens',w)]:
    context.update({f'{name}_rate_diff':f'{r.rate_diff*100:.3f}', f'{name}_spend_diff':f'{r.spend_diff:.3f}',
        f'{name}_relative_rate':f'{r.rate_relative_lift*100:.2f}', f'{name}_extra_buyers':f'{r.extra_buyers_per_1000:.2f}',
        f'{name}_extra_spend':f'{r.spend_diff*1000:.2f}',
        f'{name}_buyers_low':f'{r.rate_ci_low*1000:.2f}', f'{name}_buyers_high':f'{r.rate_ci_high*1000:.2f}'})
for field in ['rate','spend']:
    scale = 100 if field=='rate' else 1
    for key,col in [('diff','diff'),('low','ci_low'),('high','ci_high')]:
        context[f'direct_{field}_{key}'] = f'{d[f"{field}_{col}"]*scale:.3f}'
report = (Path(__file__).with_name('report_template.md')).read_text(encoding='utf-8').format(**context)
(ROOT/'reproduction_output/分析报告.md').write_text(report,encoding='utf-8')
validation = dict(date='2026-11-04',raw_sha256=SHA,row_count=len(df),buyers=int(df.conversion.sum()),
    identical_rows_beyond_first=int(df.duplicated().sum()),
    checks=['raw_vs_existing_sql_exports_all_3_groups','independent_sqlite_integer_cents_aggregation',
            'newcombe_vs_manual_wilson_combination','welch_summary_vs_raw_records',
            'equal_allocation_chisquare_diagnostic','pre_experiment_feature_smd'],
    sample_ratio_diagnostic=dict(expected_ratio='1:1:1 (approximate publisher description)',
        chi_square=float(srm.statistic),df=2,p_value=float(srm.pvalue)),
    max_absolute_baseline_smd=float(max_smd),
    figure_files=['figures/01_group_outcomes.png','figures/02_increment_intervals.png'],
    visual_review='pending',mysql_connected=False,
    versions=dict(python=sys.version,pandas=pd.__version__,numpy=np.__version__,scipy=scipy.__version__,statsmodels=statsmodels.__version__,matplotlib=matplotlib.__version__))
validation['figures_sha256'] = {f:hashlib.sha256((ROOT/'reproduction_output'/f).read_bytes()).hexdigest() for f in validation['figure_files']}
if (previous_validation.get('figures_sha256') == validation['figures_sha256']
        and previous_validation.get('visual_review') not in [None,'pending']):
    validation['visual_review'] = previous_validation['visual_review']
    validation['visual_review_basis'] = 'Previously inspected images; exact SHA-256 hashes unchanged.'
else:
    report = report.replace('图1、图2已完成视觉检查。','图1、图2的视觉检查待完成。')
    (ROOT/'reproduction_output/分析报告.md').write_text(report,encoding='utf-8')
(OUT/'report_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
print(summary.to_string())
print(effects.to_string(index=False))
print(direct.to_string(index=False))
print('Saved:', ROOT/'reproduction_output/分析报告.md')
