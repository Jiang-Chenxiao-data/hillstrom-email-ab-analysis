from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
import pandas as pd
import numpy as np
from scipy.stats import t, ttest_ind_from_stats

file_path=(ROOT / 'data/analysis_output/experiment_spend_summary.csv')

spend=pd.read_csv(file_path)

print(spend)

#平均每人消费金额
spend['mean_spend']=spend['spend_s']/spend['customer_cnt']
#各组购买相对差异
control_spend=spend.loc[spend['segment']=='No E-Mail']
result_spend=spend.loc[spend['segment']!='No E-Mail'].copy()

# 计算金额绝对增量和相对提升
result_spend['absolute_lift_spend']=result_spend['mean_spend']-control_spend['mean_spend'].iloc[0]
result_spend['relative_lift_spend']=result_spend['absolute_lift_spend']/control_spend['mean_spend'].iloc[0]

# 1.取出对照组的均值、标准差和客户数
control_mean = control_spend["mean_spend"].iloc[0]
control_std = control_spend["spend_std"].iloc[0]
control_n = control_spend["customer_cnt"].iloc[0]

# 2. 根据金额波动和人数，计算均值差的标准误
variance_mail = (
    result_spend["spend_std"] ** 2 / result_spend["customer_cnt"]
)
variance_control = control_std ** 2 / control_n

standard_error = np.sqrt(variance_mail + variance_control)

# 3. 计算 Welch 方法所需的自由度
degrees_freedom = (variance_mail + variance_control) ** 2 / (
    variance_mail ** 2 / (result_spend["customer_cnt"] - 1)
    + variance_control ** 2 / (control_n - 1)
)

# 4. 对两项金额比较进行校正，计算各自的 97.5% 置信区间
comparison_count = len(result_spend)
alpha = 0.05 / comparison_count

critical_value = t.ppf(1 - alpha / 2, degrees_freedom)

result_spend["ci_low_spend"] = (
    result_spend["absolute_lift_spend"]
    - critical_value * standard_error
)

result_spend["ci_high_spend"] = (
    result_spend["absolute_lift_spend"]
    + critical_value * standard_error
)

# 5. Welch 检验，比较邮件组与对照组的平均消费金额
spend_test = ttest_ind_from_stats(
    mean1=result_spend["mean_spend"],
    std1=result_spend["spend_std"],
    nobs1=result_spend["customer_cnt"],
    mean2=control_mean,
    std2=control_std,
    nobs2=control_n,
    equal_var=False,
    alternative="two-sided"
)

# 6. 对当前两项金额比较的 p 值进行 Bonferroni 校正
result_spend["p_value_spend"] = spend_test.pvalue

result_spend["p_value_adjusted_spend"] = (
    result_spend["p_value_spend"] * comparison_count
).clip(upper=1)

# 7. 展示结果
print(result_spend[[
    "segment",
    "mean_spend",
    "absolute_lift_spend",
    "relative_lift_spend",
    "ci_low_spend",
    "ci_high_spend",
    "p_value_adjusted_spend"
]].to_string(index=False))
