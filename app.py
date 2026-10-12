import io
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=30, show_spinner=False)
def get_intraday_data(symbol):
    try:
        df = yf.download(
            symbol,
            period="1d",
            interval="1m",
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=15
        )

        if df is None or df.empty:
            return pd.DataFrame()

        # Menangani kolom MultiIndex dari yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna(subset=["Close"])

    except Exception:
        return pd.DataFrame()


if st.button("🔄 Refresh harga"):
    get_intraday_data.clear()

df = get_intraday_data("BBNI.JK")

if df.empty:
    st.warning("Data intraday tidak tersedia. Jangan gunakan harga lama sebagai harga terbaru.")
else:
    last = df.iloc[-1]
    candle_time = df.index[-1]


st.set_page_config(page_title="V5 Mobile Swing Hunter", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container{max-width:1150px;padding-top:1rem;padding-left:.8rem;padding-right:.8rem}
.card{padding:1rem;border:1px solid rgba(128,128,128,.28);border-radius:15px;margin-bottom:.8rem;background:rgba(128,128,128,.04)}
.small-muted{font-size:.82rem;opacity:.72}
@media(max-width:700px){.block-container{padding-left:.45rem;padding-right:.45rem}h1{font-size:1.55rem!important}h2{font-size:1.3rem!important}.stButton button{width:100%}}
</style>
""", unsafe_allow_html=True)

# ---------------- Configuration ----------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SWING_DB_PATH", str(BASE_DIR / "swing_hunter_v5.sqlite3")))
try:
    DB_PATH = Path(st.secrets.get("SWING_DB_PATH", str(DB_PATH)))
except Exception:
    pass
BUY_FEE_PCT = float(os.getenv("BUY_FEE_PCT", "0.15"))
SELL_FEE_PCT = float(os.getenv("SELL_FEE_PCT", "0.25"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "25"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "10"))

# ---------------- Stock universes ----------------
# Seed constituents for the period 2026-08-03 to 2026-10-30.
# These lists are editable in the app; confirm against the latest IDX publication after each review.
DEFAULT_WATCHLIST = "ANTM,ASII,BBNI,BBRI,BBCA,BMRI,TLKM,INCO,MDKA,PGAS,ADRO,UNTR,ICBP,KLBF,AMRT,CPIN,BRIS"
INDEX_LIST_UPDATED = "2026-08-03 s.d. 2026-10-30 (seed awal; verifikasi sebelum digunakan)"
INDEX_SOURCE_URL = "https://www.idx.id/id/data-pasar/laporan-statistik/fact-sheet-index"
DEFAULT_LQ45 = "AADI,ADMR,ADRO,AKRA,AMMN,AMRT,ANTM,ASII,BBCA,BBNI,BBRI,BBTN,BMRI,BRPT,BUMI,CPIN,CUAN,DEWA,EMTK,ESSA,EXCL,GOTO,HRTA,ICBP,INCO,INDF,INDY,INKP,ISAT,ITMG,JPFA,KLBF,MAPI,MBMA,MDKA,MEDC,NCKL,PGAS,PGEO,PTBA,SCMA,TLKM,UNTR,UNVR,WIFI"
DEFAULT_IDX30 = "AADI,ADMR,ADRO,AMRT,ANTM,ASII,BBCA,BBNI,BBRI,BMRI,BRPT,BUMI,CPIN,DEWA,EMTK,GOTO,ICBP,INCO,INDF,INKP,JPFA,KLBF,MBMA,MDKA,MEDC,PGAS,PGEO,TLKM,UNTR,UNVR"
# Broad candidate pool for the liquidity filter. It is a starting universe, not a claim to include every IDX listing.
LIQUID_CANDIDATES = "AADI,ADMR,ADRO,AGII,AKRA,AMMN,AMRT,ANTM,ARTO,ASII,BBCA,BBNI,BBRI,BBTN,BDMN,BFIN,BMRI,BRIS,BRPT,BSDE,BUKA,BUMI,CMRY,CPIN,CTRA,CUAN,DEWA,DSNG,ELSA,EMTK,ENRG,ERAA,ESSA,EXCL,GOTO,HEAL,HRTA,ICBP,INCO,INDF,INDY,INKP,ISAT,ITMG,JPFA,KIJA,KLBF,MAPA,MAPI,MBMA,MDKA,MEDC,MIKA,NCKL,PGAS,PGEO,PTBA,PTRO,RAJA,SCMA,SMGR,TAPG,TLKM,TOWR,UNTR,UNVR,WIFI"

# ---------------- SQLite database ----------------
def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def db_query(sql, params=(), fetch=True):
    with db_connect() as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()] if fetch else None

def init_db():
    with db_connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS app_settings(setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, txn_time TEXT NOT NULL, symbol TEXT NOT NULL,
          txn_type TEXT NOT NULL CHECK(txn_type IN ('BUY','SELL','OPENING')), lots INTEGER NOT NULL CHECK(lots>0),
          price REAL NOT NULL CHECK(price>0), gross_amount REAL NOT NULL, fee_amount REAL NOT NULL DEFAULT 0,
          realized_pnl REAL, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_txn_symbol_time ON transactions(symbol,txn_time);
        CREATE INDEX IF NOT EXISTS idx_txn_time ON transactions(txn_time);
        CREATE TABLE IF NOT EXISTS holdings(
          symbol TEXT PRIMARY KEY, shares INTEGER NOT NULL DEFAULT 0, avg_cost_per_share REAL NOT NULL DEFAULT 0,
          total_cost REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS risk_limits(
          id INTEGER PRIMARY KEY CHECK(id=1), risk_per_trade_pct REAL NOT NULL DEFAULT 1,
          max_position_pct REAL NOT NULL DEFAULT 25, max_drawdown_pct REAL NOT NULL DEFAULT 10,
          portfolio_reference_value REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS equity_snapshots(
          id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT NOT NULL UNIQUE,
          realized_pnl REAL NOT NULL DEFAULT 0, unrealized_pnl REAL NOT NULL DEFAULT 0,
          equity_value REAL NOT NULL DEFAULT 0, note TEXT);
        """)
        conn.execute("INSERT OR IGNORE INTO risk_limits(id,risk_per_trade_pct,max_position_pct,max_drawdown_pct,portfolio_reference_value) VALUES(1,?,?,?,0)", (RISK_PER_TRADE_PCT, MAX_POSITION_PCT, MAX_DRAWDOWN_PCT))
        seed_settings = {
            "watchlist_symbols": DEFAULT_WATCHLIST,
            "index_lq45_symbols": DEFAULT_LQ45,
            "index_idx30_symbols": DEFAULT_IDX30,
            "index_list_updated": INDEX_LIST_UPDATED,
        }
        for key, value in seed_settings.items():
            conn.execute("INSERT OR IGNORE INTO app_settings(setting_key,setting_value) VALUES(?,?)", (key, value))
        n=conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        if n == 0:
            for symbol,lots,price in [("BBNI.JK",10,3603),("TLKM.JK",9,2853)]:
                shares=lots*100; gross=shares*price
                conn.execute("INSERT INTO transactions(txn_time,symbol,txn_type,lots,price,gross_amount,fee_amount,realized_pnl,notes) VALUES(?,?,?,?,?,?,?,?,?)", (datetime.now().isoformat(timespec="seconds"),symbol,"OPENING",lots,price,gross,0,None,"Saldo awal pengguna; fee historis tidak diketahui"))
                conn.execute("INSERT OR IGNORE INTO holdings(symbol,shares,avg_cost_per_share,total_cost) VALUES(?,?,?,?)",(symbol,shares,price,gross))

def get_app_setting(key, default=""):
    rows = db_query("SELECT setting_value FROM app_settings WHERE setting_key=?", (key,))
    return rows[0]["setting_value"] if rows else default

def set_app_setting(key, value):
    with db_connect() as conn:
        conn.execute("INSERT INTO app_settings(setting_key,setting_value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=CURRENT_TIMESTAMP", (key, str(value)))

def normalize_symbols(text):
    symbols = []
    for item in str(text or "").replace(";", ",").replace("\n", ",").split(","):
        code = item.strip().upper().replace(" ", "")
        if not code:
            continue
        if code.endswith(".JK"):
            base = code[:-3]
        else:
            base = code
        if base.isalnum() and 1 <= len(base) <= 6:
            symbol = base + ".JK"
            if symbol not in symbols:
                symbols.append(symbol)
    return symbols

@st.cache_data(ttl=3600, show_spinner=False)
def screen_liquid_universe(candidate_symbols, lookback=20, min_avg_value=5_000_000_000, min_avg_volume=1_000_000):
    """Screen a seed candidate pool using approximate close x volume turnover."""
    passed, rejected, failures = [], [], 0
    for symbol in candidate_symbols:
        df = download_daily(symbol, period="6mo")
        if df.empty or "Volume" not in df.columns or len(df) < max(15, int(lookback)):
            failures += 1
            rejected.append({"Kode": symbol.replace(".JK", ""), "Rata-rata nilai transaksi": None, "Rata-rata volume": None, "Status": "Data tidak cukup"})
            continue
        d = df.dropna(subset=["Close", "Volume"]).tail(int(lookback)).copy()
        if len(d) < max(15, int(lookback) // 2):
            failures += 1
            rejected.append({"Kode": symbol.replace(".JK", ""), "Rata-rata nilai transaksi": None, "Rata-rata volume": None, "Status": "Data tidak cukup"})
            continue
        avg_value = float((d["Close"].astype(float) * d["Volume"].astype(float)).mean())
        avg_volume = float(d["Volume"].astype(float).mean())
        row = {"symbol": symbol, "avg_value": avg_value, "avg_volume": avg_volume}
        if avg_value >= float(min_avg_value) and avg_volume >= float(min_avg_volume):
            passed.append(row)
        else:
            rejected.append({"Kode": symbol.replace(".JK", ""), "Rata-rata nilai transaksi": avg_value, "Rata-rata volume": avg_volume, "Status": "Di bawah ambang"})
    passed.sort(key=lambda x: x["avg_value"], reverse=True)
    return passed, rejected, failures

# ---------------- Market data and indicators ----------------
@st.cache_data(ttl=300, show_spinner=False)
def download_daily(symbol, period="1y"):
    try:
        df=yf.download(symbol,period=period,interval="1d",auto_adjust=False,progress=False,threads=False)
        if df is None or df.empty: return pd.DataFrame()
        if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        return df.dropna(subset=["Close"]).copy()
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def download_intraday(symbol):
    try:
        df=yf.download(symbol,period="5d",interval="5m",auto_adjust=False,progress=False,threads=False)
        if df is None or df.empty: return pd.DataFrame()
        if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        return df.dropna(subset=["Close"]).copy()
    except Exception: return pd.DataFrame()

def indicators(df):
    d=df.copy(); c,h,l,v=d["Close"],d["High"],d["Low"],d["Volume"]
    d["MA20"]=c.rolling(20).mean(); d["MA50"]=c.rolling(50).mean(); d["MA200"]=c.rolling(200).mean()
    delta=c.diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    ag=gain.ewm(alpha=1/14,min_periods=14,adjust=False).mean(); al=loss.ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    rs=ag/al.replace(0,np.nan); d["RSI"]=100-100/(1+rs)
    e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean(); d["MACD"]=e12-e26; d["MACD_SIGNAL"]=d["MACD"].ewm(span=9,adjust=False).mean()
    prev=c.shift(1); tr=pd.concat([(h-l),(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    d["ATR"]=tr.rolling(14).mean(); d["VOL_MA20"]=v.rolling(20).mean(); d["VOL_RATIO"]=v/d["VOL_MA20"].replace(0,np.nan)
    d["RES20"]=h.shift(1).rolling(20).max(); d["SUP20"]=l.shift(1).rolling(20).min()
    return d

def market_regime():
    df=download_daily("^JKSE")
    if df.empty or len(df)<50: return {"regime":"UNKNOWN","price":None,"ma20":None,"ma50":None,"score":5,"timestamp":None}
    d=indicators(df); r=d.iloc[-1]
    if any(pd.isna(r.get(k)) for k in ["Close","MA20","MA50"]): return {"regime":"UNKNOWN","price":float(r["Close"]),"ma20":None,"ma50":None,"score":5,"timestamp":d.index[-1]}
    p,m20,m50=map(float,[r.Close,r.MA20,r.MA50]); regime="BULLISH" if p>m20>m50 else ("BEARISH" if p<m20<m50 else "SIDEWAYS")
    return {"regime":regime,"price":p,"ma20":m20,"ma50":m50,"score":10 if regime=="BULLISH" else (0 if regime=="BEARISH" else 5),"timestamp":d.index[-1]}

def analyze(symbol, include_fundamentals=True):
    raw=download_daily(symbol)
    if raw.empty or len(raw)<50: return None
    d=indicators(raw); r=d.iloc[-1]
    required=["Close","MA20","MA50","RSI","MACD","MACD_SIGNAL","ATR","VOL_RATIO","RES20","SUP20"]
    if any(pd.isna(r.get(k)) for k in required): return None
    p,m20,m50=float(r.Close),float(r.MA20),float(r.MA50); m200=float(r.MA200) if pd.notna(r.MA200) else np.nan
    rsi,atr,vr=float(r.RSI),float(r.ATR),float(r.VOL_RATIO); res,sup=float(r.RES20),float(r.SUP20)
    reasons=[]; warnings=[]; score=0
    if p>m20: score+=5; reasons.append("Harga di atas MA20")
    else: warnings.append("Harga di bawah MA20")
    if m20>m50: score+=5; reasons.append("MA20 di atas MA50")
    if pd.notna(m200) and p>m200: score+=5; reasons.append("Harga di atas MA200")
    if 50<=rsi<=70: score+=8; reasons.append("RSI dalam momentum sehat")
    elif 45<=rsi<50: score+=4
    elif rsi>75: warnings.append("RSI tinggi; risiko mengejar harga")
    elif rsi<35: warnings.append("RSI lemah")
    if float(r.MACD)>float(r.MACD_SIGNAL): score+=7; reasons.append("MACD bullish")
    else: warnings.append("MACD belum bullish")
    if vr>=1.5: score+=15; reasons.append("Volume ≥1,5x rata-rata")
    elif vr>=1.2: score+=10; reasons.append("Volume meningkat")
    elif vr>=1: score+=5
    else: warnings.append("Volume di bawah rata-rata")
    if p>res: score+=15; reasons.append("Breakout resistance 20 hari")
    elif p>m20: score+=8; reasons.append("Price action di atas MA20")
    if (p-sup)/p<=.05: score+=10; reasons.append("Harga relatif dekat support")
    elif p<res*.98: score+=5
    market=market_regime(); score+=market["score"]
    # Fundamental metadata is optional: Yahoo Ticker.info can be slow or unavailable.
    # The broad scanner uses technical-only scoring for speed and consistency of scan coverage.
    if include_fundamentals:
        try:
            info = yf.Ticker(symbol).info
            pe, pb, roe = info.get("trailingPE"), info.get("priceToBook"), info.get("returnOnEquity")
        except Exception:
            pe = pb = roe = None
        fscore = 0
        if pe is not None and np.isfinite(pe): fscore += 2 if 0 < pe <= 15 else (1 if 15 < pe <= 25 else 0)
        if pb is not None and np.isfinite(pb): fscore += 2 if 0 < pb <= 2 else (1 if 2 < pb <= 4 else 0)
        if roe is not None and np.isfinite(roe) and roe >= .15: fscore += 1
        score += fscore
    entry_low=max(.01,min(p,m20)); entry_high=min(max(p,m20),p*1.02); entry=(entry_low+entry_high)/2
    stop=max(.01,min(p-1.2*atr,sup-.25*atr)); risk=entry-stop
    if risk<=0: stop=entry*.97; risk=entry-stop
    tp1=max(entry+2*risk,res if res>entry else entry+2*risk); tp2=max(entry+3*risk,entry*1.05)
    potential=(tp1-entry)/entry if entry else 0; rr=(tp1-entry)/risk if risk>0 else 0
    if score>=80 and potential>=.05 and rr>=2 and market["regime"]=="BULLISH" and vr>=1.2: signal="BUY CANDIDATE"
    elif score>=70 and potential>=.05 and rr>=2 and market["regime"]!="BEARISH": signal="BUY ON WEAKNESS"
    elif score>=55: signal="WATCH"
    else: signal="AVOID"
    if market["regime"]=="BEARISH": warnings.append("IHSG bearish: sinyal beli dibatasi")
    if potential<.05: warnings.append("Potensi TP1 di bawah 5%")
    if rr<2: warnings.append("Risk/reward kurang dari 1:2")
    return {"symbol":symbol,"price":p,"score":int(min(score,100)),"signal":signal,"entry_low":entry_low,"entry_high":entry_high,"stop":stop,"tp1":tp1,"tp2":tp2,"potential":potential,"rr":rr,"rsi":rsi,"atr":atr,"vol_ratio":vr,"support":sup,"resistance":res,"ma20":m20,"ma50":m50,"ma200":m200,"market":market,"reasons":reasons,"warnings":warnings,"timestamp":d.index[-1],"history":d}

# ---------------- Portfolio accounting ----------------
def get_holdings(): return db_query("SELECT symbol,shares,avg_cost_per_share,total_cost FROM holdings WHERE shares>0 ORDER BY symbol")
def get_transactions(limit=5000): return db_query("SELECT id,txn_time,symbol,txn_type,lots,price,gross_amount,fee_amount,realized_pnl,notes FROM transactions ORDER BY txn_time DESC,id DESC LIMIT ?",(int(limit),))
def current_prices(symbols):
    out={}
    for s in symbols:
        df=download_daily(s)
        if not df.empty: out[s]=float(df["Close"].dropna().iloc[-1])
    return out

def add_transaction(txn_date,symbol,txn_type,lots,price,notes,buy_fee_pct, sell_fee_pct):
    symbol=symbol.upper().strip(); symbol=symbol if symbol.endswith(".JK") else symbol+".JK"
    if not symbol[:-3].isalnum(): raise ValueError("Kode saham tidak valid; gunakan kode alfanumerik IDX, misalnya BBNI.")
    if txn_type not in ("BUY","SELL"): raise ValueError("Jenis transaksi harus BUY atau SELL.")
    if int(lots)<=0: raise ValueError("Lot harus lebih besar dari 0.")
    if not np.isfinite(float(price)) or float(price)<=0: raise ValueError("Harga harus lebih besar dari 0.")
    shares=int(lots)*100; price=float(price); gross=shares*price; fee=round(gross*float(buy_fee_pct if txn_type=="BUY" else sell_fee_pct)/100,2)
    with db_connect() as conn:
        h=conn.execute("SELECT shares,avg_cost_per_share,total_cost FROM holdings WHERE symbol=?",(symbol,)).fetchone()
        old_shares=int(h["shares"]) if h else 0; old_cost=float(h["total_cost"]) if h else 0; old_avg=float(h["avg_cost_per_share"]) if h else 0
        realized=None
        if txn_type=="SELL":
            if shares>old_shares: raise ValueError(f"Penjualan ditolak: kepemilikan hanya {old_shares//100} lot.")
            cost_removed=old_avg*shares; realized=round(gross-fee-cost_removed,2); new_shares=old_shares-shares; new_cost=max(0.0,old_cost-cost_removed); new_avg=(new_cost/new_shares) if new_shares else 0.0
        else:
            new_shares=old_shares+shares; new_cost=old_cost+gross+fee; new_avg=new_cost/new_shares
        conn.execute("INSERT INTO transactions(txn_time,symbol,txn_type,lots,price,gross_amount,fee_amount,realized_pnl,notes) VALUES(?,?,?,?,?,?,?,?,?)",(datetime.combine(txn_date,datetime.min.time()).isoformat(timespec="seconds"),symbol,txn_type,int(lots),price,gross,fee,realized,(notes or "").strip() or None))
        conn.execute("INSERT INTO holdings(symbol,shares,avg_cost_per_share,total_cost,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(symbol) DO UPDATE SET shares=excluded.shares,avg_cost_per_share=excluded.avg_cost_per_share,total_cost=excluded.total_cost,updated_at=CURRENT_TIMESTAMP",(symbol,new_shares,new_avg,new_cost))

def load_risk_limits():
    rows=db_query("SELECT * FROM risk_limits WHERE id=1")
    return rows[0] if rows else {"risk_per_trade_pct":RISK_PER_TRADE_PCT,"max_position_pct":MAX_POSITION_PCT,"max_drawdown_pct":MAX_DRAWDOWN_PCT,"portfolio_reference_value":0}
def save_risk_limits(risk,position,drawdown,reference):
    with db_connect() as conn:
        conn.execute("INSERT INTO risk_limits(id,risk_per_trade_pct,max_position_pct,max_drawdown_pct,portfolio_reference_value,updated_at) VALUES(1,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET risk_per_trade_pct=excluded.risk_per_trade_pct,max_position_pct=excluded.max_position_pct,max_drawdown_pct=excluded.max_drawdown_pct,portfolio_reference_value=excluded.portfolio_reference_value,updated_at=CURRENT_TIMESTAMP",(risk,position,drawdown,reference))
def money(x): return "Rp"+f"{float(x):,.0f}"
def show_setup(x):
    st.markdown(f"<div class='card'><div style='display:flex;justify-content:space-between;gap:10px'><div><h3 style='margin-bottom:0'>{x['symbol'].replace('.JK','')}</h3><b>{x['signal']}</b></div><div style='font-size:1.7rem;font-weight:800'>{x['score']}/100</div></div><hr><b>Harga:</b> {money(x['price'])}<br><b>Entry:</b> {money(x['entry_low'])} – {money(x['entry_high'])}<br><b>Stop:</b> {money(x['stop'])}<br><b>TP1:</b> {money(x['tp1'])} &nbsp; <b>TP2:</b> {money(x['tp2'])}<br><b>Potensi TP1:</b> {x['potential']*100:.2f}% &nbsp; <b>R:R:</b> 1:{x['rr']:.2f}<br><span class='small-muted'>Candle terakhir: {x['timestamp']} · data dapat tertunda</span></div>",unsafe_allow_html=True)
    with st.expander("Detail indikator, alasan, dan risiko"):
        a,b,c=st.columns(3); a.metric("RSI",f"{x['rsi']:.1f}"); b.metric("Volume vs MA20",f"{x['vol_ratio']:.2f}x"); c.metric("IHSG",x['market']['regime'])
        st.write("**Alasan**")
        for q in x["reasons"]: st.write("✓",q)
        if x["warnings"]:
            st.write("**Peringatan**")
            for q in x["warnings"]: st.write("⚠️",q)
        st.line_chart(x["history"][["Close","MA20","MA50","MA200"]].tail(120))

def compute_portfolio():
    holdings=get_holdings(); prices=current_prices([h["symbol"] for h in holdings]); rows=[]; cost_known=market_known=0.0
    for h in holdings:
        sym=h["symbol"]; shares=int(h["shares"]); cost=float(h["total_cost"]); avg=float(h["avg_cost_per_share"]); px=prices.get(sym); value=shares*px if px is not None else None; pnl=value-cost if value is not None else None; tech=analyze(sym) if px is not None else None
        if px is not None: cost_known+=cost; market_known+=value
        advice="DATA TIDAK TERSEDIA"
        if tech:
            if tech["market"]["regime"]=="BEARISH" and (px<tech["ma20"] or tech["signal"]=="AVOID"): advice="PERTIMBANGKAN KURANGI RISIKO"
            elif px<tech["stop"]: advice="REVIEW STOP / INVALIDASI"
            elif tech["signal"] in ("BUY CANDIDATE","BUY ON WEAKNESS") and px>avg: advice="HOLD / TRAILING STOP"
            elif tech["score"]<55: advice="REVIEW / PERTIMBANGKAN SELL"
            else: advice="HOLD / MONITOR"
        rows.append({"symbol":sym,"shares":shares,"lots":shares//100,"avg":avg,"cost":cost,"price":px,"value":value,"pnl":pnl,"pnl_pct":(pnl/cost*100 if pnl is not None and cost else None),"score":tech["score"] if tech else None,"signal":tech["signal"] if tech else "DATA N/A","advice":advice})
    return rows,prices,cost_known,market_known

def record_equity_snapshot():
    rows,prices,cost,market_value=compute_portfolio(); tx=get_transactions(100000); realized=sum(float(t["realized_pnl"] or 0) for t in tx if t["txn_type"]=="SELL")
    unrealized=sum(float(r["pnl"] or 0) for r in rows if r["price"] is not None)
    # Track marked equity as the value of current holdings plus cumulative realized P/L.
    equity=market_value+realized
    with db_connect() as conn:
        conn.execute("INSERT INTO equity_snapshots(snapshot_date,realized_pnl,unrealized_pnl,equity_value,note) VALUES(?,?,?,?,?) ON CONFLICT(snapshot_date) DO UPDATE SET realized_pnl=excluded.realized_pnl,unrealized_pnl=excluded.unrealized_pnl,equity_value=excluded.equity_value,note=excluded.note",(date.today().isoformat(),realized,unrealized,equity,"Marked using last available daily close; may be delayed"))

def page_hunter():
    st.header("🎯 Swing Hunter")
    m = market_regime()
    emoji = {"BULLISH":"🟢", "SIDEWAYS":"🟡", "BEARISH":"🔴", "UNKNOWN":"⚪"}.get(m["regime"], "⚪")
    st.markdown(f"<div class='card'><h3>IHSG {emoji} {m['regime']}</h3>Harga: {money(m['price']) if m['price'] else 'N/A'} · MA20: {money(m['ma20']) if m['ma20'] else '-'} · MA50: {money(m['ma50']) if m['ma50'] else '-'}<br><span class='small-muted'>Yahoo Finance; harga dapat tertunda. Candle terakhir: {m['timestamp']}</span></div>", unsafe_allow_html=True)

    universe = st.radio(
        "Pilih universe saham",
        ["Watchlist pribadi", "Universe likuid", "Universe indeks"],
        horizontal=True,
        key="hunter_universe_mode",
    )
    symbols = []
    universe_label = universe
    liquid_details = []
    rejected_details = []
    screen_failures = 0

    if universe == "Watchlist pribadi":
        saved_watchlist = get_app_setting("watchlist_symbols", DEFAULT_WATCHLIST).replace(",", ", ")
        watch_text = st.text_area("Kode saham (pisahkan dengan koma)", saved_watchlist, key="hunter_watchlist_text", help="Contoh: BBNI, TLKM, ANTM. Watchlist disimpan ke SQLite.")
        col_save, col_info = st.columns([1, 2])
        if col_save.button("💾 Simpan watchlist", use_container_width=True):
            clean = normalize_symbols(watch_text)
            if clean:
                set_app_setting("watchlist_symbols", ",".join(x.replace(".JK", "") for x in clean))
                st.success(f"Watchlist tersimpan: {len(clean)} saham.")
            else:
                st.error("Masukkan minimal satu kode saham yang valid.")
        col_info.caption("Disimpan pada database SQLite aktif.")
        symbols = normalize_symbols(watch_text)

    elif universe == "Universe likuid":
        st.caption("Pool kandidat awal dipindai lalu disaring memakai data harian Yahoo Finance. Ini bukan daftar lengkap seluruh saham BEI.")
        c1, c2, c3 = st.columns(3)
        lookback = c1.selectbox("Periode rata-rata", [20, 30, 60], index=0, format_func=lambda x: f"{x} hari bursa")
        min_value_b = c2.number_input("Min. nilai transaksi rata-rata (Rp miliar/hari)", min_value=0.0, max_value=1000.0, value=5.0, step=1.0)
        min_volume_m = c3.number_input("Min. volume rata-rata (juta saham/hari)", min_value=0.0, max_value=1000.0, value=1.0, step=0.5)
        if st.button("🔄 Bangun universe likuid", use_container_width=True):
            with st.spinner("Memeriksa data historis kandidat saham..."):
                candidate_symbols = tuple(normalize_symbols(LIQUID_CANDIDATES))
                passed, rejected, failures = screen_liquid_universe(candidate_symbols, int(lookback), float(min_value_b) * 1_000_000_000, float(min_volume_m) * 1_000_000)
            st.session_state["liquid_universe_symbols"] = [x["symbol"] for x in passed]
            st.session_state["liquid_universe_details"] = passed
            st.session_state["liquid_universe_rejected"] = rejected
            st.session_state["liquid_universe_failures"] = failures
            st.session_state["liquid_universe_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        symbols = st.session_state.get("liquid_universe_symbols", [])
        liquid_details = st.session_state.get("liquid_universe_details", [])
        rejected_details = st.session_state.get("liquid_universe_rejected", [])
        screen_failures = st.session_state.get("liquid_universe_failures", 0)
        if symbols:
            st.success(f"{len(symbols)} saham memenuhi filter likuiditas · hasil filter: {st.session_state.get('liquid_universe_time', '-')}")
            if liquid_details:
                liq_df = pd.DataFrame([{"Kode": x["symbol"].replace(".JK", ""), "Rata-rata nilai transaksi/hari": x["avg_value"], "Rata-rata volume/hari": x["avg_volume"]} for x in liquid_details])
                st.dataframe(liq_df, use_container_width=True, hide_index=True)
        elif "liquid_universe_symbols" not in st.session_state:
            st.info("Tekan **Bangun universe likuid** terlebih dahulu untuk menyaring kandidat.")
        if rejected_details:
            with st.expander(f"Lihat saham yang tidak lolos / data bermasalah ({len(rejected_details)})"):
                st.dataframe(pd.DataFrame(rejected_details), use_container_width=True, hide_index=True)
                if screen_failures:
                    st.caption(f"Data tidak cukup atau gagal: {screen_failures}. Saham tersebut tidak dianggap lolos.")

    else:
        index_choice = st.selectbox("Pilih indeks", ["LQ45", "IDX30", "Gabungan LQ45 + IDX30"], index=0)
        lq45_text = get_app_setting("index_lq45_symbols", DEFAULT_LQ45)
        idx30_text = get_app_setting("index_idx30_symbols", DEFAULT_IDX30)
        updated_text = get_app_setting("index_list_updated", INDEX_LIST_UPDATED)
        with st.expander("⚙️ Kelola / perbarui daftar konstituen indeks"):
            st.caption("Daftar bawaan adalah seed untuk periode 3 Agustus–30 Oktober 2026 berdasarkan publikasi pasar yang merujuk evaluasi BEI. Verifikasi dengan publikasi BEI terbaru sebelum dipakai; aplikasi tidak mengklaim memperbarui daftar indeks otomatis.")
            st.markdown(f"Sumber referensi: [{INDEX_SOURCE_URL}]({INDEX_SOURCE_URL})")
            edit_lq = st.text_area("Konstituen LQ45", lq45_text, key="edit_lq45_symbols", height=100)
            edit_idx = st.text_area("Konstituen IDX30", idx30_text, key="edit_idx30_symbols", height=100)
            edit_date = st.text_input("Periode / tanggal verifikasi daftar", updated_text, key="edit_index_date")
            if st.button("💾 Simpan daftar indeks", use_container_width=True):
                clean_lq, clean_idx = normalize_symbols(edit_lq), normalize_symbols(edit_idx)
                if not clean_lq or not clean_idx:
                    st.error("Kedua daftar indeks harus berisi minimal satu kode saham.")
                else:
                    set_app_setting("index_lq45_symbols", ",".join(x.replace(".JK", "") for x in clean_lq))
                    set_app_setting("index_idx30_symbols", ",".join(x.replace(".JK", "") for x in clean_idx))
                    set_app_setting("index_list_updated", edit_date.strip() or "Tanggal verifikasi belum diisi")
                    st.success("Daftar indeks tersimpan ke SQLite. Halaman akan memuat ulang dengan daftar terbaru.")
                    st.rerun()
        lq45 = normalize_symbols(lq45_text)
        idx30 = normalize_symbols(idx30_text)
        if index_choice == "LQ45": symbols = lq45
        elif index_choice == "IDX30": symbols = idx30
        else: symbols = list(dict.fromkeys(lq45 + idx30))
        st.caption(f"Daftar konstituen: {updated_text} · LQ45 {len(lq45)} saham · IDX30 {len(idx30)} saham. Verifikasi daftar sebelum digunakan.")

    symbols = list(dict.fromkeys(symbols))
    st.caption(f"Universe aktif: {universe_label} · {len(symbols)} ticker siap dipindai. Skor scan berbasis teknikal agar pemindaian banyak saham lebih cepat.")
    a, b, c = st.columns(3)
    min_score = a.slider("Skor minimum", 40, 85, 65)
    min_target = b.slider("Target minimum (%)", 1, 15, 5) / 100
    min_rr = c.slider("R:R minimum", 1.0, 4.0, 2.0, 0.5)

    if st.button("🚀 Scan saham", use_container_width=True, disabled=not symbols):
        results, errors = [], []
        prog = st.progress(0)
        status = st.empty()
        for i, symbol in enumerate(symbols):
            status.caption(f"Menganalisis {i+1}/{len(symbols)}: {symbol}")
            try:
                r = analyze(symbol, include_fundamentals=False)
                if r is None:
                    errors.append({"Kode": symbol.replace(".JK", ""), "Alasan": "Data kosong / histori indikator belum cukup"})
                elif r["score"] >= min_score and r["potential"] >= min_target and r["rr"] >= min_rr:
                    results.append(r)
            except Exception as exc:
                errors.append({"Kode": symbol.replace(".JK", ""), "Alasan": str(exc)[:160]})
            prog.progress((i + 1) / max(1, len(symbols)))
        prog.empty(); status.empty()
        results.sort(key=lambda x: (x["score"], x["potential"], x["rr"]), reverse=True)
        st.session_state["hunter_results"] = results
        st.session_state["hunter_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["hunter_scan_total"] = len(symbols)
        st.session_state["hunter_scan_errors"] = errors
        st.session_state["hunter_scan_universe"] = universe_label

    results = st.session_state.get("hunter_results", [])
    if results:
        st.caption(f"Scan terakhir: {st.session_state.get('hunter_time', '-')} · Universe: {st.session_state.get('hunter_scan_universe', '-')} · {len(results)} setup lolos dari {st.session_state.get('hunter_scan_total', '-')} ticker")
        out_df = pd.DataFrame([{ "Kode": r["symbol"].replace(".JK", ""), "Sinyal": r["signal"], "Skor": r["score"], "Harga": r["price"], "Potensi TP1 (%)": round(r["potential"] * 100, 2), "R:R": round(r["rr"], 2), "RSI": round(r["rsi"], 1), "Volume / MA20": round(r["vol_ratio"], 2)} for r in results])
        st.dataframe(out_df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Ekspor hasil scan CSV", out_df.to_csv(index=False).encode("utf-8-sig"), file_name=f"swing_hunter_scan_{date.today().isoformat()}.csv", mime="text/csv", use_container_width=True)
        for r in results[:12]: show_setup(r)
    elif "hunter_time" in st.session_state:
        st.warning(f"Scan terakhir ({st.session_state.get('hunter_time', '-')}) tidak menghasilkan setup yang lolos filter. Ini berbeda dari kegagalan data.")
    else:
        st.info("Pilih universe, lalu tekan Scan saham. Untuk universe likuid, bangun universe terlebih dahulu.")
    scan_errors = st.session_state.get("hunter_scan_errors", [])
    if scan_errors:
        with st.expander(f"Ticker gagal dianalisis / data tidak cukup ({len(scan_errors)})"):
            st.dataframe(pd.DataFrame(scan_errors), use_container_width=True, hide_index=True)


def page_analyzer():
    st.header("🔎 Analyzer")
    with st.form("analyzer_form"):
        symbol=st.text_input("Kode saham","ANTM").upper().strip(); submitted=st.form_submit_button("Analisis saham",use_container_width=True)
    if submitted:
        symbol=symbol if symbol.endswith(".JK") else symbol+".JK"
        with st.spinner("Mengambil data dan menghitung indikator..."): r=analyze(symbol)
        if r: show_setup(r)
        else: st.error("Data tidak tersedia atau histori belum cukup untuk indikator.")

def page_portfolio():
    st.header("💼 Portfolio Advisor")
    holdings=get_holdings()
    if not holdings: st.info("Belum ada kepemilikan saham."); return
    rows,prices,cost,value=compute_portfolio(); m=market_regime(); pnl=value-cost
    a,b,c=st.columns(3); a.metric("Biaya pokok posisi",money(sum(float(h["total_cost"]) for h in holdings))); b.metric("Nilai pasar tersedia",money(value)); c.metric("Unrealized P/L",money(pnl),f"{pnl/cost*100:.2f}%" if cost else None)
    view=[]
    for r in rows: view.append({"Saham":r["symbol"].replace(".JK",""),"Lot":r["lots"],"Avg cost":r["avg"],"Harga terakhir":r["price"],"Nilai pasar":r["value"],"Unrealized P/L":r["pnl"],"P/L %":r["pnl_pct"],"Skor":r["score"],"Saran":r["advice"]})
    st.dataframe(pd.DataFrame(view),use_container_width=True,hide_index=True)
    st.caption(f"Kondisi IHSG: {m['regime']}. Saran berbasis aturan, bukan instruksi otomatis. Unrealized P/L belum mengurangi estimasi fee jika posisi dijual.")
    for r in rows:
        with st.expander(f"{r['symbol'].replace('.JK','')} — {r['advice']}"):
            st.write(f"Kepemilikan {r['lots']} lot · Average cost {money(r['avg'])} · Harga {money(r['price']) if r['price'] is not None else 'N/A'}")
            st.write(f"Unrealized P/L: {money(r['pnl']) if r['pnl'] is not None else 'N/A'} · Signal: {r['signal']}")
            st.write("Periksa tren, support, likuiditas, biaya, dan rencana investasi sebelum bertindak.")

def page_trade():
    st.header("🔁 Buy / Sell")
    st.caption(f"Fee tetap yang digunakan: BUY {BUY_FEE_PCT:.2f}% · SELL {SELL_FEE_PCT:.2f}%. Ubah melalui environment variables bila fee broker berbeda.")
    hmap={h["symbol"]:int(h["shares"])//100 for h in get_holdings()}
    with st.form("trade_form"):
        a,b=st.columns(2); txn_type=a.selectbox("Jenis transaksi",["BUY","SELL"]); txn_date=b.date_input("Tanggal transaksi",date.today())
        symbol=st.text_input("Kode saham","BBNI").upper().strip(); c,d=st.columns(2); lots=c.number_input("Jumlah lot",min_value=1,max_value=1000000,value=1,step=1); price=d.number_input("Harga per saham (Rp)",min_value=1.0,value=1000.0,step=10.0); notes=st.text_input("Catatan (opsional)")
        fee_pct=BUY_FEE_PCT if txn_type=="BUY" else SELL_FEE_PCT; gross=int(lots)*100*price; fee=round(gross*fee_pct/100,2)
        st.info(f"Nilai bruto {money(gross)} · Fee {money(fee)} · "+(f"Debit beli {money(gross+fee)}" if txn_type=="BUY" else f"Penerimaan bersih {money(gross-fee)}"))
        if txn_type=="SELL": st.caption(f"Kepemilikan {symbol}: {hmap.get(symbol if symbol.endswith('.JK') else symbol+'.JK',0)} lot")
        submitted=st.form_submit_button("Simpan transaksi aktual",use_container_width=True)
    if submitted:
        try: add_transaction(txn_date,symbol,txn_type,int(lots),price,notes,BUY_FEE_PCT,SELL_FEE_PCT); st.success("Transaksi disimpan."); st.cache_data.clear(); st.rerun()
        except Exception as e: st.error(f"Transaksi ditolak: {e}")

def page_journal():
    st.header("📒 Trading Journal")
    tx=get_transactions(100000)
    if not tx: st.info("Belum ada transaksi."); return
    df=pd.DataFrame(tx)
    for col in ["gross_amount","fee_amount","realized_pnl","price"]: df[col]=pd.to_numeric(df[col],errors="coerce")
    sells=df[df.txn_type=="SELL"]; realized=float(sells.realized_pnl.fillna(0).sum()); closed=sells.realized_pnl.dropna(); win=float((closed>0).mean()*100) if len(closed) else 0
    rows,prices,cost,value=compute_portfolio(); unrealized=sum(float(r["pnl"] or 0) for r in rows if r["price"] is not None)
    a,b,c,d=st.columns(4); a.metric("Realized P/L",money(realized)); b.metric("Unrealized P/L",money(unrealized)); c.metric("SELL",len(sells)); d.metric("Win rate",f"{win:.1f}%")
    st.caption("Realized P/L bersih dari fee jual dan harga pokok rata-rata yang sudah memasukkan fee beli. Saldo awal tidak dikenai fee historis.")
    view=df.rename(columns={"id":"ID","txn_time":"Tanggal","symbol":"Saham","txn_type":"Jenis","lots":"Lot","price":"Harga","gross_amount":"Nilai bruto","fee_amount":"Fee","realized_pnl":"Realized P/L","notes":"Catatan"})
    st.dataframe(view,use_container_width=True,hide_index=True); st.download_button("⬇️ Ekspor histori CSV",view.to_csv(index=False).encode("utf-8-sig"),f"trading_journal_{date.today().isoformat()}.csv","text/csv",use_container_width=True)
    if not sells.empty:
        st.subheader("Realized P/L per saham"); by=sells.groupby("symbol",as_index=False).realized_pnl.sum().rename(columns={"symbol":"Saham","realized_pnl":"Realized P/L"}); st.dataframe(by,use_container_width=True,hide_index=True)

def page_risk():
    st.header("🛡️ Risk Limits")
    current=load_risk_limits()
    with st.form("risk_form"):
        risk=st.number_input("Risiko maksimum per transaksi (%)",.1,5.0,float(current["risk_per_trade_pct"]),.1); pos=st.number_input("Maksimum alokasi per saham (%)",1.0,100.0,float(current["max_position_pct"]),1.0); dd=st.number_input("Batas drawdown (%)",1.0,50.0,float(current["max_drawdown_pct"]),1.0); ref=st.number_input("Nilai referensi portofolio (Rp)",min_value=0.0,value=float(current["portfolio_reference_value"]),step=100000.0); save=st.form_submit_button("Simpan risk limits",use_container_width=True)
    if save: save_risk_limits(risk,pos,dd,ref); st.success("Risk limits disimpan."); st.rerun()
    st.subheader("Kalkulator ukuran posisi")
    a,b,c=st.columns(3); capital=a.number_input("Modal portofolio (Rp)",min_value=0.0,value=float(ref),step=100000.0,key="calc_capital"); entry=b.number_input("Harga entry (Rp)",min_value=0.0,value=1000.0,step=10.0,key="calc_entry"); stop=c.number_input("Stop loss (Rp)",min_value=0.0,value=950.0,step=10.0,key="calc_stop")
    if capital>0 and entry>stop>0:
        risk_money=capital*risk/100; risk_lots=int(risk_money/(entry-stop))//100; max_position=capital*pos/100; position_lots=int(max_position/entry/100); lots=min(risk_lots,position_lots)
        st.write(f"Risiko uang maksimum: **{money(risk_money)}**"); st.write(f"Batas alokasi per saham: **{money(max_position)}**"); st.write(f"Ukuran posisi maksimum dari kedua batas: **{lots} lot** (sekitar {money(lots*100*entry)})")
        st.caption("Kalkulator memperkirakan ukuran posisi; fee, slippage, likuiditas dan gap harga bisa membuat risiko aktual lebih besar.")
    else: st.info("Isi modal, entry, dan stop loss yang valid.")

def page_equity():
    st.header("📉 Grafik Ekuitas & Drawdown")
    st.info("Snapshot diperbarui saat halaman ini dibuka. Nilai memakai harga penutupan harian terakhir yang tersedia; bukan rekonstruksi tick-by-tick historis.")
    if st.button("📌 Catat snapshot ekuitas hari ini",use_container_width=True):
        try: record_equity_snapshot(); st.success("Snapshot tersimpan."); st.rerun()
        except Exception as e: st.error(f"Gagal menyimpan snapshot: {e}")
    snaps=db_query("SELECT snapshot_date,realized_pnl,unrealized_pnl,equity_value FROM equity_snapshots ORDER BY snapshot_date")
    if not snaps: st.warning("Belum ada snapshot. Tekan tombol di atas untuk membuat snapshot pertama."); return
    df=pd.DataFrame(snaps); df["snapshot_date"]=pd.to_datetime(df["snapshot_date"]); df=df.sort_values("snapshot_date"); df["peak_equity"]=df["equity_value"].cummax(); df["drawdown_pct"]=np.where(df["peak_equity"]>0,(df["equity_value"]-df["peak_equity"])/df["peak_equity"]*100,0)
    c1,c2,c3=st.columns(3); c1.metric("Ekuitas terakhir",money(df.equity_value.iloc[-1])); c2.metric("Drawdown saat ini",f"{df.drawdown_pct.iloc[-1]:.2f}%"); c3.metric("Max drawdown tercatat",f"{df.drawdown_pct.min():.2f}%")
    st.subheader("Ekuitas tercatat"); st.line_chart(df.set_index("snapshot_date")[["equity_value"]])
    st.subheader("Drawdown dari puncak"); st.area_chart(df.set_index("snapshot_date")[["drawdown_pct"]])
    st.dataframe(df[["snapshot_date","realized_pnl","unrealized_pnl","equity_value","peak_equity","drawdown_pct"]].rename(columns={"snapshot_date":"Tanggal","realized_pnl":"Realized P/L kumulatif","unrealized_pnl":"Unrealized P/L","equity_value":"Ekuitas tercatat","peak_equity":"Puncak ekuitas","drawdown_pct":"Drawdown %"}),use_container_width=True,hide_index=True)
    lim=load_risk_limits(); limit=float(lim["max_drawdown_pct"])
    if abs(float(df.drawdown_pct.iloc[-1]))>=limit: st.error(f"PERINGATAN: drawdown tercatat sudah mencapai batas {limit:.1f}%.")

def page_backup():
    st.header("🗄️ Backup Database")
    st.warning("Simpan backup di tempat aman. SQLite menyimpan histori transaksi dan data portofolio di satu file.")
    if DB_PATH.exists():
        st.download_button("⬇️ Backup database SQLite (.db)",DB_PATH.read_bytes(),file_name=f"swing_hunter_backup_{date.today().isoformat()}.sqlite3",mime="application/octet-stream",use_container_width=True)
    tx=get_transactions(100000); holdings=get_holdings(); risk=load_risk_limits()
    st.download_button("Ekspor transaksi CSV",pd.DataFrame(tx).to_csv(index=False).encode("utf-8-sig"),"transactions_backup.csv","text/csv",use_container_width=True)
    st.download_button("Ekspor kepemilikan CSV",pd.DataFrame(holdings).to_csv(index=False).encode("utf-8-sig"),"holdings_backup.csv","text/csv",use_container_width=True)
    snaps=db_query("SELECT * FROM equity_snapshots ORDER BY snapshot_date")
    st.download_button("Ekspor snapshot ekuitas CSV",pd.DataFrame(snaps).to_csv(index=False).encode("utf-8-sig"),"equity_snapshots.csv","text/csv",use_container_width=True)
    st.caption(f"Lokasi database aktif: {DB_PATH}. Di Streamlit Cloud, filesystem lokal tidak dijamin persisten; gunakan SQLite hanya untuk prototipe/deployment dengan persistent storage yang terjamin.")

def main():
    st.title("🎯 V5 Mobile Swing Hunter")
    st.caption("Swing scanner · Portfolio Advisor · Buy/Sell · Trading Journal · Risk Limits · Equity & Drawdown")
    try: init_db()
    except Exception as e: st.error(f"Gagal menyiapkan database SQLite: {e}"); st.stop()
    tabs=st.tabs(["🎯 Hunter","💼 Portfolio","🔁 Buy / Sell","📒 Journal","🔎 Analyzer","🛡️ Risk","📉 Equity","🗄️ Backup"])
    with tabs[0]: page_hunter()
    with tabs[1]: page_portfolio()
    with tabs[2]: page_trade()
    with tabs[3]: page_journal()
    with tabs[4]: page_analyzer()
    with tabs[5]: page_risk()
    with tabs[6]: page_equity()
    with tabs[7]: page_backup()
    st.markdown("<p class='small-muted' style='text-align:center;margin-top:2rem'>Harga Yahoo Finance dapat tertunda. Gunakan aplikasi broker untuk harga eksekusi dan konfirmasi transaksi. Aplikasi ini bukan penasihat keuangan.</p>",unsafe_allow_html=True)

if __name__=="__main__": main()
