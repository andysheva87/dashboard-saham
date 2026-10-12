import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import json

# ==========================================================
# KONFIGURASI APLIKASI & MOBILE UI STYLING
# ==========================================================
st.set_page_config(
    page_title="V5 Mobile Swing Hunter Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 0.8rem; padding-right: 0.8rem; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    .stTable, .stDataFrame { font-size: 0.8rem !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 V5 Mobile Swing Hunter Pro")
st.caption("Swing scanner • Portfolio Advisor • Buy/Sell • Trading Journal • Risk Limits • Equity & Drawdown • Backup")

# ==========================================================
# INITIALIZE SESSION STATES
# ==========================================================
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {'ticker': 'BBNI', 'lots': 9, 'avg': 3688},
        {'ticker': 'TLKM', 'lots': 9, 'avg': 2850}
    ]

if 'journal' not in st.session_state:
    st.session_state.journal = []

if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ['BBRI', 'BBNI', 'BMRI', 'BBCA', 'TLKM', 'ASII', 'ITMG', 'BDMN', 'SMGR', 'PGAS']

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def rupiah(val):
    if val is None or pd.isna(val): return "N/A"
    return f"Rp {val:,.0f}"

@st.cache_data(ttl=120)
def load_stock(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo", interval="1d", auto_adjust=False)
        if df.empty: return pd.DataFrame(), {}, "Data kosong"
        try: info = ticker.info
        except: info = {}
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
    except: pass
    return "UNKNOWN", 0, 0, 0

def calculate_indicators(df):
    data = df.copy()
    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]

    data["MA20"] = close.rolling(20).mean()
    data["MA50"] = close.rolling(50).mean()
    
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    data["RSI14"] = (100 - (100 / (1 + rs))).fillna(50)

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    data["ATR14"] = tr.rolling(14).mean()

    data["VolumeMA20"] = volume.rolling(20).mean()
    data["VolRatio"] = (volume / data["VolumeMA20"].replace(0, np.nan)).fillna(1.0)

    data["Support20"] = low.rolling(20).min().shift(1)
    data["Resistance20"] = high.rolling(20).max().shift(1)

    return data

# ==========================================================
# 8 MAIN NAVIGATION TABS
# ==========================================================
tab_hunter, tab_portfolio, tab_buysell, tab_journal, tab_analyzer, tab_risk, tab_equity, tab_backup = st.tabs([
    "🎯 Hunter", "💼 Portfolio", "🔄 Buy / Sell", "📜 Journal", "🔎 Analyzer", "🛡️ Risk", "📉 Equity", "💾 Backup"
])

# ----------------------------------------------------------
# TAB 1: HUNTER (SWING SCANNER)
# ----------------------------------------------------------
with tab_hunter:
    ihsg_stat, ihsg_p, ihsg_ma20, ihsg_ma50 = get_ihsg_status()
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with st.container():
        if ihsg_stat == "BEARISH":
            st.error(f"### IHSG 🔴 BEARISH\nHarga: {rupiah(ihsg_p)} · MA20: {rupiah(ihsg_ma20)} · MA50: {rupiah(ihsg_ma50)}")
        else:
            st.success(f"### IHSG 🟢 BULLISH\nHarga: {rupiah(ihsg_p)} · MA20: {rupiah(ihsg_ma20)} · MA50: {rupiah(ihsg_ma50)}")
        st.caption(f"Yahoo Finance; harga dapat tertunda. Update data realtime: **{current_time_str}**")

    st.markdown("---")
    st.markdown("#### Parameter Pemindaian")
    
    col_f1, col_f2, col_f3 = st.columns(3)
    min_score = col_f1.slider("Skor Minimum", 0, 100, 50)
    target_min = col_f2.slider("Target Minimum (%)", 1, 15, 3)
    min_rr = col_f3.slider("R:R Minimum", 1.0, 5.0, 2.0, step=0.25)

    if st.button("🚀 Scan Saham Watchlist", use_container_width=True):
        results = []
        for ticker in st.session_state.watchlist:
            df_s, info_s, err = load_stock(f"{ticker}.JK")
            if not err and not df_s.empty:
                df_s = calculate_indicators(df_s)
                last = df_s.iloc[-1]
                price = float(last["Close"])
                atr = float(last["ATR14"]) if pd.notna(last["ATR14"]) else price * 0.03
                support = float(last["Support20"]) if pd.notna(last["Support20"]) else price - atr
                resistance = float(last["Resistance20"]) if pd.notna(last["Resistance20"]) else price + (atr * 2)

                sl = min(support - (atr * 0.25), price - (atr * 1.2))
                tp = max(resistance, price + ((price - sl) * 2))
                
                risk_pct = ((price - sl) / price) * 100
                gain_pct = ((tp - price) / price) * 100
                rr_ratio = gain_pct / risk_pct if risk_pct > 0 else 0

                score = 50
                if price > float(last["MA20"]): score += 15
                if float(last["VolRatio"]) >= 1.2: score += 15
                if 30 <= float(last["RSI14"]) <= 55: score += 20

                if score >= min_score and gain_pct >= target_min and rr_ratio >= min_rr:
                    signal = "🟢 BUY" if score >= 70 else "🟡 WATCH"
                    results.append({
                        'Kode': ticker, 'Sinyal': signal, 'Skor': score,
                        'Harga': price, 'Potensi TP1 (%)': round(gain_pct, 2),
                        'R:R': round(rr_ratio, 2), 'RSI': round(float(last["RSI14"]), 1),
                        'Vol/MA20': round(float(last["VolRatio"]), 2)
                    })

        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        else:
            st.warning("Scan terakhir tidak menghasilkan setup yang lolos filter. Coba turunkan slider parameter.")

# ----------------------------------------------------------
# TAB 2: PORTFOLIO ADVISOR
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
        st.info("Portofolio kosong.")
    else:
        tot_modal = 0
        tot_floating = 0

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
# TAB 3: BUY / SELL EXECUTIONS
# ----------------------------------------------------------
with tab_buysell:
    st.subheader("Eksekusi & Catat Transaksi")
    if not st.session_state.portfolio:
        st.info("Tidak ada posisi portofolio yang dapat dijual.")
    else:
        sel_idx = st.selectbox("Pilih Saham yang Hendak Dijual", range(len(st.session_state.portfolio)), format_func=lambda x: st.session_state.portfolio[x]['ticker'])
        target_item = st.session_state.portfolio[sel_idx]
        
        df_target, _, _ = load_stock(f"{target_item['ticker']}.JK")
        def_price = float(df_target["Close"].iloc[-1]) if not df_target.empty else target_item['avg']
        
        sell_price = st.number_input("Harga Jual Eksekusi (Rp)", value=int(def_price))
        sell_lots = st.number_input("Jumlah Lot yang Dijual", min_value=1, max_value=int(target_item['lots']), value=int(target_item['lots']))
        
        if st.button("🔴 Eksekusi Penjualan"):
            cost_sold = sell_lots * 100 * target_item['avg']
            revenue = sell_lots * 100 * sell_price
            realized_pnl = revenue - cost_sold
            
            # Catat ke Jurnal
            st.session_state.journal.append({
                'Tanggal': datetime.now().strftime("%Y-%m-%d"),
                'Kode': target_item['ticker'],
                'Lot': sell_lots,
                'Avg Beli': target_item['avg'],
                'Harga Jual': sell_price,
                'Realized P&L': realized_pnl,
                'Status': 'TAKE PROFIT' if realized_pnl >= 0 else 'CUT LOSS'
            })
            
            # Update Lot Portofolio
            if sell_lots == target_item['lots']:
                st.session_state.portfolio.pop(sel_idx)
            else:
                target_item['lots'] -= sell_lots
                
            st.success(f"Berhasil mengoperasikan penjualan {target_item['ticker']}!")
            st.rerun()

# ----------------------------------------------------------
# TAB 4: TRADING JOURNAL
# ----------------------------------------------------------
with tab_journal:
    st.subheader("📜 Jurnal Realized P&L")
    if not st.session_state.journal:
        st.info("Belum ada riwayat transaksi yang ditutup.")
    else:
        df_j = pd.DataFrame(st.session_state.journal)
        st.dataframe(df_j, use_container_width=True, hide_index=True)
        tot_realized = sum([x['Realized P&L'] for x in st.session_state.journal])
        st.metric("Total Realized P&L Kumulatif", rupiah(tot_realized))

# ----------------------------------------------------------
# TAB 5: ANALYZER (DEEP DIVE)
# ----------------------------------------------------------
with tab_analyzer:
    st.subheader("🔎 Deep Dive Stock Analyzer")
    an_ticker = st.text_input("Masukkan Kode Saham Analisis", "TLKM").upper().strip()
    if st.button("Analisis Saham Ini"):
        df_an, info_an, err_an = load_stock(f"{an_ticker}.JK")
        if not err_an and not df_an.empty:
            df_an = calculate_indicators(df_an)
            last_an = df_an.iloc[-1]
            
            st.write(f"**Harga Terakhir:** {rupiah(last_an['Close'])}")
            st.write(f"**MA20:** {rupiah(last_an['MA20'])} | **MA50:** {rupiah(last_an['MA50'])}")
            st.write(f"**RSI Momentum:** {last_an['RSI14']:.1f}")
            st.write(f"**PER:** {info_an.get('trailingPE', 'N/A')} | **PBV:** {info_an.get('priceToBook', 'N/A')}")
            st.line_chart(df_an['Close'].tail(60))

# ----------------------------------------------------------
# TAB 6: RISK LIMITS & POSITION SIZING
# ----------------------------------------------------------
with tab_risk:
    st.subheader("🛡️ Risk Limits & Money Management")
    total_rdn = st.number_input("Total Modal RDN (Rp)", value=10000000, step=500000)
    risk_pct_input = st.slider("Toleransi Kerugian Maksimal (%)", 1.0, 5.0, 2.0)
    
    max_risk_rp = total_rdn * (risk_pct_input / 100)
    st.warning(f"💡 Batas Toleransi Kerugian per Trade: **{rupiah(max_risk_rp)}**")

# ----------------------------------------------------------
# TAB 7: EQUITY & DRAWDOWN
# ----------------------------------------------------------
with tab_equity:
    st.subheader("📉 Pertumbuhan Ekuitas & Drawdown")
    st.caption("Grafik ini melacak akumulasi modal dari hasil realized P&L transaksi.")
    if st.session_state.journal:
        df_eq = pd.DataFrame(st.session_state.journal)
        df_eq['Cumulative_PnL'] = df_eq['Realized P&L'].cumsum()
        st.line_chart(df_eq['Cumulative_PnL'])
    else:
        st.info("Belum ada data ekuitas dari transaksi tertutup.")

# ----------------------------------------------------------
# TAB 8: BACKUP & RESTORE DATA
# ----------------------------------------------------------
with tab_backup:
    st.subheader("💾 Backup & Restore State Data")
    
    backup_data = {
        'portfolio': st.session_state.portfolio,
        'journal': st.session_state.journal,
        'watchlist': st.session_state.watchlist
    }
    
    json_str = json.dumps(backup_data, indent=4)
    st.download_button("📥 Download Backup JSON", data=json_str, file_name=f"backup_swing_hunter_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json")
