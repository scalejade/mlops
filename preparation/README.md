# pbbi-clause-extraction

Training data for Stage-2B clause extraction in Perjanjian Baku BI: given a PJP
standard-form contract, return its clauses as JSON — **in exactly the request
the app makes**, so the adapter is trained on the input it is served.

## The serving contract

Read off `scalejade/perjanjian-baku-bi`, branch `sys-prompt` @ `e028187`
(`backend/internal/service/clause_extraction.go`, `pdf_extractor.go`). One call
per document, to `scalejade/qwen-sea-lion-v4.5-27b-it` on the RunPod endpoint:

| role | content |
|---|---|
| `system` | `prompts/extraction_system.md` — a byte-for-byte copy of the app's `go:embed` file (540 lines, 13,963 tokens) |
| `user` | `"DOCUMENT:\n"` + the document text |
| `assistant` | `{"clauses":[{"pasal","topic","clause_text"}, ...]}`, compact, nothing around it |

The document text is `pdftotext -layout` → form feeds to newlines → trim →
`keepIndonesianOnly()`. `serving_text.py` is a line-for-line Python port of that
pipeline; `build.py` uses it for every row. Sent with
`response_format: json_object` and `max_tokens: 65536`.

**If the app changes the prompt, the envelope, or the text pipeline, this folder
changes in the same PR.** An adapter trained on one prompt shape and served
another sees input it never trained on, and can do worse than the base model.
To refresh the prompt:

```bash
gh api "repos/scalejade/perjanjian-baku-bi/contents/backend/internal/service/prompts/extraction_system.md?ref=<sha>" \
    -H "Accept: application/vnd.github.raw" > preparation/prompts/extraction_system.md
```

…and update the sha in `serving_text.SOURCE` and here.

### Running the app's call locally

`app_request.py` is the whole extraction call, rebuilt offline — text pipeline,
size check, request body, and the app's reply parsing and `finalizeClauses`. It
never calls the API:

```bash
python preparation/app_request.py <pdf> --out /tmp/req          # the exact request body
python preparation/app_request.py <pdf> --response reply.json   # ...and parse a reply as the app would
python -m unittest preparation/test_app_request.py              # 20 offline tests
```

`build.py` takes the request shape from it, so the training rows and this tool
cannot drift apart. Checked against the app's own Go, compiled locally on
2026-10-10: `keepIndonesianOnly` identical on all 100 readable PDFs; parsing and
`finalizeClauses` identical on 461 replies (every training answer plus edge cases
and mutations).

Two things it shows about the app, even when the model's answer is perfect —
DBS Mobile Banking with its own labels as the reply loses 2 of 263 clauses:

- **`clause_text` under 8 words is dropped**, including short definitions the
  prompt requires as their own clause (`Nasabah adalah perorangan pemilik
  Rekening di Bank.` is 7).
- **`normalizeClauseName` deletes `|`, `.` and `-` without leaving a space**, so
  distinct `pasal` values collide and the later one is dropped as a repeat:
  `37. Lain-Lain|10|ii|i` and `37. Lain-Lain|10|iii` are both `37 lainlain10iii`.

Both are app behaviour, not model errors. Score an adapter on the model's raw
output, not on what survives `finalizeClauses`.

## The documents: one folder each

```
preparation/raw/                          gitignored — client contracts
    DBS - Mobile Banking/
        S&K MOBILE BANKING DBS (CLEAN).pdf      the contract, exactly one PDF
        S&K MOBILE BANKING DBS (CLEAN).xlsx     Legal's labels
        annotation.txt                          its split and categories
    MEGA - Mobile Banking/
        ...
    ... about 60 folders when the set is complete
```

`build.py` finds every folder by itself — there is no list to edit. Adding a
document means adding a folder. A folder holds:

| File | Required | What |
|---|---|---|
| `*.pdf` | exactly one | The contract the app would receive |
| `*.xlsx` | one, unless there is a gold file | Legal's labels. Columns read by position: `No`, `No. Pasal`, `Topik Klausa`, `Bunyi Klausa`. One sheet; with several, name it as `Sheet : <name>` in `annotation.txt` |
| `*.gold.json` | optional | A `review-annotation` gold version (`rows` of `pasal` / `topik` / `bunyi`, verbatim-corrected against pedoman v1.5). Wins over the xlsx |
| `annotation.txt` | yes | `Key : Value` lines — below |

`annotation.txt`:

```
Dokumen          : PT Bank DBS Indonesia - Mobile Banking

[Kategori]
Utama            : Y
BPD              : T
Multinational    : Y
Swasta Nasional  : T
BUMN             : T
LSB              : T

[Produk Dokumen]
Produk           : Mobile Banking

[Kombinasi Kategori]
Kombinasi        : Utama / Multinational

[Tipe]
Tipe             : Utama / Multinational / Mobile Banking

[Split]
Split            : Test
```

Only `Split` decides anything. The rest is carried into `build-report.json` and
printed per split as a composition table (by `Kombinasi` and `Produk`), so you
can see whether a split covers the categories it should.

A folder that is malformed stops the build with its name and the reason — no
`annotation.txt`, a `Split` that is not one of the three, two PDFs, no labels, or
the same PDF (by content) in two splits. A document silently skipped would be a
document silently missing from a split.

## The three splits

A document goes to exactly one split, whole — a PDF is never divided between them.

| `Split :` | File | Rows | Used for |
|---|---|---|---|
| `Train` | `data/train.jsonl` | whole document, or windows when too long | What the adapter learns from. **Required** — no Train folders, nothing to train |
| `Validation` | `data/eval.jsonl` | whole document, or windows when too long | The eval loss during training — is it learning or memorising. Optional: remove `data.eval` from the config to train without it |
| `Test` | `data/test.jsonl` | **always the whole document**, however long — exactly the app's call | Never trained on, never used for loss. After training, run each through the adapter and score the output against the labels |

Assign splits by document *type* (the `Tipe` line), not at random, so Validation
and Test hold categories the model has to generalise to — a BPD contract when
Train is mostly large banks — and not only near-copies of training documents.

A split with no folders writes no file. If one is left from an earlier build it
is moved to `<name>.jsonl.prev`, so a stale file is never trained on as if
current (everything in `data/` but `sample.jsonl` is gitignored).

## One row is a document — or a shorter one

With the 14k-token system prompt and its full answer, a labelled contract is
**19k–82k tokens**. The answer alone is ~1.6× the document, because every
separated child clause repeats its parent's text (rule 7).

For Train and Validation (Test is always whole):

- A document that fits `--max-row-tokens` (default 30,000) is one row, whole —
  the exact call the app makes.
- A larger one is cut into **windows**: runs of consecutive whole sections, each
  sent as its own `DOCUMENT:\n…`. The app sends short contracts in exactly this
  shape, so a window is still a faithful input. A section too large for any
  window is split on its second `pasal` segment, and the piece is given its
  section's header line from the PDF first.

A window's answer is exactly the labels of the clauses inside it. What keeps
that true:

- a window starts at the top of the document or at a section's header line,
  never mid-sentence;
- a section that cannot be located in the served text ends the window before it;
- **the leak check** — a window whose text contains any labelled clause that is
  not in its answer is dropped. It is what catches two-column PDFs, where
  `pdftotext -layout` puts two unrelated clauses on the same line.

The user side is the served PDF text, never the clean `Bunyi Klausa`: clean-in /
clean-out teaches copying. The gap between the two is the lesson.

### Thinking blocks

No reasoning in the data, so the chat template inserts an empty
`<think></think>` and the model learns to close it and go straight to the JSON.
The app sends no `enable_thinking`, so a served response may open with an empty
think block; `extractJSONValue` skips to the first `{`, so that parses as-is.

## Build

```bash
python preparation/build.py --tokenizer scalejade/qwen-sea-lion-v4.5-27b-pbbi --dry-run
```

`--tokenizer` takes an HF repo id (needs `transformers`) or a local
`tokenizer.json` (needs only `tokenizers`). Without it lengths are estimated at
3.5 chars/token — fine for a look, not for `max_seq_length`. Needs `pdftotext`
(poppler) and `openpyxl`.

Writes into `preparation/data/`: `train.jsonl`, `eval.jsonl`, `test.jsonl`,
`sample.jsonl` and `build-report.json`. The folder is gitignored except
`sample.jsonl` (8 Train rows, every field cut to 120 characters).

`build-report.json` lists every folder with its split and annotation, every row
with its document and token count, and every dropped section with its reason.
Drops fall in three groups:

- **Low coverage / not found** — the labels and the PDF disagree: clauses merged,
  reordered or edited during labelling, or the xlsx matches a different PDF
  revision. Label-quality signals worth a look, not script bugs.
- **Leaks** — a window's text carries a labelled clause from outside it; the
  window is dropped rather than teach the model to skip clauses.
- **Too long** — a single section larger than `--max-row-tokens` with no second
  `pasal` segment to split on.

Test rows are never windowed, so they are never dropped.

### Current build (2026-10-10, exact token counts)

Two folders so far:

```
DBS - Mobile Banking    Test        test.jsonl  1 row, 263 clauses, 65,665 tokens
MEGA - Mobile Banking   Validation  eval.jsonl  1 row,  82 clauses, 26,666 tokens
Train                   —           no folders yet: nothing to train on
```

The 2026-10-10 39-row training set was built from ten documents that are no
longer under `raw/` (SeaBank, OVO, OCBC ×3, ShopeePay, Mandiri ×3,
Muamalat). They come back as folders with `Split : Train`.

## Known gaps

- **Two-column PDFs.** Some contracts (UOB Credit Card was one) are laid out in
  two columns, and `pdftotext -layout` interleaves them line by line — which is
  what the app serves. No Train window of such a document can be labelled
  honestly, so the leak check drops them and the adapter meets that layout
  untrained. Put one in Test to measure it.
- **Long outputs.** The app asks for a whole document in one call — DBS's answer
  alone is ~33k tokens, the largest seen ~42k. Train rows are capped at 30k
  tokens all-in, so their answers are far shorter. Test rows are whole on
  purpose: score truncation and recall on long documents there.
- **Labels vs pedoman v1.5.** An xlsx made before the latest prompt revisions
  can disagree with `extraction_system.md`, and the adapter learns the labels.
  A `*.gold.json` from `review-annotation` in the folder fixes that document.
