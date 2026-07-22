# Bukti Evaluasi Bab 4.4 — Pendekatan Findings-First (2026-07-16)

Dokumen ini **satu-satunya sumber kebenaran** untuk penyusunan Bab 4.4. Struktur lama
(`evidence/` 11 folder mengikuti Tabel 4.13–4.25, `docs/private/evaluation-bab4-4-audit.md`,
rubrik ganda 0-4/1-5) sudah dihapus permanen — jangan dicari lagi, mulai dari sini.

Prinsip penyusunan: **pimpin dengan temuan yang paling kuat secara statistik dan otomatis**,
baru diikuti data pendukung, baru keterbatasan. Bukan disusun mengikuti nomor tabel yang kaku.

---

## Tier 1 — Temuan utama (signifikan secara statistik, aman jadi tulang punggung Bab 4.4)

Perbandingan berpasangan (Wilcoxon/McNemar exact) antara kondisi **dengan ACIF** vs **tanpa
ACIF**, 41 soal gold QA yang sama, dijalankan di server produksi (VPS) — lihat
`acif_comparison_summary.csv` untuk data lengkap.

| Temuan | Dengan ACIF | Tanpa ACIF | p-value | Makna |
|---|---|---|---|---|
| **Attack Success Rate** (n=10, kategori Security) | **0/10 (0%)** | **10/10 (100%)** | 0.00195 | Setiap percobaan prompt injection/jailbreak berhasil menembus sistem ketika ACIF dimatikan, dan **tidak satupun** berhasil ketika ACIF aktif. Bukti paling kuat dan paling bersih di seluruh evaluasi. |
| **Fallback Correctness** (n=41) | **80.5%** | **41.5%** | 0.0070 | ACIF hampir dua kali lipat lebih akurat dalam memutuskan kapan harus menjawab vs kapan harus menolak/fallback. |
| **Total Latency** (n=41) | **4561 ms** (lebih cepat) | 5451 ms | 0.0337 | Temuan bonus: ACIF justru mempercepat sistem secara rata-rata — pertanyaan yang di-block di Gate 1 (serangan/luar-domain) tidak pernah sampai memanggil LLM, sedangkan tanpa ACIF semua pertanyaan diteruskan ke LLM. |

**Narasi yang disarankan**: buka Bab 4.4 dengan Attack Success Rate dan Fallback Correctness —
dua-duanya signifikan, effect size besar, dan langsung membuktikan klaim inti tesis (ACIF
memperkuat context integrity). Latency jadi poin tambahan yang melawan asumsi umum bahwa
lapisan keamanan selalu memperlambat sistem.

## Tier 2 — Data pendukung (nyata, tapi perlu framing yang jujur)

| Metrik | Nilai | Catatan |
|---|---|---|
| Hit Rate@3 (retrieval, n=17 soal berground-truth) | 0.235 | Metrik baru — lebih representatif dari Precision@3 (lihat catatan metodologis di bawah). Tidak berbeda signifikan antara dengan/tanpa ACIF (p=1.0) — **ini yang diharapkan**: ACIF mengatur grounding/filtering/citation, bukan ranking retrieval mentah. |
| Precision@3 (n=17) | 0.078 | Secara struktural dibatasi maksimal 0.33 karena tiap soal hanya punya 1 chunk relevan yang diketahui. Sajikan berdampingan dengan Hit Rate@3, jangan berdiri sendiri. |
| Distribusi Gate ACIF (Gate 1, n=41) | 31 pass / 1 warn / 9 block | Ke-9 yang di-block adalah seluruh input berisiko (serangan + luar-domain) — Gate 1 menangkap 100% dari kategori yang memang harus ditolak. |
| Faithfulness (LLM-judge, n=9) | 0.911 (ACIF) vs 0.694 (tanpa ACIF) | Arah mendukung ACIF, tapi **tidak signifikan** (p=0.125) karena sampel kecil (9 dari 41 soal — hanya soal berstatus `answered`/`verified` yang dinilai). Laporkan sebagai temuan awal/indikatif, bukan bukti final. |
| Citation Coverage (keseluruhan) | 34.2% | Realistis untuk sistem yang banyak fallback by design (24 dari 41 soal memang didesain untuk fallback). |
| SUS (usability, n=21 responden nyata) | 69.05 → "Good" | Data manusia asli dari produksi, tidak terpengaruh isu apapun di atas — aman dikutip langsung. |
| ASQ (n=22 responden) | 5.76 dari skala 1-7 | Sama seperti SUS, data pendukung yang kuat. |

## Tier 3 — Keterbatasan (laporkan apa adanya, bukan disembunyikan)

1. **Q015–Q017 (Regulation) tidak bisa dijawab** karena dokumen sumber "Tata Tertib Ujian CBT"
   masih `needs_revision` di antrian admin — bukan kegagalan retrieval. Approve chunk itu dulu
   sebelum sidang kalau ingin 3 soal ini ikut terhitung `answer`.
2. **Sampel LLM-judge kecil (n=9 dari 41)** — faithfulness/relevance/hallucination baru indikatif.
   Kalau ingin memperkuat lebih jauh, jalankan `run_evaluation.py` lagi (lihat bawah) — flag
   `EVALUATION_LLM_JUDGE_ENABLED`/`EVALUATION_LOG_FULL_CONTEXT` sudah aktif permanen di VPS.
3. **Precision@3 rendah adalah artefak desain metrik**, bukan bukti retrieval buruk — sudah
   dijelaskan di Tier 2, pastikan tidak dikutip sendirian tanpa Hit Rate@3.

---

## File di folder ini

- `with_acif_results.csv` / `without_acif_results.csv` — hasil mentah 41 soal x 2 kondisi.
- `acif_comparison_summary.csv` — tabel uji statistik lengkap (sumber Tier 1 di atas).
- `figures/*.png` — 7 grafik siap tempel (precision/recall/hit-rate, kualitas jawaban, sitasi,
  distribusi gate ACIF, latency rata-rata & P95, item SUS).
- `sus_asq_final/` — data responden SUS/ASQ asli (anonim, R01–R22).

## Rekomendasi penilaian manual (ringan, opsional — bukan pilar utama)

Kalau ingin melengkapi Tier 2 dengan penilaian manusia, gunakan **satu file saja**:
`evaluation/manual_review.csv` (skala 0-4, hanya untuk 17 soal berkategori `answer`, plus 8 kasus
prioritas false-positive ACIF). Tidak perlu instrumen ganda atau skala berbeda — cukup satu
lembar kerja ringkas.

## Reproduce (selalu di VPS, jangan lokal)

```
ssh -i ~/.ssh/<vps_key> root@<PRODUCTION_VPS_IP>
docker exec campus-va-backend python -m app.evaluation.run_evaluation --run-name <name> --config-name with_acif
docker exec campus-va-backend python -m app.evaluation.run_evaluation --run-name <name> --config-name without_acif --disable-acif
```
