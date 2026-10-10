# V5 Mobile Swing Hunter (SQLite)

Aplikasi Streamlit mobile-first untuk scan saham IDX, Portfolio Advisor, pencatatan BUY/SELL, Trading Journal, risk limits, grafik ekuitas/drawdown, CSV export, dan backup database SQLite.

## Isi paket
- `app.py` — aplikasi lengkap.
- `requirements.txt` — dependensi Python.
- `schema.sql` — skema SQLite; aplikasi juga membuat tabel otomatis.
- `.streamlit_secrets_example.toml` — contoh konfigurasi opsional.

## Akuntansi transaksi
- 1 lot = 100 saham.
- Portofolio awal dimasukkan satu kali ketika tabel transaksi kosong: BBNI 10 lot @ Rp3.603 dan TLKM 9 lot @ Rp2.853.
- Saldo awal tidak dikenai fee historis karena fee transaksi lama tidak tersedia.
- Fee tetap default: BUY 0,15%, SELL 0,25%. Ubah melalui environment variables `BUY_FEE_PCT` dan `SELL_FEE_PCT` agar sesuai broker.
- BUY menambahkan nilai bruto + fee beli ke harga pokok. Average cost diperbarui secara berbobot.
- SELL ditolak bila jumlah yang dijual melebihi kepemilikan. Realized P/L = nilai jual bruto - fee jual - harga pokok rata-rata saham yang dijual.
- Unrealized P/L = nilai pasar posisi tersisa - biaya pokok tersisa; tidak mengurangi estimasi fee jual di masa depan.
- Transaksi dicatat manual setelah transaksi benar-benar terjadi di broker; aplikasi tidak mengirim order ke broker.

## Jalankan lokal (Windows)
1. Instal Python 3.10 atau lebih baru.
2. Ekstrak ZIP, buka terminal di folder proyek.
3. Buat environment dan instal dependensi:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Database `swing_hunter_v5.sqlite3` dibuat otomatis di folder proyek. Untuk memakai lokasi khusus, set environment variable `SWING_DB_PATH` sebelum menjalankan aplikasi.

## Menjalankan skema manual
Aplikasi otomatis membuat tabel saat startup. Jika ingin membuat database kosong secara manual, gunakan Python:

```bash
python -c "import sqlite3; c=sqlite3.connect('swing_hunter_v5.sqlite3'); c.executescript(open('schema.sql', encoding='utf-8').read()); c.close()"
```

## Deploy ke Streamlit Community Cloud
1. Upload `app.py`, `requirements.txt`, `schema.sql`, README, dan konfigurasi contoh ke repository GitHub. Jangan upload file database berisi data pribadi atau `secrets.toml`.
2. Deploy repository di Streamlit Community Cloud dengan `app.py` sebagai entrypoint.
3. Aplikasi akan membuat file SQLite di filesystem instance secara default. **Peringatan:** filesystem lokal Streamlit Community Cloud tidak dijamin persisten; file bisa hilang ketika instance dihentikan, diganti, atau aplikasi dipindahkan. Untuk catatan trading yang harus persisten, gunakan platform dengan persistent disk atau migrasikan database ke layanan database eksternal.
4. Bila host menyediakan persistent disk, atur `SWING_DB_PATH` ke direktori mount yang persisten. Gunakan tab Backup secara berkala dan simpan salinan di lokasi aman.

## Fitur
- Swing Hunter dengan MA20/50/200, RSI, MACD, ATR, volume ratio, support/resistance, dan filter IHSG.
- Portfolio Advisor: saran berbasis aturan, bukan rekomendasi otomatis.
- BUY/SELL dengan validasi lot, harga, kode saham, dan batas kepemilikan.
- Realized/unrealized P/L, histori dan ekspor CSV.
- Risk limits dan kalkulator ukuran posisi.
- Snapshot ekuitas harian, grafik ekuitas dan drawdown dari snapshot yang tercatat. Snapshot diperbarui saat pengguna menekan tombol; bukan data historis harian yang direkonstruksi otomatis.
- Backup file SQLite dan CSV untuk transaksi, kepemilikan, serta snapshot.

## Batasan penting
- Yahoo Finance/yfinance dapat memberi data tertunda, tidak lengkap, atau kosong untuk saham IDX; ini bukan feed realtime tick-by-tick resmi.
- Daftar saham scanner adalah watchlist, bukan daftar konstituen LQ45 dinamis.
- Grafik drawdown bergantung pada snapshot yang dibuat. Untuk hasil bermakna, catat snapshot secara rutin. Nilai ekuitas adalah nilai pasar kepemilikan ditambah realized P/L kumulatif, bukan rekonstruksi lengkap arus kas/deposit/withdrawal.
- Risk limits adalah peringatan/kalkulator, tidak mengirim order atau memaksa broker menolak transaksi.
- Skor adalah sistem rule-based yang belum teruji sebagai strategi menguntungkan; backtest dengan fee, slippage, dan data out-of-sample sebelum digunakan untuk keputusan riil.
