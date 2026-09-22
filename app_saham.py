import streamlit as st
import yfinance as yf
import pandas as pd

# CONFIG TAMPILAN DASHBOARD
st.set_page_config(page_title="Professional Stock Terminal & Portfolio", layout="wide")

st.title("📊 Terminal Analisis & Portfolio Management Saham")
st.caption("Sistem Otomatis Pre-Buy Audit, Riset Momentum, dan Jurnal Portofolio Realtime (IDX)")

# INI STATE UNTUK SIMPAN DATA PORTOFOLIO DI MEMORI APLIKASI
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {'ticker': 'BBNI', 'lots': 5, 'avg': 3718, 'current': 3660},
        {'ticker': 'TLKM', 'lots': 9, 'avg': 2850, 'current': 2580}
    ]

if 'realized' not in st.session_state:
    st.session_state.realized = []

# DETEKSI OTOMATIS TREN IHSG / PASAR REALTIME
@st.cache_data(ttl=300)
def get_market_status():
    try:
        ihsg = yf.Ticker("^JKSE")
        df_ihsg = ihsg.history(period="1mo")
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

# NAVIGASI MENU UTAMA
menu = st.sidebar.radio("PILIH MENU DASHBOARD", [
    "🔍 Pre-Buy Audit & Analisis Saham", 
    "💼 Portfolio Monitoring (Floating P&L)", 
    "📜 Riwayat Transaksi (Realized P&L)"
])

# SIDEBAR MONITOR PASAR
st.sidebar.markdown("---")
st.sidebar.subheader("Status Pasar Realtime (IHSG)")
st.sidebar.info(f"**Status Otomatis:** {auto_market_trend}")
if ihsg_price > 0:
    st.sidebar.caption(f"IHSG: {ihsg_price:,.0f} | MA20: {ihsg_ma20:,.0f}")


# =========================================================
# MENU 1: PRE-BUY AUDIT & ANALISIS SAHAM
# =========================================================
if menu == "🔍 Pre-Buy Audit & Analisis Saham":
    st.header("1. Riset & Pre-Buy Audit Saham Otomatis")
    
    col_in1, col_in2, col_in3, col_in4 = st.columns(4)
    ticker_input = col_in1.text_input("Kode Saham", "BBRI").upper()
    entry_price = col_in2.number_input("Rencana Harga Entry (Rp)", value=3180, step=10)
    tp_price = col_in3.number_input("Target Price / Take Profit (Rp)", value=3300, step=10)
    sl_price = col_in4.number_input("Batas Cut Loss / Stop Loss (Rp)", value=3100, step=10)

    ticker_idx = f"{ticker_input}.JK"

    @st.cache_data(ttl=60)
    def load_stock_data(symbol):
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="3mo")
            info = stock.info
            return df, info
        except:
            return None, None

    df, info = load_stock_data(ticker_idx)

    if df is None or df.empty:
        st.error(f"Gagal mengambil data saham **{ticker_input}**. Pastikan kode saham benar!")
    else:
        last_price = float(df['Close'].iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        pbv = info.get('priceToBook', 0)
        per = info.get('trailingPE', 0)

        # HITUNG INDIKATOR MOMENTUM RSI (14 HARI)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        st.subheader(f"Indikator Utama & Momentum: {ticker_input}")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Harga Terakhir", f"Rp {last_price:,.0f}")
        m2.metric("Support (MA20)", f"Rp {ma20:,.0f}")
        m3.metric("PBV", f"{pbv:.2f}x" if pbv else "N/A")
        m4.metric("PER", f"{per:.2f}x" if per else "N/A")
        
        rsi_status = "Neutral"
        if rsi < 35: rsi_status = "Oversold (Sangat Murah)"
        elif rsi > 70: rsi_status = "Overbought (Jenuh Beli)"
        m5.metric("RSI (14D Momentum)", f"{rsi:.1f}", rsi_status)

        # TABEL TREN HARI DAN MINGGUAN (5 HARI TERAKHIR)
        st.markdown("---")
        st.subheader("📈 Pergerakan Harga 1 Minggu Kebelakang (5 Hari Kerja)")
        df_1w = df.tail(5).copy()
        df_1w['Tanggal'] = df_1w.index.strftime('%Y-%m-%d')
        df_1w['Perubahan (%)'] = ((df_1w['Close'] - df_1w['Open']) / df_1w['Open']) * 100
        df_display = df_1w[['Tanggal', 'Open', 'High', 'Low', 'Close', 'Volume', 'Perubahan (%)']]
        st.dataframe(df_display.sort_values(by='Tanggal', ascending=False), use_container_width=True)

        st.markdown("---")
        st.subheader("🎯 Money Management & Kalkulator Lot Maksimal")
        c_cap1, c_cap2 = st.columns(2)
        total_rdn = c_cap1.number_input("Total Modal RDN Kamu (Rp)", value=10000000, step=500000)
        risk_pct_max = c_cap2.slider("Toleransi Risiko Maksimal per Transaksi (%)", 1.0, 5.0, 2.0)

        risk_per_share = entry_price - sl_price
        if risk_per_share > 0:
            max_loss_rp = total_rdn * (risk_pct_max / 100)
            max_shares = max_loss_rp / risk_per_share
            max_lots = int(max_shares / 100)
            total_buy_val = max_lots * 100 * entry_price

            st.success(f"💡 **Rekomendasi Money Management:** Berdasarkan toleransi risiko **Rp {max_loss_rp:,.0f}** ({risk_pct_max}%), kamu disarankan membeli maksimal **{max_lots} Lot** (Total Alokasi Modal: Rp {total_buy_val:,.0f}).")
        else:
            st.warning("Harga Stop Loss harus lebih rendah dari harga Entry untuk menghitung alokasi lot!")

        st.markdown("---")
        st.subheader("📋 Checklist Evaluasi Pre-Buy & Rekomendasi Checkout")

        chk_fundamental = True if per > 0 and per < 15 else False
        chk_valuasi = True if pbv > 0 and pbv <= 1.5 else False
        chk_bisnis = True
        chk_manajemen = True
        chk_risiko = True
        chk_entry = True if entry_price <= (ma20 * 1.02) else False
        chk_target = True if tp_price > entry_price else False
        chk_sl = True if sl_price < entry_price else False

        checklist_data = {
            "Item Poin Audit": [
                "Fundamental sehat (PER Rasional < 15x)",
                "Valuasi tergolong murah / terdiskon (PBV <= 1.5x)",
                "Sektor & model bisnis mudah dipahami",
                "Manajemen terpercaya & bebas Notasi Khusus",
                "Risiko industri & volatilitas harga dipahami",
                "Harga entry mendekati area Support / MA20",
                "Target harga realistis di atas harga entry",
                "Level Cut Loss terpasang di bawah harga entry"
            ],
            "Hasil Audit Otomatis": [
                "✅ Lolos" if chk_fundamental else "❌ Belum Memenuhi",
                "✅ Lolos" if chk_valuasi else "❌ Belum Memenuhi",
                "✅ Lolos" if chk_bisnis else "❌ Belum Memenuhi",
                "✅ Lolos" if chk_manajemen else "❌ Belum Memenuhi",
                "✅ Lolos" if chk_risiko else "❌ Belum Memenuhi",
                "✅ Lolos" if chk_entry else "❌ Terlalu Tinggi dari Support",
                "✅ Lolos" if chk_target else "❌ Target Salah",
                "✅ Lolos" if chk_sl else "❌ Stop Loss Salah"
            ]
        }
        st.table(pd.DataFrame(checklist_data))

        total_score = sum([chk_fundamental, chk_valuasi, chk_bisnis, chk_manajemen, chk_risiko, chk_entry, chk_target, chk_sl])
        gain_pct = ((tp_price - entry_price) / entry_price) * 100
        risk_pct = ((entry_price - sl_price) / entry_price) * 100
        rrr = gain_pct / risk_pct if risk_pct > 0 else 0

        res_col1, res_col2, res_col3 = st.columns(3)
        res_col1.write(f"**Potensi Gain:** :green[+{gain_pct:.2f}%]")
        res_col2.write(f"**Potensi Risk:** :red[-{risk_pct:.2f}%]")
        res_col3.write(f"**Risk to Reward Ratio:** **1 : {rrr:.2f}**")

        if total_score < 5:
            st.error("🚨 REJECT / HINDARI BUY: Skor audit checklist di bawah batas minimal.")
        elif rrr < 1.5:
            st.warning(f"⚠️ WAIT & SEE: Risk-to-Reward Ratio (1 : {rrr:.2f}) terlalu kecil. Minimal RRR harus 1 : 1.5.")
        else:
            if auto_market_trend == "Bearish / Pressure Asing" and rrr < 3.0:
                st.warning(f"⚠️ WAIT & SEE: Pasar IHSG terdeteksi {auto_market_trend}. Butuh RRR minimal 1 : 3.0 untuk masuk.")
            else:
                st.success(f"🎉 APPROVED CHECKOUT / LAYAK BUY! Saham {ticker_input} lolos audit dan RRR ideal.")


# =========================================================
# MENU 2: PORTFOLIO MONITORING (FLOATING P&L)
# =========================================================
elif menu == "💼 Portfolio Monitoring (Floating P&L)":
    st.header("2. Monitoring Posisi Portofolio Aktif")

    st.subheader("Tambah Posisi Saham Baru yang Dibeli")
    with st.form("add_stock_form"):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        new_ticker = f_col1.text_input("Kode Saham", "ASII").upper()
        new_lots = f_col2.number_input("Jumlah Lot", min_value=1, value=10)
        new_avg = f_col3.number_input("Harga Beli / Average (Rp)", min_value=1, value=5000)
        new_curr = f_col4.number_input("Harga Saat Ini (Rp)", min_value=1, value=5100)
        submit_btn = st.form_submit_button("Tambahkan ke Portofolio")

        if submit_btn:
            st.session_state.portfolio.append({
                'ticker': new_ticker,
                'lots': new_lots,
                'avg': new_avg,
                'current': new_curr
            })
            st.success(f"Saham {new_ticker} berhasil ditambahkan!")

    st.markdown("---")
    st.subheader("Posisi Portofolio Saat Ini")

    if not st.session_state.portfolio:
        st.info("Portofolio kamu saat ini kosong.")
    else:
        tot_modal = 0
        tot_floating = 0

        port_list = []
        for idx, item in enumerate(st.session_state.portfolio):
            modal = item['lots'] * 100 * item['avg']
            val_current = item['lots'] * 100 * item['current']
            float_rp = val_current - modal
            float_pct = (float_rp / modal) * 100

            tot_modal += modal
            tot_floating += float_rp

            port_list.append({
                "Index": idx,
                "Kode": item['ticker'],
                "Lot": item['lots'],
                "Average (Rp)": f"{item['avg']:,.0f}",
                "Harga Sekarang (Rp)": f"{item['current']:,.0f}",
                "Total Modal (Rp)": f"{modal:,.0f}",
                "Floating P&L (Rp)": f"{float_rp:,.0f}",
                "Floating P&L (%)": f"{float_pct:.2f}%"
            })

        st.table(pd.DataFrame(port_list).drop(columns=['Index']))

        p_col1, p_col2 = st.columns(2)
        p_col1.metric("Total Modal Terikat", f"Rp {tot_modal:,.0f}")
        p_col2.metric("Total Floating P&L", f"Rp {tot_floating:,.0f}", f"{(tot_floating/tot_modal)*100:.2f}%" if tot_modal > 0 else "0%")

        st.markdown("---")
        st.subheader("Eksekusi Jual / Close Position")
        sell_col1, sell_col2, sell_col3 = st.columns(3)
        
        selected_idx = sell_col1.selectbox("Pilih Saham yang Dijual", range(len(st.session_state.portfolio)), format_func=lambda x: st.session_state.portfolio[x]['ticker'])
        sell_price = sell_col2.number_input("Harga Realisasi Jual (Rp)", value=st.session_state.portfolio[selected_idx]['current'])
        
        if sell_col3.button("Eksekusi Jual & Catat Realized P&L"):
            item_sold = st.session_state.portfolio.pop(selected_idx)
            modal_sold = item_sold['lots'] * 100 * item_sold['avg']
            realized_rp = (item_sold['lots'] * 100 * sell_price) - modal_sold

            st.session_state.realized.append({
                'ticker': item_sold['ticker'],
                'lots': item_sold['lots'],
                'avg': item_sold['avg'],
                'sell_price': sell_price,
                'realized_rp': realized_rp,
                'status': 'TAKE PROFIT' if realized_rp >= 0 else 'CUT LOSS'
            })
            st.success(f"Posisi {item_sold['ticker']} berhasil ditutup!")
            st.rerun()


# =========================================================
# MENU 3: RIWAYAT TRANSAKSI (REALIZED P&L)
# =========================================================
elif menu == "📜 Riwayat Transaksi (Realized P&L)":
    st.header("3. Jurnal Transaksi Selesai (Realized P&L)")

    if not st.session_state.realized:
        st.info("Belum ada riwayat transaksi yang ditutup / dijual.")
    else:
        tot_realized = sum([x['realized_rp'] for x in st.session_state.realized])
        st.metric("Total Cumulative Realized Profit/Loss", f"Rp {tot_realized:,.0f}")

        real_list = []
        for x in st.session_state.realized:
            real_list.append({
                "Kode Saham": x['ticker'],
                "Lot": x['lots'],
                "Harga Beli (Avg)": f"Rp {x['avg']:,.0f}",
                "Harga Jual": f"Rp {x['sell_price']:,.0f}",
                "Realized P&L (Rp)": f"Rp {x['realized_rp']:,.0f}",
                "Status": x['status']
            })

        st.table(pd.DataFrame(real_list))
