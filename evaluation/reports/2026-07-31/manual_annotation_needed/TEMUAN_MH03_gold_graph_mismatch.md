# Temuan: Ketidaksesuaian Ground Truth vs Graf Produksi pada Pertanyaan MH03

## Ringkasan

Selama verifikasi *path correctness* untuk pertanyaan multi-hop GraphRAG (MH01–MH06), ditemukan
bahwa jawaban *ground truth* (gold dataset) untuk pertanyaan **MH03** **tidak sesuai** dengan
struktur graf Neo4j produksi yang sebenarnya, saat diverifikasi langsung dengan Cypher query pada
2026-07-31.

## Pertanyaan

> "Program studi D-III Kesehatan Gigi dan D-III Sanitasi hanya bisa didaftar melalui jalur
> pendaftaran apa?"

## Jawaban Ground Truth (gold dataset, `graphrag_multihop_dataset.jsonl`)

> "Kedua program studi tersebut (D-III Kesehatan Gigi dan D-III Sanitasi) **hanya** tersedia
> melalui jalur SPMB Prestasi, tidak tersedia di jalur pendaftaran SPMB lainnya."

## Temuan Aktual (verifikasi langsung ke Neo4j produksi)

Query yang dijalankan:
```cypher
MATCH (p:ProgramStudi)-[:TERSEDIA_PADA]->(j:JalurPendaftaran)
RETURN p.name, j.name ORDER BY p.name, j.name;
```

Hasil untuk kedua program studi tersebut:

| Program Studi | Jalur Pendaftaran (edge `TERSEDIA_PADA` yang benar-benar ada di graf) |
|---|---|
| D-III Kesehatan Gigi | **SPMB Mandiri Reguler SMA**, SPMB Prestasi |
| D-III Sanitasi | **SPMB Mandiri Reguler SMA**, SPMB Prestasi |

Kedua program studi ternyata memiliki **2 jalur pendaftaran**, bukan 1 (hanya SPMB Prestasi)
seperti yang diklaim ground truth. Graf produksi menunjukkan mereka juga tersedia melalui **SPMB
Mandiri Reguler SMA**.

## Implikasi

Ini adalah temuan nyata (bukan kesalahan pengukuran), dengan dua kemungkinan penyebab yang belum
dapat dipastikan salah satu tanpa pemeriksaan lebih lanjut terhadap dokumen sumber asli:

1. **Ground truth (gold dataset) yang keliru** — penyusun dataset mungkin salah mengasumsikan
   eksklusivitas "hanya SPMB Prestasi" tanpa memverifikasi seluruh 5 jalur dokumen secara silang.
2. **Ekstraksi graf yang keliru** — `GraphService.extract_entities` (berbasis regex/keyword)
   mungkin salah menghasilkan edge `TERSEDIA_PADA` dari D-III Kesehatan Gigi/Sanitasi ke dokumen
   "SPMB Mandiri Reguler SMA" padahal program studi tersebut sebenarnya tidak disebutkan di
   dokumen itu (mis-atribusi entitas lintas dokumen).

**Tidak diinvestigasi lebih lanjut pada sesi ini** (di luar cakupan pengumpulan data) — perlu
pembacaan langsung dokumen sumber "Pedoman SPMB Mandiri Reguler SMA" untuk memastikan apakah D-III
Kesehatan Gigi/Sanitasi benar-benar disebutkan di sana atau tidak.

## Rekomendasi Penulisan untuk Skripsi

Sebagai catatan metodologis pilihan Anda ("muat sebagai temuan"), sarankan menuliskannya di bagian
**keterbatasan (limitations)** evaluasi GraphRAG, contoh kerangka kalimat:

> "Pada evaluasi *path correctness* terhadap 6 pertanyaan multi-hop GraphRAG, ditemukan 1 kasus
> (MH03) di mana jawaban *ground truth* tidak sepenuhnya konsisten dengan struktur graf produksi
> aktual — graf menunjukkan D-III Kesehatan Gigi dan D-III Sanitasi tersedia melalui 2 jalur
> pendaftaran (SPMB Mandiri Reguler SMA dan SPMB Prestasi), bukan hanya 1 jalur seperti yang
> diasumsikan pada dataset evaluasi. Temuan ini mengindikasikan perlunya proses validasi silang
> yang lebih ketat antara *ground truth* manual dan graf pengetahuan otomatis pada tahap
> penyusunan dataset evaluasi, dan/atau perlunya audit lebih lanjut terhadap keakuratan proses
> ekstraksi entitas berbasis regex/keyword pada `GraphService`."

Dengan pembingkaian ini, **Path Correctness dilaporkan 4/5 (80%) pada item yang diperiksa langsung**
(MH01, MH02, MH04, MH06 benar; MH03 salah), dengan MH03 didiskusikan secara eksplisit sebagai
temuan/keterbatasan, bukan disembunyikan atau dihitung sebagai kegagalan sistem semata.
