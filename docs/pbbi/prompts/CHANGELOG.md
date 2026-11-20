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

## Berikutnya (belum diterapkan)

- **Perbaikan 7.1.2:** kalimat induk tidak harus diakhiri `:`. Paragraf pengantar yang memuat `Berikut ini …`, `… sebagai berikut`, atau `:` di tengah kalimat, dan langsung diikuti butir bernomor, tetap klausa induk. Target: P6 DBS 8 → 0.
- **Uji v4 di dokumen sulit lain:** OCBC KK (P3, P8), SEABANK (P2, P3), dan OY sebagai kontrol daftar sebaris.
- **Review label dengan Legal:**
  - Prosedur yang dipisah (DBS 2 dan 3).
  - Daftar `melalui:` / `dapat …:` yang dipisah (DBS 34, SEABANK 10.16).
  - Konsistensi Definisi Umum/Khusus (OCBC KK, OCBC IB).
  - NAGARI III.4.
