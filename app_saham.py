import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ==========================================================
# STOCK TRADING DECISION DASHBOARD V2
# ==========================================================

st.set_page_config(
    page_title="Stock Trading Decision Dashboard V2",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Stock Trading Decision Dashboard V2")
st.caption(
    "Technical + Fundamental + Risk/Reward Dashboard untuk Swing Trading IDX"
)

# ==========================================================
# FORMAT
# ==========================================================

def rupiah(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"Rp {value:,.0f}"

def percent(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:+.2f}%"

# ==========================================================
# LOAD DATA
# ==========================================================

@st.cache_data(ttl=300)
def load_stock(symbol):

    try:

        ticker = yf.Ticker(symbol)

        df = ticker.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )

        try:
            info = ticker.info
        except Exception:
            info = {}

        return df, info, None

    except Exception as e:

        return pd.DataFrame(), {}, str(e)


# ==========================================================
# TECHNICAL INDICATORS
# ==========================================================

def calculate_indicators(df):

    data = df.copy()

    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]

    # MA
    data["MA20"] = close.rolling(20).mean()
    data["MA50"] = close.rolling(50).mean()
    data["MA200"] = close.rolling(200).mean()

    # RSI
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    data["RSI14"] = 100 - (
        100 / (1 + rs)
    )

    # MACD
    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    data["MACD"] = ema12 - ema26

    data["MACDSignal"] = data["MACD"].ewm(
        span=9,
        adjust=False
    ).mean()

    data["MACDHist"] = (
        data["MACD"]
        - data["MACDSignal"]
    )

    # ATR
    previous_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs()
        ],
        axis=1
    ).max(axis=1)

    data["ATR14"] = tr.rolling(14).mean()

    # Volume
    data["VolumeMA20"] = volume.rolling(20).mean()

    data["VolumeRatio"] = (
        volume /
        data["VolumeMA20"]
    )

    # Support / Resistance
    data["Support20"] = (
        low
        .rolling(20)
        .min()
        .shift(1)
    )

    data["Resistance20"] = (
        high
        .rolling(20)
        .max()
        .shift(1)
    )

    # Returns
    data["Return5D"] = (
        close.pct_change(5) * 100
    )

    data["Return20D"] = (
        close.pct_change(20) * 100
    )

    return data


# ==========================================================
# TECHNICAL SCORE
# ==========================================================

def calculate_technical_score(data):

    last = data.iloc[-1]

    score = 0
    reasons = []

    # ----------------------------------
    # TREND
    # Maximum 20
    # ----------------------------------

    if last["Close"] > last["MA20"]:

        score += 5
        reasons.append(
            "Harga berada di atas MA20"
        )

    if last["MA20"] > last["MA50"]:

        score += 7
        reasons.append(
            "MA20 berada di atas MA50"
        )

    if (
        pd.notna(last["MA200"])
        and
        last["Close"] > last["MA200"]
    ):

        score += 8
        reasons.append(
            "Harga berada di atas MA200"
        )

    # ----------------------------------
    # MOMENTUM
    # Maximum 15
    # ----------------------------------

    rsi = last["RSI14"]

    if 50 <= rsi <= 70:

        score += 8

        reasons.append(
            "RSI berada pada zona momentum sehat"
        )

    elif 45 <= rsi < 50:

        score += 4

    if (
        last["MACD"]
        >
        last["MACDSignal"]
    ):

        score += 7

        reasons.append(
            "MACD bullish"
        )

    # ----------------------------------
    # VOLUME
    # Maximum 15
    # ----------------------------------

    volume_ratio = last["VolumeRatio"]

    if volume_ratio >= 1.5:

        score += 15

        reasons.append(
            "Volume breakout kuat"
        )

    elif volume_ratio >= 1.2:

        score += 10

        reasons.append(
            "Volume di atas rata-rata"
        )

    elif volume_ratio >= 1.0:

        score += 5

    # ----------------------------------
    # PRICE ACTION
    # Maximum 20
    # ----------------------------------

    if (
        pd.notna(last["Resistance20"])
        and
        last["Close"]
        >
        last["Resistance20"]
    ):

        score += 20

        reasons.append(
            "Breakout resistance 20 hari"
        )

    elif (
        pd.notna(last["MA20"])
        and
        last["Close"] > last["MA20"]
    ):

        score += 8

        reasons.append(
            "Price action berada di atas MA20"
        )

    # ----------------------------------
    # SUPPORT
    # Maximum 10
    # ----------------------------------

    if pd.notna(last["Support20"]):

        distance = (
            last["Close"]
            -
            last["Support20"]
        ) / last["Close"]

        if 0 <= distance <= 0.05:

            score += 10

            reasons.append(
                "Harga relatif dekat dengan support"
            )

    return min(score, 80), reasons


# ==========================================================
# FUNDAMENTAL SCORE
# ==========================================================

def calculate_fundamental_score(info):

    score = 0
    reasons = []

    per = info.get("trailingPE")
    pbv = info.get("priceToBook")
    roe = info.get("returnOnEquity")
    growth = info.get("earningsGrowth")

    # PER

    if per is not None and per > 0:

        if per <= 12:

            score += 3

            reasons.append(
                "PER relatif rendah"
            )

        elif per <= 20:

            score += 2

        else:

            score += 1

    # PBV

    if pbv is not None and pbv > 0:

        if pbv <= 1.5:

            score += 3

            reasons.append(
                "PBV relatif menarik"
            )

        elif pbv <= 3:

            score += 2

        else:

            score += 1

    # ROE

    if roe is not None:

        if roe >= 0.15:

            score += 2

            reasons.append(
                "ROE kuat"
            )

        elif roe >= 0.10:

            score += 1

    # Earnings growth

    if (
        growth is not None
        and
        growth > 0
    ):

        score += 2

        reasons.append(
            "Pertumbuhan laba positif"
        )

    return min(score, 10), reasons


# ==========================================================
# TRADE PLAN
# ==========================================================

def calculate_trade_plan(data):

    last = data.iloc[-1]

    price = float(last["Close"])

    atr = (
        float(last["ATR14"])
        if pd.notna(last["ATR14"])
        else price * 0.03
    )

    support = (
        float(last["Support20"])
        if pd.notna(last["Support20"])
        else price - atr
    )

    resistance = (
        float(last["Resistance20"])
        if pd.notna(last["Resistance20"])
        else price + atr * 2
    )

    ma20 = (
        float(last["MA20"])
        if pd.notna(last["MA20"])
        else price
    )

    # ENTRY

    entry_low = min(
        price,
        ma20,
        support
    )

    entry_high = max(
        price,
        ma20
    )

    if entry_high > price * 1.03:

        entry_high = price * 1.03

    # STOP LOSS

    sl = min(
        support - atr * 0.25,
        price - atr * 1.2
    )

    if sl <= 0:

        sl = price * 0.95

    # RISK

    risk = entry_high - sl

    # TP

    tp1 = max(
        resistance,
        entry_high + risk * 2
    )

    tp2 = (
        entry_high
        +
        risk * 3
    )

    risk_pct = (
        (entry_high - sl)
        /
        entry_high
    ) * 100

    gain_pct = (
        (tp1 - entry_high)
        /
        entry_high
    ) * 100

    rr = (
        gain_pct / risk_pct
        if risk_pct > 0
        else 0
    )

    return {

        "price": price,

        "entry_low": entry_low,

        "entry_high": entry_high,

        "sl": sl,

        "tp1": tp1,

        "tp2": tp2,

        "support": support,

        "resistance": resistance,

        "risk_pct": risk_pct,

        "gain_pct": gain_pct,

        "rr": rr
    }


# ==========================================================
# R:R SCORE
# ==========================================================

def calculate_rr_score(rr):

    if rr >= 3:

        return 10

    elif rr >= 2:

        return 8

    elif rr >= 1.5:

        return 5

    elif rr >= 1:

        return 2

    return 0


# ==========================================================
# SIGNAL
# ==========================================================

def generate_signal(
    score,
    rr,
    price,
    ma20
):

    if (
        score >= 80
        and
        rr >= 2
        and
        price >= ma20
    ):

        return "🟢 BUY"

    elif (
        score >= 70
        and
        rr >= 2
    ):

        return "🟡 BUY ON WEAKNESS"

    elif score >= 60:

        return "⚪ WATCH / WAIT"

    else:

        return "🔴 AVOID"


# ==========================================================
# SIDEBAR
# ==========================================================

st.sidebar.header(
    "⚙️ Parameter Analisis"
)

ticker_input = st.sidebar.text_input(
    "Kode Saham IDX",
    "BBNI"
).strip().upper()

entry_manual = st.sidebar.number_input(
    "Entry Manual (opsional)",
    min_value=0.0,
    value=0.0,
    step=10.0
)

capital = st.sidebar.number_input(
    "Modal Posisi",
    min_value=100000.0,
    value=1000000.0,
    step=100000.0
)

risk_percent = st.sidebar.slider(
    "Risiko Maksimum / Trade",
    min_value=0.25,
    max_value=2.0,
    value=1.0,
    step=0.25
)

st.sidebar.markdown("---")

st.sidebar.info(
    "Target 5% bukan kewajiban setiap transaksi. "
    "Prioritas sistem adalah setup dengan risk/reward yang sehat."
)

# ==========================================================
# LOAD STOCK
# ==========================================================

symbol = f"{ticker_input}.JK"

df, info, error = load_stock(
    symbol
)

if error or df.empty:

    st.error(
        f"Gagal mengambil data saham {ticker_input}."
    )

    if error:
        st.code(error)

    st.stop()

# ==========================================================
# INDICATORS
# ==========================================================

df = calculate_indicators(df)

last = df.iloc[-1]

technical_score, technical_reasons = (
    calculate_technical_score(df)
)

fundamental_score, fundamental_reasons = (
    calculate_fundamental_score(info)
)

trade = calculate_trade_plan(df)

rr_score = calculate_rr_score(
    trade["rr"]
)

total_score = min(
    technical_score
    +
    fundamental_score
    +
    rr_score,
    100
)

signal = generate_signal(
    total_score,
    trade["rr"],
    last["Close"],
    last["MA20"]
)

# ==========================================================
# HEADER
# ==========================================================

st.subheader(
    f"1️⃣ {ticker_input} — Trading Decision"
)

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric(
    "Harga",
    rupiah(last["Close"])
)

c2.metric(
    "MA20",
    rupiah(last["MA20"])
)

c3.metric(
    "MA50",
    rupiah(last["MA50"])
)

c4.metric(
    "RSI",
    f"{last['RSI14']:.1f}"
)

c5.metric(
    "Volume Ratio",
    f"{last['VolumeRatio']:.2f}x"
)

st.success(
    f"Signal: **{signal}** | "
    f"Score: **{total_score}/100** | "
    f"Data terakhir: "
    f"**{df.index[-1].strftime('%d-%m-%Y')}**"
)

# ==========================================================
# TRADE PLAN
# ==========================================================

st.subheader(
    "2️⃣ Automatic Trade Plan"
)

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric(
    "Entry Zone",
    f"{rupiah(trade['entry_low'])} - "
    f"{rupiah(trade['entry_high'])}"
)

c2.metric(
    "Stop Loss",
    rupiah(trade["sl"])
)

c3.metric(
    "TP1",
    rupiah(trade["tp1"])
)

c4.metric(
    "TP2",
    rupiah(trade["tp2"])
)

c5.metric(
    "Risk / Reward",
    f"1 : {trade['rr']:.2f}"
)

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Risk",
    f"-{trade['risk_pct']:.2f}%"
)

c2.metric(
    "Potensi TP1",
    f"+{trade['gain_pct']:.2f}%"
)

c3.metric(
    "Support",
    rupiah(trade["support"])
)

c4.metric(
    "Resistance",
    rupiah(trade["resistance"])
)

# ==========================================================
# SCORE
# ==========================================================

st.subheader(
    "3️⃣ Score Breakdown"
)

score_table = pd.DataFrame({

    "Komponen": [
        "Technical",
        "Fundamental",
        "Risk / Reward",
        "TOTAL"
    ],

    "Score": [
        technical_score,
        fundamental_score,
        rr_score,
        total_score
    ],

    "Maximum": [
        80,
        10,
        10,
        100
    ]
})

st.dataframe(
    score_table,
    use_container_width=True,
    hide_index=True
)

# ==========================================================
# REASONS
# ==========================================================

left, right = st.columns(2)

with left:

    st.markdown(
        "### ✅ Faktor Positif"
    )

    reasons = (
        technical_reasons
        +
        fundamental_reasons
    )

    if reasons:

        for reason in reasons:

            st.write(
                "•",
                reason
            )

    else:

        st.write(
            "Belum terdapat faktor positif kuat."
        )

with right:

    st.markdown(
        "### ⚠️ Risiko / Warning"
    )

    warnings = []

    if last["Close"] < last["MA20"]:

        warnings.append(
            "Harga berada di bawah MA20"
        )

    if last["MA20"] < last["MA50"]:

        warnings.append(
            "MA20 berada di bawah MA50"
        )

    if last["RSI14"] < 45:

        warnings.append(
            "Momentum relatif lemah"
        )

    if last["VolumeRatio"] < 0.8:

        warnings.append(
            "Volume berada di bawah rata-rata"
        )

    if trade["rr"] < 2:

        warnings.append(
            "Risk/Reward belum mencapai 1:2"
        )

    if not warnings:

        warnings.append(
            "Tidak ada warning besar."
        )

    for warning in warnings:

        st.write(
            "•",
            warning
        )

# ==========================================================
# FUNDAMENTAL
# ==========================================================

st.subheader(
    "4️⃣ Fundamental Snapshot"
)

per = info.get(
    "trailingPE"
)

pbv = info.get(
    "priceToBook"
)

roe = info.get(
    "returnOnEquity"
)

growth = info.get(
    "earningsGrowth"
)

dividend = info.get(
    "dividendYield"
)

fundamental_table = pd.DataFrame({

    "Metric": [
        "PER",
        "PBV",
        "ROE",
        "Earnings Growth",
        "Dividend Yield"
    ],

    "Value": [

        f"{per:.2f}x"
        if per
        else "N/A",

        f"{pbv:.2f}x"
        if pbv
        else "N/A",

        f"{roe * 100:.2f}%"
        if roe
        else "N/A",

        f"{growth * 100:.2f}%"
        if growth
        else "N/A",

        f"{dividend * 100:.2f}%"
        if dividend
        else "N/A"
    ]
})

st.dataframe(
    fundamental_table,
    use_container_width=True,
    hide_index=True
)

# ==========================================================
# MANUAL ENTRY AUDIT
# ==========================================================

st.subheader(
    "5️⃣ Audit Entry Manual"
)

if entry_manual > 0:

    manual_risk = (
        (entry_manual - trade["sl"])
        /
        entry_manual
    ) * 100

    manual_gain = (
        (trade["tp1"] - entry_manual)
        /
        entry_manual
    ) * 100

    manual_rr = (
        manual_gain / manual_risk
        if manual_risk > 0
        else 0
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Entry Manual",
        rupiah(entry_manual)
    )

    c2.metric(
        "Potensi TP1",
        f"{manual_gain:+.2f}%"
    )

    c3.metric(
        "R:R Manual",
        f"1 : {manual_rr:.2f}"
    )

    if (
        entry_manual >= trade["entry_low"]
        and
        entry_manual <= trade["entry_high"]
    ):

        st.success(
            "Entry berada di dalam zona entry."
        )

    elif entry_manual < trade["entry_low"]:

        st.info(
            "Entry berada lebih rendah dari zona entry. "
            "Potensi menarik, tetapi tunggu konfirmasi."
        )

    else:

        st.warning(
            "Entry terlalu tinggi dibanding zona entry."
        )

# ==========================================================
# POSITION SIZING
# ==========================================================

st.subheader(
    "6️⃣ Position Sizing"
)

maximum_loss = (
    capital
    *
    risk_percent
    /
    100
)

entry_for_size = (
    entry_manual
    if entry_manual > 0
    else trade["entry_high"]
)

risk_per_share = max(
    entry_for_size - trade["sl"],
    1
)

shares = int(
    maximum_loss
    /
    risk_per_share
)

lots = shares // 100

capital_used = (
    lots
    *
    100
    *
    entry_for_size
)

c1, c2, c3 = st.columns(3)

c1.metric(
    "Maksimum Risiko",
    rupiah(maximum_loss)
)

c2.metric(
    "Estimasi Lot",
    f"{lots} lot"
)

c3.metric(
    "Modal Terpakai",
    rupiah(capital_used)
)

st.caption(
    "Position sizing menjaga potensi kerugian sampai Stop Loss "
    "agar mendekati batas risiko yang dipilih."
)

# ==========================================================
# CHART
# ==========================================================

st.subheader(
    "7️⃣ Price Trend"
)

chart_data = df[
    [
        "Close",
        "MA20",
        "MA50",
        "MA200"
    ]
].tail(120)

st.line_chart(
    chart_data
)

# ==========================================================
# PORTFOLIO MONITOR
# ==========================================================

st.subheader(
    "8️⃣ Portfolio Monitor"
)

portfolio = pd.DataFrame({

    "Kode": [
        "BBNI",
        "TLKM"
    ],

    "Lot": [
        10,
        9
    ],

    "Avg": [
        3603,
        2853
    ]
})

portfolio_result = []

for _, row in portfolio.iterrows():

    code = row["Kode"]

    stock_df, _, _ = load_stock(
        f"{code}.JK"
    )

    if stock_df.empty:
        continue

    current = float(
        stock_df["Close"].iloc[-1]
    )

    quantity = (
        row["Lot"]
        *
        100
    )

    cost = (
        row["Avg"]
        *
        quantity
    )

    market_value = (
        current
        *
        quantity
    )

    pnl = (
        market_value
        -
        cost
    )

    pnl_percent = (
        pnl / cost
    ) * 100

    portfolio_result.append({

        "Kode": code,

        "Lot": row["Lot"],

        "Avg": rupiah(
            row["Avg"]
        ),

        "Harga": rupiah(
            current
        ),

        "Nilai": rupiah(
            market_value
        ),

        "P/L": rupiah(
            pnl
        ),

        "P/L %": f"{pnl_percent:+.2f}%"
    })

if portfolio_result:

    st.dataframe(
        pd.DataFrame(
            portfolio_result
        ),
        use_container_width=True,
        hide_index=True
    )

# ==========================================================
# SIMPLE ACTION GUIDE
# ==========================================================

st.subheader(
    "9️⃣ Decision Guide"
)

if signal == "🟢 BUY":

    st.success(
        "BUY: setup memenuhi skor, momentum, dan Risk/Reward. "
        "Tetap gunakan Stop Loss."
    )

elif signal == "🟡 BUY ON WEAKNESS":

    st.warning(
        "BUY ON WEAKNESS: jangan mengejar harga. "
        "Tunggu harga masuk Entry Zone."
    )

elif signal == "⚪ WATCH / WAIT":

    st.info(
        "WAIT: belum cukup kuat untuk entry agresif."
    )

else:

    st.error(
        "AVOID: setup belum memenuhi standar trading."
    )

# ==========================================================
# FOOTER
# ==========================================================

st.markdown("---")

st.caption(
    "Stock Trading Decision Dashboard V2 | "
    "MA20/50/200 • RSI • MACD • ATR • Volume • "
    "Support/Resistance • Fundamental • R:R • "
    "Position Sizing • Portfolio"
)
