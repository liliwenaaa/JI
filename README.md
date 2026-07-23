# AI Index — AI 智能指数基金投资平台

> AI 驱动的指数基金决策助手（非交易软件）。对应
> `AI-Index_产品规划_V1.0.md` 的 MVP + V1.0。

本工具仅供学习与信息整理，**不构成投资建议**。

## 功能

| 模块 | 实现 |
|------|------|
| Dashboard | 市场温度、宏观/政策、仓位变化、重点机会 Top10、持仓 |
| 重点机会 | 扫描宽基+行业/主题指数（约 50 只），按上涨概率排出前列，支持分组筛选 |
| 指数筛选 | 已并入重点机会；不再做基金费率/规模筛选 |
| AI 评分 | 估值/趋势/资金/盈利/风险/情绪/宏观/政策 八因子 |
| 趋势引擎 | 多周期展望（1天/1周/1月/3月/6月/1年）+ SMA/MACD/RSI/ADX/动量/量能 |
| 智能仓位 | 风险偏好 + 策略模板 → 标的、金额和再平衡方案 |
| AI 解释 | 推荐原因、谨慎原因、风险来源、统计依据 |
| 智能提醒 | 估值、趋势、风险、再平衡、定投；按待执行/风险/观察分级 |

当前“AI”是可解释的规则与多因子引擎，并未调用 OpenAI、DeepSeek
或其他 LLM。邮件、企微、Telegram、Push 也尚未接入。

**产品硬边界：不做实盘下单与券商对接。** 交易成本模型、数据信号补齐已写入
`AI-Index_产品规划_V1.0.md`（§3.1–3.2 / 路线图 V1.5），用于建议质量与回测净收益，不进入执行链路。

## 环境安装与使用

### 要求

- Python **3.11+**（推荐 3.11 / 3.12）
- 可访问公网（首次拉依赖；运行时拉行情/估值等公开数据）
- Linux / macOS / Windows 均可；下文以 Linux/macOS 为例

### 为什么要用 `.venv`

系统自带的 `python3`（例如 `/usr/bin/python3`）通常**没有**本项目的依赖。  
依赖安装在项目目录下的 **`.venv`** 中。请始终用虚拟环境里的解释器，或先 `source .venv/bin/activate`。

**不要**把 `.venv` 拷到另一台电脑直接用：环境绑定本机路径与平台，换机请按下面步骤重建。  
仓库已用 `.gitignore` 忽略 `.venv/`、`config.yaml`、本地缓存库等。

### 首次安装（新机器 / 克隆后）

```bash
cd ~/模板/JiJin   # 换成你的项目路径

# 1) 创建虚拟环境
python3 -m venv .venv
# 若本机有 uv，也可：uv venv --python 3.11 .venv

# 2) 安装依赖
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
# 若用 uv：.venv/bin/uv pip install -r requirements.txt

# 3) 配置（可选）
cp config.example.yaml config.yaml
# 按需编辑持仓、总资产、观察指数等；勿提交含隐私的 config.yaml
```

### 日常启动

```bash
cd ~/模板/JiJin

# 图形界面（推荐）
.venv/bin/python -m streamlit run app.py

# 等价：先激活再启动（激活后 which python3 应指向 .venv）
source .venv/bin/activate
python3 -m streamlit run app.py
```

浏览器打开 http://localhost:8501。

> 不要用系统解释器直接 `python3 app.py`：既缺依赖，也不是 Streamlit 的标准启动方式。

### 命令行

```bash
.venv/bin/python -m jijin screen
.venv/bin/python -m jijin alert
.venv/bin/python -m jijin strategy --risk 均衡 --monthly 3000
```

### 测试

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

### 换机迁移 checklist

| 带走 | 不要拷贝（到新机重建/忽略） |
|------|---------------------------|
| 源码、`requirements.txt`、`config.example.yaml` | `.venv/` |
| 自用的 `config.yaml`（可加密传输） | `data/*.db` 等缓存（可自动重建） |
| `.streamlit/config.toml`（主题，若你改过） | `__pycache__/`、本地 CSV 导出 |

新机：克隆/拷贝源码 → 按「首次安装」重建 `.venv` → 放入自己的 `config.yaml` → 启动。

### 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `No module named 'streamlit'` / `altair` | 用了系统 `python3` | 改用 `.venv/bin/python -m streamlit run app.py` |
| 改了代码页面没变 | 若以 `fileWatcherType none` 启动 | 重启 Streamlit 进程 |
| 依赖装失败 | 网络 / Python 过旧 | 确认 3.11+；换镜像或重试 pip |

## 快速开始（摘要）

```bash
cd ~/模板/JiJin
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp -n config.example.yaml config.yaml
.venv/bin/python -m streamlit run app.py
```

打开 http://localhost:8501。

## 设计与数据流

```text
公开市场数据
  ├─ 东方财富/天天基金：基金名录、净值、收益
  ├─ 新浪：基金规模、指数 OHLCV 日线
  ├─ 乐咕乐股：指数 PE/PB 历史序列
  ├─ 金十数据：PMI、CPI
  ├─ 东方财富：M1/M2、LPR
  └─ 雪球：单基金费率详情（可选补全）
                 │
             AKShare 适配层
                 │
         SQLite TTL 缓存（data/）
                 │
    ┌────────────┼─────────────┐
    │            │             │
估值引擎      趋势引擎      宏观/政策引擎      基金筛选器
    │            │              │                 │
    └────────────┴────── AI 八因子评分 ───────────┘
                 │
        Agent 编排 / 策略 / 提醒
                 │
          Streamlit / CLI
```

数据通过 AKShare 获取，`jijin/data/cache.py` 使用 SQLite 做 TTL 缓存。
远端估值接口失败时优先使用有效缓存，避免单个指数拖垮整个看板。
基金、估值、行情和宏观数据分别设置缓存周期；宏观数据默认缓存 24 小时。

多指数评分与重点机会扫描使用受限线程池并行请求公开数据。默认并发数为 5，
可在 `config.yaml` 调整：

```yaml
performance:
  max_workers: 5
```

程序会将并发数限制在 1–8，避免对 AKShare 上游造成过高压力。重点机会只拉取
排名所需的指数日线，不再额外请求估值和基金数据；SQLite 使用 WAL 与写入等待
机制降低并发锁冲突。

## 决策看板与仓位变化

看板采用“重点机会优先”的信息层级：

- 首屏状态条：市场温度、宏观/政策、首位机会、仓位动作；
- 全宽展示重点机会 Top10（按上涨概率排序）；
- 下方并排展示建议仓位变化与观察池评分；
- 持仓、八因子和宏观明细默认折叠。

加载时并行拉取机会扫描、观察指数评分、仓位建议与宏观数据；只为需要调整的仓位动作生成解释，减少重复计算。

仓位目标不是直接把全部资产投入单个指数。引擎先读取
`portfolio.index_plans` 的计划仓位，再根据指数估值档位乘以仓位系数：

```text
估值目标仓位 = 计划仓位 × 估值档位系数
建议变化金额 = 总资产 ×（目标仓位 - 当前仓位）
```

只有偏离达到 `alert.min_rebalance_pct`（默认 5 个百分点）才提示增持或减持；
没有计划仓位且没有持仓的指数只观察，不生成整仓买入建议。

## 重点机会（市场指数）

实现位置：`jijin/screener/opportunity.py` + `jijin/data/market.py`。

系统扫描内置**市场指数宇宙**（宽基 + 行业/主题，约 50 只），使用「策略参数」中的
趋势展望周期（`trend.default_horizon`）计算偏多概率，按概率从高到低取前 N
（默认 15）：

```text
上涨概率 TopN = sort(probability_up)[:N]
```

可在「重点机会」页按分组筛选：宽基规模、红利风格、一级行业、金融地产、
消费医药、科技成长、周期制造。行情优先新浪，失败回退东方财富。

看板「重点机会」与侧边栏「重点机会」页共用同一套扫描逻辑。基金费率、规模、
4433 等筛选已移除；调参请到「策略参数」。

## 趋势引擎

实现位置：`jijin/engine/trend.py`。

标准技术指标由主流开源库
[`pandas-ta-classic`](https://github.com/xgboosted/pandas-ta-classic)
计算，不再维护自有指标公式：

| 指标 | 参数 | 用途 |
|------|------|------|
| SMA | 20 / 60 / 120 日 | 判断多空排列和中期方向 |
| MACD | 12 / 26 / 9 | 判断动能方向及柱体扩张 |
| RSI | 14 日 | 判断超买、超卖及市场情绪 |
| ROC | 20 日 | 计算短期动量 |
| ADX | 14 日 | 衡量趋势强度，不判断方向 |
| 年化波动 | 近60日标准差 × √252 | 风险分档 |
| 量能 | 近20日均量 / 前20日均量 | 识别放量上涨、放量下跌和缩量 |

趋势分仍是项目自己的可解释规则：

```text
趋势分 = MA 30% + MACD 25% + RSI 15% + ROC动量 15% + 量能 15%
```

- 权重 / 阈值 / enhancements：始终用用户配置（校准与策略参数页才生效）；
- 指标窗口：默认展望周期用用户配置，其他周期用内置时间尺度窗口。
- ADX 体制门控、Supertrend 确认、软均线分、多周期对齐（见 `RESEARCH.md` §6）。

可通过 `config.yaml` 的 `trend.enhancements` 或「策略参数」页开关上述能力。

这些是默认值，不是写死策略。用户可在界面「策略参数」页或
`config.yaml` 的 `trend` 节修改：

- SMA、MACD、RSI、ROC、ADX、波动率和量能周期；
- MA、MACD、RSI、动量和量能的趋势分权重；
- RSI 超买/超卖、放量/缩量、波动风险阈值。

输入权重无需恰好等于 100%，引擎会在计算时按比例自动归一化。界面会校验
SMA 短/中/长期顺序、MACD 快慢线顺序和波动风险阈值。

### 策略参数自动生成（Walk-Forward）

实现位置：`jijin/engine/calibrate.py`；界面在「策略参数 → 自动校准」。

业界更稳妥的做法不是「用全部历史一次性网格搜出最好参数」（容易过拟合），而是：

| 方法 | 说明 | 本项目 |
|------|------|--------|
| Walk-Forward | 滚动训练窗选参、测试窗样本外评估 | ✅ 默认 |
| 粗网格 + 收缩 | 候选少、最优解向默认权重 shrink | ✅ |
| 组合目标 | 方向命中率 + Spearman IC + 简化多空 Sharpe | ✅ |
| 全样本调参 / 细网格 | 历史表观最好，实盘常失效 | ❌ 刻意避免 |
| HRP / 贝叶斯优化 | 更适合仓位或超大搜索空间 | 未上；后续可选 |

流程概要：

1. 拉取观察指数约 **5 年**日线（缓存最长约 1600 根 K 线）；
2. 对权重 / RSI 阈值 / 若干均线方案做粗网格；
3. 训练窗约 2 年、测试窗约 3 个月、步长约 3 个月滚动；
4. 仅当样本外目标显著优于默认，才建议写回；仍可手工强制应用。

配置节：`config.yaml` 的 `calibration`（`years` / `train_days` / `test_days` / `shrinkage` 等）。

输出包括 0–100 趋势分、MA/MACD 信号、RSI、年化波动、动量、
ADX 趋势强度、风险等级，以及所选展望周期的方向（偏多/中性/偏空）、
偏多概率和 1σ 波动带宽。`probability_up` 是把趋势分映射到
15%–85% 的**方向置信度**，并会随展望周期拉长向 50% 收缩；它不是经
样本外回测校准的真实概率，也不是点位预测。自动校准优化的是趋势规则参数，
不会把 `probability_up` 变成统计校准概率。

在「评分趋势」页进入后会**自动刷新并同时展示全部周期**：

- 未来1天 / 1周 / 1个月 / 3个月 / 6个月 / 1年

无需再选择展望周期或手动点计算；切换分析指数后也会自动重算。
热力矩阵与曲线对比一眼可见长短期差异。默认周期仅用于 AI 解释引用
（`config.yaml` 的 `trend.default_horizon`，默认 `1m`）。

选择 `pandas-ta-classic` 的原因：

- 指标口径成熟，避免手写 EMA/RSI/MACD 的实现偏差；
- 原生兼容 Pandas，无 TA-Lib C 动态库安装负担；
- 可选使用 TA-Lib 作为加速与一致性校验后端；
- 便于后续增加 ATR、OBV、布林带、Aroon 等指标。

## AI 八因子评分

实现位置：`jijin/engine/scoring.py` + `jijin/engine/macro.py`。

```text
总分 =
  估值 25% + 趋势 15% + 资金 12% + 盈利 12% +
  风险 8% + 情绪 8% + 宏观 12% + 政策 8%
```

| 因子 | 当前口径 |
|------|----------|
| 估值 | `100 - PE/PB 历史百分位`，低估高分 |
| 趋势 | 直接使用趋势引擎总分 |
| 资金 | 量能状态 + 20日动量的近似值 |
| 盈利 | PE 绝对区间 + PE 百分位修正 |
| 风险 | 年化波动和趋势风险等级 |
| 情绪 | RSI 区间 + 短期动量 |
| 宏观 | PMI、CPI、M2 同比合成 |
| 政策 | LPR 变动 + 流动性推断，可手工覆盖立场/分数 |

总分 ≥70 为“机会”，45–70 为“中性”，低于45为“谨慎”。宏观与政策是**全市场共用因子**，对所有指数同一时刻相同；资金/盈利仍是公开行情代理变量。

权重、阈值与政策立场可在「策略参数」页的「AI 八因子评分 / 宏观与政策」调整，或改 `config.yaml`。关闭宏观模块后，宏观/政策权重会并入估值与趋势。

宏观数据通过 `jijin/data/macro.py` 获取并缓存，`jijin/engine/macro.py`
负责评分。自动政策立场由 **LPR 最近变动 + M2 流动性** 推断；它不是政策
文件 NLP 或对未来政策的预测。用户可在策略参数页选择宽松/中性/偏紧，
也可直接指定 0–100 政策分覆盖自动结果。

配置示例：

```yaml
trend:
  indicators:
    ma_short: 20
    ma_medium: 60
    ma_long: 120
    rsi_length: 14
  weights:
    ma: 0.30
    macd: 0.25
    rsi: 0.15
    momentum: 0.15
    volume: 0.15

scoring:
  weights:
    valuation: 0.25
    trend: 0.15
    capital: 0.12
    earnings: 0.12
    risk: 0.08
    sentiment: 0.08
    macro: 0.12
    policy: 0.08
  labels:
    opportunity_min: 70
    neutral_min: 45

macro:
  enabled: true
  policy:
    stance: auto
```

## Agent、策略与解释

- `jijin/agents/`：编排估值、趋势、评分、仓位与 Coach，不是 LLM Agent。
- `jijin/agents/coach.py`：将指标和规则转换为推荐原因、谨慎原因、
  风险来源与统计依据。
- `jijin/strategy/`：根据风险偏好、估值分档和目标配置生成定投方案。
- `jijin/alert/`：生成估值、趋势、风险、再平衡和定投提醒。
- `jijin/screener/`：基金筛选和指数级 PE/PB、AI 分挂载。

## 智能提醒

智能提醒按优先级分为：

- **待执行（action）**：定投、增持、减持和再平衡；
- **风险（warn）**：趋势偏弱、空头排列、高波动或高估；
- **观察（info）**：低估、机会区、趋势偏多及定投日历。

页面顶部汇总三类数量，重要提醒优先显示。再平衡提醒与看板使用相同口径，
紧凑展示当前/目标仓位、变化百分点和金额；观察信息及完整说明默认折叠。
提醒目前保存在当前会话并显示在本地界面，尚未接入邮件、企业微信、
Telegram 或 App Push。

## 目录

```text
app.py                         Streamlit 入口（转调插件化 Shell）
config.yaml                    用户配置、持仓和策略参数
examples/                      第三方插件示例
jijin/
  plugin/                      插件内核（注册表 / 加载器 / 规格）
  plugins_builtin/             内置页面·Agent·策略·提醒·数据源注册
  pages/                       页面实现（可替换的 UI 组件）
  ui/                          Shell / 样式 / 控件 / 后台加载
  data/                        AKShare 数据适配与 SQLite 缓存
  engine/                      趋势、评分、宏观、校准
  agents/                      编排与规则解释
  screener/                    指数机会扫描
  strategy/                    仓位与定投方案
  alert/                       智能提醒
  portfolio/                   持仓数据
  utils/                       HTTP 超时、后台任务
tests/                         规则与插件测试
```

## 插件化扩展

扩展点（均通过 `jijin.plugin.registry` 注册）：

| 类型 | 用途 | 内置示例 |
|------|------|----------|
| Page | Streamlit 页面 | 看板 / 重点机会 / … |
| Agent | 业务编排 | score / opportunity / dashboard |
| Strategy | 仓位策略模板 | valuation_dynamic 等 |
| Alert | 提醒生成器 | position / smart |
| DataProvider | 行情与宏观数据源 | index_daily / index_valuation |

**加载架构（防卡死）：**
- 无缓存：阻塞进度面板 + `st.fragment` 每秒刷新；可点「跳过等待」
- 有缓存刷新：先渲染旧数据，后台更新
- HTTP/urllib 默认 12s 超时；机会扫描总超时约 75s，超时返回部分结果
- 换页会 bump generation，旧任务结果不再写入

配置（`config.yaml`）：

```yaml
plugins:
  disabled: []          # 禁用页面 id，如 [parameters]
  modules: []           # 额外模块，需提供 register(registry)
  entry_points: true    # 扫描 jijin.plugins 入口点
```

最小自定义页面见 `examples/hello_page_plugin.py`。

当前测试覆盖配置合并与权重归一化、趋势指标、估值辅助规则、宏观/政策
评分，以及插件注册。执行：

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

## 已知边界

- 免费公开接口可能变更、限流或短暂失效；
- 技术指标只能描述历史价格行为；
- PMI/CPI 等免费宏观接口可能存在发布时间滞后，界面会显示当前可得最新值；
- 自动政策分是 LPR/M2 的规则映射，不代表正式政策解读；
- 权重和阈值尚未经过完整的滚动样本外回测；
- 跟踪误差、ETF 成交额、申赎资金流和指数盈利增速尚未完整接入（规划见产品文档数据信号）；
- 交易成本尚未写入建议与回测（规划见产品文档 §3.1）；
- **无实盘下单能力（刻意不做）**。
