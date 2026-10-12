import os
import sqlite3
import shutil
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# Must be the first Streamlit command
st.set_page_config(page_title="V5.1 Mobile Swing Hunter", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container{max-width:1200px;padding-top:1rem;padding-left:.8rem;padding-right:.8rem}
.card{padding:1rem;border:1px solid rgba(128,128,128,.28);border-radius:14px;margin-bottom:.8rem;background:rgba(128,128,128,.04)}
.muted{font-size:.82rem;opacity:.75}
@media(max-width:700px){.block-container{padding-left:.45rem;padding-right:.45rem}h1{font-size:1.55rem!important}h2{font-size:1.3rem!important}.stButton button{width:100%}}
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SWING_DB_PATH", str(BASE_DIR / "swing_hunter_v5.sqlite3")))
try:
    DB_PATH = Path(st.secrets.get("SWING_DB_PATH", str(DB_PATH)))
except Exception:
    pass
BUY_FEE_PCT = float(os.getenv("BUY_FEE_PCT", "0.15"))
SELL_FEE_PCT = float(os.getenv("SELL_FEE_PCT", "0.25"))

DEFAULT_WATCHLIST = "ANTM,ASII,BBNI,BBRI,BBCA,BMRI,TLKM,INCO,MDKA,PGAS,ADRO,UNTR,ICBP,KLBF,AMRT,CPIN,BRIS"
LIQUID_CANDIDATES = "AADI,ADMR,ADRO,AGII,AKRA,AMMN,AMRT,ANTM,ARTO,ASII,BBCA,BBNI,BBRI,BBTN,BDMN,BFIN,BMRI,BRIS,BRPT,BSDE,BUKA,BUMI,CMRY,CPIN,CTRA,CUAN,DEWA,DSNG,ELSA,EMTK,ENRG,ERAA,ESSA,EXCL,GOTO,HEAL,HRTA,ICBP,INCO,INDF,INDY,INKP,ISAT,ITMG,JPFA,KIJA,KLBF,MAPA,MAPI,MBMA,MDKA,MEDC,MIKA,NCKL,PGAS,PGEO,PTBA,PTRO,RAJA,SCMA,SMGR,TAPG,TLKM,TOWR,UNTR,UNVR,WIFI"
DEFAULT_LQ45 = "AADI,ADMR,ADRO,AKRA,AMMN,AMRT,ANTM,ASII,BBCA,BBNI,BBRI,BBTN,BMRI,BRPT,BUMI,CPIN,CUAN,DEWA,EMTK,ESSA,EXCL,GOTO,HRTA,ICBP,INCO,INDF,INDY,INKP,ISAT,ITMG,JPFA,KLBF,MAPI,MBMA,MDKA,MEDC,NCKL,PGAS,PGEO,PTBA,SCMA,TLKM,UNTR,UNVR,WIFI"
DEFAULT_IDX30 = "AADI,ADMR,ADRO,AMRT,ANTM,ASII,BBCA,BBNI,BBRI,BMRI,BRPT,BUMI,CPIN,DEWA,EMTK,GOTO,ICBP,INCO,INDF,INKP,JPFA,KLBF,MBMA,MDKA,MEDC,PGAS,PGEO,TLKM,UNTR,UNVR"

# ---------------- Database ----------------
def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with connect_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, txn_time TEXT NOT NULL, symbol TEXT NOT NULL,
          txn_type TEXT NOT NULL CHECK(txn_type IN ('BUY','SELL','OPENING')), lots INTEGER NOT NULL CHECK(lots>0),
          price REAL NOT NULL CHECK(price>0), gross_amount REAL NOT NULL, fee_amount REAL NOT NULL DEFAULT 0,
          realized_pnl REAL, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_transactions_symbol_time ON transactions(symbol,txn_time);
        CREATE TABLE IF NOT EXISTS holdings(
          symbol TEXT PRIMARY KEY, shares INTEGER NOT NULL DEFAULT 0,
          avg_cost_per_share REAL NOT NULL DEFAULT 0, total_cost REAL NOT NULL DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS risk_limits(
          id INTEGER PRIMARY KEY CHECK(id=1), risk_per_trade_pct REAL NOT NULL DEFAULT 1,
          max_position_pct REAL NOT NULL DEFAULT 25, max_drawdown_pct REAL NOT NULL DEFAULT 10,
          portfolio_reference_value REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS equity_snapshots(
          id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT NOT NULL UNIQUE,
          realized_pnl REAL NOT NULL, unrealized_pnl REAL NOT NULL, equity_value REAL NOT NULL, note TEXT);
        """)
        for key, value in {
            "watchlist": DEFAULT_WATCHLIST,
            "lq45": DEFAULT_LQ45,
            "idx30": DEFAULT_IDX30,
            "index_checked": "Seed awal; verifikasi dengan publikasi BEI terbaru",
        }.items():
            conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (key, value))
        conn.execute("INSERT OR IGNORE INTO risk_limits(id,risk_per_trade_pct,max_position_pct,max_drawdown_pct,portfolio_reference_value) VALUES(1,1,25,10,0)")


def query(sql, params=()):
    with connect_db() as conn:
        return [dict(x) for x in conn.execute(sql, params).fetchall()]


def setting(key, default=""):
    rows = query("SELECT value FROM app_settings WHERE key=?", (key,))
    return rows[0]["value"] if rows else default


def save_setting(key, value):
    with connect_db() as conn:
        conn.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP", (key, str(value)))


def normalize_symbols(text):
    out = []
    for item in str(text or "").replace(";", ",").replace("\n", ",").split(","):
        code = item.strip().upper().replace(" ", "")
        if code.endswith(".JK"):
            code = code[:-3]
        if code.isalnum() and 1 <= len(code) <= 6 and code + ".JK" not in out:
            out.append(code + ".JK")
    return out

# ---------------- Market data ----------------
def _flatten_yf_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        # For single ticker downloads, first level is usually the OHLCV field.
        df.columns = df.columns.get_level_values(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def daily_data(symbol, period="1y"):
    try:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False, timeout=15)
        if df is None or df.empty:
            return pd.DataFrame()
        df = _flatten_yf_columns(df)
        needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[needed].copy()
        if "Close" not in df.columns:
            return pd.DataFrame()
        df = df.dropna(subset=["Close"])
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=45, show_spinner=False)
def intraday_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", auto_adjust=False, progress=False, threads=False, timeout=15)
        if df is None or df.empty:
            return pd.DataFrame()
        df = _flatten_yf_columns(df)
        if "Close" not in df.columns:
            return pd.DataFrame()
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


def indicators(df):
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"] = c.rolling(20).mean()
    d["MA50"] = c.rolling(50).mean()
    d["MA200"] = c.rolling(200).mean()
    delta = c.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    al = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    d["RSI"] = 100 - 100 / (1 + rs)
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    d["MACD"] = e12 - e26
    d["MACD_SIGNAL"] = d["MACD"].ewm(span=9, adjust=False).mean()
    prev = c.shift(1)
    tr = pd.concat([(h-l), (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.rolling(14).mean()
    d["VOL_MA20"] = v.rolling(20).mean()
    d["VOL_RATIO"] = v / d["VOL_MA20"].replace(0, np.nan)
    # Exclude current candle from resistance/support reference.
    d["RES20"] = h.shift(1).rolling(20).max()
    d["SUP20"] = l.shift(1).rolling(20).min()
    return d


def market_regime():
    df = daily_data("^JKSE")
    if df.empty or len(df) < 50:
        return {"regime": "UNKNOWN", "price": None, "ma20": None, "ma50": None, "score": 0, "timestamp": None}
    d = indicators(df)
    r = d.iloc[-1]
    if pd.isna(r["MA20"]) or pd.isna(r["MA50"]):
        return {"regime": "UNKNOWN", "price": float(r["Close"]), "ma20": None, "ma50": None, "score": 0, "timestamp": d.index[-1]}
    p, m20, m50 = float(r["Close"]), float(r["MA20"]), float(r["MA50"])
    regime = "BULLISH" if p > m20 > m50 else "BEARISH" if p < m20 < m50 else "SIDEWAYS"
    return {"regime": regime, "price": p, "ma20": m20, "ma50": m50, "score": 8 if regime == "BULLISH" else -8 if regime == "BEARISH" else 0, "timestamp": d.index[-1]}


def analyze(symbol):
    raw = daily_data(symbol)
    if raw.empty or len(raw) < 60:
        return None, "Data kosong atau histori kurang dari 60 candle"
    needed = {"Close", "High", "Low", "Volume"}
    if not needed.issubset(raw.columns):
        return None, "Kolom OHLCV tidak lengkap"
    d = indicators(raw)
    r = d.iloc[-1]
    required = ["Close", "MA20", "MA50", "RSI", "MACD", "MACD_SIGNAL", "ATR", "VOL_RATIO", "RES20", "SUP20"]
    if any(pd.isna(r[k]) for k in required):
        return None, "Indikator belum valid / data tidak cukup"
    p, ma20, ma50 = float(r.Close), float(r.MA20), float(r.MA50)
    ma200 = float(r.MA200) if pd.notna(r.MA200) else np.nan
    rsi, atr, vol_ratio = float(r.RSI), float(r.ATR), float(r.VOL_RATIO)
    resistance, support = float(r.RES20), float(r.SUP20)
    score, reasons, warnings = 0, [], []
    if p > ma20:
        score += 10; reasons.append("Harga di atas MA20")
    else: warnings.append("Harga di bawah MA20")
    if ma20 > ma50:
        score += 10; reasons.append("MA20 di atas MA50")
    else: warnings.append("MA20 belum di atas MA50")
    if pd.notna(ma200):
        if p > ma200: score += 5; reasons.append("Harga di atas MA200")
        else: warnings.append("Harga di bawah MA200")
    if 50 <= rsi <= 68:
        score += 10; reasons.append("RSI mendukung momentum")
    elif 45 <= rsi < 50:
        score += 5; reasons.append("RSI mulai menguat")
    elif rsi > 72:
        warnings.append("RSI tinggi; risiko mengejar harga")
    elif rsi < 35:
        warnings.append("RSI lemah")
    if float(r.MACD) > float(r.MACD_SIGNAL):
        score += 10; reasons.append("MACD di atas signal")
    else: warnings.append("MACD belum bullish")
    if vol_ratio >= 1.5:
        score += 15; reasons.append("Volume >= 1,5x rata-rata")
    elif vol_ratio >= 1.2:
        score += 10; reasons.append("Volume meningkat")
    elif vol_ratio >= 1.0:
        score += 5
    else: warnings.append("Volume di bawah rata-rata")
    if p > resistance:
        score += 15; reasons.append("Close menembus resistance 20 hari")
    elif p > ma20:
        score += 5; reasons.append("Harga masih di atas MA20")
    if support > 0 and (p - support) / p <= 0.05:
        score += 5; reasons.append("Harga relatif dekat support")
    market = market_regime()
    score += market["score"]
    score = int(max(0, min(100, score)))

    # Entry is a proposed zone, not a promise of execution.
    entry_low = max(0.01, min(p, ma20))
    entry_high = max(entry_low, min(p, max(ma20, entry_low) * 1.01))
    entry = (entry_low + entry_high) / 2
    # Stop must be below entry and grounded in volatility/support.
    candidate_stop = min(entry - 1.2 * atr, support - 0.15 * atr)
    stop = max(0.01, candidate_stop)
    if stop >= entry:
        stop = max(0.01, entry - max(atr, entry * 0.03))
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None, "Stop-loss tidak valid; risiko per saham <= 0"

    # Target uses nearby resistance where sensible; otherwise a volatility-based fallback.
    # Do not force target to 2R: this allows R:R to filter weak setups.
    resistance_target = resistance if resistance > entry else np.nan
    fallback_target = entry + max(2 * atr, entry * 0.03)
    tp1 = float(resistance_target) if pd.notna(resistance_target) else float(fallback_target)
    tp2 = max(tp1, entry + max(3 * atr, entry * 0.05))
    potential = (tp1 - entry) / entry if entry > 0 else 0.0
    rr = (tp1 - entry) / risk_per_share if risk_per_share > 0 else 0.0
    if potential < 0.03: warnings.append("Potensi TP1 di bawah 3%")
    if rr < 1.5: warnings.append("R:R di bawah 1:1,5")
    if market["regime"] == "BEARISH": warnings.append("IHSG bearish; pertimbangkan menurunkan risiko")
    if score >= 75 and potential >= 0.05 and rr >= 2 and market["regime"] != "BEARISH":
        signal = "BUY CANDIDATE"
    elif score >= 60 and potential >= 0.03 and rr >= 1.5:
        signal = "WATCH / WAIT"
    else:
        signal = "AVOID / NOT READY"
    result = {
        "symbol": symbol, "price": p, "score": score, "signal": signal,
        "entry_low": entry_low, "entry_high": entry_high, "entry": entry,
        "stop": stop, "tp1": tp1, "tp2": tp2, "potential": potential, "rr": rr,
        "rsi": rsi, "atr": atr, "vol_ratio": vol_ratio, "support": support,
        "resistance": resistance, "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "market": market, "reasons": reasons, "warnings": warnings,
        "timestamp": d.index[-1], "history": d,
    }
    return result, None

# ---------------- Portfolio & trades ----------------
def holdings():
    return query("SELECT symbol,shares,avg_cost_per_share,total_cost FROM holdings WHERE shares>0 ORDER BY symbol")


def transactions(limit=10000):
    return query("SELECT * FROM transactions ORDER BY txn_time DESC,id DESC LIMIT ?", (int(limit),))


def current_prices(symbols):
    prices, errors = {}, {}
    for symbol in symbols:
        df = intraday_data(symbol)
        if not df.empty:
            prices[symbol] = float(df["Close"].dropna().iloc[-1])
        else:
            daily = daily_data(symbol)
            if not daily.empty:
                prices[symbol] = float(daily["Close"].dropna().iloc[-1])
                errors[symbol] = "Intraday unavailable; using last daily close"
            else:
                errors[symbol] = "No usable price data"
    return prices, errors


def add_transaction(txn_date, symbol, txn_type, lots, price, notes=""):
    symbols = normalize_symbols(symbol)
    if len(symbols) != 1: raise ValueError("Masukkan satu kode saham yang valid.")
    symbol = symbols[0]
    if txn_type not in ("BUY", "SELL"): raise ValueError("Jenis transaksi tidak valid.")
    if int(lots) <= 0 or not np.isfinite(float(price)) or float(price) <= 0: raise ValueError("Lot dan harga harus lebih besar dari nol.")
    shares = int(lots) * 100
    price = float(price)
    gross = shares * price
    fee_pct = BUY_FEE_PCT if txn_type == "BUY" else SELL_FEE_PCT
    fee = round(gross * fee_pct / 100, 2)
    with connect_db() as conn:
        h = conn.execute("SELECT shares,avg_cost,total_cost FROM holdings WHERE symbol=?", (symbol,)).fetchone()
        old_shares = int(h["shares"]) if h else 0
        old_avg = float(h["avg_cost_per_share"]) if h else 0.0
        old_cost = float(h["total_cost"]) if h else 0.0
        realized = None
        if txn_type == "SELL":
            if shares > old_shares: raise ValueError(f"Penjualan ditolak: kepemilikan hanya {old_shares//100} lot.")
            removed_cost = old_avg * shares
            realized = round(gross - fee - removed_cost, 2)
            new_shares = old_shares - shares
            new_cost = max(0.0, old_cost - removed_cost)
            new_avg = new_cost / new_shares if new_shares else 0.0
        else:
            new_shares = old_shares + shares
            new_cost = old_cost + gross + fee
            new_avg = new_cost / new_shares
        conn.execute("INSERT INTO transactions(txn_time,symbol,txn_type,lots,price,gross_amount,fee_amount,realized_pnl,notes) VALUES(?,?,?,?,?,?,?,?,?)", (datetime.combine(txn_date, datetime.min.time()).isoformat(timespec="seconds"), symbol, txn_type, int(lots), price, gross, fee, realized, notes.strip() or None))
        conn.execute("INSERT INTO holdings(symbol,shares,avg_cost_per_share,total_cost,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(symbol) DO UPDATE SET shares=excluded.shares,avg_cost_per_share=excluded.avg_cost_per_share,total_cost=excluded.total_cost,updated_at=CURRENT_TIMESTAMP", (symbol, new_shares, new_avg, new_cost))


def money(value):
    return "N/A" if value is None or pd.isna(value) else "Rp" + f"{float(value):,.0f}"


def render_setup(x):
    st.markdown(f"<div class='card'><div style='display:flex;justify-content:space-between;gap:10px'><div><h3 style='margin:0'>{x['symbol'].replace('.JK','')}</h3><b>{x['signal']}</b></div><div style='font-size:1.6rem;font-weight:800'>{x['score']}/100</div></div><hr>Harga daily: {money(x['price'])}<br>Zona entry: {money(x['entry_low'])} – {money(x['entry_high'])}<br>Stop: {money(x['stop'])}<br>TP1: {money(x['tp1'])} · TP2: {money(x['tp2'])}<br>Potensi TP1: {x['potential']*100:.2f}% · R:R {x['rr']:.2f}:1<br><span class='muted'>Candle daily terakhir: {x['timestamp']} · data Yahoo Finance dapat tertunda</span></div>", unsafe_allow_html=True)
    with st.expander(f"Detail {x['symbol']} — indikator dan risiko"):
        a,b,c = st.columns(3)
        a.metric("RSI", f"{x['rsi']:.1f}")
        b.metric("Volume / MA20", f"{x['vol_ratio']:.2f}x")
        c.metric("IHSG", x["market"]["regime"])
        st.write("**Alasan positif**")
        for item in x["reasons"]: st.write("✓", item)
        st.write("**Peringatan**")
        if x["warnings"]:
            for item in x["warnings"]: st.write("⚠️", item)
        else: st.write("Tidak ada peringatan dari aturan dasar ini.")
        st.line_chart(x["history"][["Close", "MA20", "MA50", "MA200"]].tail(120))

# ---------------- Pages ----------------
def page_hunter():
    st.header("🎯 Swing Hunter — V5.1 Audit & Signal Engine")
    m = market_regime()
    st.markdown(f"<div class='card'><b>IHSG: {m['regime']}</b><br>Harga: {money(m['price'])} · MA20: {money(m['ma20'])} · MA50: {money(m['ma50'])}<br><span class='muted'>Timestamp daily terakhir: {m['timestamp']}</span></div>", unsafe_allow_html=True)
    universe = st.radio("Universe saham", ["Watchlist pribadi", "Universe likuid", "Universe indeks"], horizontal=True, key="universe_mode")
    symbols = []
    if universe == "Watchlist pribadi":
        text = st.text_area("Kode saham dipisahkan koma", setting("watchlist", DEFAULT_WATCHLIST), key="watchlist_input")
        c1,c2 = st.columns([1,2])
        if c1.button("Simpan watchlist", use_container_width=True):
            cleaned = normalize_symbols(text)
            if cleaned:
                save_setting("watchlist", ",".join(s.replace(".JK", "") for s in cleaned)); st.success(f"{len(cleaned)} saham tersimpan.")
            else: st.error("Masukkan minimal satu kode valid.")
        c2.caption("Watchlist disimpan ke SQLite aktif.")
        symbols = normalize_symbols(text)
    elif universe == "Universe indeks":
        idx = st.selectbox("Indeks", ["LQ45", "IDX30", "Gabungan LQ45 + IDX30"])
        lq = normalize_symbols(setting("lq45", DEFAULT_LQ45)); ix = normalize_symbols(setting("idx30", DEFAULT_IDX30))
        symbols = lq if idx == "LQ45" else ix if idx == "IDX30" else list(dict.fromkeys(lq + ix))
        st.caption(f"LQ45 seed: {len(lq)} kode · IDX30 seed: {len(ix)} kode. Daftar bawaan bukan feed otomatis; verifikasi terhadap publikasi BEI terbaru.")
        with st.expander("Edit daftar konstituen indeks"):
            lq_text = st.text_area("Daftar LQ45", setting("lq45", DEFAULT_LQ45))
            ix_text = st.text_area("Daftar IDX30", setting("idx30", DEFAULT_IDX30))
            checked = st.text_input("Tanggal/periode verifikasi", setting("index_checked", "Belum diverifikasi"))
            if st.button("Simpan konstituen indeks"):
                lq_clean, ix_clean = normalize_symbols(lq_text), normalize_symbols(ix_text)
                if not lq_clean or not ix_clean: st.error("Kedua daftar harus berisi kode valid.")
                else:
                    save_setting("lq45", ",".join(s.replace(".JK", "") for s in lq_clean)); save_setting("idx30", ",".join(s.replace(".JK", "") for s in ix_clean)); save_setting("index_checked", checked); st.success("Daftar tersimpan."); st.rerun()
    else:
        st.caption("Universe ini menyaring pool kandidat awal, bukan seluruh saham BEI. Nilai transaksi diperkirakan dari Close × Volume.")
        a,b,c = st.columns(3)
        lookback = a.selectbox("Rata-rata periode", [20,30,60], index=0)
        min_value = b.number_input("Min. nilai transaksi (Rp miliar/hari)", min_value=0.0, value=5.0, step=1.0)
        min_volume = c.number_input("Min. volume (juta saham/hari)", min_value=0.0, value=1.0, step=.5)
        if st.button("Bangun universe likuid", use_container_width=True):
            passed, rejected = [], []
            pool = normalize_symbols(LIQUID_CANDIDATES)
            bar = st.progress(0)
            for i,s in enumerate(pool):
                df = daily_data(s, "6mo")
                if df.empty or len(df) < lookback or "Volume" not in df:
                    rejected.append({"Kode":s.replace(".JK",""),"Status":"Data tidak cukup"})
                else:
                    d = df.dropna(subset=["Close","Volume"]).tail(int(lookback))
                    av = float((d.Close.astype(float)*d.Volume.astype(float)).mean())
                    vv = float(d.Volume.astype(float).mean())
                    if av >= min_value*1e9 and vv >= min_volume*1e6: passed.append({"symbol":s,"avg_value":av,"avg_volume":vv})
                    else: rejected.append({"Kode":s.replace(".JK",""),"Status":"Di bawah ambang","Rata-rata nilai transaksi":av,"Rata-rata volume":vv})
                bar.progress((i+1)/len(pool))
            bar.empty()
            st.session_state["liquid_passed"] = passed; st.session_state["liquid_rejected"] = rejected
            st.session_state["liquid_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        passed = st.session_state.get("liquid_passed", [])
        symbols = [x["symbol"] for x in passed]
        if passed:
            st.success(f"{len(passed)} saham lolos filter · {st.session_state.get('liquid_time','')}")
            st.dataframe(pd.DataFrame([{"Kode":x["symbol"].replace(".JK",""),"Rata-rata nilai transaksi":x["avg_value"],"Rata-rata volume":x["avg_volume"]} for x in passed]), use_container_width=True, hide_index=True)
        if st.session_state.get("liquid_rejected"):
            with st.expander("Kandidat tidak lolos / data bermasalah"):
                st.dataframe(pd.DataFrame(st.session_state["liquid_rejected"]), use_container_width=True, hide_index=True)

    symbols = list(dict.fromkeys(symbols))
    st.caption(f"Universe aktif: {universe} · {len(symbols)} ticker")
    a,b,c = st.columns(3)
    min_score = a.slider("Skor minimum", 30, 90, 55, 5)
    min_target = b.slider("Target minimum (%)", 1, 15, 3) / 100
    min_rr = c.slider("R:R minimum", 0.5, 4.0, 1.5, 0.5)
    if st.button("🚀 Scan + Audit", use_container_width=True, disabled=not symbols):
        audit, passed = [], []
        bar = st.progress(0); status = st.empty()
        for i,s in enumerate(symbols):
            status.caption(f"Menganalisis {i+1}/{len(symbols)}: {s}")
            r, error = analyze(s)
            if error:
                audit.append({"Kode":s.replace(".JK",""),"Data":"GAGAL","Skor":None,"Potensi %":None,"R:R":None,"Status":error})
            else:
                fail = []
                if r["score"] < min_score: fail.append(f"Skor {r['score']} < {min_score}")
                if r["potential"] < min_target: fail.append(f"Potensi {r['potential']*100:.2f}% < {min_target*100:.1f}%")
                if r["rr"] < min_rr: fail.append(f"R:R {r['rr']:.2f} < {min_rr:.1f}")
                audit.append({"Kode":s.replace(".JK",""),"Data":"OK","Skor":r["score"],"Harga daily":r["price"],"Potensi %":round(r["potential"]*100,2),"R:R":round(r["rr"],2),"RSI":round(r["rsi"],1),"Volume/MA20":round(r["vol_ratio"],2),"Status":"LOLOS" if not fail else "GAGAL FILTER: " + "; ".join(fail)})
                if not fail: passed.append(r)
            bar.progress((i+1)/len(symbols))
        bar.empty(); status.empty()
        passed.sort(key=lambda x:(x["score"],x["potential"],x["rr"]), reverse=True)
        st.session_state["hunter_passed"] = passed; st.session_state["hunter_audit"] = audit
        st.session_state["hunter_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["hunter_universe"] = universe
        st.session_state["hunter_total"] = len(symbols)
    audit = st.session_state.get("hunter_audit", [])
    passed = st.session_state.get("hunter_passed", [])
    if audit:
        st.subheader("Ringkasan scan")
        ok = sum(x["Data"] == "OK" for x in audit); fail_data = len(audit)-ok
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Ticker dipindai", len(audit)); c2.metric("Data valid", ok); c3.metric("Data gagal", fail_data); c4.metric("Setup lolos", len(passed))
        st.caption(f"Scan {st.session_state.get('hunter_time','')} · universe {st.session_state.get('hunter_universe','')}")
        audit_df = pd.DataFrame(audit)
        with st.expander("🔍 Audit seluruh ticker — mengapa lolos/gagal", expanded=True):
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
            st.download_button("Ekspor audit CSV", audit_df.to_csv(index=False).encode("utf-8-sig"), f"audit_scan_{date.today().isoformat()}.csv", "text/csv", use_container_width=True)
        if passed:
            st.subheader("Setup yang lolos filter")
            for r in passed[:15]: render_setup(r)
        else:
            st.warning("Tidak ada setup yang lolos filter. Lihat kolom Status pada Audit Scan untuk mengetahui penyebab spesifik; jangan langsung menganggap tidak ada saham menarik.")


def page_intraday():
    st.header("⏱️ Pemantauan harga intraday")
    symbol = st.text_input("Kode saham", "BBNI").upper().strip()
    if st.button("Refresh harga intraday", use_container_width=True): intraday_data.clear(); daily_data.clear()
    symbols = normalize_symbols(symbol)
    if not symbols: st.error("Kode saham tidak valid."); return
    s = symbols[0]
    df = intraday_data(s)
    if not df.empty:
        last = df.iloc[-1]
        st.metric(f"{s.replace('.JK','')} — candle 5 menit terakhir", money(last["Close"]))
        st.caption(f"Timestamp candle sumber: {df.index[-1]} · Yahoo Finance dapat tertunda dan bukan feed eksekusi realtime.")
        st.line_chart(df["Close"].tail(100))
    else:
        st.warning("Data intraday tidak tersedia. Jangan menganggap penutupan harian sebagai harga berjalan.")


def page_portfolio():
    st.header("💼 Portfolio Advisor")
    hs = holdings()
    if not hs: st.info("Belum ada kepemilikan. Catat transaksi BUY atau saldo awal terlebih dahulu."); return
    prices, warnings = current_prices([h["symbol"] for h in hs])
    rows=[]
    for h in hs:
        px=prices.get(h["symbol"]); value=px*h["shares"] if px is not None else None; pnl=value-h["total_cost"] if value is not None else None
        rows.append({"Saham":h["symbol"].replace(".JK",""),"Lot":h["shares"]//100,"Avg cost":h["avg_cost_per_share"],"Harga indikatif":px,"Nilai pasar":value,"P/L sebelum estimasi fee jual":pnl,"P/L %":pnl/h["total_cost"]*100 if pnl is not None and h["total_cost"] else None,"Catatan data":warnings.get(h["symbol"],"Intraday tersedia")})
    df=pd.DataFrame(rows)
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.caption("Harga indikatif, bukan harga eksekusi. P/L pada tabel belum mengurangi estimasi fee jual dan slippage.")


def page_trade():
    st.header("🔁 Buy / Sell")
    st.caption(f"Fee asumsi: BUY {BUY_FEE_PCT:.2f}% · SELL {SELL_FEE_PCT:.2f}%. Sesuaikan dengan broker melalui environment variables.")
    with st.form("trade_form"):
        a,b=st.columns(2); typ=a.selectbox("Jenis transaksi",["BUY","SELL"]); dt=b.date_input("Tanggal",date.today())
        symbol=st.text_input("Kode saham","BBNI"); c,d=st.columns(2); lots=c.number_input("Lot",1,100000,1); price=d.number_input("Harga per saham",min_value=1.0,value=1000.0,step=10.0); notes=st.text_input("Catatan")
        gross=lots*100*price; fee=gross*(BUY_FEE_PCT if typ=="BUY" else SELL_FEE_PCT)/100
        st.info(f"Bruto {money(gross)} · fee estimasi {money(fee)}")
        submit=st.form_submit_button("Simpan transaksi",use_container_width=True)
    if submit:
        try: add_transaction(dt,symbol,typ,int(lots),price,notes); st.success("Transaksi tersimpan."); st.rerun()
        except Exception as e: st.error(str(e))


def page_journal():
    st.header("📒 Trading Journal")
    tx=transactions()
    if not tx: st.info("Belum ada transaksi."); return
    df=pd.DataFrame(tx)
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button("Ekspor CSV",df.to_csv(index=False).encode("utf-8-sig"),f"journal_{date.today().isoformat()}.csv","text/csv",use_container_width=True)
    sells=df[df.txn_type=="SELL"]
    realized=float(pd.to_numeric(sells.realized_pnl,errors="coerce").fillna(0).sum()) if not sells.empty else 0
    st.metric("Realized P/L bersih transaksi SELL",money(realized))


def page_risk():
    st.header("🛡️ Risk Calculator")
    rows=query("SELECT * FROM risk_limits WHERE id=1")
    r=rows[0]
    with st.form("risk_form"):
        a,b,c=st.columns(3); risk=a.number_input("Risiko modal (%)",.1,5.0,float(r["risk_per_trade_pct"]),.1); pos=b.number_input("Maks. alokasi saham (%)",1.0,100.0,float(r["max_position_pct"]),1.0); ref=c.number_input("Modal referensi (Rp)",min_value=0.0,value=float(r["portfolio_reference_value"]),step=100000.0)
        save=st.form_submit_button("Simpan")
    if save:
        with connect_db() as conn: conn.execute("UPDATE risk_limits SET risk_per_trade_pct=?,max_position_pct=?,portfolio_reference_value=? WHERE id=1",(risk,pos,ref))
        st.success("Risk limit disimpan."); st.rerun()
    a,b,c=st.columns(3); capital=a.number_input("Modal untuk kalkulator (Rp)",min_value=0.0,value=float(ref),step=100000); entry=b.number_input("Entry",min_value=0.0,value=1000.0,step=10.0); stop=c.number_input("Stop",min_value=0.0,value=950.0,step=10.0)
    if capital>0 and entry>stop>0:
        risk_cash=capital*risk/100; lots_risk=int(risk_cash/(entry-stop))//100; lots_pos=int((capital*pos/100)/entry)//100; lots=min(lots_risk,lots_pos)
        st.write(f"Risiko uang: **{money(risk_cash)}** · Ukuran posisi maksimum: **{lots} lot**")
        st.caption("Perhitungan belum memperhitungkan gap, slippage, batas fraksi lot, atau fee secara penuh.")


def page_backup():
    st.header("🗄️ Backup SQLite")
    st.warning("Jangan menyimpan file database pribadi di repositori GitHub publik. Pada Streamlit Cloud, filesystem lokal tidak dijamin persisten.")
    if DB_PATH.exists():
        # Use SQLite's backup API to include committed data consistently, including WAL state.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp: temp_path=Path(tmp.name)
        try:
            src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(temp_path)
            src.backup(dst); dst.close(); src.close()
            data=temp_path.read_bytes()
        finally:
            try: temp_path.unlink(missing_ok=True)
            except Exception: pass
        st.download_button("Unduh backup database konsisten",data,f"swing_hunter_backup_{date.today().isoformat()}.sqlite3","application/octet-stream",use_container_width=True)
    tx=transactions(); hs=holdings()
    st.download_button("Ekspor transaksi CSV",pd.DataFrame(tx).to_csv(index=False).encode("utf-8-sig"),"transactions.csv","text/csv",use_container_width=True)
    st.download_button("Ekspor holdings CSV",pd.DataFrame(hs).to_csv(index=False).encode("utf-8-sig"),"holdings.csv","text/csv",use_container_width=True)
    st.caption(f"Database aktif: {DB_PATH}. Backup secara berkala ke perangkat pribadi.")


def main():
    init_db()
    st.title("🎯 V5.1 Mobile Swing Hunter")
    st.caption("Audit Scan · Signal Engine · Intraday Monitor · Portfolio · Journal · Risk · SQLite Backup")
    tabs=st.tabs(["🎯 Hunter","⏱️ Intraday","💼 Portfolio","🔁 Buy/Sell","📒 Journal","🛡️ Risk","🗄️ Backup"])
    with tabs[0]: page_hunter()
    with tabs[1]: page_intraday()
    with tabs[2]: page_portfolio()
    with tabs[3]: page_trade()
    with tabs[4]: page_journal()
    with tabs[5]: page_risk()
    with tabs[6]: page_backup()
    st.markdown("<p class='muted' style='text-align:center;margin-top:2rem'>Data Yahoo Finance dapat tertunda. Gunakan aplikasi broker untuk harga eksekusi. Sinyal adalah hasil aturan sederhana, bukan jaminan atau rekomendasi investasi personal.</p>",unsafe_allow_html=True)

if __name__ == "__main__":
    main()
