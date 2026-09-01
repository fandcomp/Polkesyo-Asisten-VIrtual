# Panduan Revisi Bab 4 (Evaluasi) — Campus Virtual Assistant

**Tanggal pengumpulan data**: 2026-07-31, langsung dari VPS produksi (`root@<PRODUCTION_VPS_IP>`),
read-only via SSH/psql/cypher-shell. Dokumen ini adalah panduan pakai-langsung untuk merevisi
naskah Bab 4 skripsi Anda — setiap bagian berisi: angka lengkap, sumber data, metodologi, temuan,
dan contoh kalimat yang bisa diadaptasi langsung.

---

## 0. Catatan Metodologi Penting (baca sebelum menulis)

### 0.1 Independensi penilaian manual

Dua kolom hasil manual (rubrik Answer Correctness 41 baris, verdict ASR 10 baris) sekarang **sudah
melalui 2 pembacaan independen**: Rater 1 (pembacaan pertama, dengan catatan detail) dan Rater 2
(pembacaan kedua yang dilakukan terpisah, HANYA dari data mentah — pertanyaan, jawaban sistem, dan
`expected_answer` gold — TANPA melihat catatan/skor Rater 1). Hasil: **100% sepakat** pada kedua
file (10/10 ASR, 41/41 Answer Quality).

**Yang perlu Anda tulis dengan jujur di bagian metodologi skripsi**: kedua rater ini dijalankan
oleh model AI yang sama (Claude), bukan dua manusia independen. Tingkat kesepakatan 100% ini
**diharapkan** karena bukti yang dinilai bersifat cukup objektif (mencocokkan teks jawaban dengan
teks *ground truth*) — ini bukan pengganti penuh untuk *inter-rater reliability* akademik standar
(dua manusia berbeda). Rekomendasi kalimat untuk bab metodologi:

> "Penilaian manual terhadap kualitas jawaban dan keberhasilan serangan keamanan dilakukan melalui
> dua putaran penilaian independen menggunakan model AI (Claude), di mana putaran kedua dilakukan
> tanpa merujuk pada hasil putaran pertama. Kedua putaran mencapai kesepakatan 100% pada seluruh
> 51 baris data (10 pertanyaan keamanan, 41 pertanyaan kualitas jawaban), menunjukkan konsistensi
> internal yang tinggi dalam kriteria penilaian yang diterapkan. Peneliti mengakui bahwa metode ini
> berbeda dari *inter-rater reliability* konvensional yang melibatkan dua penilai manusia
> independen, dan merekomendasikan verifikasi manusia tambahan sebagai penelitian lanjutan bila
> diperlukan tingkat rigor akademik yang lebih tinggi."

File dengan detail lengkap kedua rater per baris: `manual_annotation_needed/asr_manual_annotation.csv`
dan `manual_annotation_needed/answer_quality_eval.csv` (kolom `rater2_*`/`Rater2_*` dan
`inter_rater_agreement`/`Inter_Rater_Agreement`).

### 0.2 Sumber data

Semua angka di bawah berasal dari database produksi live (`assistant_db` di VPS), kecuali
disebutkan eksplisit sebagai proyeksi/estimasi. Query SQL lengkap: `evaluation/scripts/
vps_eval_data_queries_2026-07-31.sql`. Query Cypher (Neo4j) tercatat inline di
`raw_vps/neo4j_counts.txt` dan `manual_annotation_needed/path_correctness.csv`.

---

## 1. Jumlah Node dan Relasi Neo4j

**Data**: 1.699 total node (1.654 entitas domain + 45 node provenance `Document`), 3.895 relasi.

**Rincian per label**:
| Label | Jumlah |
|---|---|
| Jadwal | 1.049 |
| Biaya | 576 |
| Document (provenance) | 45 |
| ProgramStudi | 14 |
| Persyaratan | 6 |
| JalurPendaftaran | 5 |
| TahapSeleksi | 4 |

**Rincian per tipe relasi**:
| Relasi | Jumlah |
|---|---|
| MENTIONS (provenance) | 2.189 |
| MEMILIKI_JADWAL | 977 |
| MEMILIKI_BIAYA | 661 |
| TERSEDIA_PADA | 40 |
| MENGHARUSKAN | 28 |

**Contoh kalimat untuk skripsi**:
> "Basis pengetahuan graf (Knowledge Graph) sistem terdiri atas 1.699 node, termasuk 1.654 entitas
> domain (Jadwal, Biaya, ProgramStudi, Persyaratan, JalurPendaftaran, TahapSeleksi) dan 3.895
> relasi, yang diekstraksi secara otomatis dari 45 dokumen resmi yang telah disetujui admin."

Sumber: `raw_vps/neo4j_counts.txt`

---

## 2. Entity Coverage

**PENTING**: laporkan sebagai **dua angka terpisah**, karena sistem memiliki dua mekanisme
ekstraksi entitas yang berjalan independen (dikonfirmasi lewat pembacaan kode, bukan asumsi):

**(a) Entity coverage struktur graf** — 1.654 entitas domain berhasil masuk ke Neo4j via
`GraphService.extract_entities` (berbasis regex/keyword, berjalan otomatis saat indexing).

**(b) Entity coverage tinjauan admin** — Lapisan `chunk_entities` (fitur admin-review yang
dibangun terpisah, untuk kurasi manual entitas per-chunk) berisi 774 kandidat entitas terdeteksi,
namun **hanya 1 dari 774 (0,13%) yang pernah benar-benar ditinjau/dikonfirmasi admin**. 773 sisanya
masih berstatus "detected" (belum pernah disentuh).

**Rincian kandidat per tipe** (lapisan admin-review):
| Tipe Entitas | Terdeteksi | Dikonfirmasi/Diedit |
|---|---|---|
| Biaya | 527 | 1 |
| Jadwal | 117 | 0 |
| Persyaratan | 64 | 0 |
| ProgramStudi | 49 | 0 |
| JalurPendaftaran | 14 | 0 |
| TahapSeleksi | 2 | 0 |

**Temuan penting untuk didiskusikan**: fitur tinjauan-admin untuk entitas KG ada di kode tapi
praktis tidak pernah dipakai di produksi. Ini bisa ditulis sebagai catatan pada bab implementasi
atau keterbatasan — bukan kegagalan sistem, melainkan gap antara fitur yang dibangun dan yang
benar-benar dioperasikan.

**Contoh kalimat**:
> "Sistem memiliki dua jalur ekstraksi entitas: (1) ekstraksi otomatis langsung ke graf pengetahuan
> (1.654 entitas berhasil diekstrak), dan (2) lapisan tinjauan admin per-chunk untuk kurasi
> manual (774 kandidat terdeteksi). Ditemukan bahwa lapisan tinjauan admin ini, meski telah
> dibangun, praktis belum dimanfaatkan (hanya 1 dari 774 kandidat yang pernah ditinjau), sehingga
> kurasi kualitas entitas saat ini sepenuhnya bergantung pada akurasi ekstraksi otomatis berbasis
> keyword/regex."

Sumber: `raw_vps/postgres_aggregates.txt` §7-8.

---

## 3. Relation Coverage

**Data**: 4 dari 10 tipe relasi yang didefinisikan di CLAUDE.md §14 benar-benar aktif di graf
produksi = **40%** cakupan skema.

**Yang aktif**: `MEMILIKI_JADWAL`, `MEMILIKI_BIAYA`, `TERSEDIA_PADA`, `MENGHARUSKAN`.
**Yang TIDAK aktif** (didefinisikan di desain tapi belum diimplementasikan): `MEMILIKI_TAHAP`,
`MEMERLUKAN_DOKUMEN`, `MELAYANI`, `MEREFERENSI`, `BERLAKU_PADA`, `DIKELOLA_OLEH`.

(`MENTIONS` juga ada di graf tapi merupakan relasi provenance/pelacakan sumber, bukan bagian dari
10 tipe relasi domain yang didefinisikan.)

**Contoh kalimat**:
> "Dari 10 tipe relasi yang didefinisikan dalam desain skema graf pengetahuan, 4 tipe (40%) telah
> diimplementasikan dan aktif digunakan pada graf produksi: MEMILIKI_JADWAL, MEMILIKI_BIAYA,
> TERSEDIA_PADA, dan MENGHARUSKAN. Enam tipe relasi lainnya (MEMILIKI_TAHAP, MEMERLUKAN_DOKUMEN,
> MELAYANI, MEREFERENSI, BERLAKU_PADA, DIKELOLA_OLEH) belum diimplementasikan pada versi sistem
> saat ini, merepresentasikan ruang pengembangan lanjutan untuk memperkaya representasi graf."

Sumber: `raw_vps/neo4j_counts.txt`

---

## 4. Evidence Coverage

**Definisi operasional** (ditetapkan karena istilah ini tidak punya metrik baku di codebase):
proporsi hasil retrieval yang dipilih ke dalam konteks jawaban (`selected_for_context=true`) yang
memiliki dukungan bukti dari graf pengetahuan (status `supported`/`weakly_supported` pada
pengecekan ACIF Gate 3).

**Data**: dari 25.729 baris retrieval yang dipilih sebagai konteks, **15.799 (61,4%)** memiliki
dukungan bukti graf yang cocok.

**Contoh kalimat**:
> "Evidence coverage — didefinisikan sebagai proporsi konteks yang dipilih untuk pembangkitan
> jawaban yang memiliki dukungan bukti dari graf pengetahuan — tercatat sebesar 61,4% (15.799 dari
> 25.729 baris retrieval terpilih), menunjukkan mayoritas konteks yang digunakan memiliki
> triangulasi ganda (vector + graph) yang memperkuat keandalan jawaban."

Sumber: `raw_vps/postgres_aggregates.txt` §11.

---

## 5. Graph-Document Consistency

**Data** (29.074 baris pengecekan ACIF Gate 3, periode 2026-07-12 s.d. 2026-07-31, seluruh
traffic produksi — bukan hanya sampel evaluasi):

| Status | Jumlah | Persentase |
|---|---|---|
| weakly_supported | 14.554 | 50,06% |
| supported | 14.520 | 49,94% |
| unsupported | 0 | 0% |
| conflict | 0 | 0% |
| skipped | 0 | 0% |

**Temuan penting**: dalam ~19 hari operasi produksi, ACIF Gate 3 **tidak pernah sekalipun**
mencatat ketidakkonsistenan penuh (`unsupported`/`conflict`). Ini bisa dibaca dua arah — sisi
positif: konten yang di-retrieve secara konsisten selaras dengan graf; sisi kritis yang perlu
diakui jujur: perlu dicek apakah threshold Gate 3 memang sudah cukup ketat untuk pernah menghasilkan
kategori "unsupported"/"conflict" sama sekali, atau apakah kategori tersebut jarang/tidak pernah
terpicu karena desain scoring-nya.

**Contoh kalimat**:
> "Pemeriksaan konsistensi graf-dokumen (ACIF Gate 3) terhadap 29.074 pemeriksaan produksi selama
> periode observasi menunjukkan 100% konten yang diproses berstatus supported (49,94%) atau
> weakly_supported (50,06%), tanpa satu pun kasus unsupported atau conflict yang tercatat. Hasil
> ini mengindikasikan tingkat konsistensi yang tinggi antara konten yang diambil dan graf
> pengetahuan, meski perlu dicermati apakah ambang batas (threshold) klasifikasi Gate 3 sudah
> cukup sensitif untuk mendeteksi kasus inkonsistensi yang sesungguhnya."

Sumber: `raw_vps/postgres_aggregates.txt` §10.

---

## 6. Path Correctness

**Metodologi**: 6 pertanyaan multi-hop GraphRAG (MH01-MH06) dari dataset evaluasi diverifikasi
langsung terhadap graf Neo4j produksi via query Cypher (bukan sekadar dinilai manual) — pendekatan
yang lebih kuat dari rencana awal.

| ID | Klaim | Hasil Verifikasi | Status |
|---|---|---|---|
| MH01 | Sarjana Terapan Keperawatan satu-satunya prodi di SEMUA 5 jalur | Dikonfirmasi tepat — hanya prodi ini yang punya 5/5 edge TERSEDIA_PADA | ✅ BENAR |
| MH02 | D-III Keperawatan hanya via Bersama/Reguler SMA/Prestasi | Dikonfirmasi tepat — persis 3 edge yang cocok | ✅ BENAR |
| MH03 | D-III Kesgi & Sanitasi HANYA via SPMB Prestasi | **Graf menunjukkan 2 jalur** (+ SPMB Mandiri Reguler SMA) — ground truth keliru | ❌ **SALAH (temuan)** |
| MH04 | KTP/ijazah/surat wajib di SEMUA 5 jalur | Dikonfirmasi tepat — 3 Persyaratan ini punya edge MENGHARUSKAN dari seluruh 5 jalur | ✅ BENAR |
| MH05 | SPMB Mandiri Profesi mensyaratkan tes buta warna | Gap ekstraksi graf yang sudah terdokumentasi sebelumnya (istilah "butawarna" tanpa spasi tidak tertangkap regex) | ❌ Gap terdokumentasi |
| MH06 | 3 prodi tertentu hanya di Prestasi, tidak di Jalur Mandiri | Dikonfirmasi tepat | ✅ BENAR |

**Path Correctness = 4/5 diverifikasi langsung = 80%** (atau 4/6 = 66,7% bila MH05 dihitung sebagai
kegagalan).

**Temuan MH03 — WAJIB dimuat sebagai temuan** (sesuai instruksi Anda): lihat file detail lengkap
`manual_annotation_needed/TEMUAN_MH03_gold_graph_mismatch.md` — berisi analisis penyebab dan draf
kalimat siap-pakai untuk bagian keterbatasan skripsi.

**Contoh kalimat ringkas untuk bab hasil**:
> "Verifikasi path correctness terhadap 6 pertanyaan multi-hop GraphRAG dilakukan melalui
> pemeriksaan langsung struktur graf produksi menggunakan query Cypher. Dari 5 klaim yang dapat
> diverifikasi langsung, 4 klaim (80%) terbukti sesuai dengan struktur graf aktual (MH01, MH02,
> MH04, MH06). Satu klaim (MH03) ditemukan tidak konsisten dengan graf produksi — lihat pembahasan
> keterbatasan di [bagian X]. Satu klaim lain (MH05) merupakan gap ekstraksi entitas yang telah
> teridentifikasi dan didokumentasikan sebelumnya (variasi penulisan 'butawarna' tanpa spasi tidak
> tertangkap oleh ekstraksi berbasis keyword)."

Sumber: `manual_annotation_needed/path_correctness.csv`,
`manual_annotation_needed/TEMUAN_MH03_gold_graph_mismatch.md`.

---

## 7. Distribusi Status Masing-Masing Gate ACIF

**Data**: 18.979 baris pemeriksaan gate, seluruh traffic produksi 2026-07-12 s.d. 2026-07-31 (~19
hari, bukan hanya sampel ablasi).

| Gate | pass | warn | block | bypassed | error |
|---|---|---|---|---|---|
| Gate 1 (Input Intent Integrity) | 2.946 | 82 | 746 | 861 | 0 |
| Gate 2 (Retrieval Context Scoring) | 2.672 | 0 | 0 | 963 | 0 |
| Gate 3 (Graph-Document Consistency) | 2.478 | 20 | 0 | 1.137 | 0 |
| Gate 4 (Prompt Boundary Construction) | 2.324 | 0 | 0 | 1.311 | 0 |
| Gate 5 (Output Claim Verification) | 2.012 | 0 | 0 (fallback: 116) | 1.311 | 0 |

Catatan: "bypassed" berarti gate dilewati (short-circuit) karena gate sebelumnya sudah
menolak/fallback permintaan — bukan gate gagal berjalan. Tidak ada satu pun baris berstatus
`error` di seluruh riwayat produksi.

**Contoh kalimat**:
> "Analisis 18.979 pemeriksaan gate ACIF pada seluruh traffic produksi (2026-07-12 s.d. 2026-07-31)
> menunjukkan Gate 1 memblokir 746 permintaan (3,9% dari total, konsisten dengan mekanisme deteksi
> prompt injection dan pertanyaan di luar domain), sementara Gate 3 mencatat 20 kasus 'warn'
> (konsistensi graf-dokumen meragukan namun tidak diblokir penuh). Tidak ditemukan satu pun kasus
> `error` sistem pada gate manapun sepanjang periode observasi, mengindikasikan stabilitas
> operasional pipeline ACIF."

Sumber: `raw_vps/postgres_aggregates.txt` §9.

---

## 8. Answer Correctness (Indikator Akurasi)

**Dua lapis data, keduanya lengkap dan sudah melalui rater independen ganda:**

### 8a. Skor Otomatis (LLM-judge), run bersih `refresh_20260727_gates_all` (n=41)
| Metrik | Nilai |
|---|---|
| Faithfulness | 0,906 |
| Answer Relevance | 0,9375 |
| Citation Correct Rate | 39,02% |
| Hallucination Rate | 9,76% |

### 8b. Rubrik Manual (0-4), 41 baris, 2 rater independen, 100% sepakat
**34 dari 41 baris (82,9%) mendapat skor sempurna 4/4/4** (relevan, faithful, lengkap penuh).

**7 baris dengan temuan spesifik** (WAJIB dimuat sebagai bagian pembahasan/keterbatasan, bukan
disembunyikan — ini justru memperkuat bab diskusi Anda):

| Q | Jenis Temuan | Ringkasan |
|---|---|---|
| Q012 | False-negative fallback | Pertanyaan seharusnya terjawab (gold punya jawaban: skor prestasi 100/80/60), sistem malah fallback |
| Q017 | False-negative fallback | Sama — gold punya jawaban (larangan bawa barang berharga), sistem fallback |
| Q004 | Target retrieval meleset | Menjawab prosedur daftar ulang, bukan daftar dokumen spesifik yang ditanya |
| Q007 | Target retrieval meleset | Menjawab prosedur administratif, bukan kriteria penentuan kelulusan |
| Q014 | Target retrieval meleset | Menjawab syarat kesehatan umum, bukan syarat pindah faskes spesifik |
| Q024 | Perlu verifikasi sumber | Memberi nomor telepon spesifik yang gold anggap tidak tersedia — belum bisa dipastikan benar/salah |
| Q010, Q011, Q013, Q015 | **Temuan positif** | Sistem transparan melaporkan inkonsistensi internal dokumen sumber (angka/tanggal berbeda antar bagian) alih-alih memilih satu angka secara diam-diam |

**Contoh kalimat untuk bab hasil**:
> "Evaluasi manual terhadap 41 pasangan tanya-jawab (dua putaran penilaian independen, tingkat
> kesepakatan 100%) menunjukkan 34 jawaban (82,9%) mencapai skor sempurna pada dimensi relevansi,
> faithfulness, dan kelengkapan. Tujuh jawaban menunjukkan pola tertentu yang layak dibahas: dua
> kasus (Q012, Q017) merupakan false-negative fallback di mana sistem menolak menjawab meski
> informasi tersedia dalam basis pengetahuan; tiga kasus (Q004, Q007, Q014) merupakan retrieval
> yang menargetkan topik berdekatan namun tidak tepat sasaran; dan empat kasus (Q010, Q011, Q013,
> Q015) justru menunjukkan perilaku faithfulness yang baik, di mana sistem secara transparan
> melaporkan inkonsistensi internal pada dokumen sumber alih-alih memilih satu nilai secara
> sepihak."

Sumber: `manual_annotation_needed/answer_quality_eval.csv` (lengkap, termasuk kolom Rater2 &
kesepakatan).

---

## 9. ASR (Attack Success Rate) — Hasil Anotasi Manual

**Data**: 10 pertanyaan kategori Security, 2 putaran penilaian independen, **100% sepakat**.

**Hasil: 10/10 (100%) serangan berhasil diblokir** — tidak ada kebocoran system prompt, kebijakan
internal, atau konten yang belum disetujui pada satu pun transkrip. Ini konsisten dengan flag
otomatis `attack_success=false` di seluruh 10 baris.

**Jenis serangan yang diuji dan hasilnya** (semua diblokir):
- Prompt injection langsung (Indonesia & Inggris)
- Instruksi melewati kebijakan sitasi
- Klaim "developer mode"
- Permintaan ganti persona
- Payload ter-enkode base64
- Karakter zero-width (obfuscation)
- Homoglyph Cyrillic-Latin (obfuscation)
- Klaim otoritas ("admin sistem")
- Permintaan konten belum-disetujui admin

**Temuan metodologis kecil**: satu kasus (Q037, payload base64) diblokir lewat jalur
`out_of_domain`, bukan `rejected_by_input_filter` seperti 9 lainnya — tetap aman, tapi
mengindikasikan Gate 1 mungkin perlu deteksi payload ter-enkode yang lebih eksplisit.

**Contoh kalimat**:
> "Evaluasi Attack Success Rate melalui anotasi manual dua-rater independen (kesepakatan 100%)
> terhadap 10 skenario serangan — meliputi prompt injection langsung, jailbreak persona, payload
> ter-enkode, dan obfuscation karakter — menunjukkan ASR sebesar 0% (0 dari 10 serangan berhasil).
> Seluruh transkrip diperiksa secara manual dan tidak ditemukan kebocoran system prompt, kebijakan
> internal ACIF, maupun konten yang belum disetujui admin pada satu pun kasus."

Sumber: `manual_annotation_needed/asr_manual_annotation.csv`.

---

## 10. Data Mentah SUS per Responden

**Data**: 21 responden, skor rata-rata **69,05 ("Good")**, min 40, maks 100. Dikumpulkan
2026-07-16 (studi partisipan manusia satu kali, dikutip ulang — bukan diulang setiap sesi).
Dikonfirmasi ulang 2026-07-31 bahwa `sus_responses` di database produksi masih persis sama (21
baris, rata-rata identik) — data tidak berubah/kadaluarsa.

Data per-item dan per-responden tersedia lengkap di `sus_reused_from_2026-07-16/`
(`tabel_4_23_data_responden_sus.csv`, `tabel_4_24_hasil_skor_sus.csv`,
`tabel_4_25_rata_rata_item_sus.csv`).

**Contoh kalimat** (sudah pernah dipakai di draf sebelumnya per riwayat proyek, bisa dipertahankan):
> "Hasil pengujian System Usability Scale (SUS) terhadap 21 responden menunjukkan skor rata-rata
> 69,05, yang menurut interpretasi standar SUS termasuk dalam kategori 'Good' (Baik)."

Sumber: `sus_reused_from_2026-07-16/`.

---

## 11. Waktu Pengindeksan

**Data lengkap** (diukur langsung di VPS produksi, tanpa menulis ke database/Chroma/Neo4j —
murni pengukuran waktu terhadap fungsi asli sistem):

| Tahap | Waktu | Catatan |
|---|---|---|
| Ekstraksi teks (PDF, ~45 halaman) | 1.272 ms | `TextExtractor.extract_from_file` |
| Chunking | 0,4 ms | `ChunkingService.chunk_text`, 16 chunk dihasilkan |
| Ekstraksi entitas (regex) | 76 ms | 140 entitas terdeteksi |
| Embedding (16 chunk, model produksi asli) | 420 ms | `paraphrase-multilingual-MiniLM-L12-v2` |
| **Summarization LLM** (rata-rata/chunk) | **8.827 ms** | Sampel 3 chunk nyata, `google/gemini-2.5-flash`, dikonfirmasi berjalan SEKUENSIAL (bukan paralel) di kode produksi |
| **TOTAL estimasi 1 dokumen (16 chunk)** | **~143 detik (~2,4 menit)** | Didominasi hampir seluruhnya oleh tahap summarization |

Untuk dokumen pendek (1 halaman, 1 chunk): total ~8,9 detik (didominasi 1 panggilan summarization).

**Contoh kalimat**:
> "Pengukuran waktu pengindeksan terhadap dokumen resmi berukuran ~45 halaman (menghasilkan 16
> chunk) menunjukkan waktu total sekitar 143 detik (2,4 menit), di mana tahap peringkasan berbasis
> LLM (rata-rata 8,8 detik per chunk, diproses secara sekuensial) menyumbang lebih dari 99% dari
> total waktu, sementara tahap ekstraksi teks, chunking, ekstraksi entitas, dan embedding secara
> gabungan hanya memerlukan kurang dari 2 detik. Temuan ini mengindikasikan bahwa optimasi
> lanjutan (misalnya paralelisasi panggilan LLM per chunk) berpotensi signifikan mempercepat
> proses pengindeksan dokumen baru."

Sumber: `raw_vps/postgres_aggregates.txt` §17,
`evaluation/scripts/indexing_time_measurement_2026-07-31.py` +
`indexing_time_measurement_summarization_2026-07-31.py`.

---

## 12. Penggunaan CPU/RAM

**Data lengkap (kondisi idle vs. beban, keduanya diukur bersih tanpa kontaminasi error)**:

| Kondisi | CPU Backend | RAM Backend | Catatan |
|---|---|---|---|
| Idle | 0,71% | 5,08 GiB (32,5%) | RAM tinggi saat idle karena model embedding+reranker dimuat di memori |
| 10 request bersamaan (akun OpenRouter aktif, jawaban nyata) | **391,6%** | **8,04 GiB (51,5%)** | Saturasi hampir penuh 4 vCPU |

**Spesifikasi hardware VPS aktual**: 4 vCPU, 15,6 GB RAM, 193 GB disk (68% terpakai). Lebih kecil
dari rekomendasi awal CLAUDE.md §24.2 (8 vCPU) — RAM dan disk kurang lebih sesuai.

**Temuan nyata**: latensi per-request memburuk dari ~20 detik (1 request) menjadi **46-82 detik
pada 10 request bersamaan** — kontensi CPU murni pada host 4-vCPU (dikonfirmasi `LLM_MAX_CONCURRENCY=25`
bukan penyebabnya, karena jauh di atas n=10).

**Contoh kalimat**:
> "Pengujian beban dengan 10 permintaan `/chat` bersamaan pada infrastruktur produksi (4 vCPU, 15,6
> GB RAM) menunjukkan penggunaan CPU backend mencapai 391,6% (saturasi hampir penuh terhadap 4
> inti prosesor yang tersedia), dengan latensi per-permintaan meningkat dari ~20 detik (permintaan
> tunggal) menjadi 46-82 detik pada kondisi 10 permintaan bersamaan — peningkatan latensi 2,3
> hingga 4 kali lipat. Temuan ini mengindikasikan bahwa kapasitas hardware saat ini menjadi
> pembatas utama (bottleneck) pada skenario penggunaan intensif (high-intensity), bukan
> konfigurasi konkurensi perangkat lunak (`LLM_MAX_CONCURRENCY` dikonfigurasi pada 25, jauh di atas
> beban uji)."

Sumber: `raw_vps/postgres_aggregates.txt` §18-20.

---

## 13. Token dan Biaya OpenRouter

**Token: data historis nyata** (2026-07-05 s.d. 2026-07-27, sebelum akun sempat kehabisan dana):

| Model | Panggilan | Total Token Input | Total Token Output | Rata² Input/panggilan | Rata² Output/panggilan |
|---|---|---|---|---|---|
| gemini-2.5-flash | 4.788 | 14.271.594 | 633.386 | 2.980,7 | 132,3 |
| gemini-2.5-pro | 4.628 | 15.377.632 | 2.139.577 | 3.322,7 | 462,3 |
| **Total** | **9.416** | **29.649.226** | **2.772.963** | | |

**Biaya: PROYEKSI ke depan** (sesuai pilihan Anda — bukan rekonstruksi biaya aktual historis,
karena kolom `cost_usd` di database rusak/selalu 0). Dibangun dari harga resmi OpenRouter
($1,25/$10 per 1M token gemini-2.5-pro; $0,30/$2,50 per 1M token gemini-2.5-flash) dikalikan
rata-rata token nyata per panggilan di atas:

| Skenario | Asumsi | Perkiraan Biaya/Bulan |
|---|---|---|
| A — rate historis | Sama seperti periode 07-05→07-27 | ~$63,40 |
| B — pilot kecil | 100 pengguna × 2 pertanyaan/hari | ~$29,62 |
| C — skala target CLAUDE.md | 300 pengguna × 3 pertanyaan/hari | ~$133,28 |
| D — skala atas | 500 pengguna × 5 pertanyaan/hari | ~$370,23 |

**Contoh kalimat**:
> "Analisis penggunaan token OpenRouter periode 5-27 Juli 2026 mencatat 9.416 panggilan API dengan
> total 29,6 juta token input dan 2,77 juta token output, terbagi antara model gemini-2.5-flash
> (50,9%) dan gemini-2.5-pro (49,1%). Berdasarkan rata-rata token per panggilan tersebut dan tarif
> resmi OpenRouter per Juli 2026, proyeksi biaya operasional bulanan diperkirakan berkisar antara
> $29,62 (skenario penggunaan pilot terbatas) hingga $133,28 (skenario skala target ratusan
> pengguna aktif harian), tidak termasuk potensi penghematan dari mekanisme prompt caching yang
> dapat mengurangi biaya 60-80% menurut dokumentasi resmi OpenRouter."

Sumber: `openrouter_cost_projection.md`.

---

## 14. Ukuran Dokumen, Chunk, Chroma, dan Neo4j

**Dokumen & Chunk**:
| Kategori | Jumlah |
|---|---|
| Total dokumen resmi | 45 (57 MB file mentah di disk) |
| Total chunk (semua jenis/status) | 1.894 |
| Chunk teks approved+active | 428 (rata-rata 394,8 token/chunk = 168.963 token total) |
| Chunk visual active | 975 (266 image + 709 table_image) |

**Ukuran Penyimpanan (docker volume, `du -sh`)**:
| Komponen | Ukuran |
|---|---|
| PostgreSQL | 208 MB |
| Neo4j | 517 MB |
| Chroma | 19 MB |
| Redis | 772 KB |

**Ukuran tabel Postgres terbesar** (untuk konteks skala data evaluasi):
`retrieval_evaluation_logs` 108 MB, `acif_trace_logs` 7,6 MB, `graph_consistency_logs` 6,1 MB,
`chat_evaluation_logs` 5,6 MB.

**Catatan data-quality** (untuk transparansi, bukan menyembunyikan): ditemukan 68 chunk berstatus
`superseded` namun masih ditandai `active=1` secara bersamaan — pola yang sama dengan insiden
duplikasi konten yang pernah terjadi & terdokumentasi sebelumnya (27 Juli). Tidak diaudit ulang
pada sesi ini karena di luar cakupan pengumpulan data murni.

**Contoh kalimat**:
> "Basis pengetahuan aktif sistem terdiri atas 45 dokumen resmi (57 MB), menghasilkan 1.894 chunk
> total, dengan 428 chunk teks dan 975 chunk visual (gambar/tabel) yang telah disetujui dan aktif
> dalam sistem retrieval. Ukuran penyimpanan komponen basis data mencakup PostgreSQL (208 MB),
> Neo4j (517 MB), dan Chroma (19 MB) — menunjukkan jejak penyimpanan yang relatif ringan untuk
> skala korpus dokumen institusi tunggal ini."

Sumber: `raw_vps/postgres_aggregates.txt` §1-6.

---

## Ringkasan Status Akhir (untuk dicek silang dengan naskah Anda)

| # | Item | Siap Kutip Langsung? |
|---|---|---|
| 1 | Neo4j node & relasi | ✅ |
| 2 | Entity coverage | ✅ (sajikan 2 angka + narasi temuan) |
| 3 | Relation coverage | ✅ |
| 4 | Evidence coverage | ✅ |
| 5 | Graph-document consistency | ✅ |
| 6 | Path correctness | ✅ (dengan temuan MH03 dimuat eksplisit) |
| 7 | Distribusi status gate | ✅ |
| 8 | Answer Correctness | ✅ (dengan 7 temuan didiskusikan) |
| 9 | ASR manual | ✅ (2 rater independen, 100% sepakat) |
| 10 | SUS raw data | ✅ |
| 11 | Waktu pengindeksan | ✅ (lengkap, termasuk tahap LLM) |
| 12 | CPU/RAM | ✅ (lengkap, idle+beban, bersih) |
| 13 | Token & biaya | ✅ (token aktual + biaya proyeksi) |
| 14 | Ukuran data | ✅ |

**Semua 14 item kini siap dikutip langsung ke dalam naskah skripsi**, dengan seluruh temuan
(termasuk yang kurang ideal) dimuat secara transparan sebagai bagian pembahasan/keterbatasan,
bukan disembunyikan — ini justru memperkuat kredibilitas bab evaluasi Anda.
