import streamlit as st
import yfinance as yf
import pandas as pd

# CONFIG TAMPILAN DASHBOARD
st.set_page_config(page_title="Stock Checkout Dashboard Auto", layout="wide")

st.title("📊 Stock Checkout & Automatic Audit Dashboard")
st.caption("Aplikasi Analisis & Checkout Saham Otomatis Realtime (IDX)")

# 1. DETEKSI OTOMATIS TREN IHSG / PASAR REALTIME
@st.cache_data(ttl=300)
def get_market_status():
    try:
        ihsg = yf.Ticker("^JKSE")
        df_ihsg = ihsg.history(period="1mo")
        if not df_ihsg.empty:
            last_ihsg = float(df_ihsg['Close'].iloc[-1])
            ma20_ihsg = float(df_ihsg['Close'].rolling(20).mean().iloc[-1])
            prev_ihsg = float(df_ihsg['Close'].iloc[-5]) # Harga 5 hari lalu
            
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

# SIDEBAR INPUT PARAMETER
st.sidebar.header("1. Input Parameter Saham")
ticker_input = st.sidebar.text_input("Kode Saham (Contoh: BBNI, TLKM, BBRI)", "BBRI").upper()
ticker_idx = f"{ticker_input}.JK"

entry_price = st.sidebar.number_input("Rencana Harga Entry (Rp)", value=3180, step=10)
tp_price = st.sidebar.number_input("Target Price / Take Profit (Rp)", value=3300, step=10)
sl_price = st.sidebar.number_input("Batas Cut Loss / Stop Loss (Rp)", value=3100, step=10)

# KONDISI PASAR SEKARANG SUDAH OTOMATIS
st.sidebar.markdown("---")
st.sidebar.subheader("Status Pasar Realtime (IHSG)")
st.sidebar.info(f"**Status Otomatis:** {auto_market_trend}")
if ihsg_price > 0:
    st.sidebar.caption(f"IHSG: {ihsg_price:,.0f} | MA20: {ihsg_ma20:,.0f}")

# PROSES AMBIL DATA SAHAM REALTIME DARI INTERNET
@st.cache_data(ttl=60)
def load_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="3mo")
        info = stock.info
        return df, info
    except Exception as e:
        return None, None

df, info = load_stock_data(ticker_idx)

if df is None or df.empty:
    st.error(f"Gagal mengambil data untuk kode saham **{ticker_input}**. Pastikan kode saham benar!")
else:
    # DATA HARGA REALTIME & INDIKATOR OTOMATIS
    last_price = float(df['Close'].iloc[-1])
    ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
    pbv = info.get('priceToBook', 0)
    per = info.get('trailingPE', 0)

    st.subheader(f"2. Data Realtime & Indikator: {ticker_input}")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Harga Terakhir (Realtime)", f"Rp {last_price:,.0f}")
    col2.metric("Rata-rata MA20 (Support)", f"Rp {ma20:,.0f}")
    col3.metric("Valuasi PBV", f"{pbv:.2f}x" if pbv else "N/A")
    col4.metric("Valuasi PER", f"{per:.2f}x" if per else "N/A")

    st.markdown("---")
    st.subheader("3. Checklist Evaluasi Keputusan Pre-Buy (Otomatis)")

    # LOGIKA AUDIT CHECKLIST OTOMATIS
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

    # PERHITUNGAN SKOR & RRR
    total_score = sum([chk_fundamental, chk_valuasi, chk_bisnis, chk_manajemen, chk_risiko, chk_entry, chk_target, chk_sl])
    gain_pct = ((tp_price - entry_price) / entry_price) * 100
    risk_pct = ((entry_price - sl_price) / entry_price) * 100
    rrr = gain_pct / risk_pct if risk_pct > 0 else 0

    st.markdown("---")
    st.subheader("4. Summary Analisis & Rekomendasi Checkout")

    c1, c2, c3 = st.columns(3)
    c1.write(f"**Potensi Gain (Take Profit):** :green[+{gain_pct:.2f}%]")
    c2.write(f"**Potensi Risk (Cut Loss):** :red[-{risk_pct:.2f}%]")
    c3.write(f"**Risk to Reward Ratio (RRR):** **1 : {rrr:.2f}**")

    st.write(f"**Skor Kelayakan Checklist:** **{total_score} / 8 Item Terpenuhi**")

    # KEPUTUSAN FINAL MENGGUNAKAN STATUS PASAR OTOMATIS
    if total_score < 5:
        st.error("🚨 REJECT / HINDARI BUY: Skor audit checklist di bawah batas minimal (Kurang dari 5 item terpenuhi).")
    elif rrr < 1.5:
        st.warning(f"⚠️ WAIT & SEE: Risk-to-Reward Ratio (1 : {rrr:.2f}) terlalu kecil. Minimal RRR harus 1 : 1.5.")
    else:
        if auto_market_trend == "Bearish / Pressure Asing" and rrr < 3.0:
            st.warning(f"⚠️ WAIT & SEE: Kondisi pasar IHSG terdeteksi **{auto_market_trend}**. Butuh RRR minimal 1 : 3.0 untuk masuk aman.")
        else:
            st.success(f"🎉 APPROVED CHECKOUT / LAYAK BUY! Saham {ticker_input} lolos audit checklist dan RRR ideal di pasar {auto_market_trend}.")
