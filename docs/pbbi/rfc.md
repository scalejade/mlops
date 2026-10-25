# RFC: Evaluasi model berbasis kemiripan Jaccard yang dirata-rata

| | |
|---|---|
| **Status** | Draf, menunggu review |
| **Sistem** | `perjanjian-baku-bi`, fitur *Evaluasi Model* (`/settings/model-evaluation`) |
| **Kode terdampak** | `backend/internal/service/model_evaluation_service.go`, `backend/internal/domain/models.go`, `backend/internal/handler/model_evaluation_export.go`, `frontend/app/(dashboard)/settings/model-evaluation/page.tsx` |
| **Tanggal** | 25 Oktober 2026 |

## 1. Ringkasan

Fitur Evaluasi Model saat ini memasangkan klausa AI dengan baris validasi **berdasarkan nomor urut**, lalu membandingkan teksnya dengan cosine similarity bag-of-words. Akibatnya, satu perbedaan pemecahan klausa di awal dokumen menggeser semua pasangan sesudahnya, dan skor dokumen itu anjlok walaupun isinya benar.

RFC ini mengusulkan tiga perubahan:

1. Klausa dipasangkan **berdasarkan kemiripan Bunyi Klausa** (satu-ke-satu, pasangan paling mirip lebih dulu), bukan nomor urut.
2. Kemiripan diukur dengan **indeks Jaccard** atas kumpulan kata, bukan cosine bag-of-words.
3. Ditambahkan **Recall, Precision, dan F1** yang dihitung dari rata-rata skor kemiripan, tanpa ambang.

Metode ini sama dengan yang dipakai di laporan evaluasi untuk Bank Indonesia (`docs/pbbi/reports/report-pbbi-extraction-id.pptx`), sehingga angka di aplikasi dan di laporan akan sama.

## 2. Perilaku saat ini

Berdasarkan `model_evaluation_service.go` (`Evaluate`, `cosineSimilarity`, `computeEvaluationResult`):

| Aspek | Perilaku |
|---|---|
| Kunci pasangan | Kolom `No` di Excel validasi ↔ `SortOrder` klausa AI (posisi 1..M setelah diproses, `ai_service.go:662`) |
| Bunyi Klausa, Topik Klausa, Referensi Pasal, Penjelasan | Cosine similarity bag-of-words (frekuensi kata), skala 0–100, dirata-rata atas semua baris validasi; baris tanpa pasangan = 0 |
| No, No. Pasal, Status, Prinsip PK, Kategori Klausa | Exact match (case-insensitive), persentase benar atas semua baris validasi |
| Klausa AI yang tidak ada di file validasi | Diabaikan (tidak ada Precision) |
| Akurasi keseluruhan | Rata-rata semua skor field |

Catatan: notebook `docs/evaluasi_model_colab.ipynb` memakai metode yang berbeda lagi (embedding sentence-transformers, pemasangan berdasarkan Topik Klausa). Jadi saat ini aplikasi dan notebook di repo yang sama tidak konsisten.

## 3. Masalah

### 3.1 Pemasangan berdasarkan nomor urut tidak tahan terhadap perbedaan pemecahan

Logika production saya port ke Python, lalu saya jalankan pada 17 dokumen uji (2.074 klausa berlabel). Hasilnya untuk model fine-tuned v0.1.3, dokumen SEABANK:

| No | Pasal (validasi) | Pasal (AI) | Skor Bunyi Klausa |
|---|---|---|---|
| 1 | 1.1 | 1.1 | 99 |
| 7 | 2.2 | 2.2 | 97 |
| 13 | **2.9–2.16** (8 definisi digabung dalam label) | 2.8 | 45 |
| 19 | 2.23 | 2.14 | 57 |
| 31 | 2.42 | 2.26 | 21 |
| 37 | 4.3 | 2.32 | 13 |

Label menggabungkan definisi 2.9–2.16, sedangkan AI memecahnya. Mulai baris 13, setiap baris dibandingkan dengan klausa yang salah. Skor Bunyi Klausa dokumen ini **21,9**, padahal **71%** isi labelnya ada di keluaran AI kalau dipasangkan berdasarkan kemiripan.

Untuk seluruh 17 dokumen:

| | Model fine-tuned | gpt-4.1-mini |
|---|---|---|
| Bunyi Klausa, cara saat ini (gabungan 17 dokumen) | 30,5 | 17,3 |
| Bunyi Klausa, cara saat ini (rata-rata per dokumen) | 42,9 | 28,9 |
| **Recall, metode usulan** | **70,8** | **34,9** |

Skor saat ini lebih banyak mengukur apakah pemecahan klausa sama persis sejak klausa pertama, bukan kualitas ekstraksinya.

### 3.2 Tidak ada Precision

Klausa AI yang tidak ada di file validasi (karangan, duplikat, atau pecahan berlebih) tidak menurunkan skor. Model yang mengembalikan klausa sebanyak mungkin tidak dihukum.

### 3.3 Cosine bag-of-words terlalu longgar untuk teks hukum

Teks Perjanjian Baku banyak mengulang kata ("bank", "nasabah", "yang", nama produk). Cosine berbasis frekuensi menaikkan skor dari kata-kata yang berulang ini. Pada data uji, ada sekitar 8 klausa yang mendapat cosine ≥ 0,8 padahal lebih dari 40% kata uniknya tidak ada di klausa pasangannya. Cosine juga toleran terhadap kata tambahan: klausa yang tergabung dengan kalimat lain tetap mendapat skor tinggi, padahal tim Legal tetap harus memecahnya ulang.

### 3.4 Topik Klausa dinilai dengan kemiripan kata

Topik Klausa adalah ringkasan bebas, bukan teks yang disalin. Contohnya, "Definisi Account Linkage" vs "Definisi Account Linkage sebagai penghubung…" hanya mendapat skor 50 padahal keduanya benar. Skor field ini menurunkan akurasi keseluruhan tanpa mencerminkan kesalahan.

## 4. Usulan

### 4.1 Normalisasi dan skor kemiripan

```
words(t) = set kata dari lower(t), memisah pada setiap karakter yang bukan huruf atau angka
jaccard(a, b) = |words(a) ∩ words(b)| / |words(a) ∪ words(b)|      // 0..1; kedua kosong = 1
```

Pemisahan kata memakai aturan yang sudah ada di `termFrequency` (`!unicode.IsLetter && !unicode.IsDigit`), tetapi hasilnya berupa *set*, bukan frekuensi.

### 4.2 Pemasangan satu-ke-satu berdasarkan kemiripan

```
kandidat = semua pasangan (i baris validasi, j klausa AI) dengan jaccard > 0
urutkan kandidat: skor menurun, lalu i naik, lalu j naik       // deterministik
untuk setiap kandidat: pasangkan bila i dan j belum terpakai
```

Ini algoritma greedy (paling mirip lebih dulu), sama dengan `score.match_clauses` di pipeline training. Kompleksitasnya O(N·M·k), dengan k panjang klausa. Untuk dokumen terbesar di data uji (358 × 290 klausa ≈ 104 ribu pasangan), perhitungannya selesai dalam hitungan milidetik di Go.

### 4.3 Metrik utama: Jaccard dirata-rata

```
skor_i    = jaccard(pasangan baris i), atau 0 bila tidak berpasangan
total     = Σ skor_i
Recall    = total / jumlah baris validasi
Precision = total / jumlah klausa AI
F1        = 2 · P · R / (P + R)
```

Tidak ada ambang. Skala tampilan 0–100, mengikuti konvensi yang ada.

Kenapa dirata-rata, bukan ambang:
- Tidak ada parameter yang perlu dibela. Klausa berskor 0,79 dan 0,80 dinilai hampir sama.
- Klausa yang sebagian benar mendapat nilai sesuai kedekatannya dengan versi final, sejalan dengan beban perbaikan tim Legal.
- Pendekatan rata-rata sudah dipakai aplikasi, jadi perubahannya bagi pengguna kecil.

Kenapa Jaccard, bukan cosine: kata tambahan dan kata yang hilang dihukum sama beratnya, dan pengulangan kata tidak menaikkan skor.

### 4.4 Metrik pendamping

| Metrik | Definisi | Tujuan |
|---|---|---|
| Klausa tepat | Jumlah baris dengan skor ≥ 0,80 | Berapa klausa yang bisa langsung dipakai |
| Sebaran skor | Jumlah baris ≥ 0,80 / 0,50–0,79 / < 0,50 / tidak ditemukan | Menunjukkan seberapa banyak yang perlu diperbaiki |

Ambang 0,80 di sini **hanya untuk informasi**, tidak masuk ke Recall, Precision, atau F1.

### 4.5 Field lain

- **No. Pasal, Status, Prinsip PK, Kategori Klausa:** tetap exact match, tetapi dinilai **pada pasangan hasil 4.2**. Penyebutnya tetap jumlah baris validasi, dan baris tanpa pasangan dihitung salah.
- **Referensi Pasal, Penjelasan:** memakai Jaccard pada pasangan hasil 4.2, dengan cara rata-rata yang sama.
- **Topik Klausa:** ditampilkan berdampingan tanpa skor, dan tidak masuk akurasi keseluruhan (lihat pertanyaan terbuka 8.2).
- **No:** tidak lagi menjadi kunci pasangan. Kalau kolom ini ada, nilainya hanya ditampilkan.

### 4.6 Validasi input Excel

Syarat minimum berubah dari "kolom `No` + satu kolom lain" menjadi "**kolom `Bunyi Klausa` wajib**". Pesan error di `parseExcel` disesuaikan. Baris tanpa Bunyi Klausa dilewati.

## 5. Perubahan API dan data

### 5.1 `domain.EvaluationResult`, field tambahan

```go
Method              string  `json:"method"`               // "jaccard_avg_v1"
BunyiKlausaRecall   float64 `json:"bunyi_klausa_recall"`   // 0–100
BunyiKlausaPrecision float64 `json:"bunyi_klausa_precision"`
BunyiKlausaF1       float64 `json:"bunyi_klausa_f1"`
ExactClauses        int     `json:"exact_clauses"`         // skor ≥ 0,80
PartialClauses      int     `json:"partial_clauses"`       // 0,50–0,79
LowClauses          int     `json:"low_clauses"`           // < 0,50
UnmatchedAIClauses  []ClauseEvaluationScore `json:"unmatched_ai_clauses"`
```

`BunyiKlausaScore` dipertahankan sebagai alias dari `BunyiKlausaRecall`, supaya klien lama tetap berfungsi.

### 5.2 `domain.ClauseEvaluationScore`

- `BunyiKlausaScore` berisi skor Jaccard pasangan (0–100).
- Tambahan `Band string` (`exact` / `partial` / `low` / `unmatched`).
- `AINo` berisi `SortOrder` klausa AI yang menjadi pasangan (bisa berbeda dari `ValNo`).

### 5.3 Penyimpanan (`model_evaluation_saved_results`)

Tidak perlu migrasi skema. Field baru masuk ke `field_scores` (JSONB) dengan key `bunyi_klausa_recall`, `bunyi_klausa_precision`, `bunyi_klausa_f1`, dan `method`. Riwayat lama tidak punya key `method`, sehingga UI dapat menandainya sebagai "metode lama (nomor urut)" dan tidak membandingkannya langsung dengan hasil baru.

### 5.4 Export Excel (`model_evaluation_export.go`)

- Ringkasan menampilkan Recall, Precision, F1, dan sebaran skor.
- Detail per klausa menampilkan skor dan band.
- Ditambahkan sheet "Klausa AI tanpa pasangan".

Formatnya mengikuti `report-pbbi-extraction.xlsx`.

### 5.5 Frontend

- Kartu ringkasan: Recall, Precision, dan F1 untuk Bunyi Klausa, ditambah "Klausa tepat X dari N".
- Tabel detail diwarnai menurut band.
- Tab tambahan untuk klausa AI tanpa pasangan.

## 6. Pengujian

1. **Unit test** di `model_evaluation_service_test.go`:
   - `jaccard`: identik = 100, beda tanda baca = 100, tambahan kata, keduanya kosong.
   - Pemasangan: klausa tergabung, klausa dipecah, urutan acak (hasilnya harus sama dengan urutan asli), dan tie-break yang deterministik.
   - Recall dan Precision dengan klausa AI berlebih dan klausa yang hilang.
   - `TestEvaluate_MatchesByRowSequenceNumberNotByPasalOrTopikKlausa` diganti dengan test yang memastikan pasangan **tidak** bergantung pada nomor urut.
2. **Golden test** dengan 17 dokumen uji (fixture diambil dari `mlops`, tanpa teks kontrak di repo, atau di-mount saat CI). Hasil yang diharapkan:

   | | Recall | Precision | F1 | Klausa tepat |
   |---|---|---|---|---|
   | Model fine-tuned v0.1.3 | 70,8 | 84,4 | 77,0 | 1.365 |
   | gpt-4.1-mini | 34,9 | 77,9 | 48,2 | 587 |

   Toleransi ±0,1 untuk perbedaan pembulatan, dan juga untuk sedikit perbedaan tokenisasi: implementasi Python menggabungkan "non-Nasabah" menjadi satu kata, sedangkan Go memecahnya. Selisih ini harus dicek dan dicatat saat implementasi.

## 7. Rollout

1. Implementasikan di belakang flag `MODEL_EVAL_METHOD` (`sequence_cosine` | `jaccard_avg`), dengan default `jaccard_avg` di dev/UAT.
2. Jalankan kedua metode berdampingan di UAT pada beberapa dokumen nyata, lalu bandingkan.
3. Aktifkan di production. Pertahankan metode lama selama satu rilis untuk membaca riwayat.
4. Hapus metode lama dan flag setelah tidak dipakai.
5. Selaraskan `docs/evaluasi_model_colab.ipynb` dengan metode yang sama, atau tandai notebook itu sebagai usang.

## 8. Alternatif yang dipertimbangkan

| Alternatif | Alasan tidak dipilih |
|---|---|
| Tetap nomor urut, ganti cosine dengan Jaccard | Tidak menyelesaikan masalah utama (3.1) |
| Jaccard dengan ambang ≥ 0,80 sebagai metrik utama | Hasilnya peka terhadap pilihan ambang dan ada efek tepi; tetap tersedia sebagai metrik pendamping "klausa tepat" |
| Cosine bag-of-words (ambang atau rata-rata) | Longgar terhadap kata tambahan dan kata berulang (3.3); precision gpt-4.1-mini menjadi 89%, nyaris setara fine-tuned, sehingga perbedaan yang nyata tersembunyi |
| Cosine atas embedding (seperti notebook) | Mengukur makna, bukan salinan teks; butuh model embedding di backend; skornya sulit dijelaskan kepada pengguna |
| Pemasangan optimal (Hungarian) | Hasilnya hampir sama dengan greedy untuk kasus ini, tetapi lebih kompleks dan lebih lambat (O(n³)) |

## 9. Pertanyaan terbuka

1. Apakah akurasi keseluruhan (rata-rata semua field) masih diperlukan, atau diganti dengan F1 Bunyi Klausa sebagai angka utama?
2. Apakah Topik Klausa perlu dinilai sama sekali? Kalau perlu, apakah lewat review manual atau model embedding?
3. Apakah riwayat evaluasi lama perlu dihitung ulang dengan metode baru? Datanya ada: `clause_scores` menyimpan teks AI dan teks validasi.
4. Selisih tokenisasi Go vs Python ("non-Nasabah"): ikuti Go, lalu perbarui laporan bila angkanya berubah, atau sebaliknya?
