# TODO — this is a skeleton, not a working prompt.

The stage-2 system prompt does not exist anywhere in this repo. All four files in
`scratch/` (`[bca] - req - analysis.txt`, `[bca] - req - extraction.txt`,
`[jago] - req - analysis.tx`, `[jago] - req - extraction.txt`) carry the **same
extraction** system prompt — the "analysis" ones are mislabelled extraction requests.
Their `guided_json` / `json_schema` is even named `clause_extraction`.

Write the real compliance-scoring prompt here, then delete this notice.
`build_analysis_request.py` refuses to run quietly while the word TODO is present.

---

## What this prompt has to do

Stage 1 produced clauses. Stage 2 receives them as JSON and judges each one against
Bank Indonesia regulations. The user message will arrive as:

```
KLAUSA UNTUK DINILAI:
{
  "clauses": [
    { "pasal": "...", "topic": "...", "clause_text": "..." },
    ...
  ]
}
```

## What the prompt must specify

**The regulations.** Which BI rules apply, by number. This is the part no one else can
supply — it is the actual legal content, and it decides every verdict. Either inline
the relevant articles, or name them precisely enough that the model is not inventing
them. A model asked to score against regulations it has not been given will produce
confident citations that do not exist.

**The verdicts.** The output schema in `build_analysis_request.py` currently expects
`patuh` / `tidak_patuh` / `perlu_ditinjau`. Change both together if you want different
categories — the schema is enforced by `response_format`, so a prompt asking for
labels the schema forbids will fail the request, not degrade quietly.

**One result per input clause.** State that the output array must have exactly as many
entries as the input, in the same order, echoing `pasal` and `topic` verbatim. Without
this, silently dropped clauses look identical to clauses that passed.

**Citation discipline.** Every `tidak_patuh` needs a specific article in `dasar_hukum`.
"Melanggar ketentuan BI" is not a finding a legal team can act on.

**Refusal to guess.** Tell it to return `perlu_ditinjau` when the clause is ambiguous
or no supplied regulation clearly applies. The failure mode to design against is a
confident `patuh` on a clause nobody actually checked.

## Expected output

```json
{
  "results": [
    {
      "pasal": "I|1",
      "topic": "...",
      "status": "patuh | tidak_patuh | perlu_ditinjau",
      "dasar_hukum": "PBI No. .../PBI/20.. Pasal ..",
      "alasan": "..."
    }
  ]
}
```

## Budget

Measured on the BCA run: ~252 output tokens per scored clause, versus 120 at
extraction. Scoring roughly doubles a clause because it echoes the clause and adds a
verdict, a citation, and reasoning. If your prompt asks for longer reasoning, raise
`--per-clause` to match, or `max_tokens` will be set too low and the response will be
truncated with HTTP 200.
