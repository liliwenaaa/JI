# 开源指数基金工具调研

调研日期：2026-07-16（趋势引擎补充：2026-07-17）。目标：个人使用的「一键筛选指数基金 + 市场变化加减仓提醒」。

## 1. 代表性开源项目

| 项目 | 定位 | 技术栈 | 与本需求相关的能力 | 缺口 |
|------|------|--------|-------------------|------|
| [FundKit](https://github.com/liuenyan/fundkit) | 公募基金工具箱 | Python + AKShare + Streamlit + SQLite | 指数选基、费率/规模对比、指数 PE/PB 百分位 | 无持仓跟踪与加减仓比例提醒 |
| [iFund](https://github.com/OrangesHuang/ifund) | 自托管投研系统 | Flask + React + SQLite + MCP | 高级筛选、组合分析、再平衡对账 | 过重，偏团队/全品类，非轻量个人 CLI |
| [mutual-fund-skills](https://github.com/sososun/mutual-fund-skills) | 策略选基 | AKShare + CLI | 多因子打分、夏普/卡玛等 | 主动基金为主，指数选基弱；无仓位提醒 |
| [fund-cli](https://github.com/jarrey-0804/fund-cli) | 机构向 CLI | 多数据源 + 报告引擎 | 筛选、归因、组合优化 | 依赖复杂，个人场景过重 |
| [GoFundBot](https://github.com/Sebastian6848/GoFundBot) | 可视化 + AI | Flask + Vue | 4433 等筛选、自选 | 全量库约 8G，启动成本高 |
| [myquant](https://github.com/nigo81/myquant) | 指数估值 | baostock + akshare | PE/PB 历史百分位、低估高估分档 | 不做基金筛选与提醒闭环 |
| [seek-truth-funds](https://github.com/ZhiYiTree/seek-truth-funds) | 基金技能包 | 多源降级 | 筛选与数据稳健性设计可借鉴 | 非开箱即用的提醒产品 |

## 2. 数据源结论

| 数据源 | 优点 | 缺点 | 本项目用法 |
|--------|------|------|------------|
| **AKShare**（天天基金 / 乐咕乐股 / 中证） | 免费、无 Token、覆盖指数基金与估值 | 接口偶发变更、需本地缓存 | **主数据源** |
| Tushare | 质量较稳 | 需积分/Token | 可选扩展，首版不做 |
| efinance / 新浪 | 可作为净值降级源 | API 不稳定 | 预留扩展点 |

关键接口（AKShare）：

- 指数基金名录：`fund_info_index_em`
- 指数 PE/PB：`stock_index_pe_lg` / `stock_index_pb_lg`
- 中证指数估值：`stock_zh_index_value_csindex`（备用）

## 3. 加减仓逻辑业界做法

常见个人定投仓位法（非投资建议）：

1. 用指数 PE（或 PB）历史百分位划分低估 / 适中 / 高估。
2. 低估提高目标权益仓位，高估降低目标仓位。
3. 用「目标仓位 − 当前仓位」得到建议增持/减持比例。

本项目采用可配置的百分位 → 目标仓位映射表，并支持按指数维度对持仓分别提醒。

## 4. 产品差异化（本工具要做什么）

相对现有开源：

- **只做指数基金**：不做全市场主动基、养老金、AI 研报。
- **筛选 + 提醒闭环**：一键筛选 → 绑定持仓 → 估值驱动加减仓比例。
- **个人轻量**：CLI 优先、YAML 配置、SQLite 短时缓存，无 Web 后端/前端。
- **可解释**：每条提醒附带百分位、目标仓位、偏离度与动作说明。

## 5. 不做的范围（产品硬边界）

- **实盘下单、券商 API、自动跟单**（决策助手，不执行交易；见产品规划）
- 复杂再平衡优化器 / 蒙特卡洛（非首版）
- 强制依赖 Tushare Token

规划内（不做执行，但要写入决策链）：

- **交易成本模型**：申赎费 / ETF 佣金与滑点 / 再平衡成本阈值 → 建议与回测净收益
- **数据信号补齐**：成交额、跟踪误差、申赎与盈利增速等（详见 `AI-Index_产品规划_V1.0.md` §3.1–3.2）
- **回测分层实现**：L1 信号 / L2 估值仓位规则 / L3 决策链（详见产品规划 **§5**；先 B0–B1）

---

## 6. 专业趋势引擎：开源方案与可借鉴点

调研目标：把「可解释的指数趋势分」做稳，而不是做成交易机器人。专业趋势系统通常拆成三层——**指标库 / 信号编排 / 回测与门控**；很少有一个「万能趋势引擎」可直接嵌入指数基金助手。

### 6.1 开源分层对照

| 层级 | 代表开源 | 作用 | 是否直接可用 |
|------|----------|------|----------------|
| 指标库 | [pandas-ta](https://github.com/twopirllc/pandas-ta) / [pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic)、TA-Lib | SMA/EMA/MACD/RSI/ADX/**Supertrend**/ATR 等标准算法 | ✅ 本项目已用 classic |
| 信号编排 | [Freqtrade](https://github.com/freqtrade/freqtrade) 策略模板、[KhanJahanzaib/trend](https://github.com/KhanJahanzaib/trend) | 多条件确认、informative 多周期、入场/出场布尔组合 | ⚠️ 可借思路，不宜整仓依赖 |
| 体制切换 | [Regime-Aware-Algo-Trading](https://github.com/IssacWong0103/Regime-Aware-Algo-Trading-Python-Project) | ADX 高走趋势、ADX 低走均值回归 | ✅ 极适合指数趋势分门控 |
| 回测实验 | [vectorbt](https://github.com/polakowo/vectorbt) | 向量化参数扫描、信号与收益对齐 | ⚠️ 研究用；本项目已有 Walk-Forward 校准 |
| 基金/估值工具 | FundKit、myquant 等（见 §1） | 估值与选基 | ❌ 几乎不含专业趋势编排 |

结论：**没有**一个轻量开源项目同时覆盖「A 股指数日线 + 可解释多因子趋势分 + 仓位提醒」。应借 **Freqtrade / 体制切换项目的编排范式**，继续用 **pandas-ta-classic** 算指标，在本仓库内演进规则引擎。

### 6.2 业界主流趋势编排（可落地）

1. **ADX 体制门控**（几乎所有趋势策略的共识）  
   - ADX ≥ ~25：趋势市，信任均线/MACD/动量。  
   - ADX ≤ ~20：震荡市，分数向中性收缩，或偏向 RSI 均值回归解读。  
   - 参考：StockSharp Supertrend+ADX、Regime-Aware 项目、FMZ Supertrend+ADX。

2. **Supertrend（ATR 轨）作方向确认**  
   - 价格在 Supertrend 上方 / 下方给出波动率自适应的多空轨。  
   - 通常与 ADX、长均线（如 EMA100）一起过滤，而不是单独交易。  
   - pandas-ta 已提供 `supertrend`，零额外依赖。

3. **多周期确认（MTF）**  
   - Freqtrade：`@informative` 用更高周期定方向、低周期找时机。  
   - 本项目已有「同一日线、不同窗口」的多展望周期；应对齐长短周期 **bias**，冲突时压低 `probability_up`。

4. **连续分而非悬崖分**  
   - 纯「多头排列=80 / 空头=20」在穿越瞬间剧烈跳变，易导致提醒抖动。  
   - 专业实现常用价格相对均线的距离/斜率做软分数。

5. **刻意不做或后置**  
   - 全量 Freqtrade / Jesse 实盘栈、HMM 隐状态、深度学习择时：过重，且与「可解释个人助手」冲突。  
   - Ichimoku / VWAP 全套：指数日线场景增益有限，暂缓。

### 6.3 本项目已落地的借鉴优化（2026-07-17）

实现位置：`jijin/engine/trend.py` + `settings.py`。

| 借鉴点 | 实现 |
|--------|------|
| ADX 体制 | `regime`：趋势 / 过渡 / 震荡；震荡时分数向 50 收缩 |
| Supertrend 确认 | 与主方向一致小幅加分，冲突小幅扣分 |
| 软均线分 | 离散信号 + 相对中期均线偏离的连续分混合 |
| 多周期对齐 | `analyze_trend_horizons` 用更长周期 bias 微调 `probability_up` |
| Walk-Forward 校准 | 已有 `calibrate.py`（参数层，非概率校准） |

### 6.4 后续可选增强

- 将 `probability_up` 用历史命中率做 isotonic / 分桶校准（真正「概率」）。  
- 震荡市显式切换 RSI 权重（体制感知权重）。  
- ETF 份额/资金流替代纯指数成交量（产品规划已写，数据源待接）。  
- 用 vectorbt 做研究型对照回测，不引入运行时依赖。
