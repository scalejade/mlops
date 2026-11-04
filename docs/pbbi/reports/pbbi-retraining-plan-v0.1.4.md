# PBBI ekstraksi klausa — rencana training v0.1.4 (final)

**Status:** disetujui, belum dijalankan · **Tanggal:** 1 November 2026
**Keputusan:** pakai **Approach 2** (pemilihan data berdasarkan cluster struktur PDF) dan **struktur train/eval/test** di bawah.
**Dokumen pendamping:** `pbbi-v0.1.4-summary.md` dan `pbbi-v0.1.4-summary.pdf` (analisis lengkap: kenapa kalah, isu, perbandingan kedua approach).

---

## 1. Ringkasan keputusan

| Hal | Keputusan |
|---|---|
| Approach | **Approach 2: cluster struktur PDF**, 6 cluster (A daftar datar, B induk → anak, C naratif, D tabel/kolom, E dwibahasa, F desimal) |
| Sumber eval dan test | **Hanya dari 60 dokumen awal** (label pengawas BI) |
| Dokumen baru dari `/all` | **Hanya masuk train** |
| Syarat coverage | Eval dan test masing-masing punya **minimal 1 dokumen per cluster** (struktur maupun produk), dengan dua pengecualian yang tidak mungkin dipenuhi (bagian 3.4) |
| Keluaran | **Murni dari model**: tidak ada pasca-proses atau logika aplikasi. Perbaikan hanya lewat data, cara training, dan system prompt (bila disetujui) |
| PERMATA IB | Dianggap bisa diunggah (deteksi bahasa aplikasi diperbaiki atau tersedia versi PDF yang benar) |
| Komposisi | **Rekomendasi: 58 train / 9 eval / 18 test.** Maksimal: 66 / 9 / 18 |

---

## 2. Aturan yang dipegang

1. 60 dokumen `preparation/raw` tetap dipakai semuanya, dengan versi `raw` sebagai acuan bila berbeda dengan `/all`.
2. Eval dan test hanya dari 60 dokumen itu.
3. 17 dokumen test lama dipertahankan, supaya skor v0.1.4 sebanding dengan v0.1.2 dan v0.1.3.
4. Satu PDF yang sama tidak boleh berada di dua split. Karena itu CIMB IB (satu PDF dengan CIMB KD di eval) dan SINARMAS MB (satu PDF dengan SINARMAS UE di test) tidak dipakai.
5. Metrik: Jaccard rata-rata tanpa ambang (recall, precision, F1), dihitung dari keluaran model apa adanya.

---

## 3. Struktur split final

Pembagian 60 dokumen awal: **33 train · 9 eval · 18 test.**

### 3.1 Test (18)

| Dokumen | Cluster | Produk | Catatan |
|---|---|---|---|
| BCA KD | A | Kartu Debit | test lama |
| BRI UE Chip | A | UE Chip-Based | test lama |
| DBS MB | A | Mobile Banking | test lama |
| JATENG KD | A | Kartu Debit | test lama |
| MUAMALAT IB | A | Internet Banking | test lama |
| SINARMAS UE Server | A | UE Server-Based | test lama |
| SMBC KK | A | Kartu Kredit | test lama |
| SULTRA KD | A | Kartu Debit | test lama |
| BJB MB | B | Mobile Banking | test lama |
| MANDIRI MB | B | Mobile Banking | test lama |
| OCBC IB | B | Internet Banking | test lama |
| NAGARI MB | C | Mobile Banking | test lama |
| OCBC KK | C | Kartu Kredit | test lama |
| OY PG | C | Payment Gateway | test lama |
| SHOPEEPAY UE Server | C | UE Server-Based | test lama |
| BOC MB&IB | E | MB & IB | test lama |
| SEABANK MB | F | Mobile Banking | test lama |
| **KALSEL KD** | **D** | Kartu Debit | **test tambahan, pindah dari train** |

KALSEL KD masuk karena cluster D tidak punya dokumen test. Dari 3 dokumen D di 60 dokumen, UOB KK dipakai untuk eval dan BSI MB dipertahankan di train karena punya 8 contoh kalimat pembuka definisi. KALSEL KD pernah dipakai melatih v0.1.3, jadi skornya **dilaporkan terpisah** dan hanya dibandingkan dengan gpt-4.1-mini.

### 3.2 Eval (9)

| Dokumen | Cluster | Produk | Penyelenggara | Catatan |
|---|---|---|---|---|
| CIMB KD | A | Kartu Debit | Swasta nasional | eval lama |
| JAMBI KD | A | Kartu Debit | BPD | eval lama (label perlu dicek dengan Legal) |
| BNI MB | B | Mobile Banking | BUMN | eval lama |
| OVO | B | UE Server-Based | LSB | eval lama |
| **MANDIRI UE Chip** | B | **UE Chip-Based** | BUMN | pindah dari train |
| **MAYBANK MB&IB** | **C** | **MB & IB** | **Multinasional** | pindah dari train |
| **UOB KK** | **D** | **Kartu Kredit** | Multinasional | pindah dari train |
| **STANCHART IB** | **E** | **Internet Banking** | Multinasional | pindah dari train |
| **MEGA KK** | **F** | Kartu Kredit | Swasta nasional | pindah dari train |

Kelima dokumen yang dipindah dipilih supaya satu dokumen menutup lebih dari satu celah coverage. Yang **sengaja tidak dipindah** adalah dokumen yang menjadi sumber contoh langka di train:
- BSI MB, ACEH MB, SMBC IB, YUKK: contoh kalimat pembuka definisi;
- STANCHART KK: 14 contoh tabel;
- UOB MB: dokumen terpanjang.

### 3.3 Train dari 60 dokumen (33)

| Cluster | Dokumen |
|---|---|
| A (16) | BANTEN KD, BCA IB, BCA MB, BNI KK, CIMB UE Server, JATENG MB, JATIM KD, JATIM MB, JTRUST MB&IB, KALTIMTARA MB&IB, MEGA MB, NTT IB, OCBC KD, SINARMAS KD, SMBC IB, UOB IB |
| B (7) | ACEH MB, BANTEN MB, DANAMON UE Chip, GOPAY UE Server, JAGO MB, MANDIRI KD, SULSELBAR KD |
| C (2) | MASPION IB, MASPION KD |
| D (1) | BSI MB |
| E (2) | CIMB KK, STANCHART KK |
| F (5) | BTN IB, HONEST KK, UOB MB, WISE Remitansi, YUKK PG |

### 3.4 Cek syarat "minimal 1 dokumen per cluster"

| Pengelompokan | Eval (9) | Test (18) |
|---|---|---|
| Struktur A · B · C · D · E · F | 2 · 3 · 1 · 1 · 1 · 1 ✔ | 8 · 3 · 4 · 1 · 1 · 1 ✔ |
| IB · KK · KD · MB · MB&IB | 1 · 2 · 2 · 1 · 1 ✔ | 2 · 2 · 4 · 5 · 1 ✔ |
| UE Chip · UE Server | 1 · 1 ✔ | 1 · 2 ✔ |
| Payment Gateway | ✘ (pengecualian) | 1 ✔ |
| Remitansi | ✘ (pengecualian) | ✘ (pengecualian) |
| Swasta · BPD · BUMN · Multinasional · LSB | 2 · 1 · 2 · 3 · 1 ✔ | ✔ semua |

**Pengecualian yang tidak mungkin dipenuhi:**
- **Remitansi** hanya 1 dokumen di 60 (WISE). Tidak bisa ada di eval dan test sekaligus, jadi WISE tetap di train.
- **Payment Gateway** hanya 2 dokumen (OY di test, YUKK di train). Memindahkan YUKK ke eval membuat train tidak punya Payment Gateway dan kehilangan 15 contoh kalimat pembuka definisi. YUKK tetap di train.

### 3.5 Train dari dokumen baru `/all` (sudah direview pengawas, 2 November 2026)

Semua dokumen baru hanya masuk train. Urutan pengerjaan oleh pengawas mengikuti prioritas. Kolom **Persiapan PDF** berisi catatan review: bagian yang harus dipotong atau dipisah sebelum diekstrak.

**Perubahan dari review pengawas:**
- ❌ **STANCHART KD** dikeluarkan karena produknya tabungan, bukan kartu debit.
- ❌ **DANAMON General** dikeluarkan karena isinya campuran berbagai produk SP.
- ➕ **JAKARTA MB** dipecah menjadi 2 dokumen: konvensional dan syariah.
- ➕ **JOGJA** dipecah menjadi 2 dokumen: Kartu Debit dan Mobile Banking.

Jumlah dokumen baru tetap **25**.

**Prioritas 1 (12 dokumen): menyasar sub-butir yang digabung, dokumen panjang, dan kalimat pembuka definisi**

| # | Dokumen | Cluster | Produk | Token (PDF utuh) | Baris `a.` | Alasan | Persiapan PDF |
|---|---|---|---|---|---|---|---|
| 1 | JAKARTA MB (konvensional) | B | MB | 21.147 (sebelum dipecah) | 234 (gabungan) | Sub-butir terbanyak, cluster terlemah | Bagian A: judul "A. SYARAT & KETENTUAN PEMBUKAAN REKENING TABUNGAN…" (baris terakhir hlm 3) + hlm 4–12 sampai XII. Kerjasama dengan pihak lain, termasuk 2 paragraf penutup. Hlm 1–3 (RIPLAY) dibuang. |
| 2 | JAKARTA MB (syariah) | B | MB | (lihat #1) | (lihat #1) | Sama; varian syariah | Bagian B: hlm 13–25, dari judul "B. SYARAT & KETENTUAN … TABUNGAN SYARIAH …" sampai XII, lalu XIII. Kebijakan Privasi dan persetujuan "Pemrosesan Data Pribadi" (klausa, bukan formulir) |
| 3 | CIMB MB | A | MB | 20.925 (dengan bagian UE) | 125 | Banyak sub-butir | Hanya bagian MB. Bagian UE Server-Based (mulai halaman 24) dipisah dan **tidak dipakai**, karena hampir sama dengan CIMB UE Server-Based yang sudah ada di train (kemiripan kata 0,79). |
| 4 | DANA | C | UE Server | 25.446 | 53 | Panjang; cluster C; UE Server | – |
| 5 | DBS KK | C | KK | 16.734 | 0 | Kalimat pembuka definisi; Multinational | – |
| 6 | PERMATA IB | C | IB | ≈ 12–13k* | 1 | Kalimat pembuka definisi; IB baru terbesar; cluster C | Perlu versi yang bisa diunggah (deteksi bahasa aplikasi) |
| 7 | DANAMON KD | A | KD | 9.816 | 52 | Kalimat pembuka definisi dan sub-butir | – |
| 8 | LINKAJA | C | UE Server | 11.768 | 32 | Cluster C; UE Server | – |
| 9 | NOBU MB | A | MB | 20.332 | 47 | Panjang | – |
| 10 | NOBU KK | A | KK | 10.668 | 38 | KK dengan sub-butir | – |
| 11 | NTB MB | B | MB | 2.473 | 33 | Cluster B | – |
| 12 | BCA UE Server-Based | B | UE Server | 3.888 | 24 | Cluster B; UE Server | – |

\*Token PERMATA IB adalah perkiraan, karena teks utuhnya belum bisa diambil lewat pipa aplikasi.

**Cluster PERMATA IB = C (naratif).** Dokumen ini dibagi per "Pasal 1" sampai "Pasal 20", dan isi setiap pasal berupa paragraf tanpa nomor: tidak ada daftar `1.`, hanya 1 sub-butir `a.`, dan tidak ada nomor desimal. Clustering yang sama (102 PDF, Ward, 6 cluster) dihitung ulang setelah header/footer browser dibuang dan baris kolom sempit disambung kembali menjadi paragraf. Hasilnya, jarak ke pusat cluster C 1,15, sedangkan cluster terdekat berikutnya (A) 3,42. Pada teks yang rusak oleh filter bahasa, dokumen ini sempat terbaca sebagai E (dwibahasa); itu artefak filter, bukan bentuk dokumennya.

**Prioritas 2 (13 dokumen): menutup celah coverage**

| # | Dokumen | Cluster | Alasan | Persiapan PDF |
|---|---|---|---|---|
| 13 | KEPRI MB | D | Tabel dan kolom; satu-satunya dokumen 3 kolom | Halaman terakhir dibuang |
| 14 | MALUT KD | D | Tabel padat | Buang halaman formulir (1–2) dan "Bab VII. Ketentuan Pembukaan Rekening Produk Dana" |
| 15 | SUMUT KD | D | Tabel | Buang "Pasal 3: Kewenangan Bertransaksi Rekening Gabungan" |
| 16 | SULUTGO KD | D | Tabel | Buang halaman formulir (1–2), "Ketentuan Khusus Pembukaan Rekening Giro", dan "Ketentuan Khusus Pembukaan Rekening Deposito" |
| 17 | JOGJA KD | D | Multi-kolom | Hanya bagian perorangan; ambil bagian IV, V, VII, VIII; halaman lain dibuang |
| 18 | JOGJA MB | D | Multi-kolom; MB | Hanya bagian perorangan; ambil bagian VI, VII, VIII; halaman lain dibuang |
| 19 | BCA KK | C | Naratif; Kartu Kredit | – |
| 20 | BALI KD | B | Cluster B | Bisa diekstraksi tanpa OCR ✔ (2 font, tanpa gambar, 8.307 karakter teks Indonesia) |
| 21 | NTT MB | B | Cluster B | – |
| 22 | SMBC MB | A | Panjang | Halaman 1–5 dibuang |
| 23 | SINARMAS IB | A | Internet Banking | – |
| 24 | SINARMAS KK | A | Kartu Kredit | – |
| 25 | BSI KK | A | Kartu Kredit (BUMN) | – |

**Prioritas 3 (8 dokumen, opsional, untuk komposisi maksimal):** BRI KD, JAMBI MB, BJB Syariah MB, SULSELBAR MB, SUMSELBABEL MB, SUMUT MB, PERMATA MB, MEGA UE. Semuanya cluster A, pendek, dan produknya sudah kuat. Belum direview pengawas.

**Tidak dipakai (13 dokumen baru):**
- STANCHART KD: produk tabungan, bukan kartu debit (review pengawas);
- DANAMON General: campuran berbagai produk SP (review pengawas);
- BJB Syariah KD, DANAMON KK: scan;
- HSBC KK: gambar;
- BOC KD ENG, BOC KK ENG, PERMATA KK ENG: berbahasa Inggris, ditolak aplikasi;
- HSBC General, STANCHART General: terlalu panjang;
- DANAMON MB: mendekati batas token;
- BALI MB: dwibahasa, teks rusak oleh filter;
- JAMBI MB versi unclean: duplikat.

### 3.6 Komposisi akhir

| | Train | Eval | Test | Total |
|---|---|---|---|---|
| v0.1.3 (sekarang) | 39 | 4 | 17 | 60 |
| **v0.1.4 rekomendasi** (P1 + P2) | **58** = 33 + 25 baru | **9** | **18** | **85** |
| v0.1.4 maksimal (P1 + P2 + P3) | 66 = 33 + 33 baru | 9 | 18 | 93 |

---

## 4. Coverage train sebelum dan sesudah

**Per cluster struktur**

| Cluster | v0.1.3 | v0.1.4 rekomendasi | v0.1.4 maksimal |
|---|---|---|---|
| A. Daftar datar | 16 | 24 | 32 |
| B. Induk → anak | 8 | 13 | 13 |
| C. Naratif | 3 | 7 | 7 |
| D. Tabel/kolom | 3 | 7 | 7 |
| E. Dwibahasa | 3 | 2 | 2 |
| F. Desimal | 6 | 5 | 5 |
| **Total** | **39** | **58** | **66** |

**Per produk**

| Produk | v0.1.3 | v0.1.4 rekomendasi | v0.1.4 maksimal |
|---|---|---|---|
| Internet Banking | 7 | 8 | 8 |
| Kartu Kredit | 6 | 9 | 9 |
| Kartu Debit | 8 | 13 | 14 |
| Uang Elektronik (Chip + Server) | 4 | 6 | 7 |
| Mobile Banking | 9 | 18 | 24 |
| MB & IB | 3 | 2 | 2 |
| Payment Gateway | 1 | 1 | 1 |
| Remitansi | 1 | 1 | 1 |
| **Total** | **39** | **58** | **66** |

**Ciri penting**

| Ciri di train | v0.1.3 | v0.1.4 rekomendasi |
|---|---|---|
| Dokumen dengan teks ≥ 20k token | 2 | ≥ 4 (DANA, NOBU MB, ditambah JAGO MB dan UOB MB); dihitung ulang setelah PDF dipotong |
| Dokumen dengan kalimat pembuka definisi | 4 | 7 (+DBS KK, DANAMON KD, PERMATA IB) |
| Multinational | 8 | 6 (3 pindah ke eval, +1 baru: DBS KK) |
| Baris sub-butir berhuruf di teks dokumen baru | – | ≈ 800 (sebelum PDF dipotong) |

**Konsekuensi yang diterima:**
- Cluster E (dwibahasa) di train turun dari 3 menjadi 2, dan tidak ada dokumen dwibahasa baru yang bersih.
- MB & IB di train turun dari 3 menjadi 2.
- **Cluster F tidak mendapat dokumen baru**, karena STANCHART KD, satu-satunya dokumen F baru, dikeluarkan. F di train menjadi 5 (MEGA KK pindah ke eval), semuanya dari 60 dokumen awal.
- Tidak ada dokumen General di train.
- Tambahan baris sub-butir berkurang sekitar 270 karena STANCHART KD (157) dan DANAMON General (112) keluar. Cluster B naik ke 13 karena JAKARTA MB dipecah dua.

---

## 5. Cara memperbaiki model (tanpa logika aplikasi)

| Penyebab kekalahan v0.1.3 | Perbaikan dari sisi model |
|---|---|
| **Sub-butir digabung** (22,5–24,2 dari 29,2 poin recall hilang; 55–61% anak berhuruf digabung) | Dokumen prioritas 1 dengan banyak sub-butir dan dokumen panjang; opsi oversampling; opsi baris jendela |
| **Nomor urut tersalin** (JATENG, SULTRA, BRI) | Panduan label konsisten (item mandiri tanpa nomor); kalimat di system prompt bila disetujui |
| **Kalimat pembuka definisi tidak diulang** (OCBC IB) | Contoh di train naik dari 4 menjadi 7 dokumen; contoh di system prompt bila disetujui |
| **Tabel dipecah** (BRI) | Dokumen bertabel di luar Kartu Kredit (KEPRI, MALUT, SUMUT, SULUTGO, JOGJA KD, JOGJA MB) |

**Opsi cara training (perlu diputuskan sebelum build):**
- **Oversampling:** baris dokumen yang kaya sub-butir (JAKARTA MB konvensional dan syariah, CIMB MB, DANAMON KD, DANA) diulang 2–3 kali di train.
- **Baris jendela:** turunkan batas baris di `build.py` agar dokumen panjang dipecah menjadi beberapa baris berisi bagian utuh. Fitur ini sudah ada; efeknya belum diuji.
- **System prompt:** tambah kalimat "item bernomor yang berdiri sendiri ditulis tanpa nomornya" dan satu contoh kalimat pembuka definisi. Perlu persetujuan, dan semua baris dibangun ulang dengan prompt baru.

Konfigurasi training lain mengikuti v0.1.3 (LoRA r 16, lr 5e-5), dengan **1 epoch** karena v0.1.2 dan v0.1.3 sama-sama memilih step 20 (sekitar 1 epoch). Eval 9 dokumen dipakai untuk konfirmasi pilihan checkpoint.

---

## 6. Prediksi skor (17 dokumen test lama)

| Skenario | Train | Recall | Precision | F1 |
|---|---|---|---|---|
| v0.1.3 (terukur) | 39 | 70,8 | 84,4 | 77,0 |
| Pesimis: rekomendasi, model belajar sedikit | 58 | ~72,7 | ~84,0 | ~77,9 |
| **Realistis: rekomendasi** | 58 | **~74,5** | **~83,6** | **~78,8** |
| **Realistis: maksimal + oversampling + prompt** | 66 | **~76,5** | **~83,4** | **~79,8** |
| Optimis: maksimal, model memecah sub-butir dengan baik | 66 | ~79,8 | ~82,9 | ~81,3 |
| Batas atas (model menulis persis seperti label) | – | 83,2 | 81,8 | 82,5 |

| Metrik | Kemungkinan mencapai ≥ 80% |
|---|---|
| Precision | **Tercapai di semua skenario** |
| F1 | **Di ambang batas.** Realistis maksimal sekitar 79,8%; melewati 80% hanya di skenario optimis. |
| Recall | **Kemungkinan besar belum di v0.1.4.** Skenario optimis pun sekitar 79,8%. |

**Cara menghitung:**
- Titik awal adalah skor v0.1.3.
- Batas atas adalah simulasi seandainya model sendiri tidak menyalin nomor, memecah sub-butir, dan mengulang kalimat pembuka seperti label. Ini bukan aturan aplikasi.
- Seberapa jauh model bergerak ke batas atas diturunkan dari satu-satunya data historis: dari v0.1.2 ke v0.1.3, +8 dokumen menggerakkan sekitar 11% dari jarak itu.
- Rekomendasi (+19 dokumen bersih) diasumsikan bergerak sekitar 30%, maksimal dengan oversampling dan prompt sekitar 45%, dan skenario optimis sekitar 70%.
- **Ketidakpastiannya besar.** Dasarnya hanya satu langkah historis, dan efek oversampling, baris jendela, serta prompt belum pernah diukur.

---

## 7. Langkah kerja

1. **Pipa teks:** perbaiki deteksi bahasa aplikasi untuk PDF cetak browser berkolom sempit, atau dapatkan PDF PERMATA IB yang bisa diunggah.
2. **System prompt:** putuskan dua kalimat tambahan (nomor item mandiri; contoh kalimat pembuka definisi).
3. **Panduan label untuk pengawas:** anak berhuruf dipisah dengan teks induk, item mandiri tanpa nomor, kalimat pembuka definisi diulang, satu tabel satu klausa.
4. **Persiapan PDF** sesuai kolom "Persiapan PDF" di bagian 3.5: pecah JAKARTA MB (konvensional/syariah) dan JOGJA (KD/MB); potong halaman atau bagian di CIMB MB, KEPRI MB, MALUT KD, SUMUT KD, SULUTGO KD, dan SMBC MB.
5. **Ekstraksi pengawas:** prioritas 1 (12), lalu prioritas 2 (13). Prioritas 3 (8) bila waktu tersedia, setelah direview pengawas.
6. **Susun split** sesuai bagian 3: pindahkan KALSEL KD ke test, dan MANDIRI UE Chip, MAYBANK MB&IB, UOB KK, STANCHART IB, MEGA KK ke eval.
7. **Build data** dengan `build.py`; cek token semua baris (≤ 98.304) dan panjang jawaban (≤ 65.536); putuskan oversampling dan baris jendela.
8. **Training v0.1.4**, 1 epoch.
9. **Evaluasi** keluaran model apa adanya, dibandingkan gpt-4.1-mini per dokumen:
   - 17 test lama (sebanding dengan v0.1.2 dan v0.1.3);
   - KALSEL KD terpisah;
   - per cluster struktur dan per produk.

**Gerbang rilis:**
- F1 pada 17 test lama tidak di bawah v0.1.3 (77,0).
- Tidak ada dokumen yang turun lebih dari 0,03.
- Jumlah dokumen yang kalah dari gpt tidak bertambah.

Recall, precision, dan F1 dilaporkan apa adanya, termasuk bila belum mencapai 80%.

**Bila recall masih di bawah 80% setelah v0.1.4:** langkah berikutnya adalah ekstraksi pengawas untuk dokumen tambahan dengan banyak sub-butir berhuruf, karena 33 dokumen baru yang tersedia sudah terpakai. Mengubah isi test bukan jalan keluarnya, karena itu hanya mengubah cara mengukur.

---

## 8. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Model belajar memecah sub-butir lebih sedikit dari perkiraan | Recall dan F1 di bawah 80% | Oversampling, baris jendela, dan prompt; putaran data berikutnya |
| Train dari dokumen terverifikasi berkurang 6 | Contoh berkualitas tinggi berkurang | Diimbangi 25–33 dokumen baru; dokumen sumber contoh langka tetap di train |
| Cluster E di train hanya 2 | Dokumen dwibahasa tetap lemah (BOC 0,558) | Catat sebagai keterbatasan |
| Cluster F tanpa dokumen baru | Sub-butir di dalam pasal desimal (F menggabungkan 78 dari 100 anak berhuruf) belum mendapat contoh tambahan | Oversampling dokumen F di train (UOB MB, YUKK, BTN IB); cari dokumen F lain di putaran berikutnya |
| Pemotongan PDF tidak konsisten dengan teks yang dikirim aplikasi | Teks latih berbeda dari teks produksi | Potong di PDF sebelum diproses `build.py`, bukan di teks hasil ekstraksi; catat versi PDF yang dipakai |
| Label baru tidak konsisten | Model belajar pola bertentangan | Panduan label tertulis sebelum ekstraksi |
| PERMATA IB belum bisa diunggah | Prioritas 1 berkurang satu | Komposisi tetap berjalan tanpa dokumen ini (57 / 9 / 18) |
| Label JAMBI KD (eval) bermasalah | Sinyal eval berisik | Cek dengan Legal; eval kini 9 dokumen, sehingga satu dokumen tidak dominan |
| Test kecil (17 + 1) | Skor per dokumen berisik | Gerbang per dokumen; laporan per dokumen |

---

## 9. Pertanyaan terbuka

1. Apakah dua kalimat tambahan di system prompt disetujui?
2. Kapan PERMATA IB tersedia dalam versi yang bisa diunggah?
3. Apakah oversampling dan baris jendela dipakai di v0.1.4?
4. Berapa dokumen yang sanggup diekstrak pengawas: prioritas 1 saja, 1 dan 2 (rekomendasi), atau semua (maksimal)?
5. Apakah label JAMBI KD perlu dikoreksi oleh Legal sebelum dipakai sebagai eval?

---

## Lampiran — sumber angka

- Skor dan dekomposisi kesalahan: `preparation/data/scores/test-{v0.1.2,v0.1.3,gpt-4.1-mini}-t0`, diparse dengan `parse_reply` dan `finalize` aplikasi; Jaccard rata-rata dengan pasangan satu lawan satu.
- Cluster: Ward, 6 cluster, 8 fitur struktur dari teks `pdftotext -layout`; untuk 60 dokumen dihitung dari teks versi `raw`.
- Produk, penyelenggara, dan split: `preparation/data/build-report.json`.
- Token: tokenizer `scalejade/qwen-sea-lion-v4.5-27b-pbbi` revisi `8d32a4b9`.
- Batas: `max_seq_length` 98.304 (`training/configs/pbbi-extraction.yaml`); output aplikasi 65.536 (`preparation/app_request.py`).
- Rincian analisis: `pbbi-v0.1.4-summary.md`.
