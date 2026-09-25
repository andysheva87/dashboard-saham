import streamlit as st
import yfinance as yf
import pandas as pd

# CONFIG TAMPILAN DASHBOARD OPTIMIZED FOR MOBILE
st.set_page_config(page_title="Terminal Saham Mobile Pro", layout="wide", initial_sidebar_state="collapsed")

# CSS KHUSUS MOBILE UI
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 0.8rem; padding-right: 0.8rem; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    .stTable { font-size: 0.8rem !important; }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Terminal Saham Pro")
st.caption("Pre-Buy Audit (Div Yield & MA50 Included) & Jurnal Portofolio")

# STATE MEMORI APLIKASI
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {'ticker': 'BBNI', 'lots': 5, 'avg': 3718, 'current': 3660},
        {'ticker': 'TLKM', 'lots': 9, 'avg': 2850, 'current': 2580}
    ]

if 'realized' not in st.session_state:
    st.session_state.realized = []

# DETEKSI TREN IHSG OTOMATIS
@st.cache_data(ttl=300)
def get_market_status():
    try:
        ihsg = yf.Ticker("^JKSE")
        df_ihsg = ihsg.history(period="3mo")
        if not df_ihsg.empty:
            last_ihsg = float(df_ihsg['Close'].iloc[-1])
            ma20_ihsg = float(df_ihsg['Close'].rolling(20).mean().iloc[-1])
            prev_ihsg = float(df_ihsg['Close'].iloc[-5])
            diff_pct = ((last_ihsg - prev_ihsg) / prev_ihsg) * 100
            
            if last_ihsg < ma20_ihsg or diff_pct < -1.0:
                return "Bearish / Pressure Asing", last_ihsg, ma20_ihsg
            elif last_ihsg > ma20_ihsg and diff_pct > 1.0:
                return "Bullish / Uptrend", last_ihsg, ma20_ihsg
            else:
                return "Sideways / Konsolidasi", last_ihsg, ma20_ihsg
    except:
        pass
    return "Sideways / Konsolidasi", 0, 0

auto_market_trend, ihsg_price, ihsg_ma20 = get_market_status()

# NAVIGASI UTAMA
menu = st.selectbox("📌 PILIH MENU", [
    "🔍 Pre-Buy Audit & Analisis Saham", 
    "💼 Portfolio Monitoring (Floating P&L)", 
    "📜 Riwayat Transaksi (Realized P&L)"
])

st.info(f"🌐 **Pasar Realtime (IHSG):** {auto_market_trend}")

# =========================================================
# MENU 1: PRE-BUY AUDIT & ANALISIS SAHAM
# =========================================================
if menu == "🔍 Pre-Buy Audit & Analisis Saham":
    st.subheader("1. Pre-Buy Audit Saham")
    
    col_a, col_b = st.columns(2)
    ticker_input = col_a.text_input("Kode Saham", "BBRI").upper()
    entry_price = col_b.number_input("Harga Entry (Rp)", value=3180, step=10)
    
    col_c, col_d = st.columns(2)
    tp_price = col_c.number_input("Target Price (Rp)", value=3300, step=10)
    sl_price = col_d.number_input("Cut Loss (Rp)", value=3100, step=10)

    ticker_idx = f"{ticker_input}.JK"

    @st.cache_data(ttl=60)
    def load_stock_data(symbol):
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            info = stock.info
            return df, info
        except:
            return None, None

    df, info = load_stock_data(ticker_idx)

    if df is None or df.empty:
        st.error(f"Data {ticker_input} tidak ditemukan!")
    else:
        last_price = float(df['Close'].iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
        
        # Ambil data rasio dengan penanganan N/A
        pbv_raw = info.get('priceToBook')
        per_raw = info.get('trailingPE')
        pbv = float(pbv_raw) if pbv_raw is not None else 0.0
        per = float(per_raw) if per_raw is not None else 0.0
        
        # Kalkulasi Dividend Yield Akurat
        div_rate = info.get('dividendRate')
        raw_yield = info.get('dividendYield')
        
        if div_rate and div_rate > 0:
            div_yield_pct = (div_rate / last_price) * 100
        elif raw_yield and raw_yield > 0:
            div_yield_pct = raw_yield * 100 if raw_yield < 1.0 else (raw_yield / last_price) * 100
        else:
            div_yield_pct = 0.0

        # HITUNG RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        st.markdown("---")
        st.markdown("#### 📊 Indikator Utama & Valuasi")
        
        # METRIK TAMPILAN HP
        m1, m2 = st.columns(2)
        m1.metric("Harga Terakhir", f"Rp {last_price:,.0f}")
        m2.metric("Dividend Yield", f"{div_yield_pct:.2f}%" if div_yield_pct > 0 else "N/A (Pending)")

        m3, m4 = st.columns(2)
        m3.metric("Support MA20", f"Rp {ma20:,.0f}")
        m4.metric("Support MA50", f"Rp {ma50:,.0f}")

        m5, m6 = st.columns(2)
        m5.metric("PBV", f"{pbv:.2f}x" if pbv > 0 else "N/A")
        m6.metric("PER", f"{per:.2f}x" if per > 0 else "N/A")
        
        rsi_status = "Netral"
        if rsi < 35: rsi_status = "Oversold"
        elif rsi > 70: rsi_status = "Overbought"
        st.metric("RSI Momentum", f"{rsi:.1f}", rsi_status)

        # TREN HARI MINGGUAN
        with st.expander("📈 Tren Harga 1 Minggu Kebelakang"):
            df_1w = df.tail(5).copy()
            df_1w['Tanggal'] = df_1w.index.strftime('%m-%d')
            df_1w['Chg (%)'] = ((df_1w['Close'] - df_1w['Open']) / df_1w['Open']) * 100
            df_display = df_1w[['Tanggal', 'Close', 'Chg (%)']]
            st.dataframe(df_display.sort_values(by='Tanggal', ascending=False), use_container_width=True)

        # MONEY MANAGEMENT
        st.markdown("---")
        st.markdown("#### 🎯 Money Management (Lot Max)")
        total_rdn = st.number_input("Modal RDN (Rp)", value=10000000, step=500000)
        risk_pct_max = st.slider("Toleransi Risiko (%)", 1.0, 5.0, 2.0)

        risk_per_share = entry_price - sl_price
        if risk_per_share > 0:
            max_loss_rp = total_rdn * (risk_pct_max / 100)
            max_shares = max_loss_rp / risk_per_share
            max_lots = int(max_shares / 100)
            total_buy_val = max_lots * 100 * entry_price

            st.success(f"💡 Max Beli: **{max_lots} Lot** (Total: Rp {total_buy_val:,.0f})")
        else:
            st.warning("Stop Loss harus lebih kecil dari Entry!")

        # CHECKLIST AUDIT OTOMATIS (SMART PROTEKSI)
        st.markdown("---")
        st.markdown("#### 📋 Pre-Buy Checklist")

        is_bigcap = ticker_input in ['BBRI', 'BBNI', 'BMRI', 'BBCA', 'TLKM', 'ASII', 'PGAS', 'JPFA']

        chk_fundamental = True if (0 < per < 15) or (per == 0 and is_bigcap) else False
        chk_valuasi = True if (0 < pbv <= 1.5) or (pbv == 0 and is_bigcap) else False
        chk_dividen = True if (div_yield_pct >= 3.0) or (div_yield_pct == 0 and is_bigcap) else False
        chk_trend_ma50 = True if last_price >= (ma50 * 0.98) else False
        chk_entry_ma20 = True if entry_price <= (ma20 * 1.03) else False
        chk_target = True if tp_price > entry_price else False
        chk_sl = True if sl_price < entry_price else False

        checklist_items = [
            ("Fundamental PER < 15x", chk_fundamental),
            ("Valuasi PBV <= 1.5x", chk_valuasi),
            ("Dividend Yield Menarik (>= 3%)", chk_dividen),
            ("Tren Sehat (Harga di atas MA50)", chk_trend_ma50),
            ("Entry Dekat Support MA20", chk_entry_ma20),
            ("Target Price Realistis", chk_target),
            ("Stop Loss Terpasang", chk_sl)
        ]

        for item, status in checklist_items:
            st.write(f"{'✅' if status else '❌'} {item}")

        total_score = sum([chk_fundamental, chk_valuasi, chk_dividen, chk_trend_ma50, chk_entry_ma20, chk_target, chk_sl])
        gain_pct = ((tp_price - entry_price) / entry_price) * 100
        risk_pct = ((entry_price - sl_price) / entry_price) * 100
        rrr = gain_pct / risk_pct if risk_pct > 0 else 0

        st.markdown("---")
        st.write(f"**Gain:** :green[+{gain_pct:.2f}%] | **Risk:** :red[-{risk_pct:.2f}%]")
        st.write(f"**RRR:** **1 : {rrr:.2f}** | **Skor:** **{total_score}/7**")

        if total_score < 4:
            st.error("🚨 REJECT: Skor di bawah 4/7.")
        elif rrr < 1.5:
            st.warning(f"⚠️ WAIT & SEE: RRR (1:{rrr:.2f}) terlalu kecil.")
        else:
            if auto_market_trend == "Bearish / Pressure Asing" and rrr < 3.0:
                st.warning(f"⚠️ WAIT & SEE: Pasar Bearish. Butuh RRR >= 1:3.0.")
            else:
                st.success(f"🎉 APPROVED / LAYAK BUY!")


# =========================================================
# MENU 2: PORTFOLIO MONITORING (FLOATING P&L)
# =========================================================
# =========================================================
# MENU 2: PORTFOLIO MONITORING (FLOATING P&L REALTIME)
# =========================================================
elif menu == "💼 Portfolio Monitoring (Floating P&L)":
    st.subheader("2. Portofolio Aktif (Realtime Market Price)")

    with st.expander("➕ Tambah Posisi Saham Baru"):
        new_ticker = st.text_input("Kode Saham", "ASII").upper()
        new_lots = st.number_input("Jumlah Lot", min_value=1, value=10)
        new_avg = st.number_input("Harga Beli / Average (Rp)", min_value=1, value=5000)
        if st.button("Simpan Posisi"):
            st.session_state.portfolio.append({
                'ticker': new_ticker, 'lots': new_lots, 'avg': new_avg
            })
            st.success("Posisi berhasil ditambahkan!")
            st.rerun()

    if not st.session_state.portfolio:
        st.info("Portofolio kosong.")
    else:
        tot_modal = 0
        tot_floating = 0

        st.markdown("---")
        for item in st.session_state.portfolio:
            ticker_idx = f"{item['ticker']}.JK"
            
            # TARIK HARGA TERAKHIR REALTIME DARI YAHOO FINANCE
            try:
                stock_data = yf.Ticker(ticker_idx)
                hist = stock_data.history(period="1d")
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
                else:
                    current_price = item.get('current', item['avg'])
            except:
                current_price = item.get('current', item['avg'])

            modal = item['lots'] * 100 * item['avg']
            val_current = item['lots'] * 100 * current_price
            float_rp = val_current - modal
            float_pct = (float_rp / modal) * 100 if modal > 0 else 0

            tot_modal += modal
            tot_floating += float_rp

            # TAMPILAN KARTU PORTOFOLIO DENGAN HARGA REALTIME
            with st.container():
                st.markdown(f"### {item['ticker']} ({item['lots']} Lot)")
                st.write(f"Avg: **Rp {item['avg']:,.0f}** | Market Now: **Rp {current_price:,.0f}**")
                
                if float_rp >= 0:
                    st.markdown(f"Floating P&L: :green[**+Rp {float_rp:,.0f} (+{float_pct:.2f}%)**]")
                else:
                    st.markdown(f"Floating P&L: :red[**Rp {float_rp:,.0f} ({float_pct:.2f}%)**]")
                st.markdown("---")

        c1, c2 = st.columns(2)
        c1.metric("Modal Aktif", f"Rp {tot_modal:,.0f}")
        c2.metric("Total Floating P&L", f"Rp {tot_floating:,.0f}", f"{(tot_floating/tot_modal)*100:.2f}%" if tot_modal > 0 else "0%")

        st.markdown("---")
        st.subheader("Eksekusi Jual / Close Position")
        selected_idx = st.selectbox("Pilih Saham", range(len(st.session_state.portfolio)), format_func=lambda x: st.session_state.portfolio[x]['ticker'])
        
        # Ambil harga realtime saham yang dipilih untuk harga acuan jual
        selected_item = st.session_state.portfolio[selected_idx]
        try:
            default_sell = float(yf.Ticker(f"{selected_item['ticker']}.JK").history(period="1d")['Close'].iloc[-1])
        except:
            default_sell = selected_item['avg']

        sell_price = st.number_input("Harga Jual Eksekusi (Rp)", value=int(default_sell))
        
        if st.button("Jual & Catat Realized P&L"):
            item_sold = st.session_state.portfolio.pop(selected_idx)
            modal_sold = item_sold['lots'] * 100 * item_sold['avg']
            realized_rp = (item_sold['lots'] * 100 * sell_price) - modal_sold

            st.session_state.realized.append({
                'ticker': item_sold['ticker'], 'lots': item_sold['lots'], 'avg': item_sold['avg'],
                'sell_price': sell_price, 'realized_rp': realized_rp,
                'status': 'TAKE PROFIT' if realized_rp >= 0 else 'CUT LOSS'
            })
            st.success(f"Posisi {item_sold['ticker']} Berhasil Ditutup!")
            st.rerun()
# =========================================================
# MENU 3: RIWAYAT TRANSAKSI (REALIZED P&L)
# =========================================================
elif menu == "📜 Riwayat Transaksi (Realized P&L)":
    st.subheader("3. Jurnal Realized P&L")

    if not st.session_state.realized:
        st.info("Belum ada riwayat transaksi ditutup.")
    else:
        tot_realized = sum([x['realized_rp'] for x in st.session_state.realized])
        st.metric("Total Realized P&L", f"Rp {tot_realized:,.0f}")

        for x in st.session_state.realized:
            st.markdown(f"**{x['ticker']}** ({x['lots']} Lot) - **{x['status']}**")
            st.write(f"Beli: Rp {x['avg']:,.0f} | Jual: Rp {x['sell_price']:,.0f}")
            st.write(f"Gain/Loss: **Rp {x['realized_rp']:,.0f}**")
            st.markdown("---")
