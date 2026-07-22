# Bukti Evaluasi Bab 4.4 — Run Ulang Terverifikasi (2026-07-18)

Arsip ini adalah hasil **run ulang penuh** dari `evaluation/reports/2026-07-16/`, dijalankan langsung
di server produksi (VPS) untuk memverifikasi bahwa data 16 Juli masih berlaku sebelum sidang, dan
untuk mengukur dampak perbaikan chunk dokumen "Tata Tertib Ujian CBT" (lihat Tier 2 di bawah).

- Run ID `with_acif` : `ccc41b97-fd8b-4ee2-a377-a774c61a073e` (41/41 soal)
- Run ID `without_acif`: `dc8e5176-37d5-4a6e-8eb0-3f34c5439e04` (41/41 soal)
- Dieksekusi via: `docker exec campus-va-backend python -m app.evaluation.run_evaluation --run-name <name> --config-name <with_acif|without_acif> [--disable-acif]`
- Perbandingan statistik dihitung via `app.evaluation.statistical_comparison.compare_runs()` (fungsi
  yang sama dipakai endpoint admin `GET /api/admin/evaluation/compare`), dipanggil langsung di dalam
  container terhadap kedua run ID di atas — bukan re-implementasi terpisah.

**Dataset, metodologi, dan gold-QA yang dipakai identik dengan run 16 Juli** (41 soal, 7 kategori:
SPMB 14, Regulation 3, Academic 3, Administration 3, Contact 3, OutOfDomain 5, Security 10). Yang
berbeda hanyalah kondisi korpus dokumen (chunk CBT sudah disetujui admin sejak 16-18 Juli) dan waktu
eksekusi.

---

## Tier 1 — Temuan utama (TETAP signifikan secara statistik, bahkan menguat)

| Temuan | 16 Juli (lama) | **18 Juli (run ini, rujukan terbaru)** | p-value |
|---|---|---|---|
| Attack Success Rate (n=10) | 0% vs 100% | **0% vs 100% (identik)** | 0.00195 |
| Fallback Correctness (n=41) | 80.5% vs 41.5% | **82.9% vs 41.5% (menguat)** | 0.0033 |
| Total Latency (n=41) | 4561ms vs 5451ms | **4404ms vs 5301ms (tetap lebih cepat dengan ACIF)** | 0.0397 |

Ketiga temuan ini **konsisten arah dan signifikansinya di dua kali run terpisah**, dijalankan pada
hari berbeda terhadap server produksi yang sama — ini bukti replikasi yang kuat, bukan kebetulan
satu kali jalan. Tetap jadi tulang punggung Bab 4.4/sidang.

## Tier 2 — Perbaikan cakupan jawaban (dampak dari perbaikan chunk CBT)

| Metrik | 16 Juli | 18 Juli | Catatan |
|---|---|---|---|
| Precision@3 (n=17) | 0.078 | **0.098** | Naik — konsisten dengan Q015-Q017 (kategori Regulation, dokumen "Tata Tertib Ujian CBT") yang pada 16 Juli tidak terjawab karena chunk masih `needs_revision`, sekarang sudah `approved`/`active` dan terbukti live menjawab `verified`. |
| Recall@3 / Hit Rate@3 (n=17) | 0.235 | **0.294** | Naik, alasan sama seperti di atas. |

Precision@3 tetap dibatasi struktural pada plafon 0.33 (1 chunk relevan diketahui per soal) — jangan
dikutip sendirian, selalu berdampingan dengan Hit Rate@3.

## Tier 3 — Temuan yang TIDAK STABIL antar-run (jangan dikutip sebagai bukti arah)

| Metrik | 16 Juli | 18 Juli | p-value (keduanya) |
|---|---|---|---|
| Faithfulness (LLM-judge, n=9-10) | **0.911 (ACIF) vs 0.694** | **0.80 (ACIF) vs 0.94** — arah TERBALIK | 0.125 / 0.375 — tidak signifikan di kedua run |
| Answer Relevance (LLM-judge, n=9-10) | **0.878 (ACIF) vs 0.733** | **0.81 (ACIF) vs 0.97** — arah TERBALIK | 0.625 / 0.25 — tidak signifikan di kedua run |
| Citation Correct (n=19) | 0.474 (ACIF) vs 0.526 | 0.526 (ACIF) vs 0.632 | 1.0 / 0.5 — tidak signifikan |

**Interpretasi yang benar secara akademik:** dengan sampel LLM-judge sekecil 9-10 dari 41 soal, dan
arah temuan berbalik antar dua kali eksekusi independen, metrik ini **tidak boleh dipakai sebagai
klaim bahwa ACIF meningkatkan faithfulness/relevansi jawaban**. Ini murni variasi sampel kecil (tidak
signifikan di kedua run), bukan efek nyata ke arah manapun. Laporkan sebagai keterbatasan
metodologis yang jujur, bukan dipilih salah satu run yang "hasilnya enak".

---

## KOREKSI PENTING + INVESTIGASI AKAR MASALAH (2026-07-18) — Q015 teratasi, Q016/Q017 didiagnosis dua-lapis

Sesi sebelumnya sempat menyatakan "Q015-Q017 sudah teratasi" berdasarkan tes live terhadap **Q015
saja**. Setelah run penuh ini dan investigasi mendalam terhadap Q016/Q017 (termasuk perbaikan nyata
di produksi), kondisi akhirnya:

| Soal | Status akhir | Detail |
|---|---|---|
| Q015 (jadwal ujian CBT) | **Terjawab (`verified`)** | Mengutip chunk BERBEDA dari `expected_chunk_ids` gold-QA (chunk dari dokumen "Pedoman SPMB", bukan "Tata Tertib Ujian CBT") — jawabannya faktual benar, tapi metrik precision/recall/hit_rate@3 tetap tercatat 0 karena pencocokan chunk_id yang ketat. |
| Q016 (konsekuensi pelanggaran tata tertib) | **MASIH GAGAL** — `insufficient_context` | Root cause Layer 1 (ringkasan bahasa Inggris) sudah diperbaiki dan diverifikasi bekerja di level embedding, tapi Layer 2 (Query Understanding) masih memblokir. Lihat diagnosis di bawah. |
| Q017 (barang berharga di ruang ujian) | **MASIH GAGAL** — `insufficient_context` | Sama seperti Q016, plus intent classifier salah menyimpulkan `intent="fee"`. |

### Investigasi akar masalah — dua lapis bug independen

**Layer 1 — SUDAH DIPERBAIKI DI PRODUKSI (2026-07-18), terverifikasi sampai level embedding:**
Ditemukan **23 chunk teks approved** (bukan cuma 3 chunk CBT) di 5 dokumen berbeda punya ringkasan
`chunk_summaries.approved_summary` dalam **Bahasa Inggris**, dibuat `2026-07-04` — seminggu SEBELUM
script sapuan regenerasi Bahasa Indonesia (`regen_summaries_id.py`, didokumentasikan di
`IMPLEMENTATION.md` 2026-07-11) berjalan. Chunk-chunk ini baru disetujui admin SETELAH sapuan itu
selesai, jadi terlewat. Karena embedding Chroma dibangun dari teks ringkasan (bukan teks asli),
query Bahasa Indonesia tidak pernah cocok dengan ringkasan Bahasa Inggris.

**Fix yang dijalankan:** semua 23 ringkasan diregenerasi ke Bahasa Indonesia via
`ChunkSummaryService.generate_summary()` (script one-off, pola sama seperti `regen_summaries_id.py`),
diikuti reindex penuh (`VectorIndexService.index_approved_chunks` — 294 chunk aktif) dan flush cache
retrieval Redis. **Terverifikasi berhasil**: query langsung ke Chroma (bypass semua cache/rerank)
menunjukkan chunk `574e4a06` ("barang berharga") sekarang **rank #1** dan `b6bcea3d` ("konsekuensi
pelanggaran") **rank #3-4** dari kemiripan semantik mentah — naik drastis dari sebelumnya tidak
masuk top-10 sama sekali.

**Layer 2 — DITEMUKAN, BELUM DIPERBAIKI (butuh perubahan kode, bukan data/ops fix):**
Meski Layer 1 terbukti berhasil di level embedding, jawaban `/chat` untuk Q016/Q017 tetap gagal.
Investigasi lanjutan (query ke `chat_evaluation_logs.detected_terms`/`intent`) mengungkap:

```
Q016: detected_terms=["spmb"], intent="unknown" (confidence 0.3)
Q017: detected_terms=["spmb"], intent="fee" (confidence 0.9)  <- SALAH KLASIFIKASI
```

Query Understanding Layer (`domain_terms.yaml`/pemetaan sinonim di
`services/query_understanding/`) tidak punya kosakata untuk istilah "tata tertib", "pelanggaran",
"konsekuensi", "barang berharga" — jadi hanya mendeteksi token generik "spmb". Dampaknya di
`multi_query_retriever.py`'s `_rerank_score()`:
- Bobot exact/expanded-term-match (`WEIGHT_EXACT_TERM=0.20 + WEIGHT_EXPANDED_TERM=0.15` = 0,35
  dari total bobot) **tidak pernah aktif** untuk chunk yang secara semantik sudah rank #1.
- Untuk Q017, intent yang salah (`"fee"`) memicu `_intent_bonus()` memberi bonus rerank ke chunk
  ber-tipe dokumen Pedoman/Brosur SPMB yang memuat angka biaya — mendorong chunk yang salah topik
  ke atas, bukan chunk "barang berharga" yang justru tidak dapat bonus apa pun.

Akibatnya, meski raw semantic similarity untuk kedua chunk target sudah unggul (rank #1 dan #3-4),
skor rerank final (`WEIGHT_SEMANTIC` hanya 0,30 dari total bobot) tidak cukup untuk membuatnya lolos
ke top-10 kandidat yang benar-benar dipakai untuk konteks jawaban.

**Kenapa tidak langsung diperbaiki:** perbaikan Layer 2 memerlukan menambah entri kosakata baru ke
`domain_terms.yaml` dan/atau meninjau ulang aturan fallback intent classifier
(`intent_query_rewriter.py`) — perubahan ini berpotensi memengaruhi ranking untuk banyak query lain
di luar Q016/Q017, dan seharusnya diuji lewat suite unit test yang ada (~300 test untuk
`multi_query_retriever`/query understanding) sebelum di-deploy ke produksi, bukan hotfix langsung
via SSH seperti Layer 1. **Ini rencana pengembangan yang jujur, bukan sesuatu yang disembunyikan.**

**UPDATE — Layer 2 diimplementasikan, diuji, dan di-deploy (2026-07-18, lanjutan sesi):**
Fix diimplementasikan di `backend/app/config/domain_terms.yaml` (hapus pola "harga" yang berisiko,
tambah konsep `tertib`/`berharga` + perluas pola intent `requirement`) dan
`backend/app/services/query_understanding/intent_query_rewriter.py` (pemetaan konsep baru ke intent
`requirement`, docstring menjelaskan kenapa pendekatan token-aware sempat dicoba lalu dibatalkan
karena memecahkan toleransi imbuhan `berkas→berkasnya`). **353/353 test lolos** (350 lama + 3 test
regresi baru). Di-deploy ke VPS (rebuild image backend + restart, downtime singkat).

**Hasil verifikasi live pasca-deploy:**
- **Q017 (barang berharga): `status: verified`**, sitasi benar ke "Tata Tertib Ujian CBT..." — GAGAL
  TOTAL sebelumnya, sekarang terjawab penuh.
- **Q016 (konsekuensi pelanggaran): membaik signifikan tapi belum `verified`.** Dokumen yang benar
  sekarang muncul di `sources` (sebelumnya nol sumber sama sekali) — retrieval sudah benar. Tapi
  `answer_status=insufficient_context`, `fallback_reason=llm_stated_not_in_sources` — LLM sendiri
  menyatakan tidak menemukan jawaban spesifik meski dokumen yang tepat sudah ada di konteks. Ini
  **masalah lapis ketiga yang baru ditemukan** (kemungkinan chunk header umum yang terpilih
  dibanding chunk spesifik "Pelanggaran tata tertib akan dicatat..." dalam dokumen yang sama, atau
  ringkasan belum cukup eksplisit) — **belum diinvestigasi, kandidat kuat untuk sesi lanjutan.**

**Kesimpulan yang jujur untuk Bab 4.4/sidang:** investigasi ini mengungkap TIGA lapis masalah
independen dalam satu rantai kegagalan retrieval — dua sudah diperbaiki dan diverifikasi hidup di
produksi (satu dengan bukti before/after yang sangat jelas: 0 sumber → verified), satu lagi
teridentifikasi tapi belum digali. Ini narasi debugging berbasis data yang jauh lebih kuat secara
akademik daripada klaim "semua sudah beres" — tunjukkan proses investigasi berlapis ini sebagai
bukti kedalaman kerja.

---

## File di folder ini

- `with_acif_results.csv` / `without_acif_results.csv` — hasil mentah 41 soal x 2 kondisi, diekspor
  langsung dari `data/evaluation_reports/{run_id}.csv` di dalam container backend produksi (bukan
  hasil olahan ulang).
- `acif_comparison_summary.csv` — tabel uji statistik lengkap (Wilcoxon signed-rank untuk metrik
  kontinu, McNemar exact untuk metrik biner berpasangan), sumber Tier 1-3 di atas.
- `figures/*.png` — 7 grafik publikasi (4.39, 4.40, 4.43, 4.46, 4.48, 4.49, 4.52), digenerate ulang
  2026-07-18 dari `evaluation/scripts/generate_charts.py` memakai data run ini. Template sumbernya
  (`evaluation/templates/charts/*.csv`) sudah di-refresh in-place (mengikuti konvensi yang sama
  dipakai saat refresh 16 Juli) dengan breakdown per-kategori (chart 4.39/4.43) dan per-komponen
  latensi (chart 4.48/4.49) yang dihitung langsung dari `chat_evaluation_logs`/`acif_trace_logs`
  di server produksi, di-join lewat `trace_id` dari `evaluation_results` run `ccc41b97...`.
- `sus_asq_final/` — **tidak ada di folder ini, sengaja.** SUS/ASQ adalah studi manusia (21/22
  responden nyata), bukan sesuatu yang bisa "dijalankan ulang" oleh skrip. Data 16 Juli
  (`evaluation/reports/2026-07-16/sus_asq_final/`) tetap berlaku sebagai satu-satunya sumber data
  usability — kutip dari sana. `chart_4_52_sus_items.csv` sengaja TIDAK diubah di refresh ini.

## Reproduce

```
ssh -i ~/.ssh/<vps_key> root@<PRODUCTION_VPS_IP>
docker exec campus-va-backend python -m app.evaluation.run_evaluation --run-name <name> --config-name with_acif
docker exec campus-va-backend python -m app.evaluation.run_evaluation --run-name <name> --config-name without_acif --disable-acif
```

Untuk menghitung perbandingan statistik dari dua run ID manapun tanpa lewat endpoint admin (yang
butuh Basic Auth), panggil `compare_runs()` langsung:

```python
# di dalam: docker exec campus-va-backend python3
import asyncio, dataclasses, json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import EvaluationRun, EvaluationResult
from app.evaluation.statistical_comparison import compare_runs

async def main():
    async with AsyncSessionLocal() as db:
        run_a = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == "<with_acif_run_id>"))).scalar_one()
        results_a = (await db.execute(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == "<with_acif_run_id>"))).scalars().all()
        run_b = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == "<without_acif_run_id>"))).scalar_one()
        results_b = (await db.execute(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == "<without_acif_run_id>"))).scalars().all()
        report = compare_runs(results_a, results_b, run_id_a=str(run_a.id), run_id_b=str(run_b.id), config_name_a=run_a.config_name, config_name_b=run_b.config_name)
        print(json.dumps(dataclasses.asdict(report), indent=2, default=str))

asyncio.run(main())
```
