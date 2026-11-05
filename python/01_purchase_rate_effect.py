from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import pandas as pd

# 1. 读取 SQL 导出的结果
file_path=(
ROOT / 'data/analysis_output/experiment_group_summary.csv'
)
summary= pd.read_csv(file_path)

# 2. 计算各组购买率
summary["purchase_rate"]=summary['buyer_cnt']/summary['customer_cnt']

# 3.取出不发邮件组的购买率，作为统一比较基准
control_rate_column=summary.loc[summary['segment']=='No E-Mail',"purchase_rate"]
control_rate=control_rate_column.iloc[0]

# 4.对照组和实验组之间的差距
summary['absolute_lift']=summary["purchase_rate"]-control_rate
summary['relative_lift']=summary["absolute_lift"]/control_rate

# 5.千人购买增量
summary['extra_buyers_per_1000']=summary["absolute_lift"]*1000


print(summary)

from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    test_proportions_2indep
)

# 6. 取出对照组的购买人数和客户数
control = summary.loc[summary["segment"] == "No E-Mail"].iloc[0]

# 7. 只保留两个邮件组，分别与同一个对照组比较
results = summary.loc[
    summary["segment"] != "No E-Mail"
].copy()

# 8. 计算购买率绝对差的 97.5% 置信区间
results["ci_low"], results["ci_high"] = confint_proportions_2indep(
    count1=results["buyer_cnt"],
    nobs1=results["customer_cnt"],
    count2=control["buyer_cnt"],
    nobs2=control["customer_cnt"],
    compare="diff",
    method="newcomb",
    alpha=0.025
)

# 9. 检验：邮件组与对照组的购买率差异是否为 0
test_result = test_proportions_2indep(
    count1=results["buyer_cnt"],
    nobs1=results["customer_cnt"],
    count2=control["buyer_cnt"],
    nobs2=control["customer_cnt"],
    value=0,
    compare="diff",
    method="score",
    alternative="two-sided",
    correction=True
)

# 10. 进行两项比较的 Bonferroni 校正
results["p_value"] = test_result.pvalue
results["p_value_adjusted"] = (
    results["p_value"] * 2
).clip(upper=1)

# 11. 查看结果
print(results[[
    "segment",
    "absolute_lift",
    "ci_low",
    "ci_high",
    "p_value_adjusted"
]].to_string(index=False))

# 金额增量统一使用总额/人数的未舍入均值，避免读取 SQL 展示用的两位小数。
summary["spend_per_customer"] = summary["spend_s"] / summary["customer_cnt"]
#各组购买相对差异
control_spend_column=summary.loc[summary['segment']=='No E-Mail',"spend_per_customer"]
control_spend=control_spend_column.iloc[0]

# 对照组和实验组之间的差距
summary['absolute_lift_spend']=summary["spend_per_customer"]-control_spend
summary['relative_lift_spend']=summary["absolute_lift_spend"]/control_spend

print(summary)
