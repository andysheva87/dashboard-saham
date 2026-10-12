import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ==========================================================
# KONFIGURASI TAMPILAN DASHBOARD (MOBILE OPTIMIZED)
# ==========================================================
st.set_page_config(
    page_title="V5 Mobile Swing Hunter Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS agar antarmuka rapi di layar ponsel
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 0.8rem; padding-right: 0.8rem; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    .stTable, .stDataFrame { font-size: 0.8rem !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 V5 Mobile Swing Hunter")
st.caption("Swing Scanner • Portfolio Advisor • Buy/Sell • Risk Limits • Equity & Drawdown")

# ==========================================================
# INISIALISASI SESSION STATE
# ==========================================================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {'ticker': 'BBNI', 'lots': 9, 'avg': 3688},
        {'ticker': 'TLKM', 'lots': 9, 'avg': 2850}
    ]

if 'journal' not in st.session_state:
    st.session_state.journal = []

# ==========================================================
# FUNGSI PEMBANTU (FORMATTING & DATA LOADER)
# ==========================================================
def rupiah(val):
    if val is None or pd.isna(val): 
        return "N/A"
    return f"Rp {val:,.0f}"

@st.cache_data(ttl=120)
def load_stock(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo", interval="1d", auto_adjust=False)
        if df.empty: 
            return pd.DataFrame(), {}, "Data kosong."
        try: 
            info = ticker.info
        except: 
            info = {}
        return df, info, None
    except Exception as e:
        return pd.DataFrame(), {}, str(e)

@st.cache_data(ttl=120)
def get_ihsg_status():
    try:
        df, _, _ = load_stock("^JKSE")
        if not df.empty:
            close = float(df['Close'].iloc[-1])
            ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
            ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
            status = "BEARISH" if close < ma20 or ma20 < ma50 else "BULLISH"
            return status, close, ma20, ma50
    except: 
        pass
    return "UNKNOWN", 0, 0, 0

# ==========================================================
# KALKULASI INDIKATOR TEKNIKAL
# ==========================================================
def calculate_indicators(df):
    data = df.copy()
    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]

    data["MA20"] = close.rolling(20).mean()
    data["MA50"] = close.rolling(50).mean()
    
    # RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI14"] = (100 - (100 / (1 + rs))).fillna(50)

    # ATR 14
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    data["ATR14"] = tr.rolling(14).mean()

    # Volume Ratio
    data["VolumeMA20"] = volume.rolling(20).mean()
    data["VolRatio"] = (volume / data["VolumeMA20"].replace(0, np.nan)).fillna(1.0)

    data["Support20"] = low.rolling(20).min().shift(1)
    data["Resistance20"] = high.rolling(20).max().shift(1)

    return data

# ==========================================================
# TAB NAVIGASI UTAMA
# ==========================================================
tab_hunter, tab_portfolio, tab_journal, tab_risk = st.tabs([
    "🎯 Hunter", "💼 Portfolio", "📜 Journal", "🛡️ Risk Limits"
])

# ----------------------------------------------------------
# TAB 1: HUNTER (SCANNER)
# ----------------------------------------------------------
with tab_hunter:
    ihsg_stat, ihsg_p, ihsg_ma20, ihsg_ma50 = get_ihsg_status()
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Header Status IHSG Realtime
    with st.container():
        if ihsg_stat == "BEARISH":
            st.error(f"### IHSG 🔴 BEARISH\nHarga: {rupiah(ihsg_p)} · MA20: {rupiah(ihsg_ma20)} · MA50: {rupiah(ihsg_ma50)}")
        else:
            st.success(f"### IHSG 🟢 BULLISH\nHarga: {rupiah(ihsg_p)} · MA20: {rupiah(ihsg_ma20)} · MA50: {rupiah(ihsg_ma50)}")
        
        st.caption(f"Yahoo Finance; harga dapat tertunda. Update data: **{current_time_str}**")

    st.markdown("---")
    st.markdown("#### Filter Parameter Scan")
    
    col_f1, col_f2, col_f3 = st.columns(3)
    default_rr = 2.00 if ihsg_stat != "BEARISH" else 2.50
    default_score = 50

    min_score = col_f1.slider("Skor Minimum", 0, 100, default_score)
    target_min = col_f2.slider("Target Minimum (%)", 1, 15, 3)
    min_rr = col_f3.slider("R:R Minimum", 1.0, 5.0, default_rr, step=0.25)

    scan_ticker = st.text_input("Kode Saham (Analisis Tunggal)", "BBRI").upper().strip()
    
    if st.button("🚀 Scan Saham", use_container_width=True):
        df_stock, info_stock, err = load_stock(f"{scan_ticker}.JK")
        if err or df_stock.empty:
            st.error(f"Gagal memuat data {scan_ticker}. Pastikan kode saham benar!")
        else:
            df_stock = calculate_indicators(df_stock)
            last = df_stock.iloc[-1]
            price = float(last["Close"])
            atr = float(last["ATR14"]) if pd.notna(last["ATR14"]) else price * 0.03
            support = float(last["Support20"]) if pd.notna(last["Support20"]) else price - atr
            resistance = float(last["Resistance20"]) if pd.notna(last["Resistance20"]) else price + (atr * 2)

            sl = min(support - (atr * 0.25), price - (atr * 1.2))
            tp = max(resistance, price + ((price - sl) * 2))
            
            risk_pct = ((price - sl) / price) * 100
            gain_pct = ((tp - price) / price) * 100
            rr_ratio = gain_pct / risk_pct if risk_pct > 0 else 0

            st.markdown("---")
            st.markdown("#### Hasil Analisis Pre-Buy")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Harga Terakhir", rupiah(price))
            m2.metric("RSI (14)", f"{last['RSI14']:.1f}")
            m3.metric("Volume Ratio", f"{last['VolRatio']:.2f}x")

            p1, p2, p3 = st.columns(3)
            p1.metric("Area Entry", rupiah(price))
            p2.metric("Stop Loss", rupiah(sl), f"-{risk_pct:.2f}%")
            p3.metric("Target Profit (TP)", rupiah(tp), f"+{gain_pct:.2f}%")

            st.info(f"**Risk to Reward Ratio:** 1 : {rr_ratio:.2f}")

            if rr_ratio < min_rr:
                st.warning(f"⚠️ WAIT & SEE: RRR (1:{rr_ratio:.2f}) belum memenuhi batas minimum ({min_rr:.2f}).")
            else:
                st.success("🎉 APPROVED: Setup memenuhi kriteria Risk to Reward!")

# ----------------------------------------------------------
# TAB 2: PORTFOLIO (FLOATING P&L & AUTO-AVERAGE)
# ----------------------------------------------------------
with tab_portfolio:
    st.subheader("Portofolio Aktif (Realtime Market Price)")

    with st.expander("➕ Tambah / Average Down Posisi"):
        p_ticker = st.text_input("Kode Saham", "BBNI").upper().strip()
        p_lots = st.number_input("Jumlah Lot", min_value=1, value=5)
        p_price = st.number_input("Harga Beli (Rp)", min_value=1, value=3500)
        
        if st.button("Simpan / Gabungkan Posisi"):
            item_exist = next((x for x in st.session_state.portfolio if x['ticker'] == p_ticker), None)
            if item_exist:
                tot_l = item_exist['lots'] + p_lots
                tot_m = (item_exist['lots'] * 100 * item_exist['avg']) + (p_lots * 100 * p_price)
                item_exist['lots'] = tot_l
                item_exist['avg'] = round(tot_m / (tot_l * 100))
                st.success(f"Posisi {p_ticker} berhasil digabung! Total Lot: {tot_l} | Avg Baru: {rupiah(item_exist['avg'])}")
            else:
                st.session_state.portfolio.append({'ticker': p_ticker, 'lots': p_lots, 'avg': p_price})
                st.success(f"Posisi baru {p_ticker} ditambahkan.")
            st.rerun()

    if not st.session_state.portfolio:
        st.info("Portofolio saat ini kosong.")
    else:
        tot_modal = 0
        tot_floating = 0

        st.markdown("---")
        for idx, item in enumerate(st.session_state.portfolio):
            df_p, _, _ = load_stock(f"{item['ticker']}.JK")
            curr_p = float(df_p["Close"].iloc[-1]) if not df_p.empty else item['avg']

            modal = item['lots'] * 100 * item['avg']
            val = item['lots'] * 100 * curr_p
            pnl = val - modal
            pnl_pct = (pnl / modal) * 100 if modal > 0 else 0

            tot_modal += modal
            tot_floating += pnl

            with st.container():
                st.markdown(f"### {item['ticker']} ({item['lots']} Lot)")
                st.write(f"Avg: **{rupiah(item['avg'])}** | Market Now: **{rupiah(curr_p)}**")
                
                if pnl >= 0:
                    st.markdown(f"Floating P&L: :green[**+{rupiah(pnl)} (+{pnl_pct:.2f}%)**]")
                else:
                    st.markdown(f"Floating P&L: :red[**{rupiah(pnl)} ({pnl_pct:.2f}%)**]")

                with st.expander(f"⚙️ Kelola Posisi {item['ticker']}"):
                    col_e1, col_e2 = st.columns(2)
                    e_lots = col_e1.number_input("Edit Lot", min_value=1, value=int(item['lots']), key=f"el_{idx}")
                    e_avg = col_e2.number_input("Edit Avg", min_value=1, value=int(item['avg']), key=f"ea_{idx}")
                    
                    c_b1, c_b2 = st.columns(2)
                    if c_b1.button("💾 Simpan Perubahan", key=f"sb_{idx}"):
                        st.session_state.portfolio[idx]['lots'] = e_lots
                        st.session_state.portfolio[idx]['avg'] = e_avg
                        st.rerun()
                    if c_b2.button("🗑️ Hapus Posisi", key=f"db_{idx}"):
                        st.session_state.portfolio.pop(idx)
                        st.rerun()
                st.markdown("---")

        pf1, pf2 = st.columns(2)
        pf1.metric("Total Modal Terikat", rupiah(tot_modal))
        pf2.metric("Total Floating P&L", rupiah(tot_floating), f"{(tot_floating/tot_modal)*100:+.2f}%" if tot_modal > 0 else "0%")

# ----------------------------------------------------------
# TAB 3 & 4: JOURNAL & RISK LIMITS
# ----------------------------------------------------------
with tab_journal:
    st.subheader("Jurnal Transaksi Realized P&L")
    st.info("Catatan eksekusi jual/beli posisi disimpan di sini.")

with tab_risk:
    st.subheader("Aturan Batas Risiko Modal (Risk Limits)")
    cap_rdn = st.number_input("Total Modal RDN (Rp)", value=10000000, step=500000)
    risk_tol = st.slider("Maksimal Toleransi Kerugian per Trade (%)", 1.0, 5.0, 2.0)
    max_loss_allowed = cap_rdn * (risk_tol / 100)
    st.warning(f"💡 Batas kerugian maksimum per transaksi yang diizinkan sistem: **{rupiah(max_loss_allowed)}**.")
