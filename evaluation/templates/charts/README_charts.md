# Panduan Data untuk 7 Grafik Bab 4.4

> **UPDATE 2026-07-18**: seluruh CSV di folder ini sudah di-refresh lagi dari
> `evaluation/reports/2026-07-18/with_acif_results.csv` (run ulang penuh, run_id `ccc41b97...`,
> dijalankan untuk memverifikasi run 16 Juli masih berlaku sebelum sidang — lihat
> `evaluation/reports/2026-07-18/README.md` untuk detail, termasuk koreksi penting soal Q015-Q017
> yang ternyata baru SEBAGIAN teratasi). Chart 4.39/4.43/4.48/4.49 berubah angkanya; chart 4.46
> (distribusi gate) identik; chart 4.52 (SUS) sengaja tidak diubah (studi manusia, bukan hasil skrip).
>
> UPDATE 2026-07-16 (riwayat): seluruh CSV pernah di-refresh dari run 2026-07-16 pasca-perbaikan
> `gold_qa_dataset.jsonl` yang sebelumnya berisi chunk id basi — lihat
> `evaluation/reports/2026-07-16/README.md` untuk detail historis.

Setiap file di folder ini adalah tabel siap-plot untuk satu gambar. Kolom yang sudah terisi angka
diambil nyata dari `evaluation/reports/2026-07-18/with_acif_results.csv` (hasil run 2026-07-18,
kondisi ACIF aktif — 41 soal gold QA), plus query langsung ke `chat_evaluation_logs`/`acif_trace_logs`
untuk breakdown per-komponen (chart 4.48/4.49) dan `acif_trace_logs` untuk distribusi gate (chart 4.46).
Kolom kosong berarti datanya belum ada di file lokal manapun dan perlu diekspor dulu (lihat kolom
`Catatan` di tiap file untuk sumbernya). PNG hasil plot terbaru tersedia di
`evaluation/reports/2026-07-18/figures/` (dibuat oleh `evaluation/scripts/generate_charts.py`);
versi 16 Juli tetap ada di `evaluation/reports/2026-07-16/figures/` sebagai riwayat.

Rekomendasi alat: Excel/Google Sheets (cepat) atau Python `matplotlib`/`pandas` (lebih presisi,
konsisten dengan gaya dokumen skripsi). Semua grafik di bawah cukup dengan **bar chart biasa** —
tidak perlu chart jenis lain.

| Gambar | File data | Jenis chart | Sumbu X | Sumbu Y | Series | Siap plot? |
|---|---|---|---|---|---|---|
| 4.39 Precision@3 & Recall@3 | `chart_4_39_precision_recall.csv` | Bar bergerombol (grouped bar) | Kategori pertanyaan | Nilai 0-1 | 2 bar per kategori: Precision@3, Recall@3 | **Ya** (SPMB, Regulation, Keseluruhan) — 5 kategori lain memang kosong by design (tidak punya ground truth) |
| 4.40 Kualitas Jawaban | `chart_4_40_answer_quality.csv` | Bar tunggal | Nama metrik (5 metrik) | Nilai (%/skor, lihat kolom Skala) | 1 bar per metrik | **Sebagian** — Completeness kosong (perlu skor rubrik manual), Answer Relevance/Faithfulness/Hallucination baru dari n=6 sampel (kecil, sebut di teks) |
| 4.43 Citation Coverage & Correctness | `chart_4_43_citation.csv` | Bar bergerombol | Kategori pertanyaan | Persentase (%) | 2 bar per kategori: Coverage, Correctness | **Ya**, semua 7 kategori + Keseluruhan sudah terisi |
| 4.46 Distribusi Status Gate ACIF | `chart_4_46_acif_gate_distribution.csv` | Bar bertumpuk (stacked bar) | Gate 1-5 | Jumlah (count) | 5 bar/warna per gate: Pass, Warn, Block, Fallback, Error | **Belum** — jalankan SQL #3 di `docs/private/evaluation-bab4-4-audit.md` §13, atau buka `/admin/evaluation/acif-traces` dan hitung manual per gate |
| 4.48 Rata-rata Latency per Komponen | `chart_4_48_latency_per_component.csv` | Bar tunggal | Nama komponen (Query Understanding, Retrieval, GraphRAG, ACIF, LLM, Output Verification, Total) | Milidetik (ms) | 1 bar per komponen | **Sebagian** — Retrieval/LLM/Total sudah terisi, 3 komponen lain perlu export `chat-logs.csv` |
| 4.49 P95 Latency | `chart_4_49_p95_latency.csv` | Bar tunggal | Nama komponen (sama seperti 4.48) | Milidetik (ms), nilai persentil-95 | 1 bar per komponen | **Sebagian**, sama seperti 4.48 |
| 4.52 Rata-rata Item SUS | `chart_4_52_sus_items.csv` | Bar tunggal | Item SUS1-SUS10 | Rata-rata skor (skala 1-5) | 1 bar per item | **Ya (2026-07-15)** — terisi angka nyata dari 21 responden SUS domain produksi (skor SUS keseluruhan 69,05 = "Good") |

## Cara mengisi bagian yang masih kosong

1. **4.46 (distribusi gate ACIF)** — jalankan query SQL di panduan audit utama (§13, query #3),
   atau buka halaman admin **ACIF Traces** (`/admin/evaluation/acif-traces`), filter per gate, dan
   hitung jumlah baris per `gate_status`.
2. **4.48 / 4.49 (3 komponen latency yang kosong)** — buka **Export Center**
   (`/admin/evaluation/export`) → unduh `chat-logs.csv` → kolom `graph_latency_ms`,
   `acif_latency_ms`, `output_verification_latency_ms` sudah ada di situ, tinggal `AVERAGE()` /
   `PERCENTILE.INC(...,0.95)` di Excel.
3. **4.52 (SUS per item)** — **SUDAH TERISI (2026-07-15)** dari 21 responden nyata di domain
   produksi. Lihat `campus-va/docs/private/evaluation-bab4-4-audit.md` §11 untuk detail dan
   peringatan privasi (identitas responden asli sudah dianonimkan ke kode R01-R22).
4. **4.40 Completeness** — ini murni skor manusia (skala 0-4), tidak ada di sistem. Baca 41
   pasangan (jawaban sistem vs jawaban rujukan) di `gold_qa_dataset.csv`, beri skor manual per
   soal di `answer_quality_eval.csv`, baru rata-ratakan.

## Kalau ingin grafik with-ACIF vs without-ACIF (opsional, bukan bagian dari 7 gambar di atas)

Data perbandingan sudah dihitung otomatis di `evaluation/reports/thesis_acif_comparison.csv`
(hasil uji Wilcoxon/McNemar berpasangan) — kolom `mean_a`/`mean_b`/`mean_delta` per metrik sudah
bisa langsung diplot sebagai bar bergerombol (2 bar per metrik: dengan ACIF vs tanpa ACIF) tanpa
perhitungan tambahan.
