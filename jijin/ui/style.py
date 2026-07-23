from __future__ import annotations

import streamlit as st

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
.load-panel{
  max-width:560px;
  margin:1.5rem auto 1rem;
  padding:0 .25rem;
}
.load-kicker{
  margin:0 0 .35rem;
  font-size:.72rem;
  letter-spacing:.14em;
  font-weight:600;
  color:var(--teal);
  font-family:var(--font-display)!important;
}
.load-title{
  margin:0 0 .45rem;
  font-size:1.7rem;
  font-weight:700;
  letter-spacing:-.02em;
  font-family:var(--font-display)!important;
  color:var(--ink);
}
.load-sub{
  margin:0 0 1.25rem;
  font-size:.95rem;
  color:var(--muted);
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


