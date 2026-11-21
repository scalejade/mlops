# Penyesuaian label untuk v0.1.5

Label disesuaikan dengan jawaban pengawas R1–R21 ([prompts/jawaban-pengawas-v4.5.md](prompts/jawaban-pengawas-v4.5.md)) dan dengan keputusan tim tanggal 21 November 2026: daftar saluran untuk melaksanakan hak atau kewajiban dipisah. Prompt yang dipakai untuk training adalah v4.8.1 ([prompts/14-v4.8.1.md](prompts/14-v4.8.1.md)).

## Cara penerapan

- **xlsx dari Legal tidak diubah.** Setiap dokumen yang labelnya berubah mendapat file `raw/<dokumen>/<nama xlsx>.gold.json`. `build.py` memakai file gold ini menggantikan xlsx (lihat `preparation/README.md`).
- Daftar operasi per dokumen (pisah, gabung, judul ke `pasal`, beserta dasar R#), mesin penerapan, dan topik baru disimpan di `preparation/data/relabel-v0.1.5/`. Folder ini tidak masuk git karena memuat teks kontrak.
- Topik untuk 177 klausa hasil pemisahan atau penggabungan ditulis ulang mengikuti aturan 10.2 prompt (maksimal 100 karakter). Satu topik asli Legal melebihi 100 karakter (HONEST 6.1, 110 karakter) dan dibiarkan.
- Build lama disimpan di `preparation/data/build-v0.1.4/`.

## Hasil

| | Sebelum | Sesudah |
|---|---|---|
| Dokumen dengan file gold | 0 | 25 (13 train, 2 validation, 10 test) |
| Operasi | — | 62 (55 dari jawaban pengawas, 7 dari keputusan tim K1–K8) |
| Klausa di 25 dokumen tersebut | 4.553 | 4.619 |
| Baris terpanjang (UOB MB, tokenizer `qwen-sea-lion-v4.5-27b-pbbi`) | 89.619 (prompt `1d7ccdd`) | 98.076 (prompt v4.7) |
| Klausa terbuang saat build | 0 | 0 |

Operasi per dasar:

| Dasar | Arah | Jumlah |
|---|---|---|
| R13 daftar sebaris (sering bersama R2 atau R14) | pisah | 15 |
| Saluran (keputusan 21 Nov) | pisah | 7 |
| R1 pilihan, R2 `dan/atau`, kondisi alternatif | pisah | 13 |
| R3 skenario | pisah | 5 |
| R14 penyebab | pisah | 1 |
| R6 judul butir ke `pasal` | pindah | 5 |
| R8 Definisi Umum (`Pembayaran Tagihan`, `QRIS`, `QR Code`, `Pembayaran`) | gabung | 5 |
| R5 prosedur (DBS bagian 2 dan 3) | gabung | 2 |
| R16, R20, R21 | gabung | 3 |
| R19 batas sub-daftar (NAGARI III.4) | susun ulang | 1 |

## Keputusan per kasus

- Kandidat dicari otomatis di 85 dokumen; 91 kandidat ditemukan. Setiap kandidat diperiksa satu per satu. Sekitar 40 ditolak, karena:
  - sudah dipisah di tingkat terdalam;
  - daftar informatif atau satu kesatuan (komponen hak cipta, urutan pelunasan, daftar layanan, saran);
  - syarat kumulatif;
  - isi definisi.
- BANTEN 4: hanya butir a–b (sarana yang wajib dipakai) yang digabung (R16). Butir c–h adalah ketentuan sendiri dan tetap dipisah (aturan campuran 6.3).
- NAGARI III.2: butir 1–2 (saluran) dipisah. Butir 3 adalah ketentuan sendiri, bukan saluran, jadi menjadi klausa sendiri (3.2.3.6).
- NAGARI III.4: butir 3 dan 4 sub-daftar tidak ada di label lama; keduanya diambil dari teks dokumen.
- OY 9: kalimat `Kami berhak untuk menyelidiki …` diwariskan ke setiap butir sebagai teks penutup (C). Pengawas tidak menjawab kasus ini.

## Keputusan tim untuk kasus yang belum jelas (21 Nov, K1–K8)

Delapan kasus yang tidak dijawab langsung oleh pengawas diputuskan oleh tim lewat workbook `preparation/data/kasus-belum-jelas-relabel-v0.1.5-jawaban.xlsx` (tidak masuk git).

| No | Dokumen | Keputusan | Alasan tim | Perubahan label |
|---|---|---|---|---|
| K1 | BSI MB D.1 (train) | Daftar tujuan pemrosesan data pribadi **dipisah** per tujuan; sub-butir b 1)–3) ikut dipisah | Ada hak Bank memproses data pribadi | 1 → 12 klausa |
| K2 | DANA UE, Verifikasi Wajah (train) | Tujuan a)–c) **dipisah** | Setiap butir memuat beban hukum sendiri (hak memproses data) | 1 → 3 |
| K3 | UOB KK 2.3.4 (validation) | Hak (i), (ii), (iii) masing-masing klausa sendiri; kondisi (a)–(e) **hanya milik hak (iv)**, jadi (iv) dipecah per kondisi | — | 5 → 8 |
| K4 | WISE 12.3 (train) | **Tetap dipisah** (a)–(f); berbeda dari R21 | Setiap butir memuat hak WISE | tidak berubah |
| K5 | OY 9 (test) | (i)–(vi) dipisah; (vii) dipecah menjadi (vii)(a) dan (vii)(b); kalimat `Kami berhak untuk menyelidiki …` **diwariskan ke kedelapan klausa** | — | 1 → 8 |
| K6 | SEABANK 15.7 (test) | `Yang mencakup: a. … b. …` **dipisah** | Setiap butir adalah kewajiban sendiri | 1 → 2 |
| K7 | SEABANK 2.39, DBS 1\|24 (test) | SEABANK `Transaksi` tetap **Definisi Khusus**, karena menyebut produk berkategori Khusus. DBS `Transaksi` dipecah: (i) finansial Khusus, (ii)–(iii) non-finansial/lainnya Umum | — | DBS 1 → 3 |
| K8 | SEABANK 2.8, 2.20 (test) | `Direct Debit/Bayar Instan` (fitur, bukan produk) dan `Pelanggan` (pelanggan merchant) **Definisi Umum**, digabung dengan definisi umum di sebelahnya | — | 2.6–2.16 dan 2.18–2.21 digabung |

| K9 | OY 10 Ganti Rugi, OY 16.1 (test) | Daftar sebaris `yang timbul dari (i) …` / `akibat dari (i) …` **dipisah** walaupun tanpa titik dua. OY 10: kalimat `Kami berhak … pembelaan …` menjadi klausa sendiri. OY 16: anak kalimat `baik berbasis garansi …` diwariskan ke setiap butir | — | OY 10: 1 → 5; OY 16.1: 1 → 3 |
| — | DBS 23 Pusat Pelayanan (test) | Saluran untuk mencari informasi = **informasi umum, digabung** | — | tidak berubah |

**Dampak ke prompt:** K7 dan K8 mempersempit Definisi Khusus. Fitur pembayaran bermerek seperti `Bayar Instan` sekarang Umum, padahal aturan 4.3.3.4 di v4.7 menyebut "fitur layanan bermerek" sebagai Khusus. K1, K2, K3, K5, dan K6 belum punya contoh di v4.7. Prompt diselaraskan di v4.8 (K1–K8) dan v4.8.1 (K9, DBS 23); lihat `prompts/CHANGELOG.md`.

## Tahap 2 — penyesuaian ke prompt v4.8.1 (21 Nov)

Setelah prompt dibekukan di v4.8.1, label di semua dokumen dicek ulang terhadap seluruh aturan prompt itu, tanpa agent. Kandidat dicari dengan pola yang mencakup K1–K9, lalu diperiksa satu per satu: 169 kandidat setelah klausa yang sudah dipisah di tingkat terdalam disaring.

| Hasil | Jumlah | Contoh |
|---|---|---|
| Dipisah | 26 struktur | `Nasabah wajib: a. … b. …`; `PIN … akan diblokir jika:`; `menyatakan dan menjamin bahwa:`; `Kami berhak membebankan … biaya layanan, yaitu:`; Force Majeure `termasuk tetapi tidak terbatas pada:` (R14); Ganti Rugi SeaBank dan YUKK 10.10 (K9); saluran pengaduan, registrasi, dan pembayaran; skenario per jenis akun atau kewarganegaraan |
| Digabung | 1 | BALI KD `… dengan syarat-syarat berikut:` (syarat kumulatif) |
| Penanda dihapus dari awal klausa independen (aturan 10.3) | 11 | LinkAja, ShopeePay 2.2.7, BSI F.1, StanChart IB, NOBU MB |
| Tetap (salah tangkap atau sudah sesuai) | ±130 | Daftar fitur/layanan, prosedur, syarat kumulatif (`hanya jika … dan …`, `harus: …`), data sasaran satu kewajiban, saluran untuk informasi, urutan alokasi pembayaran |

**Hasil:**
- File gold sekarang ada di 36 dokumen (22 train, 3 validation, 11 test).
- Total +50 klausa dibanding akhir tahap 1.
- Data: train 6.991 klausa, eval 854, test 2.209.
- Baris terpanjang 99.737 token; 0 klausa terbuang.
- Topik untuk 82 klausa baru ditulis manual.

**Dikoreksi saat penulisan topik:** WISE 20.1 (`dapat menautkan … dengan ketentuan: (a) … dan (d) …`) tetap satu klausa. Butirnya syarat kumulatif, sesuai topik Legal.

**Ragu, tidak diubah:**
- DANAMON KD G.4.a: daftar risiko bertingkat.
- OCBC KD Contactless: informasi fitur bercampur hak dan kewajiban; label tetap dipisah.
- SULSELBAR KD: cara edukasi.
- MANDIRI UE 11: jenis gangguan teknis/nonteknis.

Rencana tahap 2 ada di `preparation/data/relabel-v0.1.5/pass2/` (tidak masuk git).

## Batasan

Kandidat dicari dengan pola teks, jadi mungkin masih ada kasus yang terlewat, terutama di dokumen train. Cara yang lebih lengkap: jalankan ekstraksi dengan prompt v4.7 di dokumen train, lalu bandingkan hasilnya dengan label. Setiap perbedaan adalah kandidat konflik.
