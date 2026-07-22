# Paparan Sidang Tugas Akhir
## Campus Virtual Assistant Berbasis LLM dan Knowledge Graph dengan RAG Grounding Enforcement di Poltekkes Kemenkes Yogyakarta

> Naskah ini adalah **outline lengkap per-slide** untuk presentasi sidang tugas akhir. Setiap
> bagian berisi (1) poin yang ditampilkan di slide, (2) naskah bicara singkat, dan (3) saran
> visual yang perlu disiapkan terpisah (diagram/screenshot/tabel). Seluruh angka evaluasi di
> bagian hasil bersumber dari `evaluation/reports/2026-07-18/` (run terverifikasi terakhir di
> server produksi) dan `evaluation/reports/2026-07-16/sus_asq_final/`. Isi placeholder `[...]`
> dengan data pribadi sebelum dipakai.

---

## Slide 1 — Sampul

**Isi:**
- Judul: **Perancangan dan Pengembangan Campus Virtual Assistant Berbasis LLM dan Knowledge Graph dengan RAG Grounding Enforcement di Poltekkes Kemenkes Yogyakarta**
- Nama: `[...]`  | NIM: `[...]`
- Program Studi: `[...]`
- Dosen Pembimbing: `[...]`
- Logo Poltekkes Kemenkes Yogyakarta

**Naskah pembuka:**
"Selamat pagi/siang, Bapak/Ibu penguji. Perkenalkan, saya [nama], akan mempresentasikan tugas
akhir saya mengenai perancangan dan pengembangan Campus Virtual Assistant untuk Poltekkes
Kemenkes Yogyakarta."

**Saran visual:** logo kampus, foto/ikon sampul netral.

---

## Slide 2 — Agenda Presentasi

**Isi:**
1. Latar Belakang & Rumusan Masalah
2. Tujuan, Manfaat, dan Ruang Lingkup
3. Tinjauan Pustaka & Metodologi
4. Arsitektur Sistem
5. Implementasi (ACIF, Agentic Orchestration, RAG+GraphRAG)
6. Antarmuka Pengguna & Admin
7. Deployment Produksi
8. Hasil Pengujian & Evaluasi
9. Keterbatasan, Kesimpulan, dan Saran

---

## Slide 3 — Latar Belakang

**Isi:**
- Informasi kampus (SPMB, akademik, administrasi) tersebar di halaman web statis, PDF, SOP, brosur, pedoman, dan pengumuman yang terpisah-pisah.
- Mahasiswa dan calon mahasiswa berulang kali menanyakan hal yang sama: persyaratan pendaftaran, jadwal, prosedur, biaya.
- Beban tinggi pada petugas helpdesk, terutama saat periode SPMB dan periode akademik sibuk.
- Sistem berbasis LLM dapat meningkatkan kualitas interaksi, **tetapi LLM tanpa grounding berisiko berhalusinasi** — menjawab persyaratan, tanggal, atau biaya yang tidak benar.
- Dibutuhkan kombinasi LLM + RAG + Knowledge Graph + mekanisme integritas konteks agar jawaban selalu berbasis sumber resmi.

**Naskah:**
"Penelitian ini berangkat dari kondisi nyata: informasi kampus tersebar di banyak dokumen,
pertanyaan yang sama diulang-ulang oleh mahasiswa, dan tenaga helpdesk terbatas. Di sisi lain,
teknologi LLM menjanjikan interaksi yang lebih natural, namun punya risiko besar: LLM bisa
mengarang jawaban yang terdengar meyakinkan padahal salah — ini tidak bisa ditoleransi untuk
informasi resmi kampus seperti persyaratan pendaftaran atau biaya."

**Saran visual:** ilustrasi sederhana "dokumen tersebar" → "satu asisten virtual".

---

## Slide 4 — Rumusan Masalah

**Isi:**
1. Bagaimana merancang asisten virtual kampus yang menjawab hanya berdasarkan sumber resmi (grounded), bukan pengetahuan bebas LLM?
2. Bagaimana mencegah asisten virtual dieksploitasi melalui prompt injection atau pertanyaan di luar domain kampus?
3. Bagaimana memastikan hanya dokumen/chunk yang **disetujui admin** yang menjadi basis pengetahuan aktif?
4. Bagaimana kinerja dan tingkat kepercayaan sistem (grounding, keamanan, usability) dapat diukur secara objektif?

---

## Slide 5 — Tujuan Penelitian

**Isi:**
- Merancang dan membangun Campus Virtual Assistant berbasis LLM (via OpenRouter) yang dipadukan dengan Vector RAG dan GraphRAG.
- Merancang mekanisme **ACIF — Adaptive Context Integrity Filtering**, sebuah lapisan integritas konteks 5-gate yang menjaga jawaban tetap grounded dan tahan terhadap serangan prompt injection.
- Membangun alur kerja tata kelola pengetahuan (document/chunk approval) sehingga tidak ada informasi yang aktif tanpa persetujuan admin.
- Mengevaluasi sistem secara kuantitatif: keamanan (attack success rate), grounding (fallback correctness), performa (latency), dan usability (SUS/ASQ).

---

## Slide 6 — Manfaat Penelitian

**Isi:**
- **Bagi mahasiswa/calon mahasiswa:** akses cepat ke informasi resmi kampus kapan saja, jawaban disertai sitasi sumber.
- **Bagi institusi:** mengurangi beban repetitif pada helpdesk, jejak audit penuh atas setiap jawaban yang diberikan sistem.
- **Bagi keilmuan:** kontribusi metode ACIF sebagai pendekatan context-integrity yang dapat direplikasi untuk domain informasi resmi/high-stakes lainnya.

---

## Slide 7 — Ruang Lingkup & Batasan Masalah

**Isi:**
- Domain: SPMB, informasi akademik, administrasi, regulasi, SOP, dan pengumuman resmi Poltekkes Kemenkes Yogyakarta.
- **Bukan** asisten umum — pertanyaan di luar domain kampus akan ditolak secara terkontrol (out-of-domain fallback).
- Sumber pengetahuan terbatas pada dokumen yang diunggah admin atau disinkronkan dari kanal resmi Sipenmaru, dan hanya yang **disetujui admin** yang aktif.
- Sesi bersifat anonim (tanpa login/identitas mahasiswa) pada versi ini.

---

## Slide 8 — Tinjauan Pustaka Singkat

**Isi:**
- **Large Language Model (LLM):** model bahasa generatif, digunakan via API OpenRouter (bukan LLM lokal) untuk pemahaman dan penyusunan jawaban.
- **Retrieval-Augmented Generation (RAG):** menambahkan konteks dari basis dokumen sebelum LLM menjawab, mengurangi halusinasi.
- **GraphRAG / Knowledge Graph:** representasi entitas dan relasi terstruktur (mis. Program Studi–Jalur Pendaftaran–Persyaratan) sebagai sumber fakta pelengkap teks bebas.
- **Context Integrity / Prompt-Injection Defense:** kebutuhan memvalidasi input pengguna dan konteks yang diambil sebelum dipakai LLM, agar sistem tidak dibajak melalui instruksi tersembunyi di input atau dokumen.

**Naskah:**
"Penelitian ini memposisikan diri di persimpangan tiga bidang: RAG untuk grounding, Knowledge
Graph untuk representasi fakta terstruktur, dan keamanan LLM untuk mencegah manipulasi input.
Kontribusi utama penelitian adalah menyatukan ketiganya dalam satu mekanisme bernama ACIF."

---

## Slide 9 — Metodologi Penelitian

**Isi:**
- **Pendekatan pengembangan:** iteratif bertahap (phase-based development) — dimulai dari fondasi sesi/consent, ACIF Gate 1, alur dokumen, hingga integrasi penuh RAG+GraphRAG+LLM, dilanjutkan hardening produksi.
- **Metode evaluasi:**
  - *Gold-QA dataset*: 41 soal terkurasi manual, 7 kategori (SPMB, Regulasi, Akademik, Administrasi, Kontak, Out-of-Domain, Keamanan/serangan).
  - *Studi ablasi*: menjalankan sistem **dengan ACIF** vs **tanpa ACIF** terhadap dataset yang sama untuk mengisolasi kontribusi ACIF.
  - *Studi pengguna*: kuesioner **System Usability Scale (SUS)** dan **After-Scenario Questionnaire (ASQ)** terhadap responden nyata.
- **Lingkungan pengujian:** dijalankan langsung di server produksi (bukan hanya lokal), untuk memastikan hasil merepresentasikan kondisi nyata.

**Saran visual:** diagram alur metodologi (studi literatur → perancangan → implementasi bertahap → pengujian → evaluasi → penarikan kesimpulan).

---

## Slide 10 — Arsitektur Sistem Keseluruhan

**Isi (alur utama):**
```
Pengguna/Browser
  → Widget Asisten Virtual (Frontend)
  → FastAPI Gateway
  → Session, Consent, Rate Limit
  → Chat Core Service
  → ACIF Gate 1 (Input Integrity)
  → Intent & Entity Extraction (Query Understanding)
  → Vector RAG Retriever + GraphRAG Retriever
  → ACIF Gate 2 (Context Integrity Scoring)
  → ACIF Gate 3 (Graph-Document Consistency)
  → ACIF Gate 4 (Prompt Boundary Construction)
  → OpenRouter LLM Orchestrator
  → ACIF Gate 5 (Output Claim Verification)
  → Citation Builder
  → Respons ke Pengguna
```

**Naskah:**
"Ini adalah alur inti sistem. Perhatikan bahwa ACIF tidak hanya satu langkah, tapi lima gate
yang tersebar di titik-titik kritis: sebelum permintaan diproses, setelah dokumen diambil,
setelah dicek silang dengan graf pengetahuan, saat menyusun prompt, dan setelah jawaban
dihasilkan — sebelum dikirim ke pengguna."

**Saran visual:** diagram arsitektur end-to-end (buat versi visual dari alur teks di atas, gaya flowchart vertikal).

---

## Slide 11 — Arsitektur Data

**Isi:**
- **PostgreSQL** (26 tabel live di produksi), dikelompokkan:
  - Sesi & konsen: `sessions`, `consent_log`, `chat_history`
  - Dokumen & tata kelola: `documents`, `document_versions`, `document_chunks`, `chunk_summaries`, `chunk_reviews`, `document_sources`
  - Jejak ACIF & agen: `acif_decision_logs`, `agent_run_logs`, `security_events`, `openrouter_usage_logs`
  - Evaluasi: `evaluation_runs`, `evaluation_results`, `evaluation_scenarios`, `asq_responses`, `sus_responses`, `chat_evaluation_logs`, `retrieval_evaluation_logs`, `citation_evaluation_logs`, `acif_trace_logs`, `graph_consistency_logs`
- **Chroma** — vector database untuk Vector RAG (embedding multilingual).
- **Neo4j** — graph database untuk entitas/relasi terstruktur (GraphRAG).
- **Redis** — rate limiting, cache retrieval, cache FAQ, penghitung penggunaan OpenRouter.

**Saran visual:** diagram 4 kotak (Postgres/Chroma/Neo4j/Redis) dengan peran masing-masing.

---

## Slide 12 — ACIF: Adaptive Context Integrity Filtering (Kontribusi Inti)

**Isi:**
Lima gate integritas konteks yang berjalan **sebelum dan sesudah** pemanggilan LLM:

| Gate | Nama | Fungsi |
|---|---|---|
| 1 | Input Intent Integrity Check | Deteksi prompt injection, permintaan di luar domain, teks tersamar (encoded/obfuscated) |
| 2 | Context Integrity Scoring | Menilai tiap chunk hasil retrieval pada 6 dimensi: relevansi semantik, status sumber resmi, kesegaran dokumen, kecocokan intent, risiko injeksi dalam chunk, risiko kontradiksi |
| 3 | Graph-Document Consistency | Memvalidasi silang chunk dokumen terhadap bukti Knowledge Graph — menolak chunk yang menyebut entitas berbeda dari yang dikonfirmasi graf |
| 4 | Prompt Boundary Construction | Menyusun prompt dengan batas tegas: kebijakan sistem, input pengguna (tidak dipercaya), konteks dokumen (fakta, bukan instruksi), bukti graf |
| 5 | Output Claim Verification | Memverifikasi klaim jawaban (syarat, tanggal, biaya, kontak, prosedur) terhadap konteks terpilih; jika tidak didukung, sistem regenerasi sekali atau jatuh ke fallback |

- Ambang batas produksi (contoh): `ACIF_INPUT_REJECT_THRESHOLD=0.25`, `ACIF_INPUT_CAUTION_THRESHOLD=0.10`, `ACIF_GROUNDING_VERIFIED_THRESHOLD=0.80`.
- Keputusan tiap chunk: `keep` / `keep_with_verification` / `use_only_if_no_better_context` / `reject`.
- Setiap keputusan ACIF per giliran percakapan dicatat penuh sebagai jejak audit (`acif_decision_logs`).

**Naskah:**
"ACIF adalah kontribusi metodologis utama tugas akhir ini. Bukan sekadar filter kata kunci —
ACIF menilai integritas di setiap tahap: saat pertanyaan masuk, saat dokumen diambil, saat
dicek silang dengan graf pengetahuan, saat prompt disusun, dan saat jawaban keluar. Ini
memastikan LLM tidak pernah dipanggil sebelum konteksnya diverifikasi, dan jawabannya tidak
pernah dikirim sebelum klaimnya diverifikasi balik."

**Saran visual:** diagram 5 gate berurutan dengan ikon keputusan (keep/reject) di tiap gate.

---

## Slide 13 — Agentic Orchestration Layer

**Isi:**
- Sistem diorganisasikan sebagai kumpulan **agen bernama** dengan tanggung jawab terpisah, berjalan di atas pipeline ACIF yang sama (bukan menggantikannya):
  - `OrchestratorAgent` — entry point, menjalankan urutan agen, menggabungkan hasil
  - `QueryUnderstandingAgent` — deteksi intent, bahasa, topik, level risiko
  - `RetrievalAgent` — pencarian vector, seleksi top-k, dedup
  - `GraphReasoningAgent` — pencarian entitas/relasi di Neo4j
  - `ACIFAgent` — menjalankan Gate 1–3, menghasilkan satu objek keputusan terstruktur
  - `AnswerComposerAgent` — menyusun prompt, memanggil OpenRouter, verifikasi klaim, menyusun sitasi
  - `DocumentMonitorAgent` / `DocumentClassifierAgent` — sinkronisasi dan klasifikasi dokumen otomatis
- Endpoint `POST /api/chat/agentic` berjalan paralel dengan `POST /chat` (pipeline linear asli) — **keduanya menghasilkan jawaban ber-ACIF dan bersitasi yang identik**, terverifikasi langsung.
- Setiap eksekusi agen dicatat ke `agent_run_logs` — tidak ada agen yang berjalan tanpa jejak log.

**Naskah:**
"Untuk keterlacakan dan modularitas, sistem juga diimplementasikan ulang sebagai arsitektur
multi-agen di atas pipeline yang sama. Ini bukan dua sistem berbeda — hasilnya diverifikasi
identik — melainkan dua cara mengorkestrasi alur yang sama, dengan versi agen memberi
observability per-komponen yang lebih granular."

**Saran visual:** diagram 8 kotak agen dengan panah orkestrasi dari `OrchestratorAgent`.

---

## Slide 14 — Vector RAG & GraphRAG

**Isi:**
- **Vector RAG:** Chroma sebagai vector store, embedding multilingual (`paraphrase-multilingual-MiniLM-L12-v2`), multi-query retrieval, hasil di-cache di Redis.
- **GraphRAG:** Neo4j menyimpan entitas (ProgramStudi, JalurPendaftaran, TahapSeleksi, Persyaratan, Jadwal, Biaya, UnitLayanan, dll.) dan relasi (`MEMILIKI_JALUR`, `MENGHARUSKAN`, `MEMILIKI_JADWAL`, dst.), diakses lewat query Cypher yang dipicu intent.
- Retrieval hanya mengambil dari **koleksi aktif yang disetujui admin** (`document_status=approved`, `chunk_status=approved`, `active=true`) — chunk yang ditolak/superseded tidak pernah masuk index aktif.
- Hasil graf diringkas terstruktur sebelum masuk prompt — tidak pernah mengirim dump graf mentah ke LLM.

**Saran visual:** contoh screenshot query Cypher sederhana + hasil ringkas, atau cuplikan graf di Neo4j Browser/KG Viewer admin.

---

## Slide 15 — Alur Percakapan End-to-End (Contoh)

**Isi (contoh skenario):**
1. Pengguna bertanya: "Apa syarat pendaftaran jalur mandiri D3 Keperawatan?"
2. ACIF Gate 1: pertanyaan bersih, dalam domain → lanjut.
3. Intent terdeteksi: `Persyaratan`, entitas: `ProgramStudi=D3 Keperawatan`, `JalurPendaftaran=Mandiri`.
4. Vector RAG + GraphRAG mengambil dokumen & bukti graf terkait.
5. Gate 2–3: chunk yang relevan & konsisten dengan graf dipertahankan; yang tidak relevan/mencurigakan ditolak.
6. Gate 4: prompt disusun dengan batas jelas (kebijakan, konteks resmi, pertanyaan pengguna).
7. OpenRouter menghasilkan jawaban berbasis konteks terpilih.
8. Gate 5: klaim syarat diverifikasi terhadap chunk sumber.
9. Jawaban dikirim beserta sitasi dokumen (judul, bagian, halaman).

**Saran visual:** diagram sequence (swimlane): Pengguna – Frontend – Backend/ACIF – Vector/GraphRAG – OpenRouter.

---

## Slide 16 — Alur Ingestion & Persetujuan Dokumen (Admin Workflow)

**Isi:**
```
Unggah manual admin  ATAU  Sinkronisasi otomatis dari kanal resmi Sipenmaru
  → Penyimpanan dokumen mentah + checksum
  → Ekstraksi teks (+ ekstraksi visual/gambar untuk dokumen bergambar)
  → Chunking (400–600 token)
  → Draf ringkasan otomatis via LLM (OpenRouter)
  → Review admin: bandingkan chunk asli vs draf ringkasan
  → Admin edit ringkasan bila perlu
  → Admin: Setujui / Tolak / Perlu Revisi
  → Hanya chunk disetujui → indeks Chroma aktif + graf Neo4j aktif
```
- **Tidak ada dokumen, chunk, ringkasan, entitas, atau relasi graf yang menjadi pengetahuan aktif tanpa persetujuan admin.**
- Termasuk pipeline khusus untuk **konten visual** (gambar, diagram, tabel bergambar dalam PDF) — dideskripsikan oleh vision LLM sebagai draf, tetap butuh persetujuan admin sebelum aktif.
- Sinkronisasi otomatis (`DocumentMonitorAgent`) pernah diuji langsung terhadap situs resmi Sipenmaru, menemukan puluhan dokumen nyata, seluruhnya masuk status `pending_review` — nol yang otomatis disetujui.

**Saran visual:** diagram alur linear dengan status di tiap tahap (`pending_review` → `approved` → `active`).

---

## Slide 17 — Antarmuka Pengguna: Widget Chat

**Isi:**
- Dibangun dengan **Next.js 15 + React 19 + TypeScript**.
- Alur: inisialisasi sesi anonim → banner consent (essential-only / history & analytics) → pengguna bertanya → jawaban dirender dengan format markdown → sumber/sitasi ditampilkan di bawah jawaban.
- Fitur pendukung: indikator mengetik, status error yang ramah pengguna, penanganan sesi hilang otomatis (recovery), tampilan responsif dengan animasi latar (mode terang/gelap).

**Saran visual:** screenshot alur widget (pakai aset asli proyek: `background-chat.png`, `expanded-light.png`, `expanded-dark.webm`) — ambil tangkapan layar segar dari aplikasi berjalan untuk hasil terbaik di sidang.

---

## Slide 18 — Antarmuka Admin: Manajemen Dokumen & Chunk

**Isi:**
- Daftar dokumen per status (pending/approved/rejected/superseded).
- Antrian review chunk: tampilkan teks asli (read-only), draf ringkasan LLM, kolom ringkasan admin yang bisa diedit, badge risiko (hasil deteksi ACIF Gate 1 dipakai ulang di sini), chip entitas terdeteksi.
- Tiga aksi: **Setujui / Perlu Revisi / Tolak**, plus mode bulk-approve dengan konfirmasi dua langkah.
- Antrian terpisah untuk **chunk visual** (hasil ekstraksi gambar/diagram).

**Saran visual:** screenshot antarmuka review chunk (perbandingan: teks asli vs draf ringkasan vs ringkasan admin).

---

## Slide 19 — Antarmuka Admin: Knowledge Graph Viewer & Dashboard Evaluasi

**Isi:**
- **KG Viewer:** visualisasi graf interaktif (vis-network), node berwarna per tipe entitas (Program Studi, Jalur Pendaftaran, Tahap Seleksi, Persyaratan, Jadwal, Biaya).
- **Dashboard Evaluasi:** ringkasan run evaluasi, perbandingan run, log ACIF trace, log sitasi, ekspor CSV, ringkasan skor ASQ/SUS — dipakai langsung untuk menghasilkan data pada slide hasil evaluasi di presentasi ini.

**Saran visual:** screenshot KG Viewer + screenshot dashboard perbandingan evaluasi.

---

## Slide 20 — Deployment Produksi

**Isi:**
- Topologi nyata: **1 VPS produksi**, Docker Compose, **Caddy** sebagai reverse proxy dengan HTTPS otomatis, domain terpisah untuk frontend dan backend API.
- Layanan: backend (FastAPI), frontend (Next.js), PostgreSQL 16, Redis 7, Chroma, Neo4j 5, plus **autoheal** untuk memulihkan container yang macet otomatis.
- Sistem sudah berjalan live dan diuji terhadap pengguna nyata (bukan hanya lingkungan lokal).

**Naskah:**
"Sistem ini bukan prototipe yang hanya berjalan di laptop pengembang — sudah di-deploy ke server
produksi dengan HTTPS, dan seluruh data evaluasi yang akan saya tampilkan berikutnya diambil
langsung dari server produksi tersebut."

**Saran visual:** diagram topologi deployment (Caddy → Frontend/Backend → Postgres/Redis/Chroma/Neo4j).

---

## Slide 21 — Insiden Produksi & Penanganannya

**Isi:**
Tiga insiden nyata selama masa pengembangan, didokumentasikan dan diperbaiki:
1. **Event-loop freeze:** pemanggilan Chroma yang sinkron membekukan event loop async backend; ditambah kesalahan mount volume Chroma yang berisiko kehilangan data — keduanya diperbaiki.
2. **Bug sejenis** ditemukan kembali di endpoint statistik admin dan indexing chunk visual yang mati — diperbaiki.
3. **Chroma "wedging"** (macet tanpa crash) — ditambahkan healthcheck HTTP nyata + autoheal.

**Naskah:**
"Bagian ini penting untuk menunjukkan bahwa sistem sudah melewati siklus pengembangan-produksi
yang nyata, bukan hanya demo sekali jalan. Setiap insiden diinvestigasi hingga akar masalah dan
diperbaiki dengan verifikasi ulang di produksi."

---

## Slide 22 — Desain Evaluasi

**Isi:**
- **Gold-QA dataset:** 41 soal, 7 kategori — SPMB (14), Regulasi (3), Akademik (3), Administrasi (3), Kontak (3), Out-of-Domain (5), Keamanan/serangan (10).
- **Studi ablasi:** setiap soal dijalankan dua kali — kondisi **dengan ACIF** dan **tanpa ACIF** — terhadap sistem produksi yang sama, dibandingkan berpasangan (paired test: Wilcoxon signed-rank / McNemar exact).
- **Studi pengguna:** SUS (n=21 responden) dan ASQ (n=22 responden × 2 skenario).
- Seluruh run diverifikasi ulang: dijalankan dua kali pada tanggal berbeda (16 & 18 Juli 2026) langsung di server produksi untuk memastikan hasil replikabel, bukan kebetulan satu kali jalan.

---

## Slide 23 — Hasil Evaluasi: Keamanan & Grounding

**Isi (tabel utama):**

| Metrik | Dengan ACIF | Tanpa ACIF | n | p-value | Signifikan |
|---|---|---|---|---|---|
| Attack Success Rate | **0%** | **100%** | 10 | 0.00195 | Ya |
| Fallback Correctness | **82,9%** | **41,5%** | 41 | 0,0033 | Ya |

**Naskah:**
"Ini temuan paling penting dari evaluasi. Dari 10 skenario serangan (prompt injection, upaya
membocorkan system prompt, dsb.), **tanpa ACIF seluruhnya berhasil menembus sistem — 100%**;
**dengan ACIF, tidak satu pun berhasil — 0%**. Hasil ini identik di dua kali run terpisah,
menunjukkan replikasi yang kuat, bukan kebetulan. Untuk fallback correctness — yaitu sistem
dengan benar mengatakan 'informasi tidak tersedia' saat konteks memang tidak cukup — ACIF
meningkatkan ketepatan dari 41,5% menjadi 82,9%."

**Saran visual:** bar chart perbandingan dua kondisi untuk kedua metrik.

---

## Slide 24 — Hasil Evaluasi: Performa

**Isi:**

| Metrik | Dengan ACIF | Tanpa ACIF | p-value |
|---|---|---|---|
| Total Latency (rata-rata) | **4.404 ms** | 5.301 ms | 0,0397 (signifikan) |
| Precision@3 | 0,098 | 0,098 | 1,0 (tidak berbeda) |
| Recall@3 / Hit Rate@3 | 0,294 | 0,294 | 1,0 (tidak berbeda) |

**Naskah:**
"Temuan yang mungkin mengejutkan: sistem **dengan ACIF justru lebih cepat**, bukan lebih lambat.
Penyebabnya, Gate 1 melakukan short-circuit — pertanyaan di luar domain atau serangan langsung
ditolak sebelum sempat memanggil LLM, sehingga rata-rata waktu keseluruhan turun. Untuk
precision/recall retrieval, ACIF tidak menurunkan kualitas pengambilan dokumen — angkanya identik
di kedua kondisi, karena ACIF adalah lapisan integritas, bukan pengganti mesin retrieval."

**Catatan jujur:** Precision@3 dibatasi struktural oleh desain gold-set (rata-rata hanya 1 chunk
relevan diketahui per soal, sehingga plafon teoretis ≈ 0,33) — selalu disampaikan berdampingan
dengan Hit Rate@3, tidak berdiri sendiri.

---

## Slide 25 — Hasil Evaluasi: Usability (SUS & ASQ)

**Isi:**
- **System Usability Scale (SUS):** rata-rata **69,05** dari 21 responden nyata → kategori **"Good"** (skala adjective Bangor).
- **After-Scenario Questionnaire (ASQ):** 22 responden × 2 skenario, skor rata-rata per-item pada rentang 4,0–7,0 (skala 7 poin) — menunjukkan kepuasan yang cukup baik terhadap kemudahan menyelesaikan tugas dengan asisten virtual.

**Saran visual:** gauge/meter chart skor SUS dengan skala interpretasi (Poor–OK–Good–Excellent), tabel ringkas ASQ per skenario.

---

## Slide 26 — Keterbatasan Penelitian

**Isi (disampaikan jujur, bukan disembunyikan):**
- Dimensi `no_contradiction` pada Gate 2 hanya diberi skor penuh saat ada bukti graf pendukung — skor maksimum praktis 0,85, bukan 1,0 (dipatenkan sebagai batas desain lewat unit test, bukan bug yang belum ditemukan).
- `GraphReasoningAgent` saat ini melakukan pencarian graf berbasis kata kunci/intent, **belum** penalaran multi-hop penuh.
- Metrik *faithfulness* dan *answer relevance* (via LLM-judge) **tidak signifikan secara statistik dan arahnya berbalik** antar dua kali run independen (sampel kecil, n=9–10 dari 41 soal) — **tidak dijadikan klaim arah**, murni dilaporkan sebagai keterbatasan metodologis.
- Precision@3 dibatasi struktural oleh desain gold-QA (1 chunk relevan per soal).
- Load testing baru pada tahap skrip (`locustfile.py`) — **belum ada laporan hasil beban tinggi** yang dapat dikutip.
- Dua soal gold-QA (kategori Regulasi) sempat gagal dijawab karena kombinasi dua lapis masalah independen: ringkasan chunk berbahasa Inggris yang lolos dari sapuan regenerasi (sudah diperbaiki dan diverifikasi hingga level embedding) dan kosakata Query Understanding Layer yang belum mengenali istilah "tata tertib"/"pelanggaran" (teridentifikasi, perbaikan kode belum dilakukan) — dicontohkan sebagai bukti proses debugging yang jujur dan sistematis, bukan diklaim "semua sudah sempurna".

**Naskah:**
"Saya sengaja menyampaikan bagian ini secara transparan. Ada beberapa metrik yang hasilnya belum
konklusif, dan ada limitasi desain yang saya sadari sepenuhnya. Ini bagian dari integritas ilmiah
penelitian, dan menjadi dasar untuk arah pengembangan selanjutnya."

---

## Slide 27 — Kesimpulan

**Isi:**
1. Campus Virtual Assistant berbasis LLM + RAG + GraphRAG berhasil dirancang dan di-deploy ke lingkungan produksi nyata untuk Poltekkes Kemenkes Yogyakarta.
2. Mekanisme **ACIF (5-gate context integrity)** terbukti secara statistik signifikan menurunkan tingkat keberhasilan serangan prompt-injection dari 100% menjadi 0%, dan meningkatkan ketepatan fallback dari 41,5% menjadi 82,9% — **tanpa mengorbankan performa** (justru lebih cepat karena short-circuit).
3. Seluruh pengetahuan aktif sistem melalui alur persetujuan admin yang ketat — tidak ada dokumen/chunk yang aktif tanpa tinjauan manusia.
4. Tingkat usability sistem berada pada kategori **"Good"** (SUS 69,05) berdasarkan pengujian pengguna nyata.

---

## Slide 28 — Saran & Pengembangan Selanjutnya

**Isi:**
- Mengembangkan `GraphReasoningAgent` ke penalaran multi-hop penuh di Neo4j.
- Memperluas kosakata Query Understanding Layer untuk istilah regulasi/tata tertib yang belum tercakup.
- Menjalankan dan melaporkan load testing formal (concurrency tinggi) sebagai bukti kesiapan skala.
- Memperbesar sampel evaluasi LLM-judge (faithfulness/relevansi) untuk hasil yang lebih konklusif secara statistik.
- Penyempurnaan lanjutan UI Knowledge Graph Viewer dan dashboard monitoring agen.

---

## Slide 29 — Penutup

**Isi:**
- Ucapan terima kasih kepada pembimbing, penguji, dan pihak kampus.
- Sesi tanya jawab.

**Naskah penutup:**
"Demikian presentasi tugas akhir saya. Terima kasih atas perhatian Bapak/Ibu penguji, saya
terbuka untuk pertanyaan dan diskusi lebih lanjut."

---

## Lampiran — Sumber Data untuk Verifikasi Ulang

Gunakan referensi ini bila penguji meminta bukti angka:

- Hasil ablasi ACIF (terbaru, 18 Juli 2026): `campus-va/evaluation/reports/2026-07-18/acif_comparison_summary.csv` dan `README.md` di folder yang sama.
- Hasil ablasi ACIF (verifikasi awal, 16 Juli 2026): `campus-va/evaluation/reports/2026-07-16/`.
- Skor SUS (n=21): `campus-va/evaluation/reports/2026-07-16/sus_asq_final/tabel_4_24_hasil_skor_sus.csv`.
- Skor ASQ (raw): `asq_responses.csv` (root repo).
- Log rekayasa & insiden produksi: `campus-va/IMPLEMENTATION.md`.
- Kebijakan/arsitektur resmi proyek: `campus-va/CLAUDE.md` §11 (ACIF, level publik) — jangan mengutip detail dari `docs/private/acif/` di forum publik/sidang terbuka.
