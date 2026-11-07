# 复现与核验

## 汇总结果检查

从根目录运行 `python python/verify_published_results.py`。该程序根据分组人数、购买人数、消费总额及标准差独立重算率差、Newcombe 区间、Welch 区间，并核对发布的结果文件。它不代替原始记录校验。

## 原始数据全量复现

1. 从 [原始发布页](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html) 获取数据。
2. 保存为 `data/raw/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv`。SHA-256 必须为 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece`；64,000 行、12 字段。许可未确认，本仓库不分发原始 CSV。
3. 安装根目录 requirements.txt 后运行 `python python/03_build_report.py`。它从原始记录重算，使用标准库 CSV、SQLite、整数美分独立核对，并与历史 SQL 导出逐组对账，不连接 MySQL。`01_purchase_rate_effect.py` 与 `02_spend_effect.py` 为基于历史 SQL 汇总的原学习脚本；03 是完整复算入口。
4. 新结果写入 `reproduction_output/data/`、`reproduction_output/figures/` 和 `reproduction_output/分析报告.md`；归档最终报告入口始终为 `report/report.md`。生成稿不覆盖最终 Word/Markdown。
5. 图表默认使用 Windows 微软雅黑；其他系统先设置 `CJK_FONT` 为已有中文字体文件路径。统计计算不依赖字体；无可用中文字体时图中文字显示可能不完整。

最终报告选自 2026-11-04 的“参照运营报告重写版”，Markdown 的 crop 伪链接已改为仓库中可打开的完整双面板图。排版及单面板裁剪以 Word 为准。历史核验记录保存在 historical_validation_20261104.json；本次复跑记录单独保存，未把历史 MySQL 导出说成本轮数据库执行结果。

统计边界：两项主要比较在各自指标内校正，金额是辅助指标；直接内容比较未校正、属探索性；数据缺少真实客户 ID、分流日志、成本、负反馈及长期结果。


## 最新报告版本

2026-11-07 更新业务表达与报告版式。当前阅读入口为 `report/report.docx` 与 `report/report.md`；既有脚本用于复现分析结果，生成的历史文稿不覆盖本次编辑版。此次未重跑全量数据，统计结果文件未修改。
