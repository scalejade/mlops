# Histori prompt ekstraksi PBBI

Setiap file adalah **system prompt utuh**, disalin apa adanya dari versi yang dipakai atau diuji. Jangan mengedit file lama; buat file baru untuk setiap perubahan.

Prompt yang dipakai training dan aplikasi tetap `preparation/prompts/extraction_system.md`. Folder ini hanya arsip dan bahan perbandingan.

Rincian perubahan per versi, kapan dibuat, arah, dan hasilnya ada di [CHANGELOG.md](CHANGELOG.md).

## Daftar versi

| File | Tanggal | Asal | Isi perubahan | Status |
|---|---|---|---|---|
| [01-app-e028187.md](01-app-e028187.md) | 2026-10-10 | Aplikasi `sys-prompt` @ `e028187` (repo `2e7b301`) | Prompt awal | Training v0.1.1–v0.1.3 |
| [02-app-1d7ccdd.md](02-app-1d7ccdd.md) | 2026-11-18 | Aplikasi `sys-prompt` @ `1d7ccdd` (repo `2e8d74e`) | Baris tabel (8.4), catatan kaki (8.6) | Training v0.1.4; gerbang gagal (report v0.1.4 §11.4) |
| [03-draft-p1-p8.md](03-draft-p1-p8.md) | 2026-11-19 | Draf | Usulan pertama P1–P8 | Tidak diuji; diganti v1 |
| [04-v1.md](04-v1.md) | 2026-11-19 | Draf | P1–P4: urutan uji 5.1.1, definisi prosedur 5.2.2, daftar informatif 5.2.3, butir/paragraf mandiri 3.3.3–3.3.5, larangan nomor klausa independen 10.3 | Diuji dengan gpt-4.1-mini |
| [05-v2.md](05-v2.md) | 2026-11-19 | Draf | v1 + nama produk 4.3.3.4, daftar definisi berpengantar 6.5.4 | Sama dengan `extraction_system.md` di working tree (belum di-commit); tidak diuji terpisah |
| [06-v3.md](06-v3.md) | 2026-11-19 | Draf | v2 + definisi bukan daftar informatif (5.2.3.4, tabel 6.6, checklist 7) | Diuji dengan agent Claude, 18 dokumen |
| [07-v3.1.md](07-v3.1.md) | 2026-11-19 | Draf | v3 + butir sebaris `(i)`/`(a)` dalam satu paragraf tetap satu klausa (3.2.4) | Diuji ulang di OY, KALSEL, SMBC. **Kandidat v0.1.5** |
| [08-v4.md](08-v4.md) | 2026-11-20 | Draf | v3.1 + penutupan sisa P1–P4 + P5–P8, dengan P1–P4 sebagai prioritas (rincian di bawah) | Diuji di DBS MB (Sonnet): F1 97,1 |

**Uji v4, DBS MB** (Sonnet, 262 klausa label, 2026-11-20):

| Prompt | Klausa | R | P | F1 | P1 | P2 | P3 | P4 | Nomor tersalin |
|---|---|---|---|---|---|---|---|---|---|
| app `1d7ccdd` | 272 | 97,7 | 94,1 | 95,9 | 13 | 3 | 0 | 13 | 34 |
| v3 | 263 | 96,8 | 96,4 | 96,6 | 17 | 3 | 0 | 13 | 34 |
| **v4** | 263 | 97,3 | 96,9 | **97,1** | **1** | 4 | 0 | **0** | **0** |

## Skor

Semua angka adalah F1 Jaccard average (`preparation/jaccard_avg.py`).

**Model PBBI** (17 dokumen test lama):

| Prompt | v0.1.3 | v0.1.4 |
|---|---|---|
| app `e028187` | 77,0 | 78,3 |
| app `1d7ccdd` | 73,3 | 74,1 |

**gpt-4.1-mini** (18 dokumen): app `1d7ccdd` 51,7, v1 54,8.

**Agent Claude** (18 dokumen, 2.168 klausa label). BJB, BOC, OCBC IB, dan DBS MB diuji dengan Sonnet; dokumen lain dengan Haiku 5.5. Setiap prompt dijalankan di agent terpisah.

| Prompt | Recall | Presisi | F1 |
|---|---|---|---|
| app `1d7ccdd` | 92,0 | 91,3 | 91,7 |
| v3 | 95,5 | 92,8 | 94,1 |
| v3.1 (OY, KALSEL, SMBC diuji ulang; dokumen lain dari run v3) | 95,9 | 93,7 | **94,8** |

Angka agent mengukur kejelasan prompt, bukan skor adapter. Adapter harus dilatih ulang dengan prompt yang akan dirilis, karena adapter yang dilatih dengan satu teks prompt rapuh terhadap perubahan teks (report v0.1.4 §11.4).

### Pola kesalahan P1–P8

Angka di bawah adalah jumlah klausa label yang terkena tiap pola, di 17 dokumen yang sama.

| Pola | v0.1.4 + `e028187` | Agent + `1d7ccdd` | Agent + v3/v3.1 |
|---|---|---|---|
| P1 Pengantar ":" + daftar anak digabung | 308 | 99 | 33 |
| P2 Butir bernomor mandiri digabung | 178 | 70 | 24 |
| P3 Paragraf terpisah digabung | 166 | 94 | 24 |
| P4 Nomor/huruf butir tersalin | 366 | 330 | 19 |
| P5 Judul ikut masuk `clause_text` | 10 | 0 | 0 |
| P6 Awalan induk tidak diwariskan | 36 | 23 | 25 |
| P7 Klausa label dipecah berlebihan | 62 | 46 | 44 |
| P8 Daftar definisi | 6 | 23 | 20 |
| **Total bermasalah** | **1.225** | **792** | **323** |

## v4: perubahan dari v3.1

Setiap aturan baru dicek dulu terhadap mayoritas label di 85 dokumen train, eval, dan test.

### Menutup sisa P1–P4 dari v3/v3.1

Sisa kesalahan v3/v3.1 adalah P1 33, P2 24, P3 24, P4 19. Sebabnya dibedah per kasus:

| Pola | Sebab sisa (dokumen) | Aturan v4 | Dasar dari label |
|---|---|---|---|
| P4 (semua 19) | Nomor milik induk teratas ikut ditulis saat diwariskan: `5. Dalam hal …, maka:\n1. …`, `1. Hak Pemegang Kartu :\na. …` (DBS, SMBC) | **7.4.3** penanda induk tingkat teratas tidak ditulis; penanda tingkat bawah tetap ditulis | Induk tanpa nomor 3.060 klausa, dengan nomor 7 |
| P1 | Daftar bertingkat: tingkat atas dipisah, tingkat terdalam digabung (DBS 37.10 `a.`–`j.`, BJB J) | **5.1.6** uji gabung/pisah diulang di setiap tingkat; butir terdalam mewarisi seluruh induk | Contoh label DBS dan BJB |
| P1 | Daftar penyebab atau ruang lingkup dianggap satu kesatuan (SHOPEEPAY 17, MANDIRI D.9, DBS 37.10) | **5.2.2.3** + tabel 6.6: `yang timbul dari:`, `akibat:`, `termasuk namun tidak terbatas pada:` → PISAH | 93% dan 77% dipisah |
| P1 | Pernyataan status produk/dana digabung (SINARMAS `Saldo …: a. Bukan merupakan simpanan …`) | **5.2.2.3** + tabel 6.6: pernyataan status/sifat hukum → PISAH | Contoh label SINARMAS, 2/2 di train |
| P1/P2 | Ketentuan bersebelahan digabung (SEABANK 5.26 `b-c`) | Tabel 6.6: `… dengan ketentuan sebagai berikut:` → uji per butir | 65% dipisah |
| P2/P3 | Butir setingkat ditempel ke daftar sebelumnya (SHOPEEPAY `15.2` + `15.3`) | **3.3.7** butir setingkat selalu klausa baru | — |
| P3 | Paragraf ketentuan baru setelah butir mandiri digabung ke butir itu (OCBC KK `12)` + `Tanpa mengesampingkan …`) | **3.3.8** paragraf tersebut menjadi klausa independen | Contoh label OCBC KK |
| P2 | Definisi badan usaha digabung ke Definisi Umum (SEABANK `AirPay adalah PT …`) | **4.3.2.3** badan usaha bernama = Definisi Khusus para pihak | 37 berdiri sendiri vs 2 digabung |

Aturan 6.7 (prioritas) ditambah 7.4.3, 5.1.6, dan 3.3.7. Aturan 5.2.4.2 dibatasi agar tidak berlaku pada `…, maka:` yang butirnya adalah akibat, karena itu tetap PISAH.

**Sisa yang sengaja tidak ditangani dengan aturan.** Kasus-kasus ini bertentangan dengan mayoritas label atau dengan aturan label yang sudah disetujui:

- DBS 34 `Bank dapat menyampaikan pemberitahuan … melalui:` dipisah oleh label. Padahal 85% daftar `melalui:` digabung, jadi aturan informatif tetap dipakai.
- SEABANK 10.16 `Anda dapat langsung: a. mengakses …` dipisah oleh label. Padahal 82% daftar `dapat mengakses:` digabung.
- DBS 2 `Berikut ini adalah proses Pembukaan Rekening …` dipisah oleh label, padahal aturan label menyatakan prosedur selalu digabung. Perlu review label.

### P5–P8

| Pola | Aturan | Dasar dari label |
|---|---|---|
| P1–P4 | **6.7** urutan prioritas. Aturan 3.3.3–3.3.5, 3.3.7, 5.1.6, 5.2.2.3/6.6, 7.4.3, dan 10.3 tidak pernah dikalahkan; aturan P5–P8 hanya berlaku bila syaratnya jelas | Permintaan: P1–P4 prioritas |
| P5 | Contoh benar/salah di 10.3, checklist 14 | Sudah 0; hanya dikunci |
| P6 | **7.1.2** kalimat induk `…:` tetap diwariskan walaupun butirnya kalimat lengkap. **7.1.3** judul butir di antara kalimat induk dan isinya ikut diwariskan, dan tiap judul adalah sub-bagian sendiri | 196 klausa label memakai pola induk + judul butir + isi, 3 tidak. Judul butir dipisah per judul di 41 struktur, digabung di 17 |
| P7 | **3.3.6** satu paragraf tidak dipecah di batas kalimat. **5.2.4** struktur bertujuan tunggal: induk `… yang:` (ciri satu objek), dan kondisi yang akibatnya baru dinyatakan setelah butir terakhir → gabung | Kondisi + akibat di akhir: 2/2 digabung. Induk `yang:`: 1/1 |
| P7 (tidak diubah) | Daftar pilihan dengan `atau` | Label 46% gabung / 54% pisah, jadi tidak dibuat aturan |
| P8 | **4.3.4** Definisi Khusus produk hanya kategori produk, nama produk bermerek, Layanan Transfer Dana, dan Layanan Pembayaran. Komponen produk (rekening, PIN, password, token, QRIS, limit, saldo, biaya, …) adalah Definisi Umum | Istilah para pihak 75–86% berdiri sendiri; istilah komponen 15–44% |

Perbaikan yang terbawa dari v3.1:

- Contoh kosong `(, )` di 5.2.3.4 sudah diisi.
- Urutan checklist 9/10 sudah dibetulkan.

**Belum diputuskan:**

- 7.1.3.2 menyatakan judul butir beserta isinya adalah sub-bagian, bukan butir daftar informatif. Aturan ini memisah struktur seperti `… pilihan pembayaran sebagai berikut:` yang tiap butirnya berjudul dan punya isi sendiri. Perlu konfirmasi bahwa ini tidak bertentangan dengan aturan label "daftar informatif selalu digabung".
- Label definisi tidak konsisten antardokumen (mis. OCBC KK memisah `Pembayaran Minimum` tetapi menggabung `Kartu Utama`). Perlu konfirmasi Legal.

## Sumber

- Hasil agent: scratchpad sesi 2026-11-19 (`agent-bjb/out/`), dihitung dengan `preparation/jaccard_avg.py`.
- Klasifikasi pola P1–P8: pengklasifikasi otomatis yang sama untuk semua kolom. Setiap klausa label dihitung di satu pola utama.
