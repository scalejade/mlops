# Laporan Lengkap — Percobaan Deployment LLM untuk Ekstraksi Klausa PJP

**Proyek:** Ekstraksi & penilaian klausa Perjanjian Baku PJP untuk tim hukum Bank Indonesia
**Periode:** 15–16 Agustus 2026
**Platform:** RunPod Serverless · template vLLM v2.25.1 (berisi vLLM 0.27.1)
**Penulis catatan:** hasil analisis log deployment

---

# BAGIAN I — RINGKASAN EKSEKUTIF

## Status akhir

| Model | Hasil | Keterangan |
|---|---|---|
| **Qwen-SEA-LION-v4-32B-IT-8BIT** | ✅ **Terpilih** | Terbukti jalan, 1 GPU, $3.49/jam |
| DeepSeek-V4-Flash-0731 | ⚠️ Berhasil sebagian | Sampai alokasi KV, butuh 2 GPU, 8 perbaikan |
| Gemma 4 31B-it (QAT) | ❌ Gagal | Arsitektur tidak didukung vLLM 0.27.1 |
| Qwen-SEA-LION-v4.5-27B-IT | ⏳ Belum diuji | Context 262,144 — layak dicoba |

## Temuan paling penting

1. **Output terpotong di produksi.** `max_tokens: 16384` lebih kecil dari kebutuhan nyata 17,258 token → ±7 klausa hilang di setiap dokumen sebesar BCA.
2. **SEA-LION v4 hanya 40,960 context** (turun dari v3 yang 128K). Margin untuk dokumen BCA hanya 75 token.
3. **Model berumur < 1 bulan berisiko tinggi.** vLLM 0.27.1 tertinggal dari Gemma 4 (gagal total) dan DeepSeek-V4 (butuh 8 perbaikan).
4. **Network volume mengubah cold start dari 2 jam → 26 detik.**

---

# BAGIAN II — PROFIL BEBAN KERJA (TERUKUR)

Diukur dengan tokenizer Qwen asli, dokumen uji: `Ketentuan m-BCA (Mobile Banking) PT BCA Tbk`.

## Ukuran token

| Komponen | Token | Karakter |
|---|---|---|
| System prompt | 10,975 | 31,329 |
| Dokumen (user) | 10,280 | 33,776 |
| Chat template | ~30 | — |
| **Total input** | **21,285** | |
| Output tahap-1 (ekstraksi) | 17,258 | |
| **Total context** | **38,543** | |

## Statistik klausa

```
jumlah klausa   : 144
rata-rata       : 120 token/klausa (tahap ekstraksi)
                  252 token/klausa (setelah penilaian)
median          : 248
p90             : 345
min / max       : 130 / 536
```

## Simulasi pembagian batch

Bila dokumen dipecah (worst-case: klausa terbesar menumpuk di satu batch):

| Batch | Klausa/call | System | Dok | Output | Total | Margin |
|---|---|---|---|---|---|---|
| 1 | 144 | 10,975 | 10,280 | 17,258 | 38,513 | 6% |
| 2 | 72 | 10,975 | 5,140 | ~10,500 | 26,615 | 35% |
| 3 | 48 | 10,975 | 3,427 | ~7,200 | 21,602 | 47% |

---

# BAGIAN III — KRONOLOGI SEMUA PERCOBAAN

## A. Percobaan 1 — Qwen-SEA-LION-v4-32B-IT-8BIT (awal)

**Waktu:** 15 Agustus, siang
**GPU:** RTX PRO 6000 96GB × 1

### Isu 1.1 — `max_model_len must be positive, got 0`

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for ModelConfig
  Value error, max_model_len must be a positive integer, got int: 0.
```

**Penyebab:** Field `MAX_MODEL_LEN` kosong di RunPod → diteruskan sebagai `0`.
vLLM 0.27 menolak (versi lama menerima 0 sebagai "auto").

**Solusi:** `MAX_MODEL_LEN=32768` (kemudian dikoreksi ke 40960)

**Status:** ✅ Selesai — endpoint berjalan

---

## B. Percobaan 2 — DeepSeek-V4-Flash-0731

**Waktu:** 15 Agustus, sore–malam
**Model:** 304B MoE, 155.43 GiB checkpoint, 149 GiB VRAM

### Isu 2.1 — `DP adjusted local rank N is out of bounds for 1 devices`

```
AssertionError: DP adjusted local rank 1 is out of bounds for 1 devices.
```

**Penyebab:** `TENSOR_PARALLEL_SIZE=2` di env, tapi **GPU count = 1** di endpoint settings.
Env var dan setting hardware adalah dua field terpisah.

**Solusi:** Endpoint → **GPU count = 2**

**Catatan:** Terulang 3× karena kebingungan antara *Max Workers* (jumlah replika) dan
*GPU count* (jumlah GPU per worker).

---

### Isu 2.2 — Worker throttled & tersebar di 2 datacenter

**Gejala:** Worker di US-NE-1 dan US-NC-1 sekaligus; satu worker berstatus `throttled`.

**Penyebab:**
- Network volume tidak terpasang → tiap worker download 155 GiB sendiri
- RTX PRO 6000 dipilih (Medium Supply) alih-alih H200 (High Supply)

**Solusi:**
- Pasang network volume (mengunci semua worker ke 1 datacenter)
- GPU type → H200 SXM saja, deselect RTX PRO 6000
- Max workers → 1

---

### Isu 2.3 — Download 2 jam

**Penyebab:** 155 GiB tanpa `HF_TOKEN` (rate-limited) dan tanpa akselerasi transfer.

**Solusi:**
```
HF_TOKEN=hf_...
HF_XET_HIGH_PERFORMANCE=1
HF_HOME=/runpod-volume/hf
```

**Hasil:** Cold start berikutnya **26 detik** (dari cache volume).

**Catatan:** `HF_HUB_ENABLE_HF_TRANSFER` sudah usang —
`FutureWarning: 'hf_transfer' is not used anymore. Please use HF_XET_HIGH_PERFORMANCE`

---

### Isu 2.4 — `dispatch_scaled_mm` (CUTLASS)

```
RuntimeError: dispatch_scaled_mm,
/workspace/csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_helper.hpp:17
```

**Penyebab:** Model memakai skala **UE8M0** (`quantization_config.scale_fmt=ue8m0`).
Format ini butuh **DeepGEMM**. Dengan `VLLM_USE_DEEP_GEMM=0`, vLLM fallback ke CUTLASS
yang tidak punya kernel untuk UE8M0 → dispatch gagal.

**Solusi:** `VLLM_USE_DEEP_GEMM=1`

---

### Isu 2.5 — `No common block size` (16 → 64 → 128 → 256)

```
ValueError: No common block size for 16.
ValueError: No common block size for 64.
ValueError: No common block size for 128.
```

**Penyebab:** DeepSeek-V4 punya **dua mekanisme attention**:
```
Using DeepSeek's fp8_ds_mla KV cache format.
Using FP8 indexer cache for Lightning Indexer.
```
vLLM harus mencari block size yang didukung **kedua** kernel. Nilai 16/64/128 tidak ada
yang cocok.

**Solusi:** `BLOCK_SIZE=256` (nilai dari resep resmi vLLM)

**Catatan diagnosis:** Sempat disimpulkan keliru bahwa vLLM terlalu tua. Setelah membaca
`recipes.vllm.ai`, ternyata versi minimum yang dibutuhkan adalah 0.25.0 — 0.27.1 sudah cukup,
hanya nilai `block-size`-nya yang salah.

---

### Isu 2.6 — `custom_all_reduce.cuh: invalid argument`

```
Failed: Cuda error /workspace/csrc/custom_all_reduce.cuh:164 'invalid argument'
→ RuntimeError: cancelled
```

**Penyebab:** Kernel all-reduce kustom vLLM gagal, meski di H200 ber-NVLink.

**Solusi:** `DISABLE_CUSTOM_ALL_REDUCE=true` (fallback ke NCCL, ~beberapa persen lebih lambat)

---

### Isu 2.7 — KV cache tidak cukup

```
ValueError: To serve at least one request with the model's max seq len (131072),
52.66 GiB KV cache is needed, which is larger than the available KV cache memory (23.37 GiB).
Estimated maximum model length is 58148.
```

**Penyebab:** `MAX_NUM_BATCHED_TOKENS=65536` menghabiskan ~26 GiB untuk memori aktivasi.

**Solusi:** `MAX_NUM_BATCHED_TOKENS=8192`

**Hasil setelah perbaikan:**
```
Available KV cache memory: 50.51 GiB
GPU KV cache size: 752,889 tokens
Maximum concurrency for 98,304 tokens per request: 7.66x
```

---

### Isu 2.8 — Startup tidak pernah selesai

**Gejala:** Log berhenti di `~3 menit 45 detik`, masih mengompilasi TileLang, tanpa
`Application startup complete`.

```
TileLang begins to compile kernel `mhc_pre_big_fuse_broadcast_with_norm_tilelang`
TileLang begins to compile kernel `mhc_post_tilelang`
TileLang begins to compile kernel `hc_head_fuse_tilelang`
[shm_broadcast] No available shared memory broadcast block found in 60 seconds.
```

**Penyebab (dugaan kuat):** DeepSeek-V4 melakukan JIT compile kernel TileLang **setiap
cold start** (~4 menit). RunPod health check kemungkinan mematikan worker sebelum vLLM
membuka port.

**Solusi yang belum diuji:** Execution/health timeout → 900 s, FlashBoot on.

**Status:** ⚠️ Endpoint dihapus sebelum sempat diverifikasi.

### Ringkasan performa DeepSeek-V4 (terukur)

| Metrik | Nilai |
|---|---|
| Checkpoint di disk | 155.43 GiB |
| Bobot di VRAM | 74.34 GiB/GPU × 2 = 148.7 GiB |
| Load dari cache volume | 25.7 detik |
| KV cache tersedia | 50.51 GiB |
| Kapasitas KV | 752,889 token (~70 KB/token) |
| TileLang JIT tiap cold start | ~4 menit |
| Biaya | $11.86/jam (2× H200) |

---

## C. Percobaan 3 — Gemma 4 31B-it-qat-w4a16-ct

**Waktu:** 16 Agustus, sore
**Repo:** `scalejade/gemma-4-31b-it-baseline` (clone dari `google/gemma-4-31B-it-qat-w4a16-ct`)

### Isu 3.1 — `--enable-auto-tool-choice requires --tool-call-parser`

```
TypeError: Error: --enable-auto-tool-choice requires --tool-call-parser
```

**Penyebab:** `ENABLE_AUTO_TOOL_CHOICE=true` membutuhkan flag pendamping
`--tool-call-parser` yang **tidak diekspos** oleh template RunPod.

**Solusi:** `ENABLE_AUTO_TOOL_CHOICE=false`

**Catatan:** Tool calling **tidak dibutuhkan** untuk kasus ini. Structured output
memakai `json_schema`/`guided_json` — mekanisme berbeda (guided decoding), murni di sisi request.

---

### Isu 3.2 — `AmbiguousGlobalPerLayerAttributeError` ❌ FATAL

```
transformers.integrations.heterogeneity.configuration_utils.AmbiguousGlobalPerLayerAttributeError:
'head_dim' is a per-layer attribute and may vary across layers.
Access it via the individual layer configs instead (e.g. config.per_layer_config[i].head_dim).
```

**Penyebab:** Gemma 4 memakai **heterogeneous config** — setiap layer bisa punya `head_dim`
berbeda (pola 50 sliding-window + 10 full attention). vLLM 0.27.1 membaca `config.head_dim`
sebagai nilai global tunggal; `transformers` menolak karena ambigu.

**Solusi:** **Tidak ada env var yang bisa memperbaiki.** Butuh vLLM versi lebih baru.

**Status:** ❌ Model tidak dapat dipakai di runtime saat ini.

**Sisi positif:** Gagal di 30 detik pertama saat parsing config — sebelum download 18 GB.

### Spesifikasi Gemma 4 31B (dari config.json)

```
num_hidden_layers       : 60
num_attention_heads     : 32
num_key_value_heads     : 16
head_dim                : 256
max_position_embeddings : 262,144
sliding_window          : 1,024
layer_types             : 5 sliding + 1 full, diulang 10×
KV cost                 : ~80 KB/token (hanya 10 layer bayar penuh)
```

---

# BAGIAN IV — PERBANDINGAN MODEL

## Spesifikasi terverifikasi (dari config.json masing-masing)

| Model | Arsitektur | Context | Layers | KV heads | head_dim | KV/token | BF16 |
|---|---|---|---|---|---|---|---|
| SEA-LION v4 32B | Qwen3 | **40,960** | 64 | 8 | 128 | 128 KB | 66 GB |
| SEA-LION v4 32B 8BIT | Qwen3 | **40,960** | 64 | 8 | 128 | 128 KB | 34 GB |
| SEA-LION v4.5 27B | **Qwen3.5** | **262,144** | 64 | 4 | 256 | 128 KB | 54 GB |
| Gemma 4 31B | Gemma4 | 262,144 | 60 | 16 | 256 | 80 KB | 61 GB |
| DeepSeek-V4-Flash | DeepseekV4 | 1,048,576 | 43 | 1 | — | ~70 KB | 149 GB |

## Kebutuhan GPU

| Model | GPU minimum | $/jam | Request paralel @41k |
|---|---|---|---|
| SEA-LION v4 8BIT | 1× L40S 48GB | 1.75 | ~1.7 |
| SEA-LION v4 8BIT | 1× RTX PRO 6000 | 3.49 | ~9.9 |
| SEA-LION v4 BF16 | 1× RTX PRO 6000 | 3.49 | ~3 |
| SEA-LION v4.5 BF16 | 1× RTX PRO 6000 | 3.49 | ~6 |
| Gemma 4 31B QAT | 1× L40S 48GB | 1.75 | ~7 |
| DeepSeek-V4 | 2× H200 | 11.86 | ~7.6 (@98k) |

---

# BAGIAN V — REQUEST & RESPONSE

## 5.1 Request (diperbaiki)

```json
{
  "model": "aisingapore/Qwen-SEA-LION-v4-32B-IT-8BIT",
  "messages": [
    { "role": "system", "content": "<system prompt — 10,975 token>" },
    { "role": "user",   "content": "DOCUMENT:\n<isi dokumen>" }
  ],
  "max_tokens": 19600,
  "temperature": 0,
  "top_p": 1.0,
  "seed": 0,
  "stream": false,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "clause_extraction",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "clauses": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "properties": {
                "pasal":       { "type": "string", "minLength": 1 },
                "topic":       { "type": "string", "minLength": 1, "maxLength": 100 },
                "clause_text": { "type": "string", "minLength": 1 }
              },
              "required": ["pasal", "topic", "clause_text"],
              "additionalProperties": false
            }
          }
        },
        "required": ["clauses"],
        "additionalProperties": false
      }
    }
  }
}
```

### Perubahan dari request lama

| Parameter | Sebelum | Sesudah | Alasan |
|---|---|---|---|
| `max_tokens` | 16,384 | **19,600** | ⚠️ **memperbaiki pemotongan output** |
| `response_format` | `json_object` | **`json_schema` strict** | JSON dijamin valid; `maxLength` ditegakkan mesin |
| `temperature` | (default) | **0** | aturan verbatim (11.3) butuh determinisme |
| `top_p` | — | 1.0 | eksplisit |
| `seed` | — | 0 | hasil dapat direproduksi |

### Anggaran token

```
21,285 (input) + 19,600 (max_tokens) = 40,885
batas model                          = 40,960
sisa                                 =      75  ⚠️ sangat tipis
```

### Versi RunPod native (`/run`)

```json
{
  "input": {
    "messages": [ ... ],
    "apply_chat_template": true,
    "stream": false,
    "sampling_params": {
      "max_tokens": 19600,
      "temperature": 0,
      "top_p": 1.0,
      "seed": 0,
      "guided_json": { "<schema sama seperti di atas>" }
    }
  }
}
```

## 5.2 Response — Tahap 1 (Ekstraksi)

```json
{
  "clauses": [
    {
      "pasal": "A. DEFINISI|1",
      "topic": "Definisi m-BCA (Mobile Banking)",
      "clause_text": "m-BCA (Mobile Banking) adalah layanan produk perbankan PT Bank Central Asia Tbk (\"BCA\") yang dapat diakses secara langsung oleh Nasabah melalui telepon seluler/handphone, menggunakan menu pada BCA mobile dengan menggunakan media jaringan internet pada handphone dikombinasikan dengan media SMS sesuai ketentuan yang berlaku di BCA."
    }
  ]
}
```

**144 objek** dalam array, ~120 token per objek.

## 5.3 Response — Tahap 2 (Penilaian, setelah disimpan ke DB)

```json
{
  "submission": {
    "id": "6ecb468b-69b4-4e99-9c8b-d371e5c434be",
    "document_name": "23e93549-....pdf",
    "company": "BCA",
    "model_ai": "aisingapore/Qwen-SEA-LION-v4-32B-IT-8BIT",
    "status": "selesai",
    "result_date": "2026-08-09T09:53:34.672686Z"
  },
  "regulation":       { "title": "Peraturan Bank Indonesia Nomor 3 Tahun 2023", "version": 1 },
  "padg_regulation":  { "title": "PADG No. 20/23/PADG/2018", "version": 1 },
  "result_number": 1,
  "clauses": [
    {
      "id": "dd911827-...",
      "assessment_result_id": "7e1219ee-...",
      "clause_group_id": "5d2f1763-...",
      "version": 1,
      "pasal": "A. DEFINISI|1",
      "clause_name": "Definisi m-BCA (Mobile Banking)",
      "clause_text": "m-BCA (Mobile Banking) adalah layanan produk perbankan ...",
      "status": "netral",
      "explanation": "Klausul hanya mendefinisikan layanan m-BCA tanpa menyebutkan aspek informasi, biaya, risiko, atau mekanisme pemberitahuan yang diatur dalam regulasi BI.",
      "reference_pasal": "—",
      "ppk_principle": "tidak relevan",
      "clause_category": "Ruang lingkup produk dan/atau layanan",
      "sort_order": 1,
      "created_at": "2026-08-09T09:53:34.421608Z"
    }
  ]
}
```

**Catatan pembagian token:**

| Bagian | Token |
|---|---|
| Digenerate model (tahap 1) | 17,258 |
| Digenerate model (tahap 1+2) | 36,326 |
| Metadata DB (uuid, timestamp) | 23,563 |
| Total file tersimpan | 59,889 |

Metadata DB **tidak** dihasilkan model — jangan dihitung dalam anggaran `max_tokens`.

## 5.4 Endpoint API

**OpenAI-compatible:**
```
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/openai/v1/chat/completions
Authorization: Bearer {RUNPOD_API_KEY}
Content-Type: application/json

→ .choices[0].message.content
```

**Native async (disarankan untuk output panjang):**
```
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/run           → { "id": "..." }
GET  https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{id}   → poll tiap 5 detik

→ .output[0].choices[0].tokens[0]
```

⚠️ **Jangan pakai `/runsync`** — generate 19,600 token butuh ~10–13 menit, jauh melebihi timeout.

---

# BAGIAN VI — KATALOG ISU LENGKAP

| # | Error | Model | Penyebab | Solusi |
|---|---|---|---|---|
| 1 | `max_model_len must be positive, got 0` | semua | field RunPod kosong | `MAX_MODEL_LEN=<nilai>` |
| 2 | `DP adjusted local rank N out of bounds` | DeepSeek | GPU count ≠ TP size | endpoint → GPU count = TP |
| 3 | Worker throttled, 2 datacenter | DeepSeek | tanpa network volume | pasang volume, kunci 1 GPU type |
| 4 | Download 2 jam | DeepSeek | tanpa token & akselerasi | `HF_TOKEN` + `HF_XET_HIGH_PERFORMANCE` + `HF_HOME` |
| 5 | `dispatch_scaled_mm` CUTLASS | DeepSeek | UE8M0 butuh DeepGEMM | `VLLM_USE_DEEP_GEMM=1` |
| 6 | `No common block size for 16/64/128` | DeepSeek | MLA + Lightning Indexer | `BLOCK_SIZE=256` |
| 7 | `custom_all_reduce.cuh invalid argument` | DeepSeek | kernel all-reduce vLLM | `DISABLE_CUSTOM_ALL_REDUCE=true` |
| 8 | KV cache tidak cukup | DeepSeek | batched tokens 65536 | turunkan ke 8192 |
| 9 | Startup tidak selesai (~4 menit) | DeepSeek | TileLang JIT vs health check | timeout 900 s, FlashBoot on |
| 10 | `--enable-auto-tool-choice requires --tool-call-parser` | Gemma 4 | flag tidak diekspos RunPod | `ENABLE_AUTO_TOOL_CHOICE=false` |
| 11 | `AmbiguousGlobalPerLayerAttributeError` | Gemma 4 | config heterogen per-layer | ❌ butuh vLLM lebih baru |
| 12 | Output terpotong | SEA-LION | `max_tokens` < kebutuhan | `max_tokens=19600` |

---

# BAGIAN VII — PELAJARAN OPERASIONAL

1. **Cek `Resolved architecture:` di 30 detik pertama.** Kalau arsitektur tidak dikenal,
   tidak ada env var yang bisa memperbaikinya — hentikan segera.

2. **GPU count adalah setting endpoint, bukan env var.** `TENSOR_PARALLEL_SIZE` dan
   *GPU count* harus diubah bersamaan. Jangan tertukar dengan *Max Workers* (jumlah replika).

3. **Network volume + `HF_HOME`** wajib untuk model besar. Tanpa itu, tiap cold start
   mengulang seluruh download.

4. **`MAX_NUM_BATCHED_TOKENS` mencuri memori KV.** Nilai 65536 memakan ~26 GiB. Untuk
   context panjang, 8192 adalah titik aman.

5. **`ENABLE_PREFIX_CACHING=true`** menghemat >60% waktu prefill bila system prompt tetap
   (di sini 10,975 token identik tiap panggilan).

6. **Baca resep resmi sebelum menyimpulkan versi runtime terlalu tua.**
   `recipes.vllm.ai` memuat nilai `block-size` yang benar untuk DeepSeek — satu jam
   debugging bisa dihindari.

7. **Model berumur < 1 bulan berisiko tinggi** di runtime terkelola. Semua kegagalan
   fatal berasal dari model yang lebih baru daripada vLLM 0.27.1.

8. **Verifikasi anggaran token dengan tokenizer asli**, bukan perkiraan karakter.
   Selisih antara `json_object` pretty-print dan minified saja ±1,700 token.

---

# BAGIAN VIII — LANGKAH BERIKUTNYA

## Segera
- [ ] Deploy `Qwen-SEA-LION-v4-32B-IT-8BIT` di RTX PRO 6000 96GB
- [ ] Verifikasi `GPU KV cache size: ~400,000 tokens` di log
- [ ] Ganti `max_tokens` 16384 → 19600 di aplikasi
- [ ] Ganti `json_object` → `json_schema` di aplikasi
- [ ] Uji 1 dokumen: pastikan **144** klausa keluar, bukan 137

## Uji cepat (gagal dalam 30 detik, biaya ~nol)
- [ ] `aisingapore/Qwen-SEA-LION-v4.5-27B-IT` — context 262,144
      Kalau `Qwen3_5ForConditionalGeneration` didukung, semua batasan context hilang
- [ ] Cek apakah RunPod merilis template vLLM lebih baru

## Jangka menengah
- [ ] Bandingkan kualitas v4 vs v4.5 (dan Gemma 4 bila runtime sudah siap) pada 20–30 klausa berlabel
- [ ] Bila tetap di v4 (40,960): pecah dokumen per header bagian (A–J)
- [ ] LoRA fine-tune dari `Qwen-SEA-LION-v4-32B-IT` (BF16) di Pod H200
- [ ] Serve adapter di atas base 8-bit (`ENABLE_LORA=true`) — tanpa merge & requantize

## Keamanan
- [ ] **Cabut token HF yang terekspos.** Token muncul di log sebagai `--hf-token hf_...`
      pada setiap baris startup, dan sempat dibagikan di percakapan.
- [ ] Pertimbangkan memakai RunPod **Secrets** alih-alih env var biasa
      (env var tidak terenkripsi)

---

# LAMPIRAN — Referensi Biaya

| Sumber daya | Spesifikasi | Biaya |
|---|---|---|
| L40S 48GB (PRO) | Ada, fp8 KV ✓ | $1.75/jam |
| 48GB non-PRO | Ampere, **fp8 KV ✗** | $1.22/jam |
| RTX PRO 6000 | Blackwell 96GB | $3.49/jam |
| H100 | 80GB | $4.79/jam |
| H200 SXM | 141GB | $5.93/jam |
| B200 | 180GB | $8.64/jam |
| Network volume | — | $0.07/GB/bulan |

**Konfigurasi terpilih:** 1× RTX PRO 6000 + volume 60 GB ≈ **$3.49/jam + $4.20/bulan**
