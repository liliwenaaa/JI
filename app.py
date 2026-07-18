from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from jijin.agents import (
    build_dashboard,
    calibrate_agent,
    coach_agent,
    opportunity_agent,
    portfolio_agent,
    score_agent,
    trend_horizons_agent,
)
from jijin.alert.smart import generate_smart_alerts
from jijin.config import cache_dir, load_config, save_config, to_yaml_safe
from jijin.data.cache import CacheStore
from jijin.data.market import INDEX_GROUPS, INDEX_SYMBOLS
from jijin.engine.settings import (
    DEFAULT_MACRO_SETTINGS,
    DEFAULT_SCORING_SETTINGS,
    DEFAULT_TREND_SETTINGS,
    get_macro_settings,
    get_scoring_settings,
    get_trend_settings,
    list_trend_horizons,
)
from jijin.screener.opportunity import (
    market_index_universe,
    opportunities_to_rows,
    opportunity_scan_errors,
)
from jijin.strategy.generator import RISK_PROFILES, STRATEGY_TEMPLATES


INDEX_OPTIONS = list(INDEX_SYMBOLS.keys())
INDEX_GROUP_OPTIONS = ["全部", *INDEX_GROUPS.keys()]


def inject_style() -> None:
    st.markdown(
        """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --ink:#132421;
  --muted:#4d615b;
  --muted-soft:#6a7d77;
  --teal:#0a6e5c;
  --teal-2:#14967c;
  --deep:#064c40;
  --mint:#dff3ec;
  --surface:rgba(255,255,255,.92);
  --surface-solid:#fff;
  --line:#d2e0da;
  --ok:#0f7a4c;
  --rose:#b04444;
  --amber:#a96510;
  --shadow:0 1px 1px rgba(12,40,34,.03), 0 12px 32px rgba(12,40,34,.06);
  --radius:16px;
  --font-display:"Sora","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;
  --font-body:"Noto Sans SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
html,body,.stApp,.stMarkdown,.stText{
  font-family:var(--font-body)!important;
  color:var(--ink);
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
}
.brand-kicker,.brand-title,.section-title,
.metric-item .value,.metric-item .label,
div[data-testid="stTabs"] [data-baseweb="tab"],
.stButton>button{
  font-family:var(--font-display)!important;
}
.stApp{
  background:
    radial-gradient(980px 420px at 0% -8%, rgba(20,150,120,.16), transparent 58%),
    radial-gradient(760px 380px at 100% 0%, rgba(10,110,92,.10), transparent 52%),
    linear-gradient(165deg,#f3f8f5 0%, #e7f0eb 42%, #e3ede8 100%);
  background-attachment:fixed;
}
.stApp::before{
  content:"";
  position:fixed; inset:0; pointer-events:none; z-index:0; opacity:.28;
  background-image:
    linear-gradient(rgba(10,110,92,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(10,110,92,.035) 1px, transparent 1px);
  background-size:28px 28px;
  mask-image:radial-gradient(ellipse 80% 70% at 50% 20%, #000 20%, transparent 75%);
}
[data-testid="stAppViewContainer"], .main, .block-container{position:relative; z-index:1}
.block-container{
  max-width:1180px;
  padding-top:3.75rem!important;
  padding-bottom:5.5rem!important;
  padding-left:2.1rem;
  padding-right:2.1rem;
}
header[data-testid="stHeader"]{
  background:rgba(243,248,245,.72)!important;
  backdrop-filter:blur(14px) saturate(1.15);
  border-bottom:1px solid rgba(210,224,218,.65);
}
div[data-testid="stDecoration"]{display:none}
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{
  background:
    radial-gradient(420px 280px at 20% 0%, rgba(126,201,178,.16), transparent 60%),
    linear-gradient(180deg,#0c2823 0%, #12352e 48%, #0b221e 100%)!important;
}
section[data-testid="stSidebar"]{
  border-right:1px solid rgba(255,255,255,.08);
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{
  padding:1.15rem .9rem 1.6rem!important;
}
section[data-testid="stSidebar"] *,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div{
  color:#f5fbf8!important;
  opacity:1!important;
  -webkit-text-fill-color:#f5fbf8!important;
}
section[data-testid="stSidebar"] .sidebar-brand{
  width:100%; box-sizing:border-box;
  padding:0 0 1rem; margin:0 0 .85rem;
  border-bottom:1px solid rgba(255,255,255,.12);
}
section[data-testid="stSidebar"] .sidebar-brand .mark{
  display:flex; align-items:center; justify-content:center;
  width:2rem; height:2rem; border-radius:10px; margin:0 0 .65rem;
  background:linear-gradient(145deg, rgba(159,217,199,.35), rgba(159,217,199,.12));
  color:#e8fff6!important; -webkit-text-fill-color:#e8fff6!important;
  font-weight:700; font-size:.95rem;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.16);
}
section[data-testid="stSidebar"] .sidebar-brand h2{
  margin:0; padding:0; font-size:1.35rem; letter-spacing:-.04em; font-weight:700;
  color:#ffffff!important; -webkit-text-fill-color:#ffffff!important;
  font-family:var(--font-display)!important;
}
section[data-testid="stSidebar"] .sidebar-brand p{
  margin:.4rem 0 0; padding:0;
  color:#d5ebe3!important; -webkit-text-fill-color:#d5ebe3!important;
  font-size:.84rem; line-height:1.55; font-weight:400;
  font-family:var(--font-body)!important; letter-spacing:.015em;
}
/* 导航：整列等宽左对齐，去掉圆点错位 */
section[data-testid="stSidebar"] [data-testid="stRadio"],
section[data-testid="stSidebar"] [data-testid="stRadio"] > div,
section[data-testid="stSidebar"] [role="radiogroup"]{
  width:100%!important;
  max-width:100%!important;
  box-sizing:border-box!important;
}
section[data-testid="stSidebar"] [role="radiogroup"]{
  display:flex!important;
  flex-direction:column!important;
  align-items:stretch!important;
  gap:.22rem!important;
  margin:0!important;
}
section[data-testid="stSidebar"] [role="radiogroup"] > *{
  width:100%!important;
  max-width:100%!important;
  box-sizing:border-box!important;
  margin:0!important;
}
section[data-testid="stSidebar"] [role="radiogroup"] > label,
section[data-testid="stSidebar"] [role="radiogroup"] label{
  width:100%!important;
  max-width:100%!important;
  box-sizing:border-box!important;
  display:flex!important;
  align-items:center!important;
  justify-content:flex-start!important;
  gap:0!important;
  margin:0!important;
  padding:.7rem .85rem .7rem 1rem!important;
  border-radius:10px!important;
  border:1px solid transparent!important;
  background:rgba(255,255,255,.05)!important;
  transition:background .15s ease, border-color .15s ease, box-shadow .15s ease;
  cursor:pointer;
}
section[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child,
section[data-testid="stSidebar"] [data-baseweb="radio"],
section[data-testid="stSidebar"] [role="radiogroup"] label span[data-baseweb="radio"]{
  display:none!important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label [data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] [role="radiogroup"] label [data-testid="stMarkdownContainer"] > *{
  width:100%!important; margin:0!important; padding:0!important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label p,
section[data-testid="stSidebar"] [role="radiogroup"] label span{
  color:#f5fbf8!important; -webkit-text-fill-color:#f5fbf8!important;
  font-size:.95rem!important; font-weight:600!important; letter-spacing:.02em;
  line-height:1.3!important; margin:0!important;
  font-family:var(--font-display)!important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover{
  background:rgba(255,255,255,.1)!important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
  background:linear-gradient(90deg, rgba(126,201,178,.3), rgba(126,201,178,.1))!important;
  border-color:rgba(180,230,210,.28)!important;
  box-shadow:inset 3px 0 0 #9fd9c7;
}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p,
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) span{
  color:#ffffff!important; -webkit-text-fill-color:#ffffff!important;
  font-weight:700!important;
}
section[data-testid="stSidebar"] svg{fill:#e8f4ef!important; stroke:#e8f4ef!important}
.brand-wrap{
  display:grid; grid-template-columns:5px minmax(0,1fr); gap:1.05rem; align-items:stretch;
  margin:0 0 1.55rem; animation:riseIn .5s cubic-bezier(.22,1,.36,1) both;
}
.brand-accent{
  border-radius:999px;
  background:linear-gradient(180deg, var(--teal-2) 0%, var(--teal) 45%, rgba(10,110,92,.25) 100%);
  box-shadow:0 0 0 4px rgba(10,110,92,.08);
  min-height:4.8rem;
}
.brand-kicker{
  margin:0; color:var(--teal); font-size:.68rem; letter-spacing:.18em;
  text-transform:uppercase; font-weight:700; line-height:1.4;
}
.brand-title{
  margin:.22rem 0 0; font-size:2.35rem; font-weight:700; color:var(--ink);
  line-height:1.12; letter-spacing:-.045em;
}
.brand-sub{
  margin:.5rem 0 0; color:var(--muted); font-size:.95rem; max-width:40rem;
  line-height:1.7; font-weight:400; letter-spacing:.02em;
  font-family:var(--font-body)!important;
}
@media(max-width:760px){
  .block-container{padding-top:4rem!important;padding-left:1rem;padding-right:1rem}
  .brand-title{font-size:1.75rem}
}
.metric-strip{
  display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.9rem;
  margin:.15rem 0 1.45rem;
}
@media(max-width:900px){.metric-strip{grid-template-columns:repeat(2,minmax(0,1fr))}}
.metric-item{
  position:relative; overflow:hidden;
  background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  padding:1.1rem 1.15rem 1.05rem; box-shadow:var(--shadow);
  backdrop-filter:blur(10px);
  transition:transform .22s ease, box-shadow .22s ease;
  animation:riseIn .55s cubic-bezier(.22,1,.36,1) both;
}
.metric-item:nth-child(2){animation-delay:.04s}
.metric-item:nth-child(3){animation-delay:.08s}
.metric-item:nth-child(4){animation-delay:.12s}
.metric-item::before{
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background:linear-gradient(180deg,var(--teal-2),var(--teal));
}
.metric-item::after{
  content:""; position:absolute; right:-18%; top:-40%; width:55%; height:90%;
  background:radial-gradient(circle, rgba(10,110,92,.08), transparent 68%);
  pointer-events:none;
}
.metric-item:hover{transform:translateY(-3px); box-shadow:0 8px 28px rgba(12,40,34,.1)}
.metric-item .label{
  font-size:.72rem; color:var(--muted); font-weight:650; letter-spacing:.04em; text-transform:uppercase;
}
.metric-item .value{
  font-size:1.78rem; font-weight:700; margin-top:.28rem; line-height:1.1;
  letter-spacing:-.04em; font-variant-numeric:tabular-nums;
}
.metric-item .hint{
  font-size:.82rem; color:var(--muted-soft); margin-top:.35rem; line-height:1.55;
  font-weight:400; letter-spacing:.01em; font-family:var(--font-body)!important;
}
.section-title{
  font-size:1.05rem; font-weight:700; margin:.1rem 0 .85rem; color:var(--ink);
  letter-spacing:-.025em; display:flex; align-items:center; gap:.55rem;
}
.section-title::before{
  content:""; width:.4rem; height:.4rem; border-radius:2px; background:var(--teal);
  box-shadow:0 0 0 4px rgba(10,110,92,.12);
}
.dash-lead{
  display:flex; justify-content:space-between; align-items:center; gap:1rem; flex-wrap:wrap;
  margin:.05rem 0 .9rem; padding:.55rem .7rem;
  background:rgba(10,110,92,.04); border:1px dashed rgba(10,110,92,.18); border-radius:10px;
}
.dash-lead .note{
  color:var(--muted); font-size:.875rem; line-height:1.65; font-weight:400;
  letter-spacing:.015em; font-family:var(--font-body)!important;
}
.dash-lead .note strong{color:var(--deep); font-weight:600}
.opp-list{
  border:1px solid var(--line); border-radius:var(--radius); overflow:hidden;
  background:var(--surface-solid); box-shadow:var(--shadow);
}
.opp-row{
  display:grid; grid-template-columns:2.5rem minmax(6.5rem,1.15fr) .7fr 1fr .85fr .85fr;
  gap:.55rem; align-items:center; padding:.78rem .95rem;
  border-bottom:1px solid var(--line); font-size:.86rem;
  transition:background .15s ease;
}
.opp-row:last-child{border-bottom:0}
.opp-row:hover{background:#f4faf7}
.opp-row.top{background:linear-gradient(90deg,#e5f5ee 0%, #fff 58%)}
.opp-row.top:hover{background:linear-gradient(90deg,#daf1e7 0%, #f8fcfa 58%)}
.opp-rank{font-weight:700; color:#7a8c86; font-variant-numeric:tabular-nums}
.opp-name{font-weight:700; letter-spacing:-.015em}
.opp-bias{font-weight:700}
/* A股习惯：红涨 / 绿跌 */
.opp-bias.up{color:var(--rose)}.opp-bias.down{color:var(--ok)}.opp-bias.flat{color:var(--muted)}
.opp-prob{font-weight:700; font-variant-numeric:tabular-nums; color:var(--deep); font-size:.95rem}
.opp-meta{color:var(--muted); white-space:nowrap; font-size:.8rem}
@media(max-width:760px){
  .opp-row{grid-template-columns:2rem 1fr .8fr .9fr}
  .opp-meta{display:none}
}
.position-summary{
  display:flex; gap:.55rem 1.1rem; flex-wrap:wrap; align-items:center;
  color:var(--muted); font-size:.82rem; margin:-.1rem 0 .85rem;
  padding:.55rem .75rem; border-radius:10px; background:rgba(10,110,92,.04);
}
.position-summary strong{color:var(--ink); font-size:.95rem}
.position-list{
  border:1px solid var(--line); border-radius:var(--radius); overflow:hidden;
  background:var(--surface-solid); box-shadow:var(--shadow);
}
.position-row{
  display:grid; grid-template-columns:minmax(7rem,1.25fr) .65fr 1.35fr .8fr 1fr;
  gap:.65rem; align-items:center; padding:.82rem .95rem;
  border-bottom:1px solid var(--line); font-size:.86rem;
  transition:background .15s ease;
}
.position-row:last-child{border-bottom:0}
.position-row:hover{background:#f5faf8}
.position-name{font-weight:700}
.position-name small{display:block; color:var(--muted); font-weight:400; margin-top:.14rem}
.position-action{font-weight:700}
.position-action.buy,.position-delta.buy{color:var(--rose)}
.position-action.sell,.position-delta.sell{color:var(--ok)}
.position-change{font-weight:650; white-space:nowrap; font-variant-numeric:tabular-nums}
.position-change .arrow{color:var(--muted); padding:0 .28rem}
.position-delta{font-weight:700; white-space:nowrap; font-variant-numeric:tabular-nums}
.position-amount{text-align:right; white-space:nowrap; color:var(--muted); font-variant-numeric:tabular-nums}
@media(max-width:760px){
  .position-row{grid-template-columns:1.2fr .7fr 1.2fr}
  .position-delta,.position-amount{display:none}
}
.alert-list{display:flex; flex-direction:column; gap:.6rem}
.alert-row{
  display:grid; grid-template-columns:4.8rem minmax(8rem,1.1fr) minmax(12rem,2fr) auto;
  gap:.7rem; align-items:center; padding:.8rem .9rem;
  border:1px solid var(--line); border-radius:13px; background:var(--surface-solid);
  font-size:.85rem; box-shadow:0 1px 2px rgba(12,40,34,.03);
  transition:transform .15s ease, box-shadow .15s ease;
}
.alert-row:hover{transform:translateY(-2px); box-shadow:var(--shadow)}
.alert-category{
  font-size:.68rem; font-weight:700; text-align:center; padding:.22rem .45rem;
  border-radius:8px; background:var(--mint); color:var(--deep); letter-spacing:.03em;
}
.alert-title{font-weight:700}
.alert-detail{color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.alert-value{font-weight:700; white-space:nowrap; text-align:right; font-variant-numeric:tabular-nums}
.alert-row.action{border-left:3px solid var(--rose)}.alert-row.action .alert-value{color:var(--rose)}
.alert-row.warn{border-left:3px solid var(--ok)}.alert-row.warn .alert-value{color:var(--ok)}
@media(max-width:760px){
  .alert-row{grid-template-columns:4.2rem 1fr auto}
  .alert-detail{display:none}
}
.trend-matrix{
  border-collapse:separate; border-spacing:0; width:100%; font-size:.82rem;
  border:1px solid var(--line); border-radius:var(--radius); overflow:hidden;
  box-shadow:var(--shadow); background:var(--surface-solid);
}
.trend-matrix th,.trend-matrix td{
  padding:.58rem .62rem; text-align:center;
  border-bottom:1px solid var(--line); border-right:1px solid var(--line);
}
.trend-matrix thead th{background:#e8f3ee; font-weight:700; color:var(--ink)}
.trend-matrix tbody th{
  background:var(--surface-solid); text-align:left; font-weight:700;
  white-space:nowrap; position:sticky; left:0;
}
.trend-matrix td:last-child,.trend-matrix th:last-child{border-right:0}
.trend-matrix tbody tr:last-child td,.trend-matrix tbody tr:last-child th{border-bottom:0}
.tm-cell{display:flex; flex-direction:column; gap:.1rem; line-height:1.2}
.tm-bias{font-weight:700}.tm-score{font-size:.72rem; opacity:.85}
.tm-legend{display:flex; gap:1rem; align-items:center; flex-wrap:wrap; color:var(--muted); font-size:.78rem; margin:.6rem 0 .1rem}
.tm-chip{display:inline-flex; align-items:center; gap:.35rem}
.tm-swatch{width:.9rem; height:.9rem; border-radius:3px; display:inline-block}
.stButton>button{
  border-radius:11px!important; font-weight:650!important; letter-spacing:-.01em;
  border:1px solid var(--line)!important; min-height:2.55rem;
  transition:transform .15s ease, background .15s ease, box-shadow .15s ease;
}
.stButton>button[kind="primary"], .stButton>button[data-testid="baseButton-primary"]{
  background:linear-gradient(180deg,#128870 0%, var(--teal) 100%)!important;
  color:#fff!important; border:0!important;
  box-shadow:0 1px 0 rgba(255,255,255,.2) inset, 0 8px 18px rgba(10,110,92,.22);
}
.stButton>button:hover{
  background:var(--deep)!important; color:#fff!important; border-color:transparent!important;
  transform:translateY(-1px);
}
div[data-testid="stWidgetLabel"] p,
.stSelectbox label p, .stNumberInput label p, .stTextInput label p,
.stCheckbox label p, .stRadio label p, .stMultiSelect label p{
  font-weight:650!important; color:var(--ink)!important; font-size:.88rem!important;
}
div[data-baseweb="select"] > div, .stNumberInput input, .stTextInput input, .stTextArea textarea{
  border-radius:11px!important; border-color:var(--line)!important;
  background:#fff!important; min-height:2.55rem;
  box-shadow:0 1px 0 rgba(12,40,34,.02);
}
div[data-baseweb="select"] > div:hover, .stNumberInput input:hover, .stTextInput input:hover{
  border-color:#b7cdc4!important;
}
div[data-baseweb="select"] > div:focus-within, .stNumberInput input:focus, .stTextInput input:focus{
  border-color:var(--teal)!important;
  box-shadow:0 0 0 3px rgba(10,110,92,.14)!important;
}
.stMarkdown h4{
  font-size:1rem!important; font-weight:700!important; letter-spacing:-.02em;
  margin:1.1rem 0 .55rem!important; color:var(--ink)!important;
  padding-left:.55rem; border-left:3px solid var(--teal);
}
.stCaption, [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p, [data-testid="stCaptionContainer"] span{
  font-family:var(--font-body)!important;
  color:var(--muted)!important;
  font-size:.875rem!important;
  line-height:1.7!important;
  font-weight:400!important;
  letter-spacing:.02em!important;
}
hr{border:none!important; border-top:1px solid var(--line)!important; margin:1.4rem 0!important}
div[data-testid="stAlert"]{
  border-radius:12px!important; border:1px solid var(--line)!important;
  box-shadow:0 1px 2px rgba(12,40,34,.03);
}
div[data-testid="stAlert"] p{
  font-family:var(--font-body)!important;
  line-height:1.65!important; letter-spacing:.015em!important; font-weight:400!important;
}
.disclaimer{
  margin-top:2.2rem; padding:1.05rem 0 0; border-top:1px solid var(--line);
  color:var(--muted-soft); font-size:.84rem; line-height:1.7;
  font-weight:400; letter-spacing:.02em; font-family:var(--font-body)!important;
}
div[data-testid="stDataFrame"]{
  border:1px solid var(--line); border-radius:var(--radius);
  background:var(--surface-solid); overflow:hidden; box-shadow:var(--shadow);
}
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:var(--surface)!important;
  border:1px solid var(--line)!important;
  border-radius:var(--radius)!important;
  box-shadow:var(--shadow);
  backdrop-filter:blur(10px);
  padding-top:.15rem;
}
div[data-testid="stTabs"]{margin-bottom:.1rem}
div[data-testid="stTabs"] [data-baseweb="tab-list"]{
  gap:.28rem!important; flex-wrap:wrap;
  background:rgba(255,255,255,.72);
  border:1px solid var(--line);
  border-radius:14px;
  padding:.38rem!important;
  margin-bottom:1rem!important;
  border-bottom:1px solid var(--line)!important;
  box-shadow:var(--shadow);
}
div[data-testid="stTabs"] [data-baseweb="tab-border"],
div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{display:none!important}
div[data-testid="stTabs"] [data-baseweb="tab"]{
  border-radius:10px!important; padding:.55rem 1rem!important;
  font-weight:650!important; font-size:.9rem!important;
  color:var(--muted)!important; background:transparent!important; border:0!important;
}
div[data-testid="stTabs"] [data-baseweb="tab"]:hover{
  background:rgba(10,110,92,.08)!important; color:var(--ink)!important;
}
div[data-testid="stTabs"] [aria-selected="true"]{
  background:linear-gradient(180deg,#128870 0%, var(--teal) 100%)!important;
  color:#fff!important;
  box-shadow:0 1px 0 rgba(255,255,255,.22) inset, 0 6px 14px rgba(10,110,92,.2);
}
div[data-testid="stTabs"] [data-baseweb="tab"] *{color:inherit!important}
.panel-hint{
  display:flex; gap:.85rem; align-items:flex-start;
  margin:0 0 1.15rem; padding:.9rem 1.05rem;
  border-radius:14px;
  background:linear-gradient(120deg, rgba(10,110,92,.06), rgba(255,255,255,.72));
  border:1px solid rgba(10,110,92,.12);
  border-left:3px solid var(--teal);
  box-shadow:0 1px 0 rgba(255,255,255,.55) inset;
}
.panel-hint-label{
  flex:0 0 auto; margin-top:.12rem;
  font-family:var(--font-display)!important;
  font-size:.66rem; font-weight:700; letter-spacing:.16em;
  text-transform:uppercase; color:var(--teal);
  padding:.2rem .45rem; border-radius:6px;
  background:rgba(10,110,92,.1); line-height:1.2;
}
.panel-hint-text{
  margin:0; flex:1 1 auto;
  font-family:var(--font-body)!important;
  color:var(--muted); font-size:.9rem; font-weight:400;
  line-height:1.75; letter-spacing:.025em;
}
.panel-hint-text strong{color:var(--ink); font-weight:600}
div[data-testid="stExpander"]{
  border:1px solid var(--line)!important; border-radius:13px!important;
  background:var(--surface-solid); overflow:hidden; box-shadow:0 1px 2px rgba(12,40,34,.03);
}
@keyframes riseIn{
  from{opacity:0; transform:translateY(10px)}
  to{opacity:1; transform:translateY(0)}
}
@keyframes accentIn{
  from{opacity:0; transform:scaleY(.7)}
  to{opacity:1; transform:scaleY(1)}
}
.brand-accent{animation:accentIn .55s cubic-bezier(.22,1,.36,1) both; transform-origin:top}
</style>
        """,
        unsafe_allow_html=True,
    )


def get_cfg() -> dict[str, Any]:
    if "cfg" not in st.session_state:
        st.session_state.cfg = load_config()
    return st.session_state.cfg


def header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
<div class="brand-wrap">
  <div class="brand-accent" aria-hidden="true"></div>
  <div>
    <p class="brand-kicker">AI Index · 指数决策助手</p>
    <p class="brand-title">{escape(title)}</p>
    <p class="brand-sub">{escape(subtitle)}</p>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    st.markdown(f'<p class="section-title">{title}</p>', unsafe_allow_html=True)


def panel_hint(text: str, *, label: str = "说明") -> None:
    """Tab 内说明：独立提示条，避免与切换项视觉混淆。"""
    body = text.strip()
    for prefix in (f"{label} · ", f"{label}· ", f"{label}·", f"{label}：", f"{label}:"):
        if body.startswith(prefix):
            body = body[len(prefix) :].lstrip()
            break
    st.markdown(
        f"""
<div class="panel-hint">
  <span class="panel-hint-label">{escape(label)}</span>
  <p class="panel-hint-text">{escape(body)}</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def _trend_cell_color(score: float | None) -> str:
    """趋势分映射到绿(跌)→灰→红(涨)的浅色底，符合 A 股习惯。"""
    if score is None:
        return "#f3f5f4"
    s = max(0.0, min(100.0, float(score)))
    if s >= 50:
        t = (s - 50) / 50  # 0..1 越大越红（偏多）
        r, g, b = 255, 243 - int(90 * t), 243 - int(90 * t)
    else:
        t = (50 - s) / 50  # 0..1 越大越绿（偏空）
        r, g, b = 238 - int(150 * t), 248 - int(20 * t), 243 - int(80 * t)
    return f"rgb({r},{g},{b})"


def _sorted_horizon_results(results: list[Any]) -> list[Any]:
    """按展望交易日数从小到大排序，避免中文标签被字母序打乱。"""
    return sorted(results, key=lambda tr: (int(getattr(tr, "horizon_days", 0) or 0), str(tr.horizon)))


def _normalize_trend_multi(multi: dict[str, list[Any]]) -> dict[str, list[Any]]:
    return {name: _sorted_horizon_results(results) for name, results in multi.items()}


def _horizon_axis_order(multi: dict[str, list[Any]]) -> list[str]:
    for results in multi.values():
        return [tr.horizon_label for tr in _sorted_horizon_results(results)]
    return []


def render_horizon_line_chart(
    multi: dict[str, list[Any]],
    *,
    value_attr: str,
    value_title: str,
    y_domain: list[float] | None = None,
) -> None:
    """用 Altair 固定横轴为 1天→1年，避免 st.line_chart 按中文拼音/字典序重排。"""
    multi = _normalize_trend_multi(multi)
    order = _horizon_axis_order(multi)
    if not order:
        return
    rows = []
    for name, results in multi.items():
        for tr in results:
            rows.append(
                {
                    "指数": name,
                    "周期": tr.horizon_label,
                    "交易日": int(tr.horizon_days),
                    value_title: float(getattr(tr, value_attr)),
                }
            )
    chart_df = pd.DataFrame(rows)
    y_enc = alt.Y(f"{value_title}:Q", title=value_title)
    if y_domain is not None:
        y_enc = alt.Y(f"{value_title}:Q", title=value_title, scale=alt.Scale(domain=y_domain))
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("周期:N", sort=order, title="展望周期"),
            y=y_enc,
            color=alt.Color(
                "指数:N",
                legend=alt.Legend(title="指数"),
                scale=alt.Scale(
                    range=["#0a6e5c", "#2f8f78", "#4aa88f", "#c45c4a", "#a96510", "#3d6b8c"]
                ),
            ),
            tooltip=["指数", "周期", "交易日", value_title],
        )
        .properties(height=300)
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#5f6d69",
            titleColor="#142421",
            gridColor="#e3ece8",
            domainColor="#d5e2dc",
        )
    )
    st.altair_chart(chart, width="stretch")


def render_trend_matrix(multi: dict[str, list[Any]]) -> None:
    """指数 × 展望周期 的趋势热力矩阵。"""
    multi = _normalize_trend_multi(multi)
    if not multi:
        return
    horizon_labels = _horizon_axis_order(multi)

    head = "".join(f"<th>{escape(h)}</th>" for h in horizon_labels)
    body_rows = []
    for name, results in multi.items():
        by_label = {tr.horizon_label: tr for tr in results}
        cells = []
        for label in horizon_labels:
            tr = by_label.get(label)
            if tr is None:
                cells.append("<td>—</td>")
                continue
            color = _trend_cell_color(tr.score)
            prob = f"{tr.probability_up:.0%}"
            band = "" if tr.move_band_pct is None else f" ±{tr.move_band_pct:.0f}%"
            cells.append(
                f'<td style="background:{color}">'
                f'<div class="tm-cell"><span class="tm-bias">{escape(tr.bias)}</span>'
                f'<span class="tm-score">{tr.score:.0f} · {prob}{band}</span></div></td>'
            )
        body_rows.append(f"<tr><th>{escape(name)}</th>{''.join(cells)}</tr>")

    st.markdown(
        f'<table class="trend-matrix"><thead><tr><th>指数 \\ 周期</th>{head}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class="tm-legend">
  <span class="tm-chip"><span class="tm-swatch" style="background:rgb(255,153,153)"></span>偏多 / 涨</span>
  <span class="tm-chip"><span class="tm-swatch" style="background:#f3f5f4"></span>中性</span>
  <span class="tm-chip"><span class="tm-swatch" style="background:rgb(88,228,163)"></span>偏空 / 跌</span>
  <span>单元格：方向 · 趋势分 · 偏多概率 · 波动带宽</span>
</div>
        """,
        unsafe_allow_html=True,
    )


def position_change_list(advices: list[Any], explanations: dict[str, Any]) -> None:
    actionable = sorted(
        [a for a in advices if a.action in {"增持", "减持"}],
        key=lambda a: abs(a.delta_pct),
        reverse=True,
    )
    stable = [a for a in advices if a.action not in {"增持", "减持"}]

    if not actionable:
        st.success("仓位均在目标范围内，暂不需要调整")
    else:
        add_amount = sum(max(0.0, a.suggest_amount) for a in actionable)
        reduce_amount = sum(abs(min(0.0, a.suggest_amount)) for a in actionable)
        st.markdown(
            f"""
<div class="position-summary">
  <span><strong>{len(actionable)}</strong> 项需调整</span>
  <span>增持约 <strong>¥{add_amount:,.0f}</strong></span>
  <span>减持约 <strong>¥{reduce_amount:,.0f}</strong></span>
</div>
            """,
            unsafe_allow_html=True,
        )
        rows = []
        for a in actionable:
            tone = "buy" if a.action == "增持" else "sell"
            sign = "+" if a.delta_pct > 0 else "−"
            amount_sign = "+" if a.suggest_amount > 0 else "−"
            percentile = "暂无百分位" if a.percentile is None else f"{a.metric.upper()} 分位 {a.percentile:.0f}%"
            rows.append(
                f"""
<div class="position-row">
  <div class="position-name">{escape(a.index)}<small>{escape(a.label)} · {percentile}</small></div>
  <div class="position-action {tone}">{a.action}</div>
  <div class="position-change">{a.current_pct:.1f}%<span class="arrow">→</span>{a.target_pct:.1f}%</div>
  <div class="position-delta {tone}">{sign}{abs(a.delta_pct):.1f}pct</div>
  <div class="position-amount">{amount_sign}¥{abs(a.suggest_amount):,.0f}</div>
</div>
                """
            )
        st.markdown(
            '<div class="position-list">' + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )

        with st.expander("查看调整依据"):
            for a in actionable:
                exp = explanations.get(f"action:{a.index}")
                st.markdown(f"**{a.index} · {a.action}**")
                if exp:
                    st.write(exp.summary)
                    reasons = exp.why_recommend + exp.risk_sources
                    for item in reasons:
                        st.write(f"- {item}")
                else:
                    st.caption(a.message)

    if stable:
        with st.expander(f"无需调整 / 数据不足（{len(stable)}）"):
            stable_df = pd.DataFrame(
                [
                    {
                        "指数": a.index,
                        "状态": a.action,
                        "当前": f"{a.current_pct:.1f}%",
                        "目标": f"{a.target_pct:.1f}%",
                        "估值": a.label,
                    }
                    for a in stable
                ]
            )
            st.dataframe(stable_df, width="stretch", hide_index=True)


def render_opportunity_list(items: list[Any], horizon_label: str) -> None:
    if not items:
        st.caption("暂无可用的市场指数机会")
        return
    st.markdown(
        f"""
<div class="dash-lead">
  <div class="note">扫描宽基与行业指数 · 展望「{escape(horizon_label)}」· 按上涨概率排序</div>
  <div class="note">首位 <strong>{escape(items[0].index)}</strong> · {items[0].probability_up:.0%}</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    rows = []
    for item in items:
        if (getattr(item, "details", None) or {}).get("empty"):
            continue
        tone = "up" if item.bias == "偏多" else ("down" if item.bias == "偏空" else "flat")
        top = " top" if item.rank <= 3 else ""
        band = "—" if item.move_band_pct is None else f"±{item.move_band_pct:.0f}%"
        regime = (getattr(item, "details", None) or {}).get("regime") or ""
        meta_extra = f"{escape(regime)} · " if regime else ""
        rows.append(
            f"""
<div class="opp-row{top}">
  <div class="opp-rank">#{item.rank}</div>
  <div class="opp-name">{escape(item.index)}</div>
  <div class="opp-bias {tone}">{escape(item.bias)}</div>
  <div class="opp-prob">{item.probability_up:.0%}</div>
  <div class="opp-meta">趋势 {item.trend_score:.0f}</div>
  <div class="opp-meta">{meta_extra}{escape(item.risk_level)} · {band}</div>
</div>
            """
        )
    if not rows:
        st.caption("暂无可用的市场指数机会")
        return
    st.markdown('<div class="opp-list">' + "".join(rows) + "</div>", unsafe_allow_html=True)


def page_dashboard(cfg: dict[str, Any]) -> None:
    header("决策看板", "重点机会优先，仓位动作次之")
    c1, c2 = st.columns([4, 1])
    with c1:
        force = st.checkbox("忽略缓存，获取最新数据", value=False, key="dash_force")
    with c2:
        go = st.button("刷新", type="primary", width="stretch")

    if go or "dash_snap" not in st.session_state:
        with st.spinner("并行加载机会 / 评分 / 仓位 / 宏观…"):
            try:
                st.session_state.dash_snap = build_dashboard(cfg, force=force)
            except Exception as exc:  # noqa: BLE001
                st.error(f"看板加载失败：{exc}")
                return

    snap = st.session_state.dash_snap
    if snap.opportunities and not hasattr(snap.opportunities[0], "probability_up"):
        with st.spinner("更新重点机会扫描…"):
            st.session_state.dash_snap = build_dashboard(cfg, force=False)
            snap = st.session_state.dash_snap

    temp = "—" if snap.market_temperature is None else f"{snap.market_temperature:.0f}%"
    buy = sum(1 for a in snap.advices if a.action == "增持")
    sell = sum(1 for a in snap.advices if a.action == "减持")
    top = snap.opportunities[0] if snap.opportunities else None
    top_text = "—" if top is None else f"{top.index}"
    top_hint = "暂无排名" if top is None else f"{top.probability_up:.0%} · {top.bias}"
    if snap.macro is not None:
        macro_value = snap.macro.stance
        macro_hint = f"宏观 {snap.macro.macro_score:.0f} · 政策 {snap.macro.policy_score:.0f}"
    else:
        macro_value = "—"
        macro_hint = snap.market_label

    st.markdown(
        f"""
<div class="metric-strip">
  <div class="metric-item"><div class="label">市场温度</div><div class="value">{temp}</div><div class="hint">{escape(snap.market_label)}</div></div>
  <div class="metric-item"><div class="label">宏观 / 政策</div><div class="value">{escape(str(macro_value))}</div><div class="hint">{escape(macro_hint)}</div></div>
  <div class="metric-item"><div class="label">首位机会</div><div class="value">{escape(top_text)}</div><div class="hint">{escape(top_hint)}</div></div>
  <div class="metric-item"><div class="label">仓位动作</div><div class="value">{buy}↑ {sell}↓</div><div class="hint">总资产 ¥{snap.total_assets:,.0f}</div></div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        section_title("重点机会")
        render_opportunity_list(snap.opportunities, snap.opportunity_horizon)

    left, right = st.columns([1.25, 1], gap="large")
    with left:
        with st.container(border=True):
            section_title("建议仓位变化")
            if not snap.advices:
                st.info("暂无仓位建议")
            else:
                position_change_list(snap.advices, snap.explanations)

    with right:
        with st.container(border=True):
            section_title("观察池评分")
            if snap.ai_scores:
                score_df = pd.DataFrame(
                    [{"指数": s.index, "总分": s.total, "判断": s.label} for s in snap.ai_scores]
                )
                st.dataframe(
                    score_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "总分": st.column_config.ProgressColumn("总分", min_value=0, max_value=100)
                    },
                )
            else:
                st.caption("暂无观察指数评分")

            if snap.holdings_exposure:
                with st.expander("当前持仓"):
                    exp_df = pd.DataFrame(
                        [
                            {
                                "指数": k,
                                "金额": round(v["amount"], 2),
                                "仓位%": round(v["weight_pct"], 1),
                            }
                            for k, v in snap.holdings_exposure.items()
                        ]
                    )
                    st.dataframe(exp_df, width="stretch", hide_index=True)
            else:
                with st.expander("当前持仓"):
                    st.caption("尚未配置持仓")

            with st.expander("八因子与宏观明细"):
                if snap.ai_scores:
                    active_weights = get_scoring_settings(cfg)["weights"]
                    detail_df = pd.DataFrame(
                        [
                            {
                                "指数": s.index,
                                "估值": s.valuation,
                                "趋势": s.trend,
                                "资金": s.capital,
                                "盈利": s.earnings,
                                "风险": s.risk,
                                "情绪": s.sentiment,
                                "宏观": s.macro,
                                "政策": s.policy,
                            }
                            for s in snap.ai_scores
                        ]
                    )
                    st.dataframe(detail_df, width="stretch", hide_index=True)
                    st.caption(
                        "权重："
                        + " · ".join(f"{key} {value * 100:.0f}%" for key, value in active_weights.items())
                    )
                if snap.macro is not None:
                    m = snap.macro
                    st.caption(
                        f"PMI {m.pmi if m.pmi is not None else '—'} · "
                        f"CPI {m.cpi if m.cpi is not None else '—'}% · "
                        f"M2 {m.m2_yoy if m.m2_yoy is not None else '—'}% · "
                        f"LPR1Y {m.lpr_1y if m.lpr_1y is not None else '—'}%"
                    )


def page_opportunities(cfg: dict[str, Any]) -> None:
    header(
        "重点机会",
        "扫描宽基 + 行业/主题指数，按策略参数上涨概率排出前列（不是基金筛选）",
    )
    trend_cfg = get_trend_settings(cfg)
    horizon = str(trend_cfg.get("default_horizon") or "1m")
    horizon_label = {
        "1d": "未来1天",
        "1w": "未来1周",
        "1m": "未来1个月",
        "3m": "未来3个月",
        "6m": "未来6个月",
        "1y": "未来1年",
    }.get(horizon, horizon)
    default_group = str((cfg.get("opportunity") or {}).get("universe_group") or "全部")
    if default_group not in INDEX_GROUP_OPTIONS:
        default_group = "全部"

    g1, g2, g3 = st.columns([2, 3, 1])
    with g1:
        group = st.selectbox(
            "指数分组",
            INDEX_GROUP_OPTIONS,
            index=INDEX_GROUP_OPTIONS.index(default_group),
            key="opp_group",
        )
    with g2:
        force = st.checkbox("忽略缓存，获取最新行情", value=False, key="opp_force")
        universe = market_index_universe(cfg, group=None if group == "全部" else group)
        st.caption(
            f"扫描 {len(universe)} 个指数 · 展望 {horizon_label} · 排名看上涨概率"
        )
    with g3:
        refresh = st.button("刷新机会", type="primary", width="stretch")

    # 临时覆盖分组，供 opportunity_agent / scan 读取
    run_cfg = dict(cfg)
    run_cfg["opportunity"] = {
        **dict(cfg.get("opportunity") or {}),
        "universe_group": None if group == "全部" else group,
        "top_n": int((cfg.get("opportunity") or {}).get("top_n") or 15),
    }

    cache_key = (horizon, group, len(universe))
    need_refresh = (
        refresh
        or "opp_list" not in st.session_state
        or st.session_state.get("opp_cache_key") != cache_key
    )
    if need_refresh:
        with st.spinner(f"扫描「{group}」指数并按 {horizon_label} 上涨概率排序…"):
            try:
                st.session_state.opp_list = opportunity_agent(
                    cfg=run_cfg, force=force, top_n=run_cfg["opportunity"]["top_n"]
                )
                st.session_state.opp_cache_key = cache_key
                st.session_state.opp_fetched_at = pd.Timestamp.now().strftime("%H:%M:%S")
            except Exception as exc:  # noqa: BLE001
                st.error(f"机会扫描失败：{exc}")
                return

    items = st.session_state.get("opp_list") or []
    scan_errors = opportunity_scan_errors(items)
    if scan_errors:
        with st.expander(f"部分指数扫描失败（{len(scan_errors)}）", expanded=False):
            st.caption("；".join(scan_errors[:12]))
    real_items = [x for x in items if not (x.details or {}).get("empty")]
    if not real_items:
        st.warning("暂无结果，请检查行情数据或稍后重试")
        return

    fetched = st.session_state.get("opp_fetched_at")
    section_title(f"上涨概率 Top {len(real_items)} · {real_items[0].horizon_label}")
    if fetched:
        st.caption(f"数据更新于 {fetched}")
    df = pd.DataFrame(opportunities_to_rows(real_items))
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "上涨概率": st.column_config.ProgressColumn(
                "上涨概率", min_value=0, max_value=1, format="percent"
            ),
            "趋势分": st.column_config.ProgressColumn("趋势分", min_value=0, max_value=100),
        },
        height=min(520, 56 + 34 * len(real_items)),
    )

    with st.expander("扫描宇宙（市场指数）"):
        by_group: dict[str, list[str]] = {}
        from jijin.data.market import index_group_of

        for name in universe:
            by_group.setdefault(index_group_of(name), []).append(name)
        for gname, names in by_group.items():
            st.markdown(f"**{gname}**（{len(names)}）")
            st.caption("、".join(names))
        st.caption("决策口径来自「策略参数」；估值百分位暂主要覆盖宽基观察池。")

    st.download_button(
        "导出结果 CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "ai_index_opportunities.csv",
        "text/csv",
    )


def page_score(cfg: dict[str, Any]) -> None:
    active_weights = get_scoring_settings(cfg)["weights"]
    weight_text = " + ".join(
        f"{key}{value * 100:.0f}%"
        for key, value in active_weights.items()
    )
    header("评分与趋势", "自动刷新全部展望周期，一眼对比方向与强弱")
    indexes = cfg.get("valuation", {}).get("watch_indexes") or ["沪深300", "中证500"]
    pick = st.multiselect(
        "分析指数",
        options=list(dict.fromkeys(indexes + INDEX_OPTIONS)),
        default=list(indexes),
        key="score_pick",
    )
    default_horizon = get_trend_settings(cfg).get("default_horizon", "1m")
    c1, c2 = st.columns([4, 1])
    with c1:
        force = st.checkbox("忽略缓存，获取最新行情", value=False, key="score_force")
    with c2:
        manual_refresh = st.button("刷新", type="primary", width="stretch")

    if not pick:
        st.info("请至少选择一个指数")
        return

    cache_key = ("|".join(pick), default_horizon)
    need_refresh = (
        manual_refresh
        or "trend_multi" not in st.session_state
        or st.session_state.get("score_cache_key") != cache_key
    )

    if need_refresh:
        rows = []
        trends = {}
        multi = {}
        with st.spinner("自动计算全部展望周期（1天~1年）…"):
            for name in pick:
                try:
                    sc = score_agent(name, cfg=cfg, force=force)
                    horizons = trend_horizons_agent(name, cfg=cfg, force=force)
                    multi[name] = horizons
                    # 主结果用默认展望周期（配置 trend.default_horizon）
                    tr = next(
                        (h for h in horizons if h.horizon == default_horizon),
                        next(
                            (h for h in horizons if h.horizon == "1m"),
                            horizons[0],
                        ),
                    )
                    trends[name] = tr
                    st_dir = (tr.details or {}).get("supertrend_dir")
                    st_label = "—"
                    if st_dir is not None:
                        st_label = "多" if int(st_dir) >= 1 else "空"
                    mtf = (tr.details or {}).get("mtf_align")
                    mtf_txt = "—"
                    if isinstance(mtf, dict) and mtf.get("agree") is not None:
                        mtf_txt = f"一致{mtf.get('agree', 0)}/冲突{mtf.get('conflict', 0)}"
                    rows.append(
                        {
                            "指数": sc.index,
                            "AI分": sc.total,
                            "标签": sc.label,
                            "估值": sc.valuation,
                            "趋势": sc.trend,
                            "资金": sc.capital,
                            "盈利": sc.earnings,
                            "风险分": sc.risk,
                            "情绪": sc.sentiment,
                            "宏观": sc.macro,
                            "政策": sc.policy,
                            "参考展望": tr.horizon_label,
                            "方向": tr.bias,
                            "趋势分": tr.score,
                            "体制": (tr.details or {}).get("regime") or "—",
                            "Supertrend": st_label,
                            "强度": tr.strength,
                            "MTF": mtf_txt,
                            "趋势风险": tr.risk_level,
                            "偏多概率": tr.probability_up,
                            "波动带宽%": tr.move_band_pct,
                            "MA": tr.ma_signal,
                            "MACD": tr.macd_signal,
                            "RSI": tr.rsi,
                            "波动%": tr.volatility,
                            "动量%": tr.momentum_20d,
                            "量能": tr.volume_trend,
                        }
                    )
                    st.session_state[f"exp_{name}"] = coach_agent(sc, tr)
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"{name}: {exc}")
        st.session_state.score_table = pd.DataFrame(rows)
        st.session_state.trend_map = trends
        st.session_state.trend_multi = multi
        st.session_state.score_cache_key = cache_key
        st.session_state.score_fetched_at = pd.Timestamp.now().strftime("%H:%M:%S")

    table = st.session_state.get("score_table")
    multi = st.session_state.get("trend_multi") or {}
    if not multi:
        st.warning("暂无趋势结果")
        return

    section_title("多周期趋势对比")
    st.caption("进入页面即自动刷新全部周期；红偏多、绿偏空、灰中性（A股红涨绿跌）。周期越长，方向置信度越向中性收缩。")
    multi = _normalize_trend_multi(multi)
    render_trend_matrix(multi)

    chart_tab, prob_tab, table_tab = st.tabs(["趋势分曲线", "偏多概率曲线", "明细表"])
    with chart_tab:
        st.caption("横轴按 1天 → 1周 → 1个月 → 3个月 → 6个月 → 1年 排列；越高越偏多（50 为中性）")
        render_horizon_line_chart(
            multi,
            value_attr="score",
            value_title="趋势分",
            y_domain=[0, 100],
        )
    with prob_tab:
        st.caption("偏多方向置信度；周期越长越向 50% 收缩")
        render_horizon_line_chart(
            multi,
            value_attr="probability_up",
            value_title="偏多概率",
            y_domain=[0, 1],
        )
    with table_tab:
        compare_rows = []
        for name, results in multi.items():
            for tr in results:
                compare_rows.append(
                    {
                        "指数": name,
                        "周期": tr.horizon_label,
                        "交易日": tr.horizon_days,
                        "方向": tr.bias,
                        "趋势分": tr.score,
                        "偏多概率": tr.probability_up,
                        "体制": (tr.details or {}).get("regime") or "—",
                        "强度": tr.strength,
                        "波动带宽%": tr.move_band_pct,
                        "风险": tr.risk_level,
                        "MA": tr.ma_signal,
                    }
                )
        compare_df = pd.DataFrame(compare_rows)
        if not compare_df.empty:
            compare_df = compare_df.sort_values(["指数", "交易日"], kind="mergesort")
        st.dataframe(
            compare_df.drop(columns=["交易日"], errors="ignore"),
            width="stretch",
            hide_index=True,
            column_config={
                "趋势分": st.column_config.ProgressColumn("趋势分", min_value=0, max_value=100),
                "偏多概率": st.column_config.ProgressColumn(
                    "偏多概率", min_value=0, max_value=1, format="percent"
                ),
            },
            height=min(460, 56 + 36 * len(compare_rows)),
        )

    if table is not None and not table.empty:
        section_title("AI 综合评分")
        core_columns = [
            "指数",
            "AI分",
            "标签",
            "参考展望",
            "方向",
            "趋势分",
            "体制",
            "Supertrend",
            "强度",
            "MTF",
            "偏多概率",
            "趋势风险",
        ]
        show_cols = [c for c in core_columns if c in table.columns]
        st.dataframe(
            table[show_cols],
            width="stretch",
            hide_index=True,
            column_config={
                "AI分": st.column_config.ProgressColumn("AI 分", min_value=0, max_value=100),
                "趋势分": st.column_config.ProgressColumn("趋势分", min_value=0, max_value=100),
                "偏多概率": st.column_config.ProgressColumn(
                    "偏多概率", min_value=0, max_value=1, format="percent"
                ),
            },
        )
        with st.expander("查看因子与技术指标明细"):
            st.caption(f"评分权重：{weight_text}")
            st.dataframe(table, width="stretch", hide_index=True)

    section_title("决策解释")
    for name in pick:
        exp = st.session_state.get(f"exp_{name}")
        if not exp:
            continue
        with st.expander(exp.title, expanded=False):
            st.write(exp.summary)
            cols = st.columns(3)
            with cols[0]:
                st.markdown("**为什么推荐**")
                for x in exp.why_recommend or ["—"]:
                    st.write(f"- {x}")
            with cols[1]:
                st.markdown("**为什么谨慎**")
                for x in exp.why_not or ["—"]:
                    st.write(f"- {x}")
            with cols[2]:
                st.markdown("**风险来源**")
                for x in exp.risk_sources or ["—"]:
                    st.write(f"- {x}")
            st.markdown("**历史/统计依据**")
            for x in exp.evidence or ["—"]:
                st.write(f"- {x}")


def page_portfolio_smart(cfg: dict[str, Any]) -> None:
    header("智能仓位", "输入风险偏好和资金，生成可执行的配置方案")
    with st.form("pos_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            risk = st.selectbox("风险偏好", list(RISK_PROFILES.keys()), index=1)
        with c2:
            template = st.selectbox(
                "策略模板",
                list(STRATEGY_TEMPLATES.keys()),
                format_func=lambda k: STRATEGY_TEMPLATES[k]["label"],
            )
        with c3:
            assets = st.number_input(
                "总资产",
                0.0,
                value=float((cfg.get("portfolio") or {}).get("total_assets") or 100000),
                step=1000.0,
            )
        with c4:
            monthly = st.number_input("月定投", 0.0, value=3000.0, step=100.0)
        write_back = st.checkbox("写回计划仓位到配置", value=False)
        ok = st.form_submit_button("生成仓位方案", type="primary", width="stretch")

    if ok:
        with st.spinner("Portfolio Agent 计算中…"):
            plan = portfolio_agent(risk=risk, template=template, monthly_dca=monthly, cfg=cfg)
            plan.total_assets = assets
            st.session_state.plan = plan
            if write_back:
                cfg.setdefault("portfolio", {})["index_plans"] = {
                    s.index: round(s.target_weight, 2) for s in plan.sleeves
                }
                cfg["portfolio"]["total_assets"] = float(assets)
                save_config(cfg)
                st.session_state.cfg = load_config()
                st.session_state.pop("dash_snap", None)

    plan = st.session_state.get("plan")
    if not plan:
        st.info("生成后将展示目标仓位与推荐基金")
        return
    st.success(plan.summary)
    m1, m2, m3 = st.columns(3)
    m1.metric("权益目标", f"{plan.equity_ratio:.1f}%")
    m2.metric("现金/债缓冲", f"{plan.cash_bond_ratio:.1f}%")
    m3.metric("月定投", f"{plan.monthly_dca:,.0f}")
    st.dataframe(plan.to_dataframe(), width="stretch", hide_index=True)
    st.bar_chart(plan.to_dataframe().set_index("指数")[["基准仓位%", "目标仓位%"]], height=260)
    st.markdown("#### 执行规则")
    for r in plan.rules:
        st.write(f"- {r}")
    st.download_button("下载策略 Markdown", plan.to_markdown().encode("utf-8"), "ai_index_strategy.md")


def page_alerts(cfg: dict[str, Any]) -> None:
    header("智能提醒", "只关注需要处理的变化")
    c1, c2 = st.columns([4, 1])
    with c1:
        force = st.checkbox("忽略缓存，获取最新数据", value=False, key="alert_force")
    with c2:
        refresh = st.button("刷新提醒", type="primary", width="stretch")
    if refresh or "smart_alerts" not in st.session_state:
        with st.spinner("扫描市场与持仓…"):
            try:
                st.session_state.smart_alerts = generate_smart_alerts(cfg, force=force)
                st.session_state.alert_fetched_at = pd.Timestamp.now().strftime("%H:%M:%S")
            except Exception as exc:  # noqa: BLE001
                st.error(f"提醒生成失败：{exc}")
                return
    if st.session_state.get("alert_fetched_at"):
        st.caption(f"数据更新于 {st.session_state.alert_fetched_at}")

    alerts = st.session_state.smart_alerts
    action_count = sum(a.level == "action" for a in alerts)
    warn_count = sum(a.level == "warn" for a in alerts)
    info_count = sum(a.level == "info" for a in alerts)
    st.markdown(
        f"""
<div class="position-summary">
  <span><strong>{action_count}</strong> 项待执行</span>
  <span><strong>{warn_count}</strong> 项风险</span>
  <span>{info_count} 项观察</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    cats = ["全部", "估值", "趋势", "风险", "再平衡", "定投"]
    cat = st.radio("类型", cats, horizontal=True)
    filtered = alerts if cat == "全部" else [a for a in alerts if a.category == cat]
    if not filtered:
        st.info("无提醒")
        return

    priority = {"action": 0, "warn": 1, "info": 2}
    filtered = sorted(filtered, key=lambda a: (priority.get(a.level, 3), a.category, a.index))
    important = [a for a in filtered if a.level in {"action", "warn"}]
    info_alerts = [a for a in filtered if a.level == "info"]
    if important:
        section_title("需要关注")
        rows = []
        for a in important:
            if a.current_pct is not None and a.target_pct is not None:
                delta = a.delta_pct if a.delta_pct is not None else a.target_pct - a.current_pct
                sign = "+" if delta > 0 else "−"
                detail = f"{a.current_pct:.1f}% → {a.target_pct:.1f}% · {sign}{abs(delta):.1f}pct"
            else:
                detail = a.message
            if a.action and a.amount is not None:
                value = f"{escape(a.action)} ¥{a.amount:,.0f}"
            elif a.level == "warn":
                value = "注意风险"
            else:
                value = escape(a.action or "待处理")
            rows.append(
                f"""
<div class="alert-row {escape(a.level)}">
  <div class="alert-category">{escape(a.category)}</div>
  <div class="alert-title">{escape(a.title)}</div>
  <div class="alert-detail" title="{escape(a.message)}">{escape(detail)}</div>
  <div class="alert-value">{value}</div>
</div>
                """
            )
        st.markdown(
            '<div class="alert-list">' + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )

    if info_alerts:
        with st.expander(f"观察信息（{len(info_alerts)}）", expanded=not important):
            info_df = pd.DataFrame(
                [
                    {
                        "类型": a.category,
                        "指数": a.index,
                        "提醒": a.title,
                        "说明": a.message,
                    }
                    for a in info_alerts
                ]
            )
            st.dataframe(info_df, width="stretch", hide_index=True, height=300)

    if important:
        with st.expander("查看完整提醒内容"):
            for a in important:
                st.markdown(f"**{a.title}**")
                st.write(a.message)


def page_holdings(cfg: dict[str, Any]) -> None:
    header("持仓配置", "维护资产、目标仓位和基金明细")
    pf = dict(cfg.get("portfolio") or {})
    total_assets = st.number_input(
        "总资产(元)",
        0.0,
        value=float(pf.get("total_assets") or sum(float(h.get("amount") or 0) for h in (pf.get("holdings") or []))),
        step=1000.0,
    )
    st.markdown("#### 计划仓位 %")
    plans = dict(pf.get("index_plans") or {})
    names = sorted(set(list(plans) + (cfg.get("valuation", {}).get("watch_indexes") or []))) or ["沪深300"]
    new_plans = {}
    cols = st.columns(min(4, len(names)))
    for i, n in enumerate(names):
        with cols[i % len(cols)]:
            new_plans[n] = st.number_input(n, 0.0, 100.0, float(plans.get(n) or 0), 1.0, key=f"pl_{n}")
    plan_sum = sum(new_plans.values())
    st.caption(f"计划仓位合计：{plan_sum:.1f}%（权益目标，无需凑满 100）")
    if plan_sum > 100:
        st.warning("计划仓位合计超过 100%，请检查。")

    holdings = pf.get("holdings") or []
    hold_df = pd.DataFrame(holdings) if holdings else pd.DataFrame(columns=["code", "name", "amount", "index", "enabled"])
    for col in ["code", "name", "amount", "index", "enabled"]:
        if col not in hold_df.columns:
            hold_df[col] = True if col == "enabled" else (0 if col == "amount" else "")
    edited = st.data_editor(
        hold_df[["code", "name", "amount", "index", "enabled"]],
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        height=280,
        column_config={
            "code": st.column_config.TextColumn("代码"),
            "name": st.column_config.TextColumn("名称"),
            "amount": st.column_config.NumberColumn("金额(元)", min_value=0, step=1000),
            "index": st.column_config.SelectboxColumn("跟踪指数", options=INDEX_OPTIONS),
            "enabled": st.column_config.CheckboxColumn("启用"),
        },
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("保存", type="primary", width="stretch"):
            rows = []
            for _, r in edited.iterrows():
                code = str(r.get("code") or "").strip()
                if not code:
                    continue
                rows.append(
                    {
                        "code": code.zfill(6),
                        "name": str(r.get("name") or ""),
                        "amount": float(r.get("amount") or 0),
                        "index": str(r.get("index") or ""),
                        "enabled": bool(r.get("enabled", True)),
                    }
                )
            cfg["portfolio"] = {**pf, "total_assets": float(total_assets), "index_plans": new_plans, "holdings": rows}
            save_config(cfg)
            st.session_state.cfg = load_config()
            st.session_state.pop("dash_snap", None)
            st.success("已保存")
    with c2:
        if st.button("重载配置", width="stretch"):
            st.session_state.cfg = load_config()
            st.rerun()
    with c3:
        if st.button("清空缓存", width="stretch"):
            n = CacheStore(cache_dir(cfg) / "jijin_cache.db").clear()
            for k in list(st.session_state.keys()):
                if (
                    k.startswith("dash")
                    or k.startswith("screen")
                    or k.startswith("smart")
                    or k.startswith("exp_")
                    or k.startswith("opp_")
                    or k.startswith("score")
                    or k.startswith("trend")
                ):
                    st.session_state.pop(k, None)
            st.success(f"清除 {n} 条")


def _invalidate_analysis_state() -> None:
    for key in list(st.session_state.keys()):
        if key in {
            "dash_snap",
            "dash_cache_key",
            "opp_list",
            "opp_cache_key",
            "opp_fetched_at",
            "score_table",
            "trend_map",
            "trend_multi",
            "score_cache_key",
            "score_fetched_at",
            "smart_alerts",
            "alert_fetched_at",
            "cal_result",
        } or str(key).startswith("exp_"):
            st.session_state.pop(key, None)


def page_parameters(cfg: dict[str, Any]) -> None:
    header(
        "策略参数",
        "高级设置：趋势、八因子评分、宏观与政策、自动校准",
    )
    trend = get_trend_settings(cfg)
    scoring = get_scoring_settings(cfg)
    macro = get_macro_settings(cfg)

    trend_tab, scoring_tab, macro_tab, auto_tab = st.tabs(
        ["趋势引擎", "AI 八因子评分", "宏观与政策", "自动校准"]
    )
    with trend_tab:
        panel_hint(
            "说明 · 默认展望周期用于机会排名与看板；权重保存时自动归一化。"
            "默认周期的指标窗口用本页配置，其他周期仍用内置时间尺度窗口。"
        )
        with st.form("trend_parameters"):
            horizon_options = list_trend_horizons()
            horizon_labels = {k: lab for k, lab, _ in horizon_options}
            cur_h = str(trend.get("default_horizon") or "1m")
            default_horizon_pick = st.selectbox(
                "默认展望周期（机会排名 / 看板）",
                options=[k for k, _, _ in horizon_options],
                index=[k for k, _, _ in horizon_options].index(cur_h)
                if cur_h in horizon_labels
                else 2,
                format_func=lambda k: horizon_labels.get(k, k),
            )
            enhancements = dict(trend.get("enhancements") or {})
            st.markdown("#### 专业增强（可开关）")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                en_soft = st.checkbox(
                    "软均线分", value=bool(enhancements.get("soft_ma_score", True))
                )
            with e2:
                en_regime = st.checkbox(
                    "ADX 体制门控", value=bool(enhancements.get("regime_filter", True))
                )
            with e3:
                en_st = st.checkbox(
                    "Supertrend 确认",
                    value=bool(enhancements.get("supertrend_confirm", True)),
                )
            with e4:
                en_mtf = st.checkbox(
                    "多周期对齐",
                    value=bool(enhancements.get("multi_horizon_align", True)),
                )

            st.markdown("#### 技术指标周期")
            c1, c2, c3, c4 = st.columns(4)
            indicators = trend["indicators"]
            with c1:
                ma_short = st.number_input(
                    "短期 SMA", 2, 250, int(indicators["ma_short"])
                )
                ma_medium = st.number_input(
                    "中期 SMA", 3, 500, int(indicators["ma_medium"])
                )
                ma_long = st.number_input(
                    "长期 SMA", 5, 1000, int(indicators["ma_long"])
                )
            with c2:
                macd_fast = st.number_input(
                    "MACD 快线", 2, 100, int(indicators["macd_fast"])
                )
                macd_slow = st.number_input(
                    "MACD 慢线", 3, 200, int(indicators["macd_slow"])
                )
                macd_signal = st.number_input(
                    "MACD 信号线", 2, 100, int(indicators["macd_signal"])
                )
            with c3:
                rsi_length = st.number_input(
                    "RSI 周期", 2, 100, int(indicators["rsi_length"])
                )
                roc_length = st.number_input(
                    "ROC 动量周期", 2, 250, int(indicators["roc_length"])
                )
                adx_length = st.number_input(
                    "ADX 周期", 2, 100, int(indicators["adx_length"])
                )
            with c4:
                volatility_window = st.number_input(
                    "波动率窗口", 10, 500, int(indicators["volatility_window"])
                )
                volume_window = st.number_input(
                    "量能窗口", 5, 250, int(indicators["volume_window"])
                )

            st.markdown("#### 趋势分权重 %")
            weights = trend["weights"]
            weight_cols = st.columns(5)
            trend_weight_values = {}
            for col, key, label in zip(
                weight_cols,
                ["ma", "macd", "rsi", "momentum", "volume"],
                ["均线", "MACD", "RSI", "动量", "量能"],
            ):
                with col:
                    trend_weight_values[key] = st.number_input(
                        label,
                        0.0,
                        100.0,
                        float(weights[key] * 100),
                        1.0,
                        key=f"tw_{key}",
                    )
            st.caption(
                f"当前输入合计：{sum(trend_weight_values.values()):.1f}%（无需手工凑到100）"
            )

            st.markdown("#### 信号与风险阈值")
            thresholds = trend["thresholds"]
            t1, t2, t3, t4 = st.columns(4)
            with t1:
                rsi_oversold = st.number_input(
                    "RSI 超卖", 1.0, 49.0, float(thresholds["rsi_oversold"]), 1.0
                )
                rsi_overbought = st.number_input(
                    "RSI 超买", 51.0, 99.0, float(thresholds["rsi_overbought"]), 1.0
                )
            with t2:
                volume_expand = st.number_input(
                    "放量倍数",
                    1.0,
                    5.0,
                    float(thresholds["volume_expand_ratio"]),
                    0.05,
                )
                volume_contract = st.number_input(
                    "缩量倍数",
                    0.1,
                    1.0,
                    float(thresholds["volume_contract_ratio"]),
                    0.05,
                )
            with t3:
                risk_vol_medium = st.number_input(
                    "中风险波动率%",
                    1.0,
                    100.0,
                    float(thresholds["risk_volatility_medium"]),
                    1.0,
                )
                adx_trend_min = st.number_input(
                    "ADX 趋势线",
                    10.0,
                    50.0,
                    float(thresholds.get("adx_trend_min", 25)),
                    1.0,
                )
            with t4:
                risk_vol_high = st.number_input(
                    "高风险波动率%",
                    1.0,
                    150.0,
                    float(thresholds["risk_volatility_high"]),
                    1.0,
                )
                adx_range_max = st.number_input(
                    "ADX 震荡线",
                    5.0,
                    40.0,
                    float(thresholds.get("adx_range_max", 20)),
                    1.0,
                )

            save_trend = st.form_submit_button(
                "保存趋势参数", type="primary", width="stretch"
            )

        if save_trend:
            if not (ma_short < ma_medium < ma_long):
                st.error("SMA 周期必须满足：短期 < 中期 < 长期")
            elif macd_fast >= macd_slow:
                st.error("MACD 快线周期必须小于慢线周期")
            elif risk_vol_medium > risk_vol_high:
                st.error("中风险波动率不能高于高风险波动率")
            elif adx_range_max > adx_trend_min:
                st.error("ADX 震荡线不能高于趋势线")
            else:
                prev = dict(cfg.get("trend") or {})
                cfg["trend"] = {
                    **prev,
                    "default_horizon": default_horizon_pick,
                    "indicators": {
                        "ma_short": int(ma_short),
                        "ma_medium": int(ma_medium),
                        "ma_long": int(ma_long),
                        "macd_fast": int(macd_fast),
                        "macd_slow": int(macd_slow),
                        "macd_signal": int(macd_signal),
                        "rsi_length": int(rsi_length),
                        "roc_length": int(roc_length),
                        "adx_length": int(adx_length),
                        "volatility_window": int(volatility_window),
                        "volume_window": int(volume_window),
                    },
                    "weights": {
                        key: value / 100
                        for key, value in trend_weight_values.items()
                    },
                    "thresholds": {
                        **dict(prev.get("thresholds") or {}),
                        "rsi_oversold": float(rsi_oversold),
                        "rsi_overbought": float(rsi_overbought),
                        "volume_expand_ratio": float(volume_expand),
                        "volume_contract_ratio": float(volume_contract),
                        "risk_volatility_medium": float(risk_vol_medium),
                        "risk_volatility_high": float(risk_vol_high),
                        "adx_trend_min": float(adx_trend_min),
                        "adx_range_max": float(adx_range_max),
                    },
                    "enhancements": {
                        "soft_ma_score": bool(en_soft),
                        "regime_filter": bool(en_regime),
                        "supertrend_confirm": bool(en_st),
                        "multi_horizon_align": bool(en_mtf),
                    },
                }
                save_config(cfg)
                st.session_state.cfg = load_config()
                _invalidate_analysis_state()
                st.success("趋势参数已保存；权重已在计算时自动归一化。")
                st.rerun()

    with scoring_tab:
        panel_hint(
            "说明 · 八因子权重保存时自动归一化为 100%。"
            "关闭宏观模块后，宏观/政策权重会并入估值与趋势。"
        )
        with st.form("scoring_parameters"):
            st.markdown("#### 八因子权重 %")
            weights = scoring["weights"]
            cols = st.columns(4)
            scoring_weight_values = {}
            score_items = [
                ("valuation", "估值"),
                ("trend", "趋势"),
                ("capital", "资金"),
                ("earnings", "盈利"),
                ("risk", "风险"),
                ("sentiment", "情绪"),
                ("macro", "宏观"),
                ("policy", "政策"),
            ]
            for i, (key, label) in enumerate(score_items):
                with cols[i % 4]:
                    scoring_weight_values[key] = st.number_input(
                        label,
                        0.0,
                        100.0,
                        float(weights[key] * 100),
                        1.0,
                        key=f"sw_{key}",
                    )
            st.caption(
                f"当前输入合计：{sum(scoring_weight_values.values()):.1f}%（无需手工凑到100）"
            )

            st.markdown("#### 标签阈值")
            label_cols = st.columns(2)
            labels = scoring["labels"]
            with label_cols[0]:
                neutral_min = st.number_input(
                    "中性最低分",
                    0.0,
                    100.0,
                    float(labels["neutral_min"]),
                    1.0,
                )
            with label_cols[1]:
                opportunity_min = st.number_input(
                    "机会最低分",
                    0.0,
                    100.0,
                    float(labels["opportunity_min"]),
                    1.0,
                )
            save_scoring = st.form_submit_button(
                "保存评分参数", type="primary", width="stretch"
            )

        if save_scoring:
            if neutral_min > opportunity_min:
                st.error("中性最低分不能高于机会最低分")
            else:
                cfg["scoring"] = {
                    "weights": {
                        key: value / 100
                        for key, value in scoring_weight_values.items()
                    },
                    "labels": {
                        "neutral_min": float(neutral_min),
                        "opportunity_min": float(opportunity_min),
                    },
                }
                save_config(cfg)
                st.session_state.cfg = load_config()
                _invalidate_analysis_state()
                st.success("评分参数已保存；权重已在计算时自动归一化。")

    with macro_tab:
        panel_hint(
            "说明 · PMI / CPI / M2 / LPR 来自公开数据；政策立场可自动推断，也可手工覆盖。"
        )
        with st.form("macro_parameters"):
            enabled = st.checkbox("启用宏观与政策因子", value=bool(macro["enabled"]))
            st.markdown("#### 宏观内部分项权重 %")
            mw = macro["weights"]
            mcols = st.columns(3)
            macro_weight_values = {}
            for col, key, label in zip(
                mcols,
                ["pmi", "cpi", "liquidity"],
                ["制造业 PMI", "CPI", "流动性(M2)"],
            ):
                with col:
                    macro_weight_values[key] = st.number_input(
                        label,
                        0.0,
                        100.0,
                        float(mw[key] * 100),
                        1.0,
                        key=f"mw_{key}",
                    )

            st.markdown("#### 阈值")
            th = macro["thresholds"]
            t1, t2, t3 = st.columns(3)
            with t1:
                pmi_expansion = st.number_input("PMI 荣枯线", 40.0, 60.0, float(th["pmi_expansion"]), 0.1)
                pmi_strong = st.number_input("PMI 强扩张", 45.0, 65.0, float(th["pmi_strong"]), 0.1)
            with t2:
                cpi_low = st.number_input("CPI 偏低线%", -2.0, 5.0, float(th["cpi_low"]), 0.1)
                cpi_comfort_high = st.number_input("CPI 舒适上限%", 0.0, 8.0, float(th["cpi_comfort_high"]), 0.1)
                cpi_high = st.number_input("CPI 偏高线%", 1.0, 12.0, float(th["cpi_high"]), 0.1)
            with t3:
                m2_soft = st.number_input("M2 偏弱线%", 0.0, 20.0, float(th["m2_soft"]), 0.1)
                m2_comfort = st.number_input("M2 舒适上限%", 0.0, 25.0, float(th["m2_comfort"]), 0.1)
                m2_hot = st.number_input("M2 过热线%", 0.0, 30.0, float(th["m2_hot"]), 0.1)

            st.markdown("#### 政策立场")
            stance_options = [
                ("auto", "自动（依据 LPR 变动 + M2）"),
                ("easing", "宽松"),
                ("neutral", "中性"),
                ("tightening", "偏紧"),
            ]
            current_stance = str(macro["policy"].get("stance") or "auto").lower()
            stance_alias = {
                "auto": 0,
                "自动": 0,
                "easing": 1,
                "宽松": 1,
                "neutral": 2,
                "中性": 2,
                "tightening": 3,
                "偏紧": 3,
            }
            stance_choice = st.selectbox(
                "立场",
                stance_options,
                index=stance_alias.get(current_stance, 0),
                format_func=lambda x: x[1],
            )
            use_manual = st.checkbox(
                "手工指定政策分",
                value=macro["policy"].get("manual_score") is not None,
            )
            manual_score = st.number_input(
                "政策分（0-100）",
                0.0,
                100.0,
                float(macro["policy"].get("manual_score") or 55),
                1.0,
                disabled=not use_manual,
            )
            save_macro = st.form_submit_button(
                "保存宏观与政策参数", type="primary", width="stretch"
            )

        if save_macro:
            if pmi_expansion > pmi_strong:
                st.error("PMI 荣枯线不能高于强扩张线")
            elif cpi_low > cpi_comfort_high or cpi_comfort_high > cpi_high:
                st.error("CPI 阈值需满足：偏低线 ≤ 舒适上限 ≤ 偏高线")
            elif m2_soft > m2_comfort or m2_comfort > m2_hot:
                st.error("M2 阈值需满足：偏弱线 ≤ 舒适上限 ≤ 过热线")
            else:
                cfg["macro"] = {
                    "enabled": bool(enabled),
                    "weights": {key: value / 100 for key, value in macro_weight_values.items()},
                    "thresholds": {
                        "pmi_expansion": float(pmi_expansion),
                        "pmi_strong": float(pmi_strong),
                        "cpi_low": float(cpi_low),
                        "cpi_comfort_high": float(cpi_comfort_high),
                        "cpi_high": float(cpi_high),
                        "m2_soft": float(m2_soft),
                        "m2_comfort": float(m2_comfort),
                        "m2_hot": float(m2_hot),
                    },
                    "policy": {
                        "stance": stance_choice[0],
                        "manual_score": float(manual_score) if use_manual else None,
                    },
                }
                save_config(cfg)
                st.session_state.cfg = load_config()
                _invalidate_analysis_state()
                st.success("宏观与政策参数已保存。")

    with auto_tab:
        panel_hint(
            "说明 · 用近约 5 年指数日线做 Walk-Forward（滚动样本外）粗网格搜索："
            "在训练窗选参数，在测试窗评估方向命中率、Spearman IC 与简化多空 Sharpe；"
            "最优解向默认参数收缩，且仅当样本外明显优于默认才建议写回，降低过拟合。"
        )
        cal = dict(cfg.get("calibration") or {})
        c1, c2, c3 = st.columns(3)
        with c1:
            cal_years = st.number_input(
                "回看年数", 2.0, 8.0, float(cal.get("years", 5.0)), 0.5
            )
            cal_forward = st.number_input(
                "前瞻交易日", 5, 63, int(cal.get("forward_days", 21)), 1
            )
        with c2:
            cal_train = st.number_input(
                "训练窗(交易日)", 126, 756, int(cal.get("train_days", 504)), 21
            )
            cal_test = st.number_input(
                "测试窗(交易日)", 21, 126, int(cal.get("test_days", 63)), 21
            )
        with c3:
            cal_step = st.number_input(
                "滚动步长", 21, 126, int(cal.get("step_days", 63)), 21
            )
            cal_shrink = st.slider(
                "向默认收缩",
                0.0,
                0.8,
                float(cal.get("shrinkage", 0.35)),
                0.05,
                help="越大越保守，越接近内置默认权重",
            )
        force_cal = st.checkbox("强制刷新行情缓存", value=False)
        run_cal = st.button("运行自动校准", type="primary", width="stretch")

        if run_cal:
            cfg["calibration"] = {
                **cal,
                "years": float(cal_years),
                "forward_days": int(cal_forward),
                "train_days": int(cal_train),
                "test_days": int(cal_test),
                "step_days": int(cal_step),
                "shrinkage": float(cal_shrink),
            }
            save_config(cfg)
            with st.spinner("正在拉取约 5 年行情并 Walk-Forward 搜索…"):
                result = calibrate_agent(cfg, force=force_cal, write_back=False)
            st.session_state["cal_result"] = result

        result = st.session_state.get("cal_result")
        if result is not None:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("样本外命中率", f"{result.best_oos.hit_rate:.1%}")
            m2.metric("样本外 IC", f"{result.best_oos.ic:.3f}")
            m3.metric("样本外 Sharpe", f"{result.best_oos.sharpe:.2f}")
            m4.metric("滚动折数", f"{result.folds}")
            st.write(
                f"指数：{', '.join(result.indexes_used) or '-'}　｜　"
                f"中位历史长度 {result.lookback_days} 日　｜　"
                f"前瞻 {result.forward_days} 日　｜　收缩 {result.shrinkage:.0%}"
            )
            st.info(result.reason)
            w = result.best_trend.get("weights") or {}
            st.markdown(
                "建议权重："
                + "　".join(
                    f"{k.upper()} {float(w.get(k, 0)) * 100:.0f}%"
                    for k in ["ma", "macd", "rsi", "momentum", "volume"]
                )
            )
            with st.expander("对比默认 / 候选（样本外）"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "方案": "当前默认基线",
                                "命中率": round(result.default_oos.hit_rate, 4),
                                "IC": round(result.default_oos.ic, 4),
                                "Sharpe": round(result.default_oos.sharpe, 4),
                            },
                            {
                                "方案": "最优候选(收缩前评估)",
                                "命中率": round(result.best_oos.hit_rate, 4),
                                "IC": round(result.best_oos.ic, 4),
                                "Sharpe": round(result.best_oos.sharpe, 4),
                            },
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
            apply_cols = st.columns(2)
            with apply_cols[0]:
                if st.button(
                    "应用建议参数到趋势引擎",
                    type="primary",
                    width="stretch",
                    disabled=not result.indexes_used,
                ):
                    merged_trend = {
                        **dict(cfg.get("trend") or {}),
                        **dict(result.best_trend or {}),
                    }
                    if (cfg.get("trend") or {}).get("enhancements") and not merged_trend.get(
                        "enhancements"
                    ):
                        merged_trend["enhancements"] = deepcopy(
                            cfg["trend"]["enhancements"]
                        )
                    cfg["trend"] = to_yaml_safe(merged_trend)
                    cfg["calibration"] = to_yaml_safe(
                        {
                            **dict(cfg.get("calibration") or {}),
                            "last_run": {
                                "accepted": result.accepted,
                                "reason": result.reason,
                                "indexes": result.indexes_used,
                                "folds": result.folds,
                                "default_oos": {
                                    "hit_rate": float(result.default_oos.hit_rate),
                                    "ic": float(result.default_oos.ic),
                                    "sharpe": float(result.default_oos.sharpe),
                                    "samples": int(result.default_oos.samples),
                                },
                                "best_oos": {
                                    "hit_rate": float(result.best_oos.hit_rate),
                                    "ic": float(result.best_oos.ic),
                                    "sharpe": float(result.best_oos.sharpe),
                                    "samples": int(result.best_oos.samples),
                                },
                                "details": result.details,
                            },
                        }
                    )
                    save_config(cfg)
                    st.session_state.cfg = load_config()
                    _invalidate_analysis_state()
                    st.success("已写入 config.yaml 的 trend 节；请到「趋势引擎」核对。")
                    st.rerun()
            with apply_cols[1]:
                if result.accepted:
                    st.caption("已通过稳健性门槛，建议应用。")
                else:
                    st.caption("未通过门槛：可仍手工应用，但更易过拟合。")

    st.markdown("---")
    confirm_reset = st.checkbox("确认恢复全部默认（趋势 / 评分 / 宏观）", value=False)
    if st.button(
        "恢复趋势 / 评分 / 宏观默认参数",
        width="stretch",
        disabled=not confirm_reset,
    ):
        cfg["trend"] = deepcopy(DEFAULT_TREND_SETTINGS)
        cfg["scoring"] = deepcopy(DEFAULT_SCORING_SETTINGS)
        cfg["macro"] = deepcopy(DEFAULT_MACRO_SETTINGS)
        save_config(cfg)
        st.session_state.cfg = load_config()
        _invalidate_analysis_state()
        st.success("已恢复默认参数")
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="AI Index", page_icon="◎", layout="wide", initial_sidebar_state="expanded")
    inject_style()
    cfg = get_cfg()
    with st.sidebar:
        st.markdown(
            """
<div class="sidebar-brand">
  <div class="mark">◎</div>
  <h2>AI Index</h2>
  <p>指数基金决策助手<br>本地运行 · 数据不出本机</p>
</div>
            """,
            unsafe_allow_html=True,
        )
        page = st.radio(
            "导航",
            ["看板", "重点机会", "评分趋势", "智能仓位", "智能提醒", "持仓", "策略参数"],
            label_visibility="collapsed",
        )

    {
        "看板": page_dashboard,
        "重点机会": page_opportunities,
        "评分趋势": page_score,
        "智能仓位": page_portfolio_smart,
        "智能提醒": page_alerts,
        "策略参数": page_parameters,
        "持仓": page_holdings,
    }[page](cfg)

    st.markdown(
        '<p class="disclaimer">AI Index 输出为概率化决策辅助，不构成投资建议。通知渠道（邮件/企微/Telegram）可在后续版本接入。</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
