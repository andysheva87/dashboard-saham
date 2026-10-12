# V5.1 Mobile Swing Hunter — Audit & Signal Engine

## Perubahan utama
- `st.set_page_config()` dijalankan sebelum perintah Streamlit lainnya.
- Intraday dipisahkan dari data daily; scanner tetap menggunakan candle daily untuk indikator swing.
- Target TP1 tidak lagi dipaksa minimal 2R; R:R bisa benar-benar menyaring setup.
- Audit scan menunjukkan semua ticker, status data, skor, potensi, R:R, dan alasan gagal filter.
- Universe watchlist, pool likuid awal, dan daftar indeks yang dapat diedit.
- Backup SQLite menggunakan SQLite backup API agar konsisten dengan WAL.
- P/L portfolio menjelaskan bahwa angka masih indikatif dan belum mengurangi estimasi fee jual.

## Jalankan lokal
1. Install Python 3.10 atau lebih baru.
2. Buka terminal di folder ini.
3. Jalankan `pip install -r requirements.txt`.
4. Jalankan `streamlit run app.py`.

## Deploy Streamlit Cloud
1. Backup database dan unduh salinan repositori lama terlebih dahulu.
2. Upload `app.py` dan `requirements.txt` ke branch yang dipakai aplikasi.
3. Pastikan Main file path menunjuk ke `app.py` yang benar.
4. Commit perubahan dan periksa log deployment.
5. Uji scan dengan watchlist kecil terlebih dahulu.

## Penting tentang data dan persistensi
- Yahoo Finance bukan feed eksekusi realtime; intraday dapat terlambat, kosong, atau berubah.
- Universe likuid hanya memeriksa pool kandidat yang tertulis dalam kode, bukan seluruh saham BEI.
- Daftar LQ45/IDX30 adalah seed awal dan harus diverifikasi dengan publikasi resmi terbaru.
- SQLite lokal di Streamlit Cloud tidak dijamin persisten. Untuk histori trading yang penting, gunakan penyimpanan persisten atau database eksternal. Jangan commit database pribadi ke repositori publik.
- Ini aplikasi analisis teknikal dasar; uji dan validasi strategi sebelum mengambil keputusan trading.
