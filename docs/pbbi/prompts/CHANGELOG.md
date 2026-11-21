# Changelog prompt ekstraksi PBBI

Dokumen ini mencatat apa yang berubah di setiap versi prompt, kapan perubahan dibuat, apa tujuannya, dan bagaimana hasilnya. Semua file prompt ada di folder ini; daftar file dan skor ringkas ada di [README.md](README.md).

Semua waktu dalam WIB (UTC+7). Waktu versi app diambil dari commit di repo ini. Waktu draf diambil dari jam terakhir file disimpan.

## Ringkasan arah

```
Okt–18 Nov   Fase 1  Format keluaran          app e028187 → app 1d7ccdd
19 Nov       Fase 2  Balik default ke PISAH    draf P1–P8 → v1 → v2
19 Nov       Fase 3  Rem pemecahan berlebihan   v3 → v3.1
20 Nov       Fase 4  Tutup sisa + P5–P8        v4
```

1. **Fase 1** menambah aturan format (tabel, catatan kaki) dan tidak menyentuh cara memecah klausa. Efek sampingnya: adapter yang dilatih dengan prompt lama turun ±4 poin, karena adapter rapuh terhadap perubahan teks prompt.
2. **Fase 2** mengubah arah prompt. Prompt app condong **menggabung** ("uji proses dulu secara holistik", "klausa yang tidak dapat dipisahkan"), padahal label memecah 85–89% daftar. Default dibalik menjadi **pisah**, kecuali prosedur, daftar informatif, dan syarat kumulatif.
3. **Fase 3** menyeimbangkan. Setelah default menjadi pisah, muncul pemecahan berlebihan di dua tempat, yaitu definisi dan daftar sebaris `(i)`, `(ii)`. Keduanya dibatasi.
4. **Fase 4** menambah aturan untuk P5–P8, lalu menutup sisa P1–P4 dengan aturan yang lebih spesifik. Aturan prioritas (6.7) dipasang supaya aturan baru tidak bisa melemahkan P1–P4.

Setiap aturan baru sejak Fase 2 dicek terhadap mayoritas label di 85 dokumen (train, eval, test) sebelum dimasukkan.

## Hasil per versi

| Versi | Dibuat | Diuji dengan | F1 | Klausa label bermasalah* |
|---|---|---|---|---|
| app `e028187` | 10 Okt 21:56 | Adapter v0.1.3 / v0.1.4 (17 dok) | 77,0 / 78,3 | 1.355 / 1.225 |
| app `1d7ccdd` | 18 Nov 19:34 | Adapter v0.1.3 / v0.1.4 (17 dok); agent (18 dok) | 73,3 / 74,1; agent 91,7 | agent 792 |
| draf P1–P8 | 19 Nov 15:40 | — | — | — |
| v1 | 19 Nov 15:54 | gpt-4.1-mini (18 dok) | 54,8 (app `1d7ccdd`: 51,7) | — |
| v2 | 19 Nov 15:54 | — | — | — |
| v3 | 19 Nov 15:57 | Agent (18 dok) | 94,1 | — |
| v3.1 | 19 Nov 22:39 | Agent (OY, KALSEL, SMBC ulang) | 94,8 (gabungan) | 323 |
| v4 | 20 Nov 07:36 → 07:56 | Agent Sonnet (DBS MB) | DBS 97,1 (v3: 96,6) | DBS: P1 1, P4 0 |

\* Klausa label yang tidak cocok sempurna, dihitung dengan pengklasifikasi P1–P8 yang sama di 17 dokumen test lama.

---

## app `e028187` — 10 Okt 2026 21:56 (repo `2e7b301`)

**Asal:** prompt awal di branch `sys-prompt` aplikasi.

**Isi:** aturan dasar header, klausa induk-anak dan independen, taksonomi (hak/kewajiban, definisi umum/khusus, informatif), urutan uji 5.2–5.5 (proses → hak/kewajiban → definisi khusus → definisi umum), pewarisan induk (7), format `pasal`/`topic`/`clause_text`.

**Masalah yang kemudian ditemukan:**
- Uji pertama 5.2 menanyakan "proses atau prosedur" secara holistik.
- Ada kriteria kabur "klausa-klausa anak yang tidak dapat dipisahkan".
- 6.1.2 menggabung prosedur "MESKIPUN" ada hak/kewajiban.

Akibatnya model condong menggabung (pola P1–P3), dan tidak ada larangan menulis nomor klausa independen (P4).

**Dipakai:** training adapter v0.1.1–v0.1.3.

## app `1d7ccdd` — 18 Nov 2026 19:34 (repo `2e8d74e`)

**Perubahan:**

| Aturan | Isi |
|---|---|
| 1.1.1 | Catatan yang dirujuk angka atau bintang di badan teks **bukan** footer |
| 8.4 | Tabel: setiap baris di baris baru, diawali dan diakhiri `\|` |
| 8.6 (baru) | Catatan kaki dan catatan akhir: diekstraksi, ditempel di akhir klausa yang memuat penandanya, tidak menjadi klausa sendiri |
| 10.3 | Daftar penyusunan ulang yang diizinkan bertambah dari empat menjadi lima (ditambah catatan kaki) |
| 11.1 #6 | Checklist catatan kaki |

**Arah:** format keluaran (tabel, catatan kaki). Aturan pemecahan klausa tidak disentuh.

**Hasil:** adapter v0.1.3 dan v0.1.4 sama-sama turun ±4 poin dibanding prompt lama, dan DBS MB runtuh (F1 21,5). Ablation tidak menemukan satu aturan pemicu; adapter rapuh terhadap perubahan teks apa pun (report v0.1.4 §11.4). Gerbang rilis v0.1.4 gagal.

## draf P1–P8 — 19 Nov 2026 15:40

**Asal:** analisis kesalahan v0.1.3 dan v0.1.4 di 17 dokumen test, ditambah audit kebiasaan label di 75 dokumen. Hasil audit: label memecah 89% daftar hak/kewajiban, 87% daftar kondisi, dan 85% daftar prosedur.

**Perubahan** (dari app `1d7ccdd`):

| Pola | Aturan | Isi |
|---|---|---|
| P1 | 5.1.1, 5.2, 6.1.1, 6.1.2 | Kriteria kabur "tidak dapat dipisahkan" dihapus. Gabung hanya untuk **prosedur** (5.2.2), **daftar informatif** (5.2.3), dan **syarat kumulatif** (5.2.1). Jika ragu, bukan prosedur |
| P1 | 5.2.2 (baru) | Definisi prosedur = langkah berurutan untuk satu tindakan. 5.2.2.3: kondisi, hak/kewajiban/larangan, pernyataan, alasan/akibat, dan `wajib … dengan cara:` **bukan** prosedur |
| P1 | 5.2.3 (baru) | Daftar informatif (fitur, menu, saluran, tips) selalu digabung |
| P1 | 6.6 (baru), 7.1.1 | Tabel panduan cepat berdasarkan bunyi kalimat induk, dan contoh pemisahan daftar kondisi |
| P2, P3 | 3.3.3–3.3.5 (baru) | Butir bernomor mandiri dan paragraf mandiri adalah klausa sendiri; satu bagian tidak pernah ditulis sebagai satu klausa |
| P4 | 7.4.2, 10.3 | Nomor klausa independen tidak ditulis di `clause_text` |
| P5 | 10.3 | Judul bagian klausa independen dicatat di `pasal`, bukan `clause_text` |
| P6 | 7.3.1 (baru) | Setiap klausa anak hasil pemisahan wajib memuat kalimat induk |
| P8 | 4.3.3.4, 6.5.4 (baru) | Nama produk sebagai Definisi Khusus; daftar definisi berpengantar diperlakukan sebagai struktur campuran |

**Arah:** membalik default dari **gabung** menjadi **pisah**, mengikuti label, dan mencakup semua pola sekaligus.

**Hasil:** tidak diuji. Diganti v1 supaya efek P1–P4 bisa diukur terpisah.

## v1 — 19 Nov 2026 15:54

**Perubahan** (dari draf P1–P8):

| Aturan | Isi |
|---|---|
| 4.3.3.4, 6.5.4, 7.3.1 | **Dihapus**: aturan P6 dan P8 dikeluarkan, fokus hanya P1–P4 |
| 10.3 | Contoh judul bagian (P5) dihapus; ditegaskan bahwa aturan 8.2 tidak mengubah larangan nomor |
| 3.3.4, 3.3.5 | Batas ditegaskan: paragraf di dalam struktur induk-anak diatur 3.5, bukan 3.3.4; lanjutan kalimat bukan klausa baru |
| 5.2.2.3 | Pengecualian: daftar unsur wajib (5.2.1) dan daftar informatif (5.2.3) tetap digabung, walaupun bentuknya mirip daftar yang dipisah |
| 11.1 #7 | Checklist baru: prosedur, informatif, dan kumulatif digabung; kondisi, hak/kewajiban, dan pernyataan dipisah |

**Arah:** mempersempit cakupan ke pola terbesar (P1–P4, ±83% kesalahan), dan menutup celah yang bisa membuat aturan baru bertentangan dengan aturan lama.

**Hasil:** gpt-4.1-mini F1 54,8 vs 51,7 dengan app `1d7ccdd`.

## v2 — 19 Nov 2026 15:54

**Perubahan** (dari v1):

| Aturan | Isi |
|---|---|
| 4.3.3.4 (kembali) | Nama produk, aplikasi, atau fitur bermerek milik Penyelenggara adalah Definisi Khusus |
| 6.5.4 (kembali) | Daftar definisi berpengantar: Definisi Khusus dipisah, Definisi Umum yang bersebelahan digabung, dan pengantar diwariskan. Dilengkapi contoh |
| 3.3.5 | Penggabungan independen hanya untuk Definisi Umum yang **bersebelahan**; bagian definisi tidak pernah ditulis seluruhnya sebagai satu klausa |

**Arah:** aturan P2/P3 baru ("butir mandiri tidak digabung") berbenturan dengan bagian Definisi, yang memang boleh digabung. v2 mengembalikan aturan definisi supaya kedua aturan tidak bertentangan.

**Hasil:** tidak diuji terpisah. File ini sama dengan `preparation/prompts/extraction_system.md` di working tree (belum di-commit).

## v3 — 19 Nov 2026 15:57

**Perubahan** (dari v2):

| Aturan | Isi |
|---|---|
| 5.2.3.4 (baru) | Daftar **definisi** bukan daftar informatif; diatur 4.3, 6.3, dan 6.5 |
| 6.6 | Baris "Daftar informatif" diberi catatan: bukan daftar definisi |
| 11.1 #7 | Ditambah: bagian definisi dipisah per Definisi Khusus dan per rangkaian Definisi Umum |

**Arah:** menghapus kontradiksi antara aturan label "daftar informatif selalu digabung" dan aturan definisi. Tanpa ini, satu daftar definisi bisa dibaca sebagai informatif lalu digabung seluruhnya.

**Hasil** (agent, 18 dokumen): F1 94,1 vs 91,7 dengan app `1d7ccdd`. 12 dokumen naik, 3 sama, 3 turun. OY turun 6,5 karena daftar sebaris `(i)`, `(ii)` dipecah, dan ini satu-satunya pelanggaran gerbang.

## v3.1 — 19 Nov 2026 22:39

**Perubahan** (dari v3):

| Aturan | Isi |
|---|---|
| 3.2.4 (baru) | Penanda butir yang ditulis **di dalam** satu kalimat atau paragraf (`(i)`, `(a)`, `1)`) bukan klausa anak; paragraf itu tetap satu klausa, apa pun isinya |
| 3.3.3 | Butir sebaris bukan "butir" dalam pengertian aturan ini |
| 6.6 | Tabel hanya untuk daftar yang butirnya **mengawali baris baru** |
| 11.1 #10 | Checklist baru: tidak ada paragraf dipecah karena butir sebaris |

**Arah:** rem untuk efek samping Fase 2. Aturan "kondisi alternatif → pisah" ikut memecah daftar sebaris, padahal label menggabungnya (29 digabung vs ±5 dipisah).

**Hasil:** OY 82,8 → 92,1 (app `1d7ccdd`: 89,3), KALSEL 89,3 → 95,0, SMBC tetap 92,2. Gabungan 18 dokumen F1 94,8, tanpa dokumen yang turun > 3 poin. Klausa bermasalah 792 → 323 (P1 99→33, P2 70→24, P3 94→24, P4 330→19).

**Cacat yang diketahui:** contoh kosong `(, )` di 5.2.3.4, dan urutan checklist #9/#10 tertukar. Keduanya diperbaiki di v4.

## v4 — 20 Nov 2026, dua tahap

### Tahap 1 — 07:36: P5–P8

| Pola | Aturan | Isi | Dasar dari label |
|---|---|---|---|
| P1–P4 | 6.7 (baru) | Urutan prioritas: aturan P1–P4 tidak pernah dikalahkan; aturan baru hanya berlaku bila syaratnya jelas | Permintaan: P1–P4 prioritas |
| P5 | 10.3, #14 | Contoh benar/salah judul bagian; klausa independen tidak pernah diawali judul | Sudah 0, hanya dikunci |
| P6 | 7.1.2 (baru) | Kalimat induk `…:` tetap diwariskan walaupun butirnya kalimat lengkap | Kasus OY |
| P6 | 7.1.3 (baru) | Judul butir di antara induk dan isi ikut diwariskan; tiap judul adalah sub-bagian sendiri | 196 klausa label memakai pola ini, 3 tidak |
| P7 | 3.3.6 (baru) | Satu paragraf tidak dipecah di batas kalimat | Kasus OY, OCBC KK |
| P7 | 5.2.4 (baru) | Gabung: induk `… yang:` (ciri satu objek), dan kondisi yang akibatnya muncul setelah butir terakhir | 1/1 dan 2/2 |
| P8 | 4.3.4 (baru) | Definisi Khusus produk hanya kategori, nama bermerek, Transfer Dana, dan Pembayaran; komponen produk adalah Definisi Umum | Para pihak 75–86% berdiri sendiri, komponen 15–44% |
| — | 5.1.1, 5.2, 5.2.2.3, 6.1.2, 6.6, 7.6 | Rujukan silang ke 5.2.4 | — |
| — | 5.2.3.4, 11.1 | Perbaikan cacat v3.1 | — |

**Tidak dibuat aturan:** daftar pilihan dengan `atau`, karena label terbelah 46% gabung dan 54% pisah.

### Tahap 2 — 07:54–07:56: menutup sisa P1–P4

Sisa v3/v3.1 dibedah per kasus:

| Pola | Sebab sisa | Aturan | Dasar dari label |
|---|---|---|---|
| P4 (semua 19) | Nomor induk teratas ikut ditulis (`5. Dalam hal …, maka:`) | 7.4.3 (baru) | Induk tanpa nomor 3.060, dengan nomor 7 |
| P1 | Daftar bertingkat: tingkat terdalam digabung | 5.1.6 (baru): uji diulang di setiap tingkat | DBS 37.10, BJB J |
| P1 | `yang timbul dari:`, `termasuk namun tidak terbatas pada:` digabung | 5.2.2.3 dan 6.6: PISAH | 93% dan 77% dipisah |
| P1 | Pernyataan status produk digabung | 5.2.2.3 dan 6.6: PISAH | SINARMAS |
| P1/P2 | Ketentuan bersebelahan digabung | 6.6: `… dengan ketentuan sebagai berikut:` diuji per butir | 65% dipisah |
| P2/P3 | Butir setingkat ditempel ke butir sebelumnya | 3.3.7 (baru) | SHOPEEPAY 15.2/15.3 |
| P3 | Paragraf ketentuan baru setelah butir digabung | 3.3.8 (baru) | OCBC KK |
| P2 | Definisi badan usaha digabung | 4.3.2.3 (baru): `X adalah PT …` adalah para pihak | 37 vs 2 |
| — | 5.2.4.2 dibatasi | `…, maka:` yang butirnya akibat tetap PISAH | DBS 5, 7 |

**Arah:** P1–P4 "habis tuntas" dengan aturan yang sempit dan berbasis label, lalu dikunci di 6.7.

**Hasil** (DBS MB, Sonnet, 20 Nov ±08:10):

| Prompt | F1 | P1 | P2 | P3 | P4 | Nomor tersalin | P5 | P6 | P7 | P8 |
|---|---|---|---|---|---|---|---|---|---|---|
| app `1d7ccdd` | 95,9 | 13 | 3 | 0 | 13 | 34 | 0 | 8 | 6 | 0 |
| v3 | 96,6 | 17 | 3 | 0 | 13 | 34 | 0 | 8 | 4 | 0 |
| **v4** | **97,1** | **1** | 4 | 0 | **0** | **0** | 0 | 8 | **1** | 0 |

- **P4 hilang total.** Sisa P1 (1) adalah paragraf penutup bagian 32, bukan daftar yang digabung.
- **Sisa P2 (4)** adalah definisi 16–24 dan `proses Pembukaan Rekening`. Yang kedua adalah konflik label dengan aturan "prosedur selalu digabung".
- **P6 tetap 8, tapi kasusnya berganti.** 7.1.3 memperbaiki 8 kasus di bagian 36 Pajak. Namun 7.1.2 menimbulkan 8 kasus baru di bagian 3: pengantar `Berikut ini adalah proses pendaftaran …` diakhiri titik, dan model membaca "diakhiri `:`" sebagai syarat wajib.

### Uji v4 di 6 dokumen sulit (20 Nov, agent Claude, 1.199 klausa label)

| Dokumen | app `1d7ccdd` | v3 | v3.1 | **v4** |
|---|---|---|---|---|
| DBS MB (Sonnet) | 95,9 | 96,6 | — | **97,1** |
| OCBC KK | 85,6 | 95,5 | — | **95,6** |
| SEABANK MB | 90,7 | 93,6 | — | 93,5 |
| OY PG | 89,3 | 82,8 | 92,1 | **95,3** |
| MUAMALAT IB | 100,0 | 98,6 | — | 99,6 |
| SHOPEEPAY UE | 95,1 | 94,5 | — | **96,4** |
| **Gabungan** | **92,0** | **94,1** | **94,9** | **95,6** |

v4 adalah yang terbaik secara keseluruhan (R 96,2, P 94,9). Tidak ada dokumen yang turun lebih dari 3 poin dari prompt app. Semua skor diukur terhadap label **sebelum** jawaban pengawas, jadi angka OY, SEABANK, dan DBS akan berubah setelah label disesuaikan (lihat v4.5).

## v4.5 — 20 Nov 2026: jawaban pengawas R1–R21

**Asal:** 21 pertanyaan aturan dijawab pengawas (workbook `pertanyaan-pengawas-sysprompt-v4.5.xlsx`; jawaban lengkap dicatat di [jawaban-pengawas-v4.5.md](jawaban-pengawas-v4.5.md), file aslinya di `preparation/data/jawaban-pengawas-sysprompt-v4.5.xlsx`, tidak masuk git). Semua keputusan mengikuti pengawas.

**Prinsip pengawas** (dipasang sebagai 5.1.0): **pisah** bila kalimat induk memuat hak/kewajiban **dan** setiap butir adalah opsi yang berdiri sendiri; **gabung** bila butir merupakan satu kesatuan (syarat bersama, ciri satu objek, prosedur) atau hanya informasi.

| No | Aturan | Perubahan |
|---|---|---|
| — | 5.1.0 (baru) | Prinsip dasar gabung/pisah di atas |
| R13 | 3.2.4, 3.3.6, 6.6, #7, #10 | **Dibalik dari v3.1:** daftar sebaris `(i)`, `(ii)` yang diantar kalimat induk diuji gabung/pisah seperti daftar biasa (contoh OY: `Anda tidak dapat: (i) …; (ii) …` → PISAH). Penanda di tengah kalimat tanpa pengantar tetap satu klausa |
| R5 | 7.1.2.1 (baru), #11 | Pengantar yang diakhiri titik (`… berikut ini.`, `Berikut ini adalah …`) tetap kalimat induk. Contoh BCA PASPOR dan DBS 3 → digabung |
| R5 | 5.2.4.4 (baru) | Kesatuan syarat → gabung (BCA PASPOR Xpresi) |
| R1 | 5.2.2.3, 6.6 | Daftar **pilihan** cara/waktu/pihak → PISAH (BJB D.9, DBS 11.7) |
| R2 | 5.2.1.2, 6.6 | `dan/atau` = alternatif (yang diutamakan `atau`) |
| R8 | 4.3.2.3, 4.3.3.3, 4.3.3.4, 4.3.4, #13 | Khusus: `Transaksi QRIS`, `Transaksi Finansial`. Umum: `QRIS`, `Pembayaran Tagihan`, `Transfer Terjadwal`, `Transaksi Berkala`, komponen produk, peran umum `Penerbit`. Contoh "pembayaran tagihan/biller" dihapus dari 4.3.3.3 |
| R6 | 10.1, #14 | Judul butir tanpa kalimat induk (`1. Penggunaan Informasi.`) = segmen `pasal`; `clause_text` tanpa judul dan tanpa penanda |
| R12 | 9.6 (baru), 9.2, #15 | Istilah Inggris di dalam kalimat Indonesia disalin apa adanya (`'Kirim' atau 'Submit'`, `Telegraphic Transfer (TT)`) |
| R16 | 5.2.4.3 (baru), 6.6 | Sarana/data yang wajib dipakai atau didaftarkan (Livin') → gabung |
| R17 | 5.2.3.5.1 (baru), 6.6 | Tata cara pengamanan tanpa penanda hak/kewajiban → gabung |
| R20 | 5.2.3.5.2 (baru), 5.2.2.3, 6.6 | **Dibalik dari v4:** pernyataan status produk (Simas E-Money) → gabung |
| R21 | 5.2.3.5.3 (baru), 6.6 | **Dibalik dari v4:** `tunduk pada ketentuan berikut` yang butirnya menjelaskan satu fitur (SeaBank 5.26) → gabung |
| R18 | 3.5.9 (baru) | Contoh teks penutup (C): DBS 21 diwariskan ke setiap butir; OCBC KK 12 = klausa sendiri (D) |
| R19 | 3.2.3.6 (baru) | Sub-daftar berakhir saat butir tidak lagi melanjutkan kalimat induk (NAGARI III.4: 1–5 anak, 6 dst. klausa sendiri) |
| R3, R4, R7, R9, R10, R11, R14, R15 | — | Dikonfirmasi, tidak berubah. R3 ditambahkan ke tabel 6.6 sebagai contoh |

**Tafsiran untuk jawaban yang ambigu:**
- R1 DBS: kolom jawaban "digabung", catatan "dipisah karena opsi". Diikuti catatannya (pisah), sesuai prinsip pengawas.
- R6 OCBC KK: `pasal` `D. Lain-Lain|D. Lain-Lain|a` dianggap salah ketik untuk `D. Lain-Lain|5. Fitur Reward Kartu Kredit|a`.
- R8 (b): "bukan" dibaca "bukan Definisi Khusus" (= Umum), sesuai label SEABANK dan OCBC KK.
- R21: SEABANK 5.26 digabung seluruhnya (a–g), termasuk butir e dan g yang memuat kewajiban dan pengecualian tanggung jawab.

**Perbaikan dari rencana v4.5 awal:** #1 (7.1.2) masuk lewat R5, #3 (definisi) diganti jawaban R8. #2 (butir yang tercetak menyambung di baris sebelumnya) tidak diperlukan lagi, karena R13 membuat daftar sebaris diuji sama dengan daftar biasa.

**Panjang:** 24.732 token (v4: 21.463; prompt di data sekarang `1d7ccdd`: 14.282), dihitung dengan tokenizer `qwen-sea-lion-v4.5-27b-pbbi`. Dengan v4.5, **2 dari 85 baris training melewati `max_seq_length` 98.304**: UOB MB 100.129 dan JAGO MB 99.295.

**Uji DBS MB** (20 Nov malam, agent Sonnet, satu run per prompt, F1 Jaccard average). Label DBS disesuaikan dengan jawaban pengawas hanya di scratchpad, `raw/` belum diubah. Yang disesuaikan:
- Bagian 2 dan 3 digabung (R5).
- Definisi 12–14 digabung (R8).
- Daftar sebaris 6|2 dan 22|3 dipisah (R13).
- Daftar `dan/atau` 10|8, 11|3|1, dan 12|1 dipisah (R2).

| Prompt | Klausa | Label lama | Label sesuai pengawas |
|---|---|---|---|
| v4 | 263 | **97,1** | 91,4 |
| v4.5 (draf pertama) | 272 | 90,8 | 94,6 |
| **v4.5** (setelah perbaikan) | 251 | 92,3 | **98,1** (R 97,9, P 98,3) |

**Perbaikan setelah draf pertama:**
- **3.2.3.6 dipersempit.** Aturan ini hanya berlaku kalau butir awal sub-daftar berupa penggalan yang melanjutkan kalimat induk. Di draf pertama, model memakainya untuk memotong bagian 2 dan 3 DBS: butir 4 dan seterusnya dijadikan klausa mandiri tanpa kalimat induk, sehingga presisi turun ke 91,1.
- **Contoh 7.1.2.1 dipertegas.** Seluruh butir di bawah `Berikut ini adalah proses …` digabung, sampai header berikutnya.
- **Konflik "saluran" diselesaikan.** Kata ini muncul di daftar pilihan (pisah, 5.2.2.3) dan di daftar informatif (gabung, 5.2.3.1). Sekarang dibedakan: saluran yang diantar hak atau kewajiban adalah daftar pilihan, sedangkan saluran yang hanya informasi adalah daftar informatif.

**Sisa selisih:**
- 12|1 (`Aplikasi … dapat digunakan untuk Transfer dana dari; (i) …`) digabung oleh model. Ini wajar: subjeknya aplikasi, jadi kalimat ini daftar fitur informatif, bukan opsi hak suatu pihak. Saat label diubah nanti, kasus ini **tetap digabung**.
- 11|6: satu paragraf dipecah di batas kalimat, melanggar 3.3.6. Ini kesalahan model, bukan teks prompt.

## v4.6 — 20 Nov 2026: perbaikan dari uji v4.5 di 7 dokumen

**Acuan:** jawaban pengawas ([jawaban-pengawas-v4.5.md](jawaban-pengawas-v4.5.md)). Kunci jawaban uji = label lama, ditambah semua jawaban pengawas, ditambah kasus yang bentuknya sama persis dengan contoh pengawas. Kalau tidak ada jawaban pengawas yang mencakup suatu kasus, label lama yang dipakai. v4.5 tidak diubah (`09-v4.5.md`).

**Uji v4.5** (agent Sonnet, satu run per dokumen, F1 Jaccard average terhadap kunci jawaban di atas; label di `raw/` belum diubah):

| Dokumen | Klausa kunci | app `1d7ccdd` | v3 | v4 | **v4.5** |
|---|---|---|---|---|---|
| DBS MB | 249 | — | — | 91,9 | **97,6** |
| OY PG | 98 | 85,1 | 88,9 | 89,9 | **96,0** |
| NAGARI MB | 47 | 93,0 | 93,9 | — | **96,8** |
| SINARMAS UE | 47 | **99,4** | 98,3 | — | 96,2 |
| SMBC KK | 172 | 91,1 | 92,5 | — | **94,0** |
| BJB MB | 114 | — | — | — | 94,9 |
| SEABANK MB | 356 | 90,7 | 92,3 | 94,0 | **94,7** |

Penyesuaian kunci jawaban selama uji, semuanya dari jawaban pengawas:
- BJB E.1: dua skenario `apabila: a. Telah memiliki …, maka … b. Tidak memiliki …, maka …` dipisah (R3).
- SMBC definisi 27 `"Pembayaran" adalah setiap transaksi pembayaran tagihan …` jadi Definisi Umum (R8).
- DBS 22|3 (saluran pengaduan) dikembalikan ke digabung, sesuai label, karena tidak ada jawaban pengawas yang mencakupnya.

**Perubahan** (dari v4.5):

| No | Aturan | Masalah di v4.5 | Bukti | Perbaikan |
|---|---|---|---|---|
| F1 | 5.2.2.3, 5.2.3.1, 6.6 | Batas daftar saluran belum tegas | Keputusan user 21 Nov: **ikuti prinsip pengawas** (R1, R2) | Saluran untuk melaksanakan hak/kewajiban = daftar pilihan → **PISAH**, juga bila dihubungkan `dan/atau` (BJB M.1.b, NAGARI III.2, DBS 22\|3). Tetap digabung: saluran yang hanya informasi (BJB L.1) dan saluran yang butirnya berisi langkah (SINARMAS Cash-In = prosedur). *Draf pertama v4.6 sempat menggabung semua saluran mengikuti label lama; dibatalkan* |
| F2 | 6.5.1.1 (baru) | Butir `X yaitu …` di luar bagian definisi digabung sebagai Definisi Umum | SMBC Pasal 11 (status kolektibilitas 1–5) | Aturan 6.5 hanya berlaku di bagian definisi |
| F3 | 7.1.3.5 (baru) | Pewarisan tiga tingkat (induk + judul butir + induk kedua + butir) kehilangan dua tingkat teratas | OY 6.4 (5 klausa) | Contoh benar/salah tiga tingkat |
| F4 | 6.6 | Contoh skenario hanya bentuk `maka:` | BJB E.1 (model sudah benar) | Ditambah contoh `apabila: a. … maka … b. … maka …`; langkah di dalam satu skenario digabung |
| F5 | 10.1 | Aturan judul butir (R6) bisa berbenturan dengan 7.4.3 (`1. Hak Pemegang Kartu :`) | Laporan agent SMBC | Aturan R6 hanya untuk judul tanpa `:`; pengantar berakhiran `:` tetap klausa induk (7.4.3) |
| F6 | 3.2.3.6 | Batas sub-daftar (R19) masih dipakai di luar kasus Nagari | SEABANK 5.25: butir b–h kehilangan kalimat induk | Hanya berlaku kalau sub-daftar memakai skema nomor yang sama dengan daftar di atasnya; contoh 5.25 (a–h tetap anak) |
| F7 | 5.2.4.3 | Daftar informasi/data sasaran satu kewajiban dipisah | SEABANK 6.11, 10.17, 11.9 | Digabung termasuk teks penutupnya, sejalan dengan R16 |
| F8 | 3.2.4.5 | R13 tidak diterapkan pada kewajiban dengan kondisi sebaris `(a)…(b)…(c)` | SEABANK 15.3 | Contoh ditambahkan; kalimat sesudahnya klausa sendiri |
| F9 | 5.2.3.5.3 | R21 hanya diterapkan sebagian (a–c digabung, d–g dipisah) | SEABANK 5.26 | Seluruh a–g digabung, termasuk butir kewajiban; 6.3 tidak diterapkan |

**Panjang:** 26.201 token (v4.5: 24.958). UOB MB menjadi 101.538 token, masih di bawah `max_seq_length` 102.400, dengan sisa 862 token. Pemadatan prompt (rencana B) belum dikerjakan.

**Hasil — SEABANK MB** (agent Sonnet, satu run, kunci jawaban yang sama dengan uji v4.5):

| Prompt | Klausa | Label lama | Kunci sesuai pengawas |
|---|---|---|---|
| app `1d7ccdd` | 371 | 90,7 | 90,7 |
| v4 | 372 | 93,5 | 94,0 |
| v4.5 | 375 | 94,2 | 94,7 |
| **v4.6** | 353 | **96,4** | **99,0** (R 98,6, P 99,4) |

- Semua kasus yang diperbaiki sekarang cocok: 5.25 (F6), 6.11, 10.17, dan 11.9 (F7), 15.3 (F8), dan 5.26 (F9). Uji ini memakai draf pertama F1 (saluran digabung); F1 kemudian diubah mengikuti prinsip pengawas, jadi 23\|d belum diuji dengan aturan final.
- **Sisa selisih:**
  - Definisi 2.20 `Pelanggan` dan 2.39 `Transaksi` digabung sebagai Definisi Umum, padahal label memisahnya. `Transaksi` (setiap transaksi melalui Aplikasi) mirip `Transaksi Finansial`, yang menurut pengawas Definisi Khusus (R8). Kasus ini belum diatur tegas di prompt.
  - 15.7 `Yang mencakup:` dipisah. Ini sejalan dengan R14 (ruang lingkup suatu kewajiban dipisah), tetapi label menggabungnya.
- Belum diuji di dokumen lain.

## v4.7 — 21 Nov 2026: v4.6 dipadatkan

**Tujuan:** memberi ruang token. Dengan v4.6, baris terpanjang (UOB MB) hanya punya sisa 862 token di bawah `max_seq_length`.

**Perubahan** (dari v4.6). Isi aturan tidak berubah; yang dibuang hanya pengulangan:

| Bagian | Sebelum | Sesudah |
|---|---|---|
| 2.3 | Tiga subaturan dan contoh | Satu aturan dengan contoh yang sama |
| 3.5.6–3.5.8 | Penomoran `pasal` 4 tingkat dan dua contoh blok kode | Tiga butir dan dua contoh ringkas, isinya sama (uji tumbukan nomor, segmen buatan, (D) tidak mewarisi induk) |
| 5.1.1–5.1.5 | Lima aturan cara uji | Empat aturan ringkas; 5.1.3 dilebur ke 5.1.2 |
| 6.1–6.4 | Aturan gabung/pisah versi app dan contoh 8 anak dengan blok kode | Aturan singkat; algoritme campuran 6.3 dalam empat butir; contoh 6.4 dalam satu kalimat |
| 7.5, 8.1, 10.1 | Penomoran otomatis dijelaskan tiga kali | Dijelaskan sekali di 7.5; 8.1 dan 10.1 merujuk ke sana |
| 10.1 (klausa tunggal) | Lima butir | Dua butir |
| 11.1 | 15 butir yang mengulang aturan, dengan nomor 15 ganda | 8 butir yang merujuk nomor aturan |

**Tidak diubah:** jawaban pengawas (R1–R21) beserta contohnya, prinsip 5.1.0, tabel 6.6, perbaikan F1–F9, aturan format (bagian 8–11).

**Panjang:** 22.739 token (v4.6: 26.201, −3.462). UOB MB menjadi ±98.080 token, dengan sisa ±8.400 token di bawah `max_seq_length` 106.496.

**Hasil — SEABANK MB** (agent Sonnet, satu run). Kunci jawaban yang sama dengan uji v4.6, ditambah keputusan saluran 21 Nov: 23|d dipisah per saluran.

| Prompt | Klausa | Label lama | Kunci sesuai pengawas |
|---|---|---|---|
| v4.5 | 375 | 94,2 | 95,1 |
| v4.6 (draf F1) | 353 | 96,4 | 98,5 |
| **v4.7** | 356 | 95,8 | **98,6** (R 98,2, P 99,0) |

**Hasil — 7 dokumen** (agent Sonnet, satu run per dokumen, paralel, 21 Nov). Kunci jawaban: label lama + jawaban pengawas + kasus yang bentuknya sama + keputusan saluran. Selama uji, kunci jawaban ditambah tiga kasus di SMBC Pasal 10: 5 (skenario, R3), 6 (kondisi alternatif), dan 13 (saluran). Semua skor v4.5 di tabel dihitung ulang dengan kunci jawaban yang sama.

| Dokumen | Klausa kunci | app `1d7ccdd` | v4 | v4.5 | **v4.7** |
|---|---|---|---|---|---|
| SEABANK MB | 359 | 90,3 | 93,6 | 95,1 | **98,6** |
| SINARMAS UE | 47 | 99,4 | — | 96,2 | **100,0** |
| NAGARI MB | 49 | 95,8 | — | 99,2 | **99,2** |
| DBS MB | 249 | — | 91,8 | 98,6 | **98,2** |
| SMBC KK | 175 | 92,1 | — | 94,4 | **96,8** |
| BJB MB | 115 | — | — | 95,5 | **95,2** |
| OY PG | 98 | 85,1 | 89,9 | 96,0 | **94,8** |
| **Rata-rata** | | | | **96,4** | **97,5** |

- v4.7 naik di SEABANK (+3,5), SMBC (+2,4), dan SINARMAS (+3,8), berkat perbaikan F1–F9. Di NAGARI hasilnya sama; di DBS dan BJB turun kurang dari 0,5, masih dalam variasi antar-run.
- **OY −1,2.** Selisihnya terutama dari kalimat penutup bagian 9 (`Kami berhak untuk menyelidiki … pelanggaran-pelanggaran dari salah satu hal di atas …`). Model menjadikannya klausa sendiri (D); kunci jawaban mewariskannya ke setiap butir (C). Pengawas tidak menjawab kasus ini, dan kedua tafsiran sah menurut aturan 3.5.
- **Kandidat perbaikan berikutnya:** BJB D.11 `Biaya yang dikenakan kepada Pengguna … adalah sebagai berikut: a. … b. … c. …` digabung model sebagai daftar informatif. Label memisahnya, dan prinsip pengawas juga memisahnya, karena setiap biaya adalah beban Pengguna.

Pemadatan tidak menurunkan skor. Sisa selisihnya sama dengan v4.6: definisi 2.6–2.8 dan 2.20–2.21 (batas Khusus/Umum untuk `Direct Debit/Bayar Instan`, `Pelanggan`, `Transaksi`), serta 15.7 `Yang mencakup:`. v4.7 menggantikan v4.6 di `preparation/prompts/extraction_system.md`.

## v4.7.1 — 21 Nov 2026: daftar biaya dipisah

**Masalah di v4.7:** BJB D.11 `Biaya yang dikenakan kepada Pengguna … adalah sebagai berikut: a. Biaya internet … b. Biaya transaksi … c. Biaya pulsa …` digabung sebagai daftar jenis/komponen yang informatif. Label memisahnya. Prinsip pengawas (5.1.0) juga memisahnya, karena setiap biaya adalah beban Pengguna yang berdiri sendiri.

**Perubahan:**
- 5.2.2.3: tambah baris "daftar biaya, denda, atau beban yang dikenakan kepada suatu pihak", yang bukan daftar informatif.
- Tabel 6.6: tambah satu baris **PISAH** untuk daftar tersebut.

**Panjang:** 22.876 token (+137 dari v4.7).

**Hasil:** belum diuji. **Tidak dipakai.** Keputusan 21 Nov: training v0.1.5 memakai v4.7, yang sudah diuji di 7 dokumen. Label BJB D.11 tetap dipisah, sesuai prinsip 5.1.0.

## Berikutnya (belum diterapkan)

- **Penyesuaian label** (raw, gitignored) sesuai jawaban pengawas:
  - R13: ±29 daftar sebaris yang digabung → dipisah.
  - R5: DBS 3 → digabung.
  - R1: BJB D.9 → dipisah.
  - R6: SMBC Pasal 13 → judul ke `pasal`.
  - R8: SEABANK 2.21, 2.34, 2.43, DBS 1|13, OCBC IB 34 → Definisi Umum, digabung dengan tetangganya.
  - R19: NAGARI III.4.
  - R20: SINARMAS → digabung.
  - R21: SEABANK 5.26 → digabung.
  - R11: SHOPEEPAY 8.6 → digabung.
  - Temuan uji DBS: bagian 2 → digabung (sama dengan bagian 3, R5); 10|8 dan 11|3|1 → dipisah (R2); 6|2 dan 22|3 → dipisah (R13); definisi 12–14 → digabung (R8). 12|1 tetap digabung.
- **Batas token:** `max_seq_length` dinaikkan ke 102.400 (v4.5), lalu ke 106.496 untuk v4.6 (`training/configs/pbbi-extraction.yaml`). VRAM terukur: baris 89.298 token (UOB) memakai puncak 103,2 GB dari 141 GB, dan training v0.1.4 memakai puncak 100,4 GB. Ekstrapolasinya ±109 GB untuk UOB dengan v4.7 (±98 ribu token) dan ±114 GB di batas 106.496. Sebelum training, jalankan `training/scripts/test.py --max-seq-length 106496 --steps 2` sebelum training.
- **Uji v4.5** setelah label disesuaikan: DBS, OCBC KK, SEABANK, OY, NAGARI, SINARMAS, dengan MUAMALAT sebagai kontrol.
