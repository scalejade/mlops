# Jawaban pengawas untuk prompt v4.5

Dokumen ini mencatat jawaban pengawas atas 21 pertanyaan aturan system prompt ekstraksi (R1–R21), yang diterima pada 20 November 2026. File jawaban aslinya (`ans.xlsx`) akan dihapus. Salinannya disimpan di `preparation/data/jawaban-pengawas-sysprompt-v4.5.xlsx` (tidak masuk git). Pertanyaannya ada di `preparation/data/pertanyaan-pengawas-sysprompt-v4.5.xlsx`.

Kesempatan bertanya ke pengawas hanya sekali. Karena itu, jawaban yang ambigu ditafsirkan oleh tim, dan setiap tafsiran dicatat di bawah. Semua keputusan mengikuti pengawas. Perubahan prompt ada di [09-v4.5.md](09-v4.5.md), dan rinciannya di [CHANGELOG.md](CHANGELOG.md).

## Prinsip pengawas

Catatan-catatan pengawas memakai satu prinsip, yang dipasang sebagai aturan 5.1.0:

- **PISAH** apabila kalimat induk memuat hak atau kewajiban, **dan** setiap butir adalah opsi yang dapat berdiri sendiri.
- **GABUNG** apabila butir-butirnya merupakan satu kesatuan (syarat yang dipenuhi bersama, ciri satu objek, atau prosedur), **atau** hanya berisi informasi.

## Ringkasan

| No | Prioritas | Topik | Keputusan | Aturan v4.5 | Label yang berubah |
|---|---|---|---|---|---|
| R5 | 1 | 7.1.2 Kalimat induk | Pengantar bertitik tetap kalimat induk; BCA dan DBS 3 digabung (kesatuan syarat / prosedur) | 7.1.2.1, 5.2.4.4, 3.2.3.6 (batas) | DBS MB bagian 3 → 1 klausa; DBS MB bagian 2 ikut digabung (bentuk sama) |
| R8 | 1 | 4.3.2 / 4.3.4 Definisi Khusus vs Umum | Khusus: Transaksi QRIS, Transaksi Finansial. Umum: QRIS, Transfer Terjadwal, Transaksi Berkala, Pembayaran Tagihan, PIN, OTP, Token, Rekening Deposit, Kartu Utama, Kartu Tambahan, Penerbit | 4.3.2.3, 4.3.3.3, 4.3.3.4, 4.3.4, #13 | SEABANK MB 2.21, 2.34, 2.43; DBS MB 1\|13 (digabung 12–14); OCBC IB 34 |
| R1 | 2 | (belum ada) | Daftar pilihan → PISAH | 5.2.2.3, 6.6 | BJB MB D.9 → 2 klausa |
| R2 | 2 | 6.6 Kumulatif vs alternatif | `dan/atau` = alternatif → PISAH | 5.2.1.2, 6.6 | DBS MB 10\|8, 11\|3\|1, 12\|1 (ditemukan saat uji DBS) |
| R6 | 2 | 10.3 / 7.1.3 Judul butir | Judul butir tanpa kalimat induk menjadi segmen `pasal`; `clause_text` tanpa judul dan tanpa penanda | 10.1, #14 | SMBC KK Pasal 13 |
| R16 | 2 | 5.2.1 Syarat kumulatif | GABUNG | 5.2.4.3, 6.6 | — (label sudah digabung) |
| R17 | 2 | 5.2.2.3 / 5.2.3 Tips vs kewajiban | GABUNG | 5.2.3.5.1, 6.6 | — (label sudah digabung) |
| R18 | 2 | 3.5 / 7.6 Paragraf setelah butir | Ikuti aturan 3.5. DBS 21 = teks penutup (C) diwariskan ke setiap butir; OCBC KK 12 = klausa sendiri (D) | 3.5.9 (contoh baru) | — (label DBS 21 sudah mewariskan ke kedua butir) |
| R3 | 3 | 5.2.4.2 Induk "maka:" | PISAH (dikonfirmasi) | 6.6 (contoh BRIZZI ditambahkan) | — |
| R4 | 3 | 5.2.4.2 Akibat di akhir | GABUNG (dikonfirmasi) | — | — |
| R7 | 3 | 7.1.3.2 Sub-bagian berjudul | PISAH per judul (dikonfirmasi) | — | — |
| R9 | 3 | 3.3.4 / 1.3 Pembuka & penutup | PISAH per paragraf (dikonfirmasi) | — | — |
| R10 | 3 | 3.3.6 Satu paragraf | Tidak dipecah per kalimat (dikonfirmasi) | — | — |
| R11 | 3 | 5.2.2 Prosedur | GABUNG, prosedur (dikonfirmasi) | — | SHOPEEPAY UE 8.6 → 1 klausa |
| R12 | 3 | 9.1–9.5 Bahasa Inggris | Istilah Inggris di dokumen berbahasa Indonesia dibiarkan apa adanya | 9.6 (baru), 9.2, #15 | — |
| R13 | 3 | 3.2.4 Daftar sebaris | **Dibalik dari v3.1:** daftar sebaris yang diantar kalimat induk berisi hak/kewajiban dan butirnya opsi → PISAH | 3.2.4, 3.3.6, 6.6, #7, #10 | ±29 daftar sebaris di seluruh data, termasuk OY PG; DBS MB 6\|2, 22\|3 |
| R14 | 3 | 5.2.2.3 Ruang lingkup / penyebab | PISAH (dikonfirmasi) | — | — |
| R15 | 3 | 5.2.4.1 Ciri satu objek | GABUNG (dikonfirmasi) | — | — |
| R19 | 3 | 3.2.3 Batas sub-daftar | Sub-daftar berhenti di butir 5; butir 6–9 klausa sendiri | 3.2.3.6 (baru; dipersempit setelah uji DBS) | NAGARI MB III.4 |
| R20 | 3 | 5.2.2.3 Pernyataan status produk | **Dibalik dari v4:** GABUNG (informasi) | 5.2.3.5.2, 5.2.2.3, 6.6 | SINARMAS UE Saldo 1 → 1 klausa |
| R21 | 3 | 6.6 Ketentuan berikut | **Dibalik dari v4:** GABUNG bila butirnya menjelaskan satu fitur | 5.2.3.5.3, 6.6 | SEABANK MB 5.26 a–g → 1 klausa |

## Rincian per pertanyaan

### R5 — 7.1.2 Kalimat induk

**Pertanyaan:** Paragraf yang diakhiri TITIK tetapi mengantar daftar butir — apakah tetap kalimat induk dan diwariskan ke setiap butir?

- **Contoh:** PT Bank Central Asia Tbk (BCA) / PT Bank DBS Indonesia · Kartu Debit (Kartu PASPOR Xpresi) / Mobile Banking (digibank) · BCA: B. Syarat-Syarat Umum 4 / DBS: 3. Pendaftaran Aplikasi
- **Isi v4:** Kalimat induk harus diakhiri ":" (cacat: pengantar berakhiran titik tidak diwariskan)
- **Usulan tim:** Ya

**Jawaban pengawas** (apa adanya):

> BCA: "Gambar pada Kartu PASPOR Xpresi … berlaku ketentuan berikut ini." → a) Tidak boleh mengandung unsur pornografi. b) Tidak melanggar tata susila … c) … BCA berhak meminta penggantian gambar …" -> digabung karena children bukan opsi yang dapat dipisah satu dengan lainnya,melainkan satu kesatuan syarat yang dipenuhi
> DBS: "Berikut ini adalah proses pendaftaran … : Untuk dapat melakukan pendaftaran … Bank." -> tetap parent-child, namun digabung karena merupakan prosedur pendaftaran aplikasi

**Keputusan:** Pengantar bertitik tetap kalimat induk; BCA dan DBS 3 digabung (kesatuan syarat / prosedur). **Aturan v4.5:** 7.1.2.1, 5.2.4.4, 3.2.3.6 (batas). **Label:** DBS MB bagian 3 → 1 klausa; DBS MB bagian 2 ikut digabung (bentuk sama).

**Tafsiran tim:** Bagian 2 DBS tidak ditanyakan; diperlakukan sama dengan bagian 3 karena pengantarnya identik (`Berikut ini adalah proses …`).

### R8 — 4.3.2 / 4.3.4 Definisi Khusus vs Umum

**Pertanyaan:** (a) Jenis layanan/transaksi pembayaran = Definisi Khusus? (b) Komponen/instrumen produk = Definisi Umum? (c) Penerbit/badan usaha = Definisi Khusus para pihak?

- **Contoh:** PT Bank Seabank Indonesia / PT Bank OCBC NISP Tbk / PT Bank DBS Indonesia / PT Bank SMBC Indonesia Tbk · Mobile Banking (SeaBank) / Internet Banking & Kartu Kredit (OCBC) / Mobile Banking (digibank) / Kartu Kredit (Kartu Kredit Jenius) · SeaBank: 2. Definisi / OCBC IB: 1. Umum, A. Definisi / OCBC KK: A. Definisi / DBS: 1. Definisi 13 / SMBC: Pasal 1 Definisi 36
- **Isi v4:** (a) Umum (cacat)  (b) Umum  (c) Khusus
- **Usulan tim:** Ya / ya / ya

**Jawaban pengawas** (apa adanya):

> (a) SEABANK: 'QRIS' -> bukan, 'Transaksi QRIS' -> Iya; 'Transaksi Terjadwal' -> bukan; OCBC IB:  Transaksi Berkala -> bukan, Transaksi Finansial -> iya; DBS MB: 'Pembayaran Tagihan' -> bukan
> (b) SEABANK: PIN, OTP, Token, Rekening Deposit -> bukan; OCBC KK:  Kartu Utama, Kartu Tambahan -> bukan
> (c) SMBC KK: 'Penerbit' -> bukan

**Catatan pengawas:**

> (c) karena tidak spesifik merujuk ke penerbit SMBC (bisa merujuk pihak lain)

**Keputusan:** Khusus: Transaksi QRIS, Transaksi Finansial. Umum: QRIS, Transfer Terjadwal, Transaksi Berkala, Pembayaran Tagihan, PIN, OTP, Token, Rekening Deposit, Kartu Utama, Kartu Tambahan, Penerbit. **Aturan v4.5:** 4.3.2.3, 4.3.3.3, 4.3.3.4, 4.3.4, #13. **Label:** SEABANK MB 2.21, 2.34, 2.43; DBS MB 1\|13 (digabung 12–14); OCBC IB 34.

**Tafsiran tim:** Untuk (b) dan (c), "bukan" dibaca "bukan Definisi Khusus" (= Umum), sesuai label SEABANK dan OCBC KK yang sudah menggabungkan istilah tersebut.

### R1 — (belum ada)

**Pertanyaan:** Daftar PILIHAN yang dihubungkan "atau" (pilihan cara, waktu, pihak — bukan kondisi): digabung atau dipisah?

- **Contoh:** Bank BJB / PT Bank DBS Indonesia · Mobile Banking (DIGI bank bjb, jenis bjb DigiCash) / Mobile Banking (digibank — bagian Kartu Debit) · BJB: D. Ketentuan bjb DigiCash 9 / DBS: 11.7 Pemblokiran dan Pengakhiran Kartu Debit
- **Isi v4:** Tidak diatur (label di seluruh data 46% gabung / 54% pisah)
- **Usulan tim:** Gabung

**Jawaban pengawas** (apa adanya):

> - BJB: "Penggantian PIN … dapat dilakukan atas: a. Inisiatif Pengguna … setiap saat; atau b. Perintah … otomatis … setiap 1 (satu) tahun sekali." -> dipisah
> - DBS: "Pengguna dapat mengakhiri Kartu Debit dengan cara: 1. pemblokiran permanen … 2. pemberitahuan tertulis …" -> digabung

**Catatan pengawas:**

> - BJB dipisah karena children ada unsur hak per pihak (dari pihak konsumen (a) dan pihak penyelenggara (b))
> - DBS dipisah karena children merepresentasikan opsi kemungkinan pengakhiran kartu.

**Keputusan:** Daftar pilihan → PISAH. **Aturan v4.5:** 5.2.2.3, 6.6. **Label:** BJB MB D.9 → 2 klausa.

**Tafsiran tim:** Untuk DBS, kolom jawaban berbunyi "digabung" tetapi catatan berbunyi "dipisah karena children merepresentasikan opsi". Diikuti catatannya (PISAH), sesuai prinsip pengawas dan label DBS yang sudah dipisah.

### R2 — 6.6 Kumulatif vs alternatif

**Pertanyaan:** "dan/atau" dianggap alternatif (dipisah) atau kumulatif (digabung)?

- **Contoh:** Bank BJB · Mobile Banking (DIGI bank bjb, jenis bjb DigiCash) · M.2.b SLA Klaim Transaksi
- **Isi v4:** Hanya mengenal "dan" (kumulatif) dan "atau" (alternatif)
- **Usulan tim:** Alternatif

**Jawaban pengawas** (apa adanya):

> "Bank dapat memperpanjang jangka waktu paling lama 10 (sepuluh) Hari Kerja apabila terdapat kondisi: 1) … memerlukan penelitian khusus …; dan/atau 2) … di luar kendali Bank." -> dipisah

**Catatan pengawas:**

> Dipisah karena  dalam konteks 'dan/atau' yang diprioritaskan adalah 'atau'

**Keputusan:** `dan/atau` = alternatif → PISAH. **Aturan v4.5:** 5.2.1.2, 6.6. **Label:** DBS MB 10\|8, 11\|3\|1, 12\|1 (ditemukan saat uji DBS).

### R6 — 10.3 / 7.1.3 Judul butir

**Pertanyaan:** Judul butir bernomor yang langsung diikuti sub-butir: DITULIS di setiap sub-butir (tanpa nomor) atau TIDAK?

- **Contoh:** PT Bank SMBC Indonesia Tbk / PT Bank OCBC NISP Tbk · Kartu Kredit (Kartu Kredit Jenius) / Kartu Kredit · SMBC: Pasal 13 Hak dan Kewajiban Bank, 1 / OCBC KK: D. Lain-Lain, 5. Fitur Reward Kartu Kredit
- **Isi v4:** Tidak diatur (dua label bertentangan)
- **Usulan tim:** —

**Jawaban pengawas** (apa adanya):

> - SMBC (judul DITULIS): "Penggunaan Informasi." ⏎ "a. Bank berhak untuk meminta, memverifikasi …" -> No.Pasal: 'Pasal 13 Hak dan Kewajiban Bank|1. Penggunaan Informasi.|a', Bunyi Klausa ditulis apa adanya, tanpa disertai nomor 'a.'.
> - OCBC KK (judul TIDAK ditulis): "5. Fitur Reward Kartu Kredit" → "a. Bank berhak untuk menolak penukaran point reward …" -> No.Pasal dipecah menjadi dua, yaitu 'D. Lain-Lain|D. Lain-Lain|a' dan 'D. Lain-Lain|D. Lain-Lain|b',  Bunyi Klausa masing-masing ditulis apa adanya, tanpa disertai nomor 'a.' dan 'b.'.

**Keputusan:** Judul butir tanpa kalimat induk menjadi segmen `pasal`; `clause_text` tanpa judul dan tanpa penanda. **Aturan v4.5:** 10.1, #14. **Label:** SMBC KK Pasal 13.

**Tafsiran tim:** `pasal` OCBC KK yang ditulis `D. Lain-Lain|D. Lain-Lain|a` dianggap salah ketik untuk `D. Lain-Lain|5. Fitur Reward Kartu Kredit|a` (sama dengan label sekarang).

### R16 — 5.2.1 Syarat kumulatif

**Pertanyaan:** Daftar BENDA / PERANGKAT / DATA yang wajib dipakai atau didaftarkan (bukan tindakan): digabung sebagai syarat kumulatif, atau dipisah per butir?

- **Contoh:** PT Bank Mandiri (Persero) Tbk · Mobile Banking (Livin') · A. Persyaratan dan Tata Cara Penggunaan Aplikasi Livin', 2
- **Isi v4:** Tidak tegas: induk memuat "wajib" → cenderung dipisah (model memisah)
- **Usulan tim:** Gabung (sesuai label)

**Jawaban pengawas** (apa adanya):

> Dalam penggunaan aplikasi Livin', Anda wajib menggunakan atau mendaftarkan: a. Smartphone sesuai dengan Operating System (OS) dan spesifikasi minimum … b. Nomor ponsel Indonesia … c. Alamat email aktif … — label: DIGABUNG -> tetap digabung

**Catatan pengawas:**

> karena secara kesatuan parent clause dan children clauses adalah prosedur

**Keputusan:** GABUNG. **Aturan v4.5:** 5.2.4.3, 6.6. **Label:** — (label sudah digabung).

### R17 — 5.2.2.3 / 5.2.3 Tips vs kewajiban

**Pertanyaan:** "Tata cara pengamanan …:" TANPA kata "wajib", berisi butir "Tidak memberitahukan …", "Tidak mencatatkan …": tips/informatif (digabung) atau kewajiban/larangan (dipisah)?

- **Contoh:** Bank Kalsel · Kartu Debit & layanan e-channel (Bank Kalsel Online, SMS Banking, Internet Banking) · E. Syarat dan Ketentuan Layanan, 5.b
- **Isi v4:** Tidak tegas (kata "cara" bukan penentu, 5.2.2.4) → model memisah
- **Usulan tim:** Gabung jika induk tanpa "wajib"

**Jawaban pengawas** (apa adanya):

> - "Tata cara pengamanan User ID, Password Login dan PIN Transaksi: 1) Tidak memberitahukan … kepada orang lain. 2) Tidak mencatatkan … pada kertas … 3) Berhati-hati … 4) Sering mengganti …" — label: DIGABUNG. -> tetap digabung

**Catatan pengawas:**

> Tidak ada unsur hak/kewajiban sama sekali baik di parent maupun children clause

**Keputusan:** GABUNG. **Aturan v4.5:** 5.2.3.5.1, 6.6. **Label:** — (label sudah digabung).

### R18 — 3.5 / 7.6 Paragraf setelah butir

**Pertanyaan:** Paragraf TANPA nomor yang muncul setelah butir: (a) lanjutan butir tepat di atasnya, (b) penutup yang diwariskan ke SEMUA butir, atau (c) klausa sendiri?

- **Contoh:** PT Bank DBS Indonesia / PT Bank OCBC NISP Tbk · Mobile Banking (digibank) / Kartu Kredit · DBS: 21. Berakhirnya Aplikasi digibank / OCBC KK: B. Ketentuan Umum, 8. Pembayaran Tagihan 12
- **Isi v4:** 3.5 (uji penutup/kelengkapan/normatif) + 3.3.8 (ketentuan baru → klausa sendiri)
- **Usulan tim:** Klausa sendiri jika menetapkan ketentuan baru

**Jawaban pengawas** (apa adanya):

> - OCBC KK (label: klausa sendiri 12|1): "12) Apabila Pemegang Kartu dinyatakan pailit … ⏎ Tanpa mengesampingkan hak-hak Bank … jika Pemegang Kartu tidak dapat membayar …" -> klausa sendiri
> - DBS (label: menempel ke butir 1 saja): "… dapat diakhiri apabila: 1. Pengguna meng-uninstall Aplikasi … ⏎ Sehubungan dengan berakhirnya atau diakhirinya Aplikasi … Pengguna setuju untuk membebaskan Bank dari segala tuntutan …" 2. Bank menghentikan … -> kalimat setelah poin no.2 'Sehubungan dengan berakhirnya atau diakhirinya Aplikasi digibank Mobile Banking tersebut, Pengguna setuju untuk
> membebaskan Bank dari segala tuntutan maupun kerugian yang mungkin timbul akibat pengakhiran Aplikasi digibank Mobile Banking.' diwariskan ke setiap anak

**Catatan pengawas:**

> sudah ada aturannya: merujuk ke aturan `3.5. Klausa Ambigu Tanpa Penomoran di Dalam Struktur Induk-Anak` system prompt. Ada 4 opsi kapan suatu klausa ambigu diperlakukan

**Keputusan:** Ikuti aturan 3.5. DBS 21 = teks penutup (C) diwariskan ke setiap butir; OCBC KK 12 = klausa sendiri (D). **Aturan v4.5:** 3.5.9 (contoh baru). **Label:** — (label DBS 21 sudah mewariskan ke kedua butir).

### R3 — 5.2.4.2 Induk "maka:"

**Pertanyaan:** Induk diakhiri "maka:" dan butirnya adalah AKIBAT untuk keadaan berbeda: dipisah per butir?

- **Contoh:** Bank BRI · Uang Elektronik Chip (BRIZZI) · Masa Berlaku 4
- **Isi v4:** Pisah
- **Usulan tim:** Setuju (pisah)

**Jawaban pengawas** (apa adanya):

> "Jika ada BRIZZI yang sudah lebih dari 10 tahun tidak dilakukan isi ulang namun masih terdapat sisa nominal saldo maka: 1. Jika nominal saldo tersisa di kartu … 2. Jika nominal saldo tersisa pada nominal saldo tertunda …" -> dipisah per butir

**Catatan pengawas:**

> dipisah karena ada dua skenario berbeda yang dapat terjadi sehingga sama saja seperti penggunaan tanda hubung 'atau'

**Keputusan:** PISAH (dikonfirmasi). **Aturan v4.5:** 6.6 (contoh BRIZZI ditambahkan). **Label:** —.

### R4 — 5.2.4.2 Akibat di akhir

**Pertanyaan:** Daftar kondisi yang akibatnya baru muncul SETELAH daftar: satu klausa?

- **Contoh:** PT Bank Seabank Indonesia · Mobile Banking (SeaBank) · 4. Ketentuan Penggunaan 4.12
- **Isi v4:** Gabung
- **Usulan tim:** Setuju (gabung)

**Jawaban pengawas** (apa adanya):

> "Dalam hal Nasabah: 1. Meninggal dunia; 2. Pailit; 3. … 4. … 5. … maka Akun akan ditutup, dan sisa saldo Rekening Deposit akan dibayarkan …" -> digabung

**Catatan pengawas:**

> karena akibatnya/kondisi hak dan kewajibannya muncul setelah daftar

**Keputusan:** GABUNG (dikonfirmasi). **Aturan v4.5:** —. **Label:** —.

### R7 — 7.1.3.2 Sub-bagian berjudul

**Pertanyaan:** Butir yang punya JUDUL dan ISI sendiri di bawah pengantar informatif: dipisah per judul (walau ada aturan "informatif selalu digabung")?

- **Contoh:** PT Dompet Harapan Bangsa (OY! Indonesia) · Payment Gateway (OY!) · 6. Metode Pembayaran
- **Isi v4:** Pisah per judul
- **Usulan tim:** Setuju (pisah)

**Jawaban pengawas** (apa adanya):

> "Dalam pelaksanaan Layanan, Kami menyediakan beberapa pilihan pembayaran sebagai berikut:" → "1. PEMBAYARAN MELALUI VIRTUAL ACCOUNT" + isi → "2. …" → "4. PEMBAYARAN MELALUI PEMROSESAN KARTU" + isi -> tetap dipisah

**Keputusan:** PISAH per judul (dikonfirmasi). **Aturan v4.5:** —. **Label:** —.

### R9 — 3.3.4 / 1.3 Pembuka & penutup

**Pertanyaan:** Pembuka atau penutup yang terdiri dari beberapa paragraf (dipisah baris kosong): dipisah per paragraf?

- **Contoh:** PT Bank SMBC Indonesia Tbk / PT Bank OCBC NISP Tbk · Kartu Kredit (Kartu Kredit Jenius) / Internet Banking (OCBC mobile) · SMBC: paragraf pembuka (1) / OCBC IB: paragraf penutup (4)
- **Isi v4:** Pisah
- **Usulan tim:** Setuju (pisah)

**Jawaban pengawas** (apa adanya):

> -SMBC: 3 paragraf — keberlakuan S&K / telah disesuaikan dengan ketentuan BI & OJK / info layanan di www.jenius.com -> dipisah
> - OCBC IB: "… TELAH DISESUAIKAN DENGAN … OTORITAS JASA KEUANGAN." + "PT Bank OCBC NISP Tbk berizin dan diawasi oleh OJK & Bank Indonesia, serta merupakan peserta penjaminan LPS." -> dipisah

**Keputusan:** PISAH per paragraf (dikonfirmasi). **Aturan v4.5:** —. **Label:** —.

### R10 — 3.3.6 Satu paragraf

**Pertanyaan:** Satu paragraf berisi beberapa kalimat hak/kewajiban TIDAK PERNAH dipecah di batas kalimat?

- **Contoh:** PT AirPay International Indonesia · Uang Elektronik Server-Based (ShopeePay) · 2. Layanan, 2.11 Split Bill
- **Isi v4:** Tidak dipecah
- **Usulan tim:** Setuju

**Jawaban pengawas** (apa adanya):

> "Split Bill adalah fitur pada Platform yang memudahkan Pengguna … Pengguna dapat menggunakan fitur Split Bill baik sebagai pembuat tagihan maupun sebagai peserta. Setelah struk berhasil dipindai …" -> tetap digabung dan tidak dipecah per batas kalimat

**Catatan pengawas:**

> karena tidak ada unsur parent-child (bentuknya continuous 1 paragraf)

**Keputusan:** Tidak dipecah per kalimat (dikonfirmasi). **Aturan v4.5:** —. **Label:** —.

### R11 — 5.2.2 Prosedur

**Pertanyaan:** Rangkaian tindakan BANK yang berurutan termasuk prosedur (digabung)?

- **Contoh:** PT AirPay International Indonesia · Uang Elektronik Server-Based (ShopeePay) · 8. Kesalahan 8.6
- **Isi v4:** Prosedur → gabung
- **Usulan tim:** Setuju (gabung)

**Jawaban pengawas** (apa adanya):

> "Segera setelah Anda memberitahu kami mengenai dugaan Transaksi tidak sah atau kesalahan, atau jika kami mengetahui terjadinya hal tersebut: a. Kami akan mengadakan penyelidikan … b. Kami akan merampungkan penyelidikan … c. Jika kami memerlukan tambahan … d. Kami akan memberitahukan …" -> digabung

**Catatan pengawas:**

> tetap digabung karena merupakan prosedur

**Keputusan:** GABUNG, prosedur (dikonfirmasi). **Aturan v4.5:** —. **Label:** SHOPEEPAY UE 8.6 → 1 klausa.

### R12 — 9.1–9.5 Bahasa Inggris

**Pertanyaan:** (a) Istilah Inggris tanpa padanan Indonesia dipertahankan? (b) Padanan berpasangan: bagian Inggris dibuang?

- **Contoh:** PT Bank Muamalat Indonesia · Internet Banking · Transfer & instruksi transaksi
- **Isi v4:** Ambigu
- **Usulan tim:** Ya / ya

**Jawaban pengawas** (apa adanya):

> MUAMALAT IB (a) "Telegraphic Transfer (TT)" dan (b) "'Kirim' atau 'Submit'" → menjadi "'Kirim'" -> dibiarkan saja (tidak diubah apa-apa)

**Catatan pengawas:**

> karena dokumen ini bukan dokumen dwibahasa, melainkan hanya bahasa Indonesia saja; Oleh karena itu, jika dihilangkan akan merubah makna klausa

**Keputusan:** Istilah Inggris di dokumen berbahasa Indonesia dibiarkan apa adanya. **Aturan v4.5:** 9.6 (baru), 9.2, #15. **Label:** —.

### R13 — 3.2.4 Daftar sebaris

**Pertanyaan:** Butir (i), (ii), (a) yang ditulis DI DALAM satu kalimat/paragraf (bukan baris baru) tetap SATU klausa, walaupun isinya larangan/kondisi alternatif?

- **Contoh:** PT Dompet Harapan Bangsa (OY! Indonesia) · Payment Gateway (OY!) · 2. Penggunaan Layanan 2; 9. Kegiatan Tidak Sah
- **Isi v4:** Satu klausa
- **Usulan tim:** Setuju

**Jawaban pengawas** (apa adanya):

> - "Anda tidak dapat: (i) menyalin, memodifikasi … ; (ii) mendistribusikan, menampilkan secara umum …" -> dipisah karena parent clause mengandung hak/kewajiban dan children merepresentasikan opsi
> - "Anda setuju bahwa Anda tidak akan melakukan salah satu dari berikut …: (i) berupaya mengakses …; (ii) …" — label: SATU klausa (29 kasus digabung vs ±5 dipisah di seluruh data) ->  dipisah karena parent clause mengandung hak/kewajiban dan children merepresentasikan opsi

**Keputusan:** **Dibalik dari v3.1:** daftar sebaris yang diantar kalimat induk berisi hak/kewajiban dan butirnya opsi → PISAH. **Aturan v4.5:** 3.2.4, 3.3.6, 6.6, #7, #10. **Label:** ±29 daftar sebaris di seluruh data, termasuk OY PG; DBS MB 6\|2, 22\|3.

### R14 — 5.2.2.3 Ruang lingkup / penyebab

**Pertanyaan:** Daftar setelah "termasuk namun tidak terbatas pada:" atau "yang timbul dari / akibat:" pada suatu hak, kewajiban, atau pengecualian tanggung jawab → DIPISAH per butir?

- **Contoh:** PT AirPay International Indonesia / PT Bank DBS Indonesia / PT Bank Mandiri (Persero) Tbk · Uang Elektronik Server-Based (ShopeePay) / Mobile Banking (digibank) / Mobile Banking (Livin') · ShopeePay: 17. Ganti Rugi / DBS: 37. Lain-Lain 10 / Mandiri: D. Permintaan, Perintah, dan Dokumentasi 9
- **Isi v4:** Pisah (kecuali daftar jenis informatif, mis. "Jenis Data … termasuk namun tidak terbatas pada:")
- **Usulan tim:** Setuju

**Jawaban pengawas** (apa adanya):

> -ShopeePay: "… Anda setuju untuk membebaskan Kami … dari … klaim … yang timbul atau sehubungan dengan: a. Pelanggaran Anda … b. … e. …" -> dipisah karena masing-masing children merepresentasikan opsi dan parent memiliki unsur hak/kewajiban
> - MANDIRI MB:  -> dipisah karena masing-masing children merepresentasikan opsi dan parent memiliki unsur hak/kewajiban
> - DBS: "Bank tidak bertanggung jawab terhadap segala risiko …, termasuk namun tidak terbatas kepada: …"   -> dipisah karena masing-masing children merepresentasikan opsi dan parent memiliki unsur hak/kewajiban

**Keputusan:** PISAH (dikonfirmasi). **Aturan v4.5:** —. **Label:** —.

### R15 — 5.2.4.1 Ciri satu objek

**Pertanyaan:** Induk diakhiri "… yang:" dengan butir berupa CIRI/SYARAT dari satu objek → satu klausa, walaupun induk memuat "wajib"?

- **Contoh:** Bank of China (BOC) · Mobile Banking & Internet Banking (BOC Mobile / BOCNet) · 5. Kewajiban Keamanan 5.2
- **Isi v4:** Gabung (dasar label: 1 contoh)
- **Usulan tim:** Setuju

**Jawaban pengawas** (apa adanya):

> "Nasabah wajib untuk memilih ID pengguna dan kode sandi yang: 1. Merupakan 6-20 digit kode alpha-numeric … 2. Tidak memiliki hubungan yang jelas dengan nama, alamat … 3. Bukan merupakan urutan huruf-huruf atau angka-angka …" -> digabung

**Catatan pengawas:**

> karena masing-masing children tidak dapat terlepas satu dengan lainnya dan merupakan prosedur pembuatan ID pengguna & kode sandi

**Keputusan:** GABUNG (dikonfirmasi). **Aturan v4.5:** —. **Label:** —.

### R19 — 3.2.3 Batas sub-daftar

**Pertanyaan:** Butir yang diakhiri ":" diikuti sub-daftar bernomor 1, 2, 3 …; di tengah jalan nomor berikutnya berupa kalimat lengkap yang tidak lagi melanjutkan butir tsb. Di mana sub-daftar berakhir?

- **Contoh:** Bank Nagari · Mobile Banking (OLLIN) · III. Ketentuan Lainnya, 4 Pernyataan
- **Isi v4:** Tidak diatur (semua prompt menganggap 1–7 anak butir 4)
- **Usulan tim:** Sesuai label

**Jawaban pengawas** (apa adanya):

> "4 Dalam hal terjadi perubahan kebijakan … yang berkaitan dengan : 1 Administrasi dan operasional Bank. 2 Standar pelayanan … 3 … 4 Tarif … 5 Pembatasan-pembatasan … 6 Dengan memberikan pemberitahuan sebelumnya … Bank berhak mengubah … 7 Nasabah memberi wewenang …" 1–5 milik butir 4 (dipisah), lalu 6-9 berdiri menjadi klausa sendiri lanjutan dari nomor 4. Subdaftar berhenti sampai no.5

**Keputusan:** Sub-daftar berhenti di butir 5; butir 6–9 klausa sendiri. **Aturan v4.5:** 3.2.3.6 (baru; dipersempit setelah uji DBS). **Label:** NAGARI MB III.4.

### R20 — 5.2.2.3 Pernyataan status produk

**Pertanyaan:** Daftar pernyataan mengenai STATUS / SIFAT HUKUM suatu produk atau dana (bukan hak/kewajiban langsung) → dipisah per butir?

- **Contoh:** PT Bank Sinarmas · Uang Elektronik Server-Based (Simas E-Money) · Saldo dalam Rekening Simas E-Money, 1
- **Isi v4:** Pisah (dasar label: 1 dokumen test + 2 kasus train)
- **Usulan tim:** Setuju

**Jawaban pengawas** (apa adanya):

> "Saldo uang elektronik yang tersimpan dalam rekening Simas E-Money: a. Bukan merupakan simpanan sebagaimana dimaksud dalam Undang-Undang tentang Perbankan … b. Tidak termasuk yang dijamin oleh Lembaga Penjamin Simpanan … c. Tidak mendapatkan bunga dalam bentuk apapun." -> digabung karena ketiga butir tersebut merupakan informasi saja (yang menjelaskan terkait SIMAS) dan masing-masing bukan merupakan opsi yang bisa berdiri sendiri

**Keputusan:** **Dibalik dari v4:** GABUNG (informasi). **Aturan v4.5:** 5.2.3.5.2, 5.2.2.3, 6.6. **Label:** SINARMAS UE Saldo 1 → 1 klausa.

### R21 — 6.6 Ketentuan berikut

**Pertanyaan:** Induk "… dengan tunduk pada ketentuan-ketentuan berikut:" / "… dengan ketentuan sebagai berikut:" → setiap butir ketentuan diuji sendiri (umumnya dipisah)?

- **Contoh:** PT Bank Seabank Indonesia · Mobile Banking (SeaBank) · 5. Ketentuan Umum untuk Rekening Deposit, 5.26 Transfer Terjadwal
- **Isi v4:** Uji per butir, umumnya pisah
- **Usulan tim:** Setuju

**Jawaban pengawas** (apa adanya):

> "Nasabah dapat melakukan Transfer Terjadwal dengan tunduk pada ketentuan-ketentuan berikut: a. Transfer Terjadwal adalah fitur … b. Transfer Terjadwal dapat dilakukan untuk keperluan: i. … ii. … c. …" -> digabung karena children informasi mengenai transfer terjadwal saja. kalimat "tunduk pada ketentuan berikut" tidak memiliki beban hak/kewajiban pada konteks klausa ini saja (belum tentu berlaku hal yang sama di klausa lainnya).

**Keputusan:** **Dibalik dari v4:** GABUNG bila butirnya menjelaskan satu fitur. **Aturan v4.5:** 5.2.3.5.3, 6.6. **Label:** SEABANK MB 5.26 a–g → 1 klausa.

**Tafsiran tim:** Pengawas hanya mengutip butir a–c. Butir e (`Nasabah harus memastikan …`) dan g (`Bank tidak bertanggung jawab …`) ikut digabung, mengikuti jawaban pengawas.
