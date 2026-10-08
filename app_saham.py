import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# STOCK SWING HUNTER V3
# MOBILE-FIRST | IDX | TARGET SWING >= 5%
# ============================================================

st.set_page_config(
    page_title="Stock Swing Hunter V3",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# MOBILE CSS
# ============================================================

st.markdown("""
<style>

.block-container {
    padding-top: 1rem;
    padding-left: 1rem;
    padding-right: 1rem;
    max-width: 1400px;
}

h1 {
    font-size: 1.8rem !important;
}

h2 {
    font-size: 1.35rem !important;
}

h3 {
    font-size: 1.1rem !important;
}

.metric-card {
    padding: 14px;
    border-radius: 14px;
    border: 1px solid rgba(128,128,128,.25);
    margin-bottom: 10px;
}

.stock-card {
    padding: 16px;
    border-radius: 16px;
    border: 1px solid rgba(128,128,128,.25);
    margin-bottom: 14px;
    background: rgba(128,128,128,.04);
}

.stock-title {
    font-size: 1.25rem;
    font-weight: 700;
}

.signal-buy {
    font-size: 1.05rem;
    font-weight: 700;
}

.small-text {
    font-size: .85rem;
    opacity: .75;
}

div[data-testid="stMetric"] {
    padding: 8px;
}

@media (max-width: 768px) {

    .block-container {
        padding-left: .7rem;
        padding-right: .7rem;
        padding-top: .5rem;
    }

    h1 {
        font-size: 1.45rem !important;
    }

    h2 {
        font-size: 1.15rem !important;
    }

    h3 {
        font-size: 1rem !important;
    }

    div[data-testid="stMetric"] {
        padding: 4px;
    }

    div[data-testid="stMetricLabel"] {
        font-size: .72rem !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1rem !important;
    }

    .stock-card {
        padding: 12px;
    }

}

</style>
""", unsafe_allow_html=True)


# ============================================================
# CONFIG
# ============================================================

TARGET_PROFIT = 5.0
MIN_RR = 2.0

# Universe IDX
LQ45 = [
    "ACES", "ADRO", "AKRA", "AMRT", "ANTM",
    "ASII", "BBCA", "BBNI", "BBRI", "BBTN",
    "BMRI", "BRIS", "CPIN", "EMTK", "EXCL",
    "GOTO", "ICBP", "INCO", "INDF", "INKP",
    "ITMG", "JSMR", "KLBF", "MDKA", "MEDC",
    "PGAS", "PGEO", "PTBA", "SMGR", "SMRA",
    "TLKM", "TOWR", "UNTR", "UNVR"
]

IDX30 = [
    "ADRO", "AMRT", "ANTM", "ASII", "BBCA",
    "BBNI", "BBRI", "BMRI", "BRIS", "CPIN",
    "GOTO", "ICBP", "INDF", "ITMG", "KLBF",
    "MDKA", "PGAS", "PTBA", "SMGR", "TLKM",
    "UNTR", "UNVR"
]

# ============================================================
# HELPERS
# ============================================================

def rupiah(x):

    if x is None or pd.isna(x):
        return "N/A"

    return f"Rp {x:,.0f}"


def pct(x):

    if x is None or pd.isna(x):
        return "N/A"

    return f"{x:+.2f}%"


# ============================================================
# DATA
# ============================================================

@st.cache_data(ttl=300)
def get_stock(symbol):

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

        return df, info

    except Exception:

        return pd.DataFrame(), {}


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    x = df.copy()

    close = x["Close"]
    high = x["High"]
    low = x["Low"]
    volume = x["Volume"]

    # Moving averages
    x["MA20"] = close.rolling(20).mean()
    x["MA50"] = close.rolling(50).mean()
    x["MA200"] = close.rolling(200).mean()

    # RSI
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    x["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    x["MACD"] = ema12 - ema26

    x["MACD_SIGNAL"] = x["MACD"].ewm(
        span=9,
        adjust=False
    ).mean()

    x["MACD_HIST"] = (
        x["MACD"]
        -
        x["MACD_SIGNAL"]
    )

    # ATR
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ],
        axis=1
    ).max(axis=1)

    x["ATR"] = tr.rolling(14).mean()

    # Volume
    x["VOL_MA20"] = volume.rolling(20).mean()

    x["VOL_RATIO"] = (
        volume /
        x["VOL_MA20"]
    )

    # Support / Resistance
    x["SUPPORT"] = (
        low
        .rolling(20)
        .min()
        .shift(1)
    )

    x["RESISTANCE"] = (
        high
        .rolling(20)
        .max()
        .shift(1)
    )

    # Returns
    x["RETURN_5D"] = (
        close.pct_change(5) * 100
    )

    x["RETURN_20D"] = (
        close.pct_change(20) * 100
    )

    return x


# ============================================================
# SCORE
# ============================================================

def calculate_score(df, info):

    last = df.iloc[-1]

    score = 0

    reasons = []

    warnings = []

    # --------------------------------------------------------
    # TREND — 20 POINT
    # --------------------------------------------------------

    if last["Close"] > last["MA20"]:

        score += 5

        reasons.append(
            "Harga > MA20"
        )

    else:

        warnings.append(
            "Harga < MA20"
        )

    if last["MA20"] > last["MA50"]:

        score += 7

        reasons.append(
            "MA20 > MA50"
        )

    else:

        warnings.append(
            "MA20 < MA50"
        )

    if (
        pd.notna(last["MA200"])
        and
        last["Close"] > last["MA200"]
    ):

        score += 8

        reasons.append(
            "Harga > MA200"
        )

    # --------------------------------------------------------
    # MOMENTUM — 15 POINT
    # --------------------------------------------------------

    rsi = last["RSI"]

    if 50 <= rsi <= 70:

        score += 8

        reasons.append(
            "RSI sehat"
        )

    elif 45 <= rsi < 50:

        score += 4

    elif rsi > 75:

        warnings.append(
            "RSI terlalu tinggi"
        )

    else:

        warnings.append(
            "Momentum lemah"
        )

    if last["MACD"] > last["MACD_SIGNAL"]:

        score += 7

        reasons.append(
            "MACD bullish"
        )

    else:

        warnings.append(
            "MACD bearish"
        )

    # --------------------------------------------------------
    # VOLUME — 15 POINT
    # --------------------------------------------------------

    volume_ratio = last["VOL_RATIO"]

    if volume_ratio >= 1.5:

        score += 15

        reasons.append(
            "Volume breakout kuat"
        )

    elif volume_ratio >= 1.2:

        score += 10

        reasons.append(
            "Volume meningkat"
        )

    elif volume_ratio >= 1:

        score += 5

    else:

        warnings.append(
            "Volume rendah"
        )

    # --------------------------------------------------------
    # PRICE ACTION — 20 POINT
    # --------------------------------------------------------

    resistance = last["RESISTANCE"]

    if (
        pd.notna(resistance)
        and
        last["Close"] > resistance
    ):

        score += 20

        reasons.append(
            "Breakout resistance"
        )

    elif last["Close"] > last["MA20"]:

        score += 8

    # --------------------------------------------------------
    # SUPPORT — 10 POINT
    # --------------------------------------------------------

    support = last["SUPPORT"]

    if pd.notna(support):

        distance = (
            last["Close"]
            -
            support
        ) / last["Close"]

        if 0 <= distance <= 0.05:

            score += 10

            reasons.append(
                "Dekat support"
            )

    # --------------------------------------------------------
    # FUNDAMENTAL — 10 POINT
    # --------------------------------------------------------

    per = info.get("trailingPE")
    pbv = info.get("priceToBook")
    roe = info.get("returnOnEquity")

    if per is not None and 0 < per <= 20:

        score += 3

    if pbv is not None and 0 < pbv <= 3:

        score += 3

    if roe is not None and roe >= 0.10:

        score += 4

        reasons.append(
            "ROE cukup sehat"
        )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    return (
        min(score, 80),
        reasons,
        warnings
    )


# ============================================================
# TRADE PLAN
# ============================================================

def create_trade_plan(df):

    last = df.iloc[-1]

    price = float(last["Close"])

    atr = float(last["ATR"])

    support = float(
        last["SUPPORT"]
    ) if pd.notna(
        last["SUPPORT"]
    ) else price - atr

    resistance = float(
        last["RESISTANCE"]
    ) if pd.notna(
        last["RESISTANCE"]
    ) else price + atr * 2

    ma20 = float(
        last["MA20"]
    )

    # Entry zone
    entry_low = min(
        price,
        ma20,
        support
    )

    entry_high = max(
        price,
        ma20
    )

    # Batasi entry terlalu jauh
    entry_high = min(
        entry_high,
        price * 1.03
    )

    # Stop
    sl = min(
        support - atr * 0.25,
        entry_high - atr * 1.2
    )

    if sl <= 0:

        sl = entry_high * 0.95

    risk = (
        entry_high - sl
    )

    # TP berdasarkan 2R dan resistance
    tp1 = max(
        entry_high + risk * 2,
        resistance
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

    tp_pct = (
        (tp1 - entry_high)
        /
        entry_high
    ) * 100

    rr = (
        tp_pct / risk_pct
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
        "tp_pct": tp_pct,
        "rr": rr
    }


# ============================================================
# SIGNAL
# ============================================================

def determine_signal(
    score,
    trade
):

    if (
        score >= 80
        and
        trade["tp_pct"] >= TARGET_PROFIT
        and
        trade["rr"] >= MIN_RR
    ):

        return "🟢 BUY"

    if (
        score >= 70
        and
        trade["tp_pct"] >= TARGET_PROFIT
        and
        trade["rr"] >= MIN_RR
    ):

        return "🟡 BUY ON WEAKNESS"

    if score >= 60:

        return "⚪ WATCH"

    return "🔴 AVOID"


# ============================================================
# ANALYZE ONE STOCK
# ============================================================

def analyze_stock(code):

    df, info = get_stock(
        f"{code}.JK"
    )

    if df.empty:

        return None

    if len(df) < 60:

        return None

    df = calculate_indicators(
        df
    )

    score, reasons, warnings = (
        calculate_score(
            df,
            info
        )
    )

    trade = create_trade_plan(
        df
    )

    # R:R score
    if trade["rr"] >= 3:

        rr_score = 10

    elif trade["rr"] >= 2:

        rr_score = 8

    elif trade["rr"] >= 1.5:

        rr_score = 5

    else:

        rr_score = 0

    total_score = min(
        score + rr_score,
        100
    )

    signal = determine_signal(
        total_score,
        trade
    )

    last = df.iloc[-1]

    return {

        "Code": code,

        "Score": total_score,

        "Signal": signal,

        "Price": float(last["Close"]),

        "EntryLow": trade["entry_low"],

        "EntryHigh": trade["entry_high"],

        "SL": trade["sl"],

        "TP1": trade["tp1"],

        "TP2": trade["tp2"],

        "RR": trade["rr"],

        "Potential": trade["tp_pct"],

        "RSI": last["RSI"],

        "VolumeRatio": last["VOL_RATIO"],

        "Support": trade["support"],

        "Resistance": trade["resistance"],

        "Return5D": last["RETURN_5D"],

        "Return20D": last["RETURN_20D"],

        "Reasons": reasons,

        "Warnings": warnings,

        "Data": df,

        "Info": info
    }


# ============================================================
# SIDEBAR FILTER
# ============================================================

with st.sidebar:

    st.header("⚙️ Scanner Settings")

    universe = st.selectbox(
        "Universe",
        [
            "LQ45",
            "IDX30",
            "Custom"
        ]
    )

    if universe == "LQ45":

        selected_symbols = LQ45

    elif universe == "IDX30":

        selected_symbols = IDX30

    else:

        custom = st.text_input(
            "Kode saham pisahkan koma",
            "ANTM,ASII,BMRI,BBNI,TLKM"
        )

        selected_symbols = [
            x.strip().upper()
            for x in custom.split(",")
            if x.strip()
        ]

    min_score = st.slider(
        "Minimum Score",
        50,
        90,
        70,
        5
    )

    min_profit = st.slider(
        "Minimum Potensi TP (%)",
        3.0,
        10.0,
        5.0,
        0.5
    )

    min_rr = st.slider(
        "Minimum R:R",
        1.0,
        4.0,
        2.0,
        0.5
    )

    max_results = st.slider(
        "Jumlah hasil",
        3,
        15,
        10
    )

# ============================================================
# HEADER
# ============================================================

st.title(
    "🎯 Stock Swing Hunter V3"
)

st.caption(
    "Mobile-first scanner untuk mencari setup swing IDX "
    "dengan potensi minimal 5%."
)

# ============================================================
# SCAN
# ============================================================

scan_button = st.button(
    "🔄 SCAN SAHAM SEKARANG",
    type="primary",
    use_container_width=True
)

if (
    scan_button
    or
    "scan_results" not in st.session_state
):

    results = []

    progress = st.progress(
        0
    )

    status = st.empty()

    total = len(
        selected_symbols
    )

    for i, code in enumerate(
        selected_symbols
    ):

        status.write(
            f"Scanning **{code}**..."
        )

        result = analyze_stock(
            code
        )

        if result:

            if (
                result["Score"] >= min_score
                and
                result["Potential"] >= min_profit
                and
                result["RR"] >= min_rr
            ):

                results.append(
                    result
                )

        progress.progress(
            (i + 1) / total
        )

    status.success(
        f"Scan selesai — {len(results)} setup ditemukan."
    )

    st.session_state.scan_results = results


# ============================================================
# RESULTS
# ============================================================

results = st.session_state.get(
    "scan_results",
    []
)

if not results:

    st.info(
        "Belum ada setup yang memenuhi filter. "
        "Coba turunkan Minimum Score atau Minimum R:R."
    )

else:

    results = sorted(
        results,
        key=lambda x: (
            x["Score"],
            x["Potential"],
            x["RR"]
        ),
        reverse=True
    )

    results = results[
        :max_results
    ]

    st.subheader(
        "🏆 Top Swing Setup"
    )

    # --------------------------------------------------------
    # TOP 3
    # --------------------------------------------------------

    for rank, result in enumerate(
        results,
        start=1
    ):

        signal = result["Signal"]

        if "BUY" in signal:

            border = "🟢"

        elif "WATCH" in signal:

            border = "🟡"

        else:

            border = "🔴"

        st.markdown(
            f"""
            <div class="stock-card">

            <div class="stock-title">
            {border} #{rank} {result['Code']}
            </div>

            <div class="small-text">
            Score {result['Score']}/100
            &nbsp;&nbsp;|&nbsp;&nbsp;
            {signal}
            </div>

            </div>
            """,
            unsafe_allow_html=True
        )

        # Mobile friendly metrics
        c1, c2 = st.columns(2)

        c1.metric(
            "Harga",
            rupiah(
                result["Price"]
            )
        )

        c2.metric(
            "Potensi",
            f"+{result['Potential']:.2f}%"
        )

        c1, c2 = st.columns(2)

        c1.metric(
            "Entry",
            f"{rupiah(result['EntryLow'])} - "
            f"{rupiah(result['EntryHigh'])}"
        )

        c2.metric(
            "R:R",
            f"1 : {result['RR']:.2f}"
        )

        c1, c2 = st.columns(2)

        c1.metric(
            "Stop Loss",
            rupiah(
                result["SL"]
            )
        )

        c2.metric(
            "TP1",
            rupiah(
                result["TP1"]
            )
        )

        with st.expander(
            f"🔎 Detail {result['Code']}"
        ):

            st.write(
                f"**TP2:** {rupiah(result['TP2'])}"
            )

            st.write(
                f"**Support:** {rupiah(result['Support'])}"
            )

            st.write(
                f"**Resistance:** {rupiah(result['Resistance'])}"
            )

            st.write(
                f"**RSI:** {result['RSI']:.1f}"
            )

            st.write(
                f"**Volume:** {result['VolumeRatio']:.2f}x"
            )

            st.write(
                f"**Return 5D:** {pct(result['Return5D'])}"
            )

            st.write(
                f"**Return 20D:** {pct(result['Return20D'])}"
            )

            st.markdown(
                "### ✅ Faktor Positif"
            )

            for reason in result[
                "Reasons"
            ]:

                st.write(
                    "•",
                    reason
                )

            if result["Warnings"]:

                st.markdown(
                    "### ⚠️ Warning"
                )

                for warning in result[
                    "Warnings"
                ]:

                    st.write(
                        "•",
                        warning
                    )

            st.line_chart(
                result["Data"][
                    [
                        "Close",
                        "MA20",
                        "MA50",
                        "MA200"
                    ]
                ].tail(100)
            )


# ============================================================
# PORTFOLIO
# ============================================================

st.markdown("---")

st.subheader(
    "💼 Portfolio Anda"
)

portfolio = [

    {
        "Code": "BBNI",
        "Lot": 10,
        "Avg": 3603
    },

    {
        "Code": "TLKM",
        "Lot": 9,
        "Avg": 2853
    }

]

for position in portfolio:

    df, info = get_stock(
        f"{position['Code']}.JK"
    )

    if df.empty:

        continue

    current = float(
        df["Close"].iloc[-1]
    )

    quantity = (
        position["Lot"]
        *
        100
    )

    cost = (
        position["Avg"]
        *
        quantity
    )

    value = (
        current
        *
        quantity
    )

    pnl = (
        value
        -
        cost
    )

    pnl_pct = (
        pnl / cost
    ) * 100

    if pnl >= 0:

        status = "🟢"

    else:

        status = "🔴"

    st.markdown(
        f"""
        <div class="stock-card">

        <div class="stock-title">
        {status} {position['Code']}
        </div>

        <div>
        {position['Lot']} lot
        @ {rupiah(position['Avg'])}
        </div>

        <div>
        Harga sekarang:
        <b>{rupiah(current)}</b>
        </div>

        <div>
        P/L:
        <b>{rupiah(pnl)}</b>
        ({pnl_pct:+.2f}%)
        </div>

        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# MARKET EDUCATION
# ============================================================

st.markdown("---")

with st.expander(
    "ℹ️ Cara membaca hasil scanner"
):

    st.write(
        """
        **🟢 BUY**
        
        Setup memenuhi score tinggi, potensi target minimal 5%,
        dan Risk/Reward minimal 1:2.
        
        **🟡 BUY ON WEAKNESS**
        
        Setup cukup kuat tetapi lebih baik menunggu harga masuk
        Entry Zone daripada mengejar harga.
        
        **⚪ WATCH**
        
        Belum cukup kuat untuk entry agresif.
        
        **🔴 AVOID**
        
        Setup belum memenuhi standar.
        
        **Penting:** target 5% adalah target screening,
        bukan jaminan keuntungan.
        """
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Stock Swing Hunter V3 | "
    "MA20 • MA50 • MA200 • RSI • MACD • ATR • "
    "Volume • Support/Resistance • R:R • "
    "Target ≥5% • Mobile First"
)
