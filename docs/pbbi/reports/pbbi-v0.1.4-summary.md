# PBBI ekstraksi klausa — dua approach untuk v0.1.4

**Tanggal:** 1 November 2026 · **Status:** rencana, belum dijalankan · **Deck:** `pbbi-v0.1.4-summary.pdf`

**Aturan yang dipegang:**
- 60 dokumen `preparation/raw` (label pengawas BI) tetap dipakai semuanya.
- Eval (4) dan test (17) hanya dari 60 dokumen itu. Dokumen baru dari `/all` hanya masuk train.
- **Keluaran harus murni dari model.** Tidak ada pasca-proses atau logika tambahan di aplikasi. Semua perbaikan harus lewat model: data latih, cara training, dan bila disetujui, system prompt (perlu training ulang).
- PERMATA Internet Banking **dianggap bisa diunggah**, dengan asumsi deteksi bahasa aplikasi diperbaiki atau tersedia versi PDF yang benar.
- Metrik: Jaccard rata-rata tanpa ambang. Angka "strict" ditandai.

**Titik awal v0.1.3 (17 dokumen test):**
- Recall 70,8%, precision 84,4%, F1 77,0%.
- Kalah dari gpt-4.1-mini di 4 dokumen: BRI UE, OCBC IB, JATENG KD, SULTRA KD.
- Dari 44 dokumen baru di `/all`, **33 bisa dipakai** (termasuk PERMATA IB). 11 tidak bisa: scan, berbahasa Inggris, terlalu panjang, atau teksnya rusak oleh filter.

---

# Kenapa model fine-tuned v0.1.3 kalah dari gpt-4.1-mini

## Di mana kalahnya

Secara keseluruhan model fine-tuned jauh lebih baik (F1 77,0 vs 48,2), dan menang di 13 dari 17 dokumen. Model kalah di **4 dokumen**:

| Dokumen | Klausa label | F1 fine-tuned | F1 gpt | Selisih |
|---|---|---|---|---|
| BRI – Uang Elektronik Chip-Based | 27 | 0,827 | 0,896 | −0,069 |
| OCBC – Internet Banking | 176 | 0,506 | 0,567 | −0,061 |
| JATENG – Kartu Debit | 15 | 0,942 | 1,000 | −0,058 |
| SULTRA – Kartu Debit | 18 | 0,849 | 0,895 | −0,045 |

## Penjelasan spesifik per dokumen

**1. JATENG Kartu Debit: nomor urut ikut tersalin.** Isi dan pemisahan klausanya sama dengan label. Yang berbeda hanya nomor di awal teks: 14 dari 15 klausa model diawali nomor, sedangkan label dan gpt 0. Klausanya pendek, jadi satu token nomor saja menurunkan kemiripan 4–8% per klausa. Di dokumen yang hanya punya 15 klausa, itu cukup untuk kalah.

**2. SULTRA Kartu Debit: nomor urut ikut tersalin.** 14 dari 18 klausa model diawali nomor (label 1, gpt 0).

**3. BRI UE Chip-Based: nomor urut, tabel, dan rentang.**
- Nomor tersalin di 21 dari 33 klausa.
- **Tabel dipecah:** label memasukkan seluruh tabel `Tarif & Limitasi` ke satu klausa (aturan prompt 8.4), sedangkan model hanya mengambil baris "Biaya Perdana" (0,43; gpt 0,64).
- **Rentang:** butir `13-17` tidak dikelompokkan. Ini salah di kedua model (0,43 dan 0,40).
- Contoh tabel di train hanya 15 klausa di 2 dokumen, dan keduanya Kartu Kredit.

**4. OCBC Internet Banking: kalah karena kalimat pembuka definisi; sub-butir digabung oleh kedua model.**
- **Kalimat pembuka definisi tidak diulang. Inilah penyebab kalah.** Label mengulang "Apabila tidak secara tegas dinyatakan lain …" di setiap klausa definisi, dan gpt juga. Model fine-tuned tidak (0 dari 45). Rata-rata kemiripan klausa definisi: model 0,47, gpt 0,89. Di 153 klausa non-definisi keduanya setara (0,41 vs 0,40). Gaya ini sudah ada di train (49 klausa di 4 dokumen), tetapi model belum menangkapnya.
- **Sub-butir digabung, oleh kedua model.** Bagian "6. Syarat dan Ketentuan Pemegang Token" punya 21 klausa di label (butir a–s). Model fine-tuned menjadikannya 1 klausa (4.813 karakter), dan gpt juga 1 klausa (4.810 karakter). Ini membuat skor keduanya rendah, tetapi bukan alasan kalah.
- **Nomor tersalin:** 109 dari 116 klausa model.

## Contoh keluaran berdampingan: pengawas, gpt, dan model fine-tuned

Teks panjang dipotong dengan "…". Tanda **⟦…⟧** menandai bagian yang salah. Kemiripan = Jaccard kata terhadap klausa label.

| Kasus | Pengawas (label) | gpt-4.1-mini | v0.1.3 fine-tuned |
|---|---|---|---|
| **JATENG KD**, pasal `2` | `Besarnya penarikan uang tunai dan transaksi lainnya dengan BPD Card berdasarkan ketentuan yang berlaku.` | Teks sama — **1,00** | `⟦2.⟧ Besarnya penarikan uang tunai …` — **0,93** |
| **SULTRA KD**, `Pasal 1 PENGERTIAN\|1` | `Kartu Debit adalah kartu elektronik yang diterbitkan oleh Bank Sultra … Platinum, Gold dan Silver.` | Teks sama — **1,00** | `⟦1.⟧ Kartu Debit adalah kartu elektronik …` — **0,96** |
| **BRI UE**, `Ketentuan Umum\|3` | `Kepemilikan BRIZZI dapat dialihkan dengan cara memberikan fisik BRIZZI kepada orang lain.` | Teks sama — **1,00** | `⟦3.⟧ Kepemilikan BRIZZI dapat dialihkan …` — **0,92** |
| **BRI UE**, `Ketentuan Umum\|13-17` | Satu klausa berisi 5 definisi (`13. Nominal Saldo …` sampai `17. Top Up Deposit/tertunda …`) | Hanya butir 14 ⟦13, 15–17 tidak dikelompokkan⟧ — **0,40** | Hanya butir 14 ⟦13, 15–17 tidak dikelompokkan⟧ — **0,43** |
| **BRI UE**, `Tarif & Limitasi` | Seluruh tabel = 1 klausa: `\|Jenis\|Jumlah (Rp)\|` `\|Biaya Perdana\|35,000.00*\|` … `*Harga dapat berubah …` | Tabel utuh tanpa pemisah kolom `\|` — **0,64** | ⟦Hanya satu baris⟧: `Biaya Perdana 35,000.00*` — **0,43** |
| **OCBC IB**, `A. Definisi\|1` | `Apabila tidak secara tegas dinyatakan lain … mempunyai arti sebagai berikut:` `1. "Data Transaksi" adalah …` | Kalimat pembuka diulang persis — **1,00** | ⟦kalimat pembuka tidak ada⟧ `1. "Data Transaksi" adalah …` — **0,58** |
| **OCBC IB**, `6. Pemegang Token` | **21 klausa terpisah** (butir a–s) | ⟦1 klausa, 4.810 karakter⟧ — tidak terpasang | ⟦1 klausa, 4.813 karakter⟧ — tidak terpasang |

## Kenapa gpt menang di dokumen ini, padahal kalah jauh secara keseluruhan
- gpt **tidak menyalin nomor** di keempat dokumen itu, dan **menyalin kalimat pembuka definisi** apa adanya.
- Di dokumen pendek (15–27 klausa) dan di bagian definisi OCBC IB, keunggulan kecil itu cukup untuk menang.
- Di dokumen lain gpt kalah telak karena **melewatkan banyak isi**: recall gpt 34,9%, dan 14,2 poin recall-nya hilang karena isi terlewat. Model fine-tuned hampir tidak pernah melewatkan isi (1,0 poin).

## Solusi: semua lewat model, tanpa logika aplikasi

Karena keluaran harus murni dari model, tidak ada perbaikan instan. Semua perbaikan masuk lewat **training v0.1.4**:

| Penyebab kalah | Solusi dari sisi model | Kenapa diharapkan membantu |
|---|---|---|
| Nomor urut tersalin (JATENG, SULTRA, BRI) | (a) Data baru yang konsisten: item mandiri ditulis tanpa nomor, sesuai label. (b) Bila disetujui, satu kalimat di system prompt: "item bernomor yang berdiri sendiri ditulis tanpa nomornya". | Label train sudah 99% tanpa nomor, tetapi prompt tidak menyebutnya secara eksplisit (aturan 7.4/10.3 hanya mengatur penanda bila ada teks induk). |
| Kalimat pembuka definisi (OCBC IB) | Data dengan gaya ini: DBS KK, DANAMON KD, DANAMON General, **PERMATA IB**. Bila disetujui, satu contoh di prompt. | Contoh di train bertambah dari 4 menjadi 8 dokumen. Prompt aturan 7.1/7.3 sudah sejalan dengan label. |
| Sub-butir digabung (OCBC IB, dokumen panjang) | Data dengan banyak sub-butir dan dokumen panjang; opsi baris jendela; opsi oversampling (lihat Bab 2) | Kehilangan terbesar ada di sini (22,5–24,2 poin recall) |
| Tabel dipecah (BRI) | Dokumen bertabel di luar Kartu Kredit (MALUT, SUMUT, SULUTGO, KEPRI, JOGJA) | Contoh tabel di train sekarang hanya di 2 dokumen KK |

**Gambaran seberapa besar dampaknya bila model sudah belajar.** Simulasi pada jawaban v0.1.3 menunjukkan skor yang bisa dicapai **seandainya model sendiri** sudah menulis dengan benar. Ini **target perilaku untuk training, bukan aturan aplikasi**:

| Bila model sendiri … | Recall | Precision | F1 | Dokumen yang kalah dari gpt |
|---|---|---|---|---|
| (v0.1.3 sekarang) | 70,8 | 84,4 | 77,0 | 4 |
| … tidak lagi menyalin nomor urut | 71,4 | 85,1 | 77,6 | 2 (JATENG dan SULTRA jadi seri) |
| … juga memecah sub-butir berhuruf seperti label | 82,8 | 81,4 | 82,1 | 1 (BRI) |
| … juga mengulang kalimat pembuka definisi | 83,2 | 81,8 | 82,5 | 1 (BRI) |

Seberapa jauh v0.1.4 mendekati target itu bergantung pada seberapa banyak model belajar dari data baru (bagian Bab 2 dan Penutup).

---

# Isu yang ditemukan dan solusinya

Bagian ini menyebut **semua masalah** yang ditemukan, termasuk yang tidak bisa diselesaikan dengan data. Kedua bab berikutnya membahas **cara memilih data**.

## A. Isu model (penyebab kekalahan v0.1.3)

| # | Isu | Bukti | Solusi dari sisi model |
|---|---|---|---|
| A1 | **Klausa digabung** | 22,5–24,2 dari 29,2 poin recall hilang karena isi klausa label tergabung ke klausa model yang lebih besar. Model 1.741 klausa, label 2.074. Juga menekan precision. | Data dengan banyak sub-butir; dokumen panjang; opsi baris jendela; opsi oversampling |
| A2 | **Sub-butir berhuruf paling sering digabung** | 55–61% anak berhuruf (248–272 dari 448) digabung; anak berangka 12%, desimal 2% | Sama dengan A1. Label train memisahkan 1.174 klausa anak berhuruf dan hanya menggabungkan 98, jadi polanya ada tetapi belum cukup kuat. |
| A3 | **Dokumen panjang kurang dipecah** | Dokumen > 45k token: model hanya 66–81% jumlah klausa label. Train hanya punya 2 dokumen ≥ 20k token. | +5 dokumen ≥ 20k token |
| A4 | **Nomor urut tersalin** | Label 0,8% diawali nomor; model 22%; gpt 5% | Data konsisten; kalimat di prompt (perlu persetujuan dan training ulang) |
| A5 | **Kalimat pembuka definisi tidak diulang** | Label 8 dokumen konsisten (49 klausa train); model 0 dari 45 di OCBC IB | 4 dokumen contoh baru, termasuk PERMATA IB; contoh di prompt |
| A6 | **Tabel dipecah** | Tabel di train hanya 15 klausa di 2 dokumen KK | Dokumen bertabel di luar KK |
| A7 | **Dwibahasa** | BOC MB&IB 0,558; 47% digabung | Belum ada solusi data |
| A8 | **Prompt tidak menyebut nomor item mandiri** | Aturan 7.4/10.3 hanya mengatur penanda bila ada teks induk | Tambah satu kalimat di prompt saat training v0.1.4 (perlu persetujuan) |

## B. Isu data dan label

| # | Isu | Solusi |
|---|---|---|
| B1 | **4 dokumen `raw` berbeda isinya dengan `/all`** (SMBC IB, SULTRA KD, SINARMAS UE, CIMB KD; `raw` adalah subset) | Versi `raw` jadi acuan; uji v0.1.3 sekali pada versi `/all` |
| B2 | 7 dokumen `raw` punya tambahan kecil di `/all` (misalnya artikel SHOPEEPAY, versi Inggris SMBC KK) | Versi `raw` jadi acuan |
| B3 | **79 xlsx `/all` tidak bisa dipakai** sebagai label | Ekstraksi ulang oleh pengawas dengan panduan label tertulis |
| B4 | PDF kembar: CIMB IB (satu PDF dengan CIMB KD, eval) dan SINARMAS MB (satu PDF dengan SINARMAS UE, test) | Tidak boleh masuk train |
| B5 | JAMBI MB punya dua versi | Pakai versi biasa |
| B6 | Label JAMBI KD (eval) dicurigai (loss eval sekitar 0,65) | Cek dengan Legal |
| B7 | Gaya penulisan bank bocor antar-produk (6 bank) | Catat di laporan |

## C. Isu PDF dan pipa teks aplikasi

| # | Isu | Solusi |
|---|---|---|
| C1 | **PERMATA IB ditolak aplikasi.** Header browser terdeteksi Inggris; 96% baris isi < 8 kata sehingga "ambigu" dan ikut terhitung Inggris; porsi Indonesia 5,2% < 10%. | Perbaiki deteksi bahasa, atau minta versi PDF dokumen asli. Dokumen ini dianggap bisa diunggah dalam rencana ini. |
| C2 | **Dwibahasa berdampingan, filter gagal** (HSBC General, STANCHART General, BALI MB) | Filter per kolom, atau PDF satu bahasa |
| C3 | Scan/gambar (BJB Syariah KD, DANAMON KK, HSBC KK) | OCR atau file berteks |
| C4 | Inggris saja (BOC KD/KK, PERMATA KK ENG) | Minta versi Indonesia |
| C5 | Terlalu panjang (HSBC General, STANCHART General) | Pecah per produk atau minta dokumen per produk |
| C6 | Batas output aplikasi 65.536 token (jawaban terbesar sekarang 49.729) | Pantau dokumen panjang |

## D. Isu evaluasi

| # | Isu | Solusi |
|---|---|---|
| D1 | Test kecil: 17 dokumen; satu kontrak bisa menggeser F1 sekitar 0,01 | Gerbang per dokumen; laporan per dokumen |
| D2 | Eval sempit: 4 dokumen, tanpa KK, Multinational, dan cluster C–F | Checkpoint 1 epoch (step 20 konsisten di v0.1.2 dan v0.1.3) |
| D3 | **Cluster D (tabel/kolom) tidak pernah diuji** | KALSEL KD dipindah ke test tambahan (approach 2) |
| D4 | Simulasi target perilaku dihitung di test | Hanya indikasi besarnya dampak, bukan proyeksi; ukuran sebenarnya baru dari v0.1.4 |
| D5 | Skor per produk tidak menjelaskan penyebab | Laporkan juga per cluster struktur |

---

# Bab 1 — Approach pertama: kategori produk dan penyelenggara

## 1.1 Cara mengelompokkan
Dokumen dikelompokkan menurut **produk** (MB, KD, KK, IB, UE, dan lainnya) dan **jenis penyelenggara** (BPD, swasta nasional, BUMN, multinasional, PJP non-bank). Ini kategori yang dipakai di anotasi pengawas dan laporan klien.

## 1.2 Apa yang terlihat dari sudut ini

| Produk | Test | gpt | v0.1.2 | v0.1.3 | Klausa digabung model |
|---|---|---|---|---|---|
| Kartu Debit | 3 | 0,805 | 0,910 | 0,910 | 6% |
| Payment Gateway | 1 | 0,425 | 0,870 | 0,853 | 10% |
| UE Chip-Based | 1 | **0,896** | 0,841 | 0,827 | 0% |
| Mobile Banking | 5 | 0,449 | 0,765 | 0,799 | 20% |
| UE Server-Based | 2 | 0,450 | 0,825 | 0,775 | 26% |
| Kartu Kredit | 2 | 0,332 | 0,747 | 0,747 | 23% |
| Internet Banking | 2 | **0,625** | 0,625 | 0,622 | 37% |
| MB & IB | 1 | 0,460 | 0,605 | 0,558 | 47% |
| Multinational (penyelenggara) | 4 | 0,473 | 0,649 | 0,685 | 36% |

**Kesimpulan:** produk terlemah adalah Internet Banking, MB & IB, Kartu Kredit, dan Multinational. UE Server-Based dan Payment Gateway turun di v0.1.3 karena tidak mendapat data baru.

**Keterbatasan:** produk tidak menjelaskan kenapa model kalah. Internet Banking lemah hanya karena OCBC IB (MUAMALAT IB 0,991), dan tiga dari empat kekalahan justru ada di Kartu Debit dan UE Chip, dua produk yang skornya tinggi.

## 1.3 Kekalahan dan solusinya dari sudut produk

| Kekalahan | Produk | Penyebab | Solusi dari sisi model |
|---|---|---|---|
| BRI UE (0,827 vs 0,896) | UE Chip | Nomor tersalin, tabel dipecah, rentang 13-17 | Data UE dan dokumen bertabel; prompt soal nomor |
| OCBC IB (0,506 vs 0,567) | Internet Banking | Kalimat pembuka definisi (penyebab kalah); sub-butir digabung (juga gpt); nomor tersalin | Tambah dokumen IB (SINARMAS IB, PERMATA IB) dan Multinational |
| JATENG KD (0,942 vs 1,000) | Kartu Debit | Nomor tersalin | Data KD konsisten tanpa nomor; prompt |
| SULTRA KD (0,849 vs 0,895) | Kartu Debit | Nomor tersalin | Sama |

## 1.4 Dokumen yang ditambahkan (23 dokumen, semuanya train)

**Logika:** tambah produk dan penyelenggara dengan skor terendah atau yang tidak mendapat data di v0.1.3. Dasar buktinya: di v0.1.3 produk yang mendapat data naik (MB 0,765 → 0,799), sedangkan yang tidak mendapat data turun (UE Server 0,825 → 0,775).

| # | Dokumen | Produk | Penyelenggara | Token | Justifikasi |
|---|---|---|---|---|---|
| 1 | SINARMAS Internet Banking | IB | Swasta nasional | 6.471 | IB terlemah (0,622, seri gpt) |
| 2 | **PERMATA Internet Banking** | IB | Swasta nasional | ≈ 12–13k (perkiraan) | IB baru terbesar; punya kalimat pembuka definisi |
| 3 | DBS Kartu Kredit | KK | Multinasional | 16.734 | KK (0,747) dan Multinational (0,685) sekaligus; kalimat pembuka definisi |
| 4 | NOBU Kartu Kredit | KK | Swasta nasional | 10.668 | KK hanya 6 di train |
| 5 | SINARMAS Kartu Kredit | KK | Swasta nasional | 8.214 | Variasi penerbit KK |
| 6 | BCA Kartu Kredit | KK | Swasta nasional | 4.175 | KK bank swasta besar |
| 7 | BSI Kartu Kredit | KK | BUMN | 3.186 | Train belum punya KK BUMN |
| 8 | DANA | UE Server | PJP non-bank | 25.446 | UE Server turun; penyelenggara non-bank hanya 1 di train |
| 9 | LINKAJA | UE Server | PJP non-bank | 11.768 | Variasi PJP non-bank |
| 10 | BCA UE Server-Based | UE Server | Swasta nasional | 3.888 | UE Server dari bank |
| 11 | MEGA UE Server-Based | UE Server | Swasta nasional | 1.139 | UE Server dari bank, pendek |
| 12 | JAKARTA Mobile Banking | MB | BPD | 21.147 | MB panjang (≥ 20k); pola yang menaikkan DBS dan BJB di v0.1.3 |
| 13 | CIMB Mobile Banking | MB | Swasta nasional | 20.925 | MB panjang |
| 14 | NOBU Mobile Banking | MB | Swasta nasional | 20.332 | MB panjang |
| 15 | SMBC Mobile Banking | MB | Swasta nasional | 14.723 | MB menengah–panjang |
| 16 | KEPRI Mobile Banking | MB | BPD (syariah) | 6.210 | MB dengan tabel |
| 17 | BJB Syariah Mobile Banking | MB | BPD (syariah) | 2.647 | Variasi BPD syariah |
| 18 | PERMATA Mobile Banking | MB | Swasta nasional | 2.805 | Variasi bank swasta |
| 19 | MALUT Kartu Debit | KD | BPD | 10.372 | Tabel padat; BRI kalah karena tabel |
| 20 | SUMUT Kartu Debit | KD | BPD | 6.996 | Tabel |
| 21 | SULUTGO Kartu Debit | KD | BPD | 5.339 | Tabel |
| 22 | JOGJA Kartu Debit | KD | BPD | 7.900 | Multi-kolom |
| 23 | STANCHART Kartu Debit | KD | Multinasional | 13.067 | Multinational, penyelenggara terlemah |

Tidak masuk: CIMB IB (satu PDF dengan dokumen eval), BALI MB (teks rusak oleh filter).

## 1.5 Coverage train sebelum dan sesudah

| Produk | Sebelum | Sesudah | | Penyelenggara | Sebelum | Sesudah |
|---|---|---|---|---|---|---|
| Internet Banking | 7 | 9 | | Swasta nasional | 15 | 26 |
| Kartu Kredit | 6 | 11 | | BPD | 10 | 17 |
| Kartu Debit | 8 | 13 | | Multinasional | 8 | 10 |
| Uang Elektronik | 4 | 8 | | BUMN | 5 | 6 |
| Mobile Banking | 9 | 16 | | LSB / PJP non-bank | 1 | 3 |
| MB & IB, PG, Remitansi | 5 | 5 | | | | |
| **Total** | **39** | **62** | | **Total** | **39** | **62** |

## 1.6 Hasil yang bisa diharapkan (tanpa pasca-proses)

| Skenario | Recall | Precision | F1 |
|---|---|---|---|
| v0.1.3 sekarang | 70,8 | 84,4 | 77,0 |
| + 23 dokumen produk (perkiraan) | ~73–75 | ~85 | ~78–79 |

- **Precision ≥ 80%: ya.** **F1 ≥ 80%: kemungkinan belum.** **Recall ≥ 80%: tidak.**
- Dasar perkiraan: dari v0.1.2 ke v0.1.3, +8 dokumen hanya menaikkan recall 1,3 poin.
- Approach ini tidak menyasar sumber kehilangan terbesar, yaitu sub-butir yang digabung (Bab 2).

---

# Bab 2 — Approach kedua: cluster struktur PDF

## 2.0 Apa yang dilakukan di approach ini

| Langkah | Yang dilakukan | Hasil |
|---|---|---|
| 1. Profil semua PDF | 106 PDF `/all` dan 60 PDF `raw` diubah menjadi teks persis seperti di aplikasi; cek metadata, bahasa, tata letak, token | 33 dokumen baru bisa dipakai (termasuk PERMATA IB), 11 tidak |
| 2. Ukur struktur teks | 8 fitur: penomoran `1.`, `1.1`, `a.`, `A.`, tabel, kolom, paragraf tanpa nomor, dwibahasa | Vektor struktur per dokumen |
| 3. Clustering | Ward pada 102 PDF unik; uji 3–8 cluster; pilih 6 (silhouette 0,23) | Cluster A–F |
| 4. Petakan 60 dokumen | Cluster dihitung dari teks versi `raw` | Coverage per split; D tanpa test |
| 5. Urai kesalahan model | Setiap klausa label test: cocok / digabung / dipecah / terlewat; dicek ulang dengan teks verbatim | 22,5–24,2 dari 29,2 poin recall karena digabung |
| 6. Hubungkan kesalahan dengan cluster | Skor dan porsi penggabungan per cluster | B, C, F banyak digabung; A banyak nomor tersalin |
| 7. Ukur target perilaku | Simulasi skor seandainya model sendiri menulis seperti label; cek kebiasaan label train | Target F1 82,1; label train memisahkan 1.174 anak berhuruf vs 98 yang digabung |
| 8. Pilih dokumen baru | Prioritas: banyak sub-butir, panjang, cluster B/C/D/F, kalimat pembuka definisi | 12 prioritas 1, 13 prioritas 2, 8 opsional |
| 9. Hitung coverage | Sebelum dan sesudah per cluster; test tambahan dari 60 dokumen | 63 / 4 / 18; KALSEL KD = test cluster D |

## 2.0b Cara kerja clustering, dalam bahasa sederhana

**Intinya:** PDF dikelompokkan menurut **bentuk teksnya**, bukan menurut produknya. Dua dokumen masuk kelompok yang sama kalau cara penulisannya mirip, walaupun produknya berbeda. Alasannya, model gagal karena bentuk teks (nomor tersalin, sub-butir digabung, tabel dipecah), bukan karena jenis produk.

1. **PDF → teks.** Setiap PDF diubah menjadi teks persis seperti yang dikirim aplikasi ke model.
2. **Teks → 8 angka.** Dihitung berapa persen baris yang punya ciri tertentu:

   | Ciri | Contoh baris | Arti |
   |---|---|---|
   | `1.` | `3. Kepemilikan BRIZZI dapat dialihkan …` | Daftar bernomor satu tingkat |
   | `1.1` | `2.1.3 Nasabah wajib …` | Nomor desimal bertingkat |
   | `a.` | `b. Pendaftaran Token …` | Sub-butir berhuruf |
   | `A.` | `B. KETENTUAN UMUM` | Judul bagian berhuruf kapital |
   | Tabel | `Biaya Perdana      35,000.00` | Baris berbentuk tabel |
   | Kolom | teks terbagi dua kolom | Tata letak dua kolom |
   | Paragraf | paragraf panjang tanpa nomor | Gaya halaman web atau naratif |
   | Dwibahasa | baris Inggris yang dibuang filter | Dokumen dua bahasa |

3. **Kelompokkan yang mirip.** Komputer membandingkan 8 angka itu antar dokumen dan menggabungkan yang paling mirip sedikit demi sedikit (metode Ward), sampai terbentuk 6 kelompok. Ibaratnya memilah tumpukan dokumen menurut "rupa" halamannya tanpa membaca isinya.
4. **Hubungkan ke kesalahan model.** Setiap kelompok dicek kesalahan khasnya, lalu dokumen baru dipilih untuk mengisi kelompok yang lemah atau kosong.

**Contoh (nilai rata-rata cluster):**

| | `1.` | `a.` | Paragraf | Cluster | Kesalahan khas |
|---|---|---|---|---|---|
| Bergaya JATENG KD | **0,25** | 0,04 | 0,41 | A (daftar datar) | Nomor urut tersalin |
| Bergaya OCBC IB | 0,22 | **0,15** | 0,38 | B (induk → anak) | Sub-butir digabung |
| Bergaya OY | 0,08 | 0,03 | **0,65** | C (naratif) | Paragraf digabung |

Kedua dokumen pertama sama-sama banyak bernomor. Yang membedakannya adalah sub-butir `a.`, dan bagian itulah yang paling sering digabung model. Kartu Debit bisa berbentuk A (JATENG KD, BCA KD) maupun B (MANDIRI KD, SULSELBAR KD).

**Catatan:** pengelompokan ini tidak tegas (silhouette 0,23). Banyak dokumen berada di antara dua cluster, jadi cluster dibaca sebagai kecenderungan bentuk.

## 2.1 Profil enam cluster

**Rata-rata fitur per cluster** (porsi baris; tebal = paling khas)

| Cluster | `1.` | `1.1` | `a.` | `A.` | Tabel | Kolom | Paragraf | Dwibahasa |
|---|---|---|---|---|---|---|---|---|
| A. Daftar bernomor datar | **0,25** | 0,00 | 0,04 | 0,01 | 0,00 | 0,02 | 0,41 | 0,00 |
| B. Induk → anak | 0,22 | 0,00 | **0,15** | 0,03 | 0,00 | 0,02 | 0,38 | 0,00 |
| C. Paragraf naratif | 0,08 | 0,02 | 0,03 | 0,00 | 0,00 | 0,01 | **0,65** | 0,01 |
| D. Multi-kolom dan tabel | 0,13 | 0,03 | 0,05 | 0,01 | **0,12** | **0,53** | 0,56 | 0,03 |
| E. Dwibahasa | 0,08 | 0,04 | 0,02 | 0,00 | 0,04 | 0,20 | 0,51 | **0,50** |
| F. Desimal bertingkat | 0,04 | **0,21** | 0,13 | 0,00 | 0,00 | 0,02 | 0,42 | 0,00 |

| Cluster | Bentuk khas | `/all` (102) | di 60 (train/eval/test) | Baru bisa dipakai | F1 v0.1.3 vs gpt | Digabung model | Kesalahan khas |
|---|---|---|---|---|---|---|---|
| **A. Datar** | `1. … 2. … 3. …` | 43 | 26 (16/2/8) | 17 | **0,820** vs 0,609 | 13% | Nomor urut tersalin |
| **B. Induk → anak** | `1. Bank berhak:` lalu `a. … b. …` | 18 | 13 (8/2/3) | 5 | **0,691** vs 0,522 (terlemah) | 26% | Sub-butir digabung |
| **C. Naratif** | Paragraf panjang tanpa nomor | 14 | 7 (3/0/4) | 4 | 0,775 vs 0,407 | 27% | Paragraf dan blok definisi digabung |
| **D. Tabel/kolom** | Dua kolom, tabel tarif dan limit | 11 | 3 (3/0/0) | 5 | **belum pernah diuji** | – | Tabel dipecah |
| **E. Dwibahasa** | Indonesia dan Inggris | 8 | 4 (3/0/1) | 0 | 0,558 vs 0,460 | 47% | Teks terpotong filter, digabung |
| **F. Desimal** | `2.1 → 2.1.1` gaya pasal | 8 | 7 (6/0/1) | 1 | 0,789 vs 0,236 | 24% | Sub-butir di dalam pasal digabung |

PERMATA IB masuk **cluster C (naratif)**: dibagi per Pasal 1–20 dengan isi paragraf tanpa nomor. Setelah header/footer browser dibuang dan baris kolom sempit disambung kembali, jaraknya ke pusat C 1,15 (cluster terdekat berikutnya, A, 3,42). Pada teks yang rusak oleh filter bahasa, dokumen ini sempat terbaca sebagai E; itu artefak filter.

**Anggota cluster di 60 dokumen**

| Cluster | Train | Eval | Test |
|---|---|---|---|
| A | BANTEN KD, BCA IB, BCA MB, BNI KK, CIMB UE, JATENG MB, JATIM KD, JATIM MB, JTRUST MB&IB, KALTIMTARA MB&IB, MEGA MB, NTT IB, OCBC KD, SINARMAS KD, SMBC IB, UOB IB | CIMB KD, JAMBI KD | BCA KD, BRI UE, DBS MB, JATENG KD, MUAMALAT IB, SINARMAS UE, SMBC KK, SULTRA KD |
| B | ACEH MB, BANTEN MB, DANAMON UE, GOPAY, JAGO MB, MANDIRI KD, MANDIRI UE, SULSELBAR KD | BNI MB, OVO | BJB MB, MANDIRI MB, OCBC IB |
| C | MASPION IB, MASPION KD, MAYBANK MB&IB | – | NAGARI MB, OCBC KK, OY, SHOPEEPAY |
| D | BSI MB, KALSEL KD, UOB KK | – | – |
| E | CIMB KK, STANCHART IB, STANCHART KK | – | BOC MB&IB |
| F | BTN IB, HONEST KK, MEGA KK, UOB MB, WISE, YUKK | – | SEABANK MB |

## 2.2 Kenapa model kalah, dilihat dari struktur

| Kehilangan recall v0.1.3 | Poin |
|---|---|
| Digabung ke klausa model yang lebih besar | **24,2** (22,5 dengan verifikasi teks verbatim) |
| Dipecah atau terpotong | 1,8 |
| Cocok, beda teks kecil (misalnya nomor) | 1,7 |
| Isi terlewat | 1,0 |
| Lainnya | 0,4 |
| **Total** | **29,2** |

- Penggabungan juga menekan precision: 13,2 dari 15,6 poin precision yang hilang adalah sisa kemiripan pada klausa model yang terlalu besar.
- **Sub-butir berhuruf paling sering digabung:** 55–61% (248–272 dari 448). Anak berangka 12%, butir desimal 2%. Sub-butir berhuruf adalah ciri cluster B dan F.
- **Dokumen panjang paling parah:** di dokumen test > 45k token, model hanya menghasilkan 66–81% dari jumlah klausa label (kecuali SMBC KK). Train hanya punya 2 dokumen ≥ 20k token.
- **Empat kekalahan dipetakan ke cluster:**
  - JATENG, SULTRA, dan BRI ada di A (nomor tersalin).
  - OCBC IB ada di B: kalah karena kalimat pembuka definisi, sedangkan sub-butirnya digabung oleh kedua model.
- **Cluster D tidak pernah diuji.**

## 2.3 Solusi per cluster (semua lewat model)

| Cluster | Data | Prompt (bila disetujui) | Cara training |
|---|---|---|---|
| A | Data konsisten: item mandiri tanpa nomor | "Item bernomor yang berdiri sendiri ditulis tanpa nomornya" | – |
| B | Dokumen dengan banyak sub-butir berhuruf dan dokumen panjang | Contoh kalimat pembuka definisi | Opsi oversampling dokumen B |
| C | Tambah dokumen naratif (train 3 vs test 4) | – | – |
| D | Dokumen bertabel di luar KK; 1 dokumen D ke test | – | – |
| E | Belum ada (0 dokumen baru yang bersih) | – | – |
| F | Dokumen desimal dengan sub-butir | – | – |
| Semua dokumen panjang | +5 dokumen ≥ 20k token | – | **Opsi baris jendela:** turunkan batas baris di `build.py` agar dokumen panjang dipecah menjadi beberapa baris berisi bagian utuh (fitur sudah ada; efek belum diuji) |

**Target perilaku per cluster** (F1 seandainya model sendiri tidak menyalin nomor dan memecah sub-butir; simulasi pada jawaban v0.1.3):

| Cluster | v0.1.3 | Target perilaku |
|---|---|---|
| A | 0,820 | 0,837 |
| B | 0,691 | **0,786** |
| C | 0,775 | 0,820 |
| E | 0,558 | 0,558 |
| F | 0,789 | 0,875 |
| Semua | 0,770 | 0,821 |

## 2.4 Dokumen yang ditambahkan (25 dokumen, semuanya train)

**Prioritas 1 (12 dokumen): menyasar penggabungan, dokumen panjang, dan kalimat pembuka definisi**

| Dokumen | Cluster | Token | Baris `a.` | Alasan |
|---|---|---|---|---|
| JAKARTA Mobile Banking | B | 21.147 | 234 | Sub-butir terbanyak, panjang, cluster terlemah |
| STANCHART Kartu Debit | F | 13.067 | 157 | Sub-butir; Multinational |
| CIMB Mobile Banking | A | 20.925 | 125 | Panjang dengan banyak sub-butir |
| DANA | C | 25.446 | 53 | Panjang; cluster C; UE Server |
| DBS Kartu Kredit | C | 16.734 | 0 | Kalimat pembuka definisi; Multinational |
| **PERMATA Internet Banking** | C | ≈ 12–13k | 1 | Kalimat pembuka definisi; IB baru terbesar |
| DANAMON Kartu Debit | A | 9.816 | 52 | Kalimat pembuka definisi dan sub-butir |
| LINKAJA | C | 11.768 | 32 | Cluster C, UE Server |
| NOBU Mobile Banking | A | 20.332 | 47 | Panjang |
| NOBU Kartu Kredit | A | 10.668 | 38 | KK dengan sub-butir |
| NTB Mobile Banking | B | 2.473 | 33 | Cluster B |
| BCA UE Server-Based | B | 3.888 | 24 | Cluster B, UE Server |

**Prioritas 2 (13 dokumen): menutup celah coverage**

| Dokumen | Cluster | Alasan |
|---|---|---|
| KEPRI MB, MALUT KD, SUMUT KD, SULUTGO KD, JOGJA KD | D | Tabel dan kolom; cluster D baru punya 3 dokumen train |
| BCA KK | C | Naratif, KK |
| BALI KD, NTT MB | B | Cluster B |
| DANAMON General | A | Jenis General pertama; kalimat pembuka; panjang |
| SMBC MB | A | Panjang |
| SINARMAS IB, SINARMAS KK, BSI KK | A | Produk IB dan KK |

**Prioritas 3 (8 dokumen, opsional):** BRI KD, JAMBI MB, BJB Syariah MB, SULSELBAR MB, SUMSELBABEL MB, SUMUT MB, PERMATA MB, MEGA UE. Semuanya cluster A, pendek, dan produknya sudah kuat.

## 2.5 Coverage sebelum dan sesudah

| Cluster | Sebelum | + P1 | + P1 + P2 |
|---|---|---|---|
| A. Datar | 16 | 20 | 25 |
| B. Induk → anak | 8 | 11 | **13** |
| C. Naratif | 3 | 7 | **8** |
| D. Tabel/kolom | 3 | 3 | **7** (8, dikurangi KALSEL yang pindah ke test) |
| E. Dwibahasa | 3 | 3 | 3 |
| F. Desimal | 6 | 7 | 7 |
| **Total** | **39** | **51** | **63** |

| Ciri di train | Sebelum | Sesudah |
|---|---|---|
| Dokumen dengan teks ≥ 20k token | 2 | 7 |
| Dokumen dengan kalimat pembuka definisi | 4 | 8 |
| Multinational | 8 | 10 |
| Internet Banking | 7 | 9 |
| Baris sub-butir berhuruf di teks baru | – | +1.066 |

**Eval dan test (dari 60 dokumen):** test 17 tetap; **KALSEL KD dipindah dari train ke test tambahan** supaya cluster D terukur (dilaporkan terpisah, dibandingkan dengan gpt); eval 4 tetap. Komposisi **63 / 4 / 18**.

## 2.6 Hasil yang bisa diharapkan (tanpa pasca-proses)

| Skenario | Recall | Precision | F1 |
|---|---|---|---|
| v0.1.3 sekarang | 70,8 | 84,4 | 77,0 |
| v0.1.4 dengan 25 dokumen + prompt (perkiraan) | ~73–76 | ~85–86 | ~79–80 |
| Target perilaku: model sendiri tidak menyalin nomor dan memecah sub-butir | 82,8 | 81,4 | 82,1 |

- **Precision ≥ 80%: ya.**
- **F1 ≥ 80%: mungkin, tetapi tidak pasti.** Perkiraannya 79–80%, dengan ketidakpastian besar.
- **Recall ≥ 80%: kemungkinan besar belum di v0.1.4.** Untuk mencapainya, model harus belajar memecah sub-butir jauh lebih baik: kehilangan karena penggabungan perlu turun sekitar 40%, padahal dari v0.1.2 ke v0.1.3 (+8 dokumen) hanya turun sekitar 6%.
- **Cara memperbesar peluang** (semuanya dari sisi model): dokumen prioritas 1 lebih dulu; kalimat tambahan di prompt (perlu persetujuan); opsi baris jendela dan oversampling dokumen dengan banyak sub-butir. Efek masing-masing baru bisa diukur setelah training.

## 2.7 Dibanding approach pertama

| | Approach 1 (produk) | Approach 2 (struktur) |
|---|---|---|
| Menjelaskan kekalahan | Sebagian | Ya: 22,5–24,2 dari 29,2 poin recall karena penggabungan |
| Dokumen | 23 | 25 (+8 opsional), dengan prioritas |
| Irisan | 20 dokumen sama | 20 dokumen sama |
| Cluster B (terlemah) | +2 | +5 |
| Contoh kalimat pembuka | +2 (DBS KK, PERMATA IB) | +4 |
| Cluster D terukur | Tidak | Ya (KALSEL ke test) |
| Perkiraan F1 | ~78–79 | ~79–80 |

**Rekomendasi:** jalankan approach 2.

---

# Penutup — komposisi akhir kedua approach

| Split | Sekarang (60) | Approach 1 (produk) | Approach 2 (struktur) |
|---|---|---|---|
| **Train** | 39 (65,0%) | **62** (74,7%) = 39 + 23 baru | **63** (74,1%) = 39 − 1 (KALSEL) + 25 baru |
| **Eval** | 4 (6,7%) | **4** (4,8%) | **4** (4,7%) |
| **Test** | 17 (28,3%) | **17** (20,5%) | **18** (21,2%) = 17 + KALSEL KD |
| **Total** | 60 | **83** | **85** |

**Per produk**

| Produk | Train A1 | Train A2 | Eval | Test A1 | Test A2 |
|---|---|---|---|---|---|
| Internet Banking | 9 | 9 | 0 | 2 | 2 |
| Kartu Kredit | 11 | 11 | 0 | 2 | 2 |
| Kartu Debit | 13 | 14 | 2 | 3 | 4 |
| Uang Elektronik | 8 | 7 | 1 | 3 | 3 |
| Mobile Banking | 16 | 16 | 1 | 5 | 5 |
| MB & IB | 3 | 3 | 0 | 1 | 1 |
| General | 0 | 1 | 0 | 0 | 0 |
| Payment Gateway | 1 | 1 | 0 | 1 | 1 |
| Remitansi | 1 | 1 | 0 | 0 | 0 |
| **Total** | **62** | **63** | **4** | **17** | **18** |

**Per cluster struktur**

| Cluster | Train A1 | Train A2 | Eval | Test A1 | Test A2 |
|---|---|---|---|---|---|
| A. Daftar datar | 26 | 25 | 2 | 8 | 8 |
| B. Induk → anak | 10 | 13 | 2 | 3 | 3 |
| C. Naratif | 8 | 8 | 0 | 4 | 4 |
| D. Tabel/kolom | 8 | 7 | 0 | 0 | 1 |
| E. Dwibahasa | 3 | 3 | 0 | 1 | 1 |
| F. Desimal | 7 | 7 | 0 | 1 | 1 |
| **Total** | **62** | **63** | **4** | **17** | **18** |

## Peta split per dokumen

**Eval (4, sama di kedua approach):** BNI MB, CIMB KD, JAMBI KD, OVO UE Server.

**Test (17, sama di kedua approach):** BCA KD, BJB MB, BOC MB&IB, BRI UE Chip, DBS MB, JATENG KD, MANDIRI MB, MUAMALAT IB, NAGARI MB, OCBC IB, OCBC KK, OY PG, SEABANK MB, SHOPEEPAY UE Server, SINARMAS UE Server, SMBC KK, SULTRA KD. Approach 2 menambah **KALSEL KD** sebagai test tambahan.

**Train dari 60 dokumen** (39 di A1; 38 di A2 karena KALSEL KD pindah ke test): ACEH MB, BANTEN KD, BANTEN MB, BCA IB, BCA MB, BNI KK, BSI MB, BTN IB, CIMB KK, CIMB UE Server, DANAMON UE Chip, GOPAY UE Server, HONEST KK, JAGO MB, JATENG MB, JATIM KD, JATIM MB, JTRUST MB&IB, KALSEL KD, KALTIMTARA MB&IB, MANDIRI KD, MANDIRI UE Chip, MASPION IB, MASPION KD, MAYBANK MB&IB, MEGA KK, MEGA MB, NTT IB, OCBC KD, SINARMAS KD, SMBC IB, STANCHART IB, STANCHART KK, SULSELBAR KD, UOB IB, UOB KK, UOB MB, WISE Remitansi, YUKK PG.

## Diagram Venn dokumen tambahan

```
      Approach 1 · produk (23)          Approach 2 · struktur (25)
   ┌───────────────────────┬───────────────────────┬───────────────────────┐
   │   Hanya A1 · 3        │   Sama · 20           │   Hanya A2 · 5        │
   │                       │                       │                       │
   │   MEGA UE             │   SINARMAS IB,        │   DANAMON KD          │
   │   BJB Syariah MB      │   PERMATA IB          │   DANAMON General     │
   │   PERMATA MB          │   DBS KK, NOBU KK,    │   NTB MB              │
   │                       │   SINARMAS KK, BCA KK,│   NTT MB              │
   │   (cluster A, pendek; │   BSI KK              │   BALI KD             │
   │   di A2 menjadi       │   DANA, LINKAJA,      │                       │
   │   prioritas 3)        │   BCA UE              │   (kalimat pembuka    │
   │                       │   JAKARTA MB, CIMB MB,│   definisi; cluster B)│
   │                       │   NOBU MB, SMBC MB,   │                       │
   │                       │   KEPRI MB            │                       │
   │                       │   MALUT KD, SUMUT KD, │                       │
   │                       │   SULUTGO KD, JOGJA KD│                       │
   │                       │   STANCHART KD        │                       │
   └───────────────────────┴───────────────────────┴───────────────────────┘
```

| Irisan | Jumlah | Isi |
|---|---|---|
| **Sama di keduanya** | 20 | IB 2 · KK 5 · UE 3 · MB 5 · KD 5. Semua dokumen panjang, bertabel, dan Multinational. |
| **Hanya approach 1** | 3 | MEGA UE, BJB Syariah MB, PERMATA MB (cluster A, pendek; di approach 2 menjadi prioritas 3) |
| **Hanya approach 2** | 5 | DANAMON KD, DANAMON General, NTB MB, NTT MB, BALI KD (kalimat pembuka definisi dan cluster B) |

KALSEL KD bukan dokumen baru: di approach 2 dokumen ini hanya dipindah dari train ke test.

## Langkah kerja

1. Perbaiki deteksi bahasa aplikasi atau dapatkan versi PDF PERMATA IB yang bisa diunggah.
2. Putuskan perubahan system prompt (nomor item mandiri; contoh kalimat pembuka definisi).
3. Tulis panduan label untuk pengawas: anak berhuruf dipisah dengan teks induk, item mandiri tanpa nomor, kalimat pembuka definisi diulang, satu tabel satu klausa.
4. Pengawas mengekstrak prioritas 1 (12), lalu prioritas 2 (13).
5. Bangun data dengan `build.py` dan cek token; putuskan opsi baris jendela dan oversampling.
6. Latih v0.1.4 selama 1 epoch.
7. Evaluasi pada 17 test, test tambahan KALSEL, dan per cluster, dibandingkan dengan gpt per dokumen.

**Gerbang rilis:** F1 tidak di bawah v0.1.3; tidak ada dokumen yang turun lebih dari 0,03; jumlah dokumen yang kalah dari gpt tidak bertambah. Recall, precision, dan F1 dilaporkan apa adanya, termasuk bila belum mencapai 80%.

---

## Lampiran — sumber dan metode

- Skor dari `preparation/data/scores/test-{v0.1.2,v0.1.3,gpt-4.1-mini}-t0`, diparse dengan `parse_reply` dan `finalize` aplikasi. Jaccard rata-rata dengan pasangan satu lawan satu.
- **"Digabung":** klausa label yang tidak terpasang atau kemiripannya < 0,3, dan ≥ 80% katanya ada di dalam satu klausa model. Verifikasi ketat: 10 kata terakhir klausa label ditemukan berurutan di klausa model (429 dari 471 terkonfirmasi).
- **Target perilaku:** jawaban v0.1.3 diubah seolah model tidak menyalin nomor (kecuali `pasal` rentang) dan memecah klausa dengan ≥ 2 baris `a.`/`b.` menjadi teks induk + butir (kecuali rentang dan definisi), lalu diskor ulang. Ini **bukan** aturan aplikasi; hanya mengukur besarnya dampak bila model belajar perilaku itu.
- **Clustering:** Ward, 6 cluster, 8 fitur, 102 PDF unik. Untuk 60 dokumen dipakai teks versi `raw`.
- **Perkiraan v0.1.4:** ekstrapolasi kasar dari v0.1.2 (R 69,5, P 85,0) ke v0.1.3 (R 70,8, P 84,4).
- **Token** dihitung dengan tokenizer `scalejade/qwen-sea-lion-v4.5-27b-pbbi` revisi `8d32a4b9`. Token PERMATA IB adalah perkiraan, karena teks utuhnya belum bisa diambil dengan pipa aplikasi.
