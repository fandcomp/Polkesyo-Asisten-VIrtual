# Evaluasi ASQ per Skenario — 2026-08-02

Workbook baru: `ASQ_Evaluasi_Skenario_Lengkap_2026-08-02.xlsx` — dibangun dari data yang **sudah
ada** di VPS produksi (`root@<PRODUCTION_VPS_IP>`), read-only, tanpa panggilan `/chat` baru maupun
evaluation run baru.

Menggabungkan dua instrumen evaluasi yang **belum pernah dihubungkan sebelumnya** di proyek ini:

1. **Studi usability ASQ manusia 2026-07-16** (22 partisipan, skenario S1/S2, 3 item ASQ skala
   1-7). Sumber: `evaluation/reports/2026-07-16/sus_asq_final/asq_responses_anonymized.csv`.
2. **Run gold-QA otomatis bersih `refresh_20260727_gates_all`** (n=41 soal, 7 kategori) — sumber
   citation correctness, hallucination rate, dan false-positive rate.

Linkage antara keduanya (untuk latency, task success, dan citation correctness **per skenario per
responden**, serta 3 korelasi yang diminta) dibangun via `trace_id`/`session_id` yang tersimpan di
tabel `asq_responses` — kolom yang tidak ada di file anonim 2026-07-16, sehingga harus digali ulang
dari sumbernya via query read-only baru terhadap log produksi (`chat_evaluation_logs`,
`citation_evaluation_logs`).

## Privasi (baca sebelum memakai file lain di folder ini)

File `E:\Kerjaan\1 miliar\VirtualAsisst_2.0\asq_responses.csv` (di luar `campus-va/`) berisi kode
partisipan asli beserta `trace_id`/`session_id` — dipakai **hanya secara internal** untuk
membangun linkage di atas, atas persetujuan eksplisit pengguna. Kode R01-R22 pada workbook ini
adalah **label anonim baru** yang dibangun khusus untuk laporan ini (diurutkan berdasarkan waktu
submisi skenario pertama masing-masing partisipan) — **tidak harus sama** dengan R01-R22 pada
laporan 2026-07-16 (dua reverse-matching attempt terhadap label lama gagal tervalidasi — lihat
komentar di `build_r0x_traceid_map_2026-08-02.py`). Statistik agregat tetap identik terlepas dari
label spesifik, karena keduanya berasal dari 43 baris mentah yang sama (diverifikasi: mean ASQ
keseluruhan 5.76/7, cocok persis dengan angka referensi dari laporan-laporan sebelumnya).

**Tidak ada** kode partisipan asli, `trace_id` mentah, atau `session_id` mentah yang dituliskan ke
workbook, CSV, atau file manapun di folder ini.

## Ringkasan 17 Angka yang Diminta

| # | Item | Nilai | Sheet |
|---|---|---|---|
| 1-2 | ASQ per item & skenario | lihat tabel agregat | 1 |
| 3 | ASQ keseluruhan | 5.76/7 (n=43, SD=1.35) | 2 |
| 4 | Median/Mean/SD/IQR/CI | Mean 5.76, Median lihat sheet, SD 1.35, 95% CI [5.34, 6.17] | 2 |
| 5 | Cronbach's alpha per skenario | S1=0.969, S2=0.951 (indikatif, 3 item) | 3 |
| 6 | Task success rate per skenario | S1=42.9%, S2=42.9% (persis sama) | 4 |
| 7 | Completion time per skenario (median, proxy) | S1=148 detik (n bersih=19), S2=150 detik (n bersih=21) | 5 |
| 8 | Latency per skenario | lihat sheet 6 (mean/median/p95) | 6 |
| 9 | % jawaban sitasi benar | 39.0% (16/41, run gold-QA bersih) | 7 |
| 10 | Hallucination rate | 9.8% (4/41) | 7 |
| 11 | False-positive rate filtering | 12.5% (2/16 soal kategori jawaban-valid) — **dihitung ulang dari data terkini**, bukan reuse angka 2026-07-15 (0%) yang sudah usang | 7 |
| 12 | Korelasi ASQ vs latency | Pearson r=0.071, p=0.657, n=42 (tidak signifikan) | 8 |
| 13 | Korelasi ASQ vs task success | point-biserial r=0.067, p=0.673, n=42 (tidak signifikan) | 8 |
| 14 | Korelasi dukungan informasi (ASQ_3) vs citation correctness | point-biserial r=0.170, p=0.283, n=42 (tidak signifikan) | 8 |
| 15 | Perbedaan ASQ antar skenario | Wilcoxon p=1.0000, n=21 pasangan (13/21 pasangan skor identik — lihat catatan metodologi) | 9 |
| 16 | 3 masalah pengguna tersering | sintesis berbukti | 10 |
| 17 | 3 penyebab teknis terbesar + rekomendasi | sintesis berbukti | 11-12 |

**Temuan paling penting**: task success rate objektif (42.9%, berdasar `answer_status` produksi)
jauh di bawah kepuasan subjektif ASQ (5.76/7) — kesenjangan nyata antara persepsi dan hasil
objektif, layak dibahas eksplisit di bab diskusi. Semua 3 korelasi lemah dan tidak signifikan
secara statistik (p > 0.05, n=42) — laporkan sebagai temuan negatif yang jujur, bukan dipaksakan
signifikan.

## File di folder ini

```
ASQ_Evaluasi_Skenario_Lengkap_2026-08-02.xlsx   14 sheet, lihat daftar isi (sheet "0. Ringkasan Eksekutif")
raw_joined_by_scenario.csv                       data mentah R0x-keyed di balik sheet 1/4/5/6/8 (aman, tanpa trace_id/session_id)
figures/*.png                                    4 chart yang di-embed ke workbook
README.md                                        file ini
```

## Reproduksibilitas

```
campus-va/evaluation/scripts/build_r0x_traceid_map_2026-08-02.py   # bangun label R01-R22 + trace_id (output HARUS ke scratch, jangan commit)
campus-va/evaluation/scripts/vps_query_asq_linkage_2026-08-02.sql  # template query read-only (tanpa trace_id literal)
campus-va/evaluation/scripts/build_asq_scenario_excel_2026-08-02.py # komputasi statistik + build workbook
```

Alur ulang: (1) jalankan `build_r0x_traceid_map_2026-08-02.py --root-csv <path asq_responses.csv
asli> --out <scratch>/r0x_traceid_map.csv`; (2) substitusi daftar trace_id dari file itu ke
`vps_query_asq_linkage_2026-08-02.sql`, jalankan read-only via `docker exec -i campus-va-postgres
psql -U assistant_user -d assistant_db --csv -c "<query>"` untuk tiap query A/B/C/E, simpan sebagai
`A_chat_logs.csv`/`B_citations.csv`/`C_session_first_turn.csv`/`E_eval_results_detail.csv` di
direktori scratch yang sama; (3) jalankan `build_asq_scenario_excel_2026-08-02.py --input-dir
<scratch>`.

## Keterbatasan (ringkasan — detail lengkap di sheet 13 workbook)

- 1 dari 43 baris ASQ tidak punya `trace_id` (tidak ada linkage objektif untuk giliran itu).
- Completion time adalah proxy operasional (selisih waktu submit ASQ), bukan stopwatch — 3 baris
  dikeluarkan dari rata-rata bersih (1 durasi negatif, 2 outlier >1 jam, kemungkinan sisa
  `session_id` dari sesi uji-coba sebelumnya).
- Cronbach's alpha dari 3 item saja — indikatif (memang standar desain ASQ, bukan kekurangan).
- Kolom `notes` pada `asq_responses` nyaris seluruhnya kosong — temuan #16-17 adalah sintesis dari
  hasil kuantitatif workbook ini + temuan terverifikasi `evaluation/reports/2026-07-31/`, bukan
  penambangan teks bebas baru.
