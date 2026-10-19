<div class="cover" markdown="1">
<div class="cover-kicker">PBBI · Perjanjian Baku Bank Indonesia</div>
<div class="cover-title">A purpose-built model extracts more than twice as many contract clauses as a general-purpose AI</div>
<div class="cover-sub">Results of the v0.1.3 clause-extraction model, compared with OpenAI gpt-4.1-mini on 17 previously unseen standard-form contracts</div>
<div class="cover-meta">Scalejade · October 2026</div>
</div>

<div class="page"></div>

## Executive summary

Bank Indonesia's supervisors (*Pengawas*) review the standard-form terms and conditions (*Perjanjian Baku*) that banks and payment providers issue to their customers. Every review starts the same way: the contract has to be broken down into its individual clauses, each with its article number, topic and exact wording. Only then can each clause be checked against consumer-protection rules.

We trained a dedicated model, **v0.1.3**, to do this first step, using contracts the supervisors had already broken down by hand. We then tested it against a leading general-purpose model, **OpenAI's gpt-4.1-mini**, on 17 real contracts that neither model had seen before.

<div class="takeaways" markdown="1">
**Key findings**

1. **The dedicated model finds 66 of every 100 clauses; the general-purpose model finds 28.** That is 2.3 times as many.
2. **It is also more accurate.** 78 of every 100 clauses it returns match the supervisors' version, against 63 for gpt-4.1-mini.
3. **It performs better on 13 of 17 contracts** and equally on 2.
4. **Its lead is largest on long contracts**, where it finds three times as many clauses. These are the documents where manual review is hardest.
5. **It captures 97% of the contract content.** The wording of 97 of every 100 clauses in the supervisors' version appears in the dedicated model's output. Only about 3 in 100 are missing altogether.
6. **The remaining gap is about where clauses are split, not missing content.** Of the 97 in 100 clauses whose wording is captured, 66 are split exactly as the supervisors split them. The rest are split differently, for example two clauses kept together. These differences are linked to inconsistencies in how the training contracts were labelled.
</div>

**Why it matters.** A clause that is not extracted is never reviewed. The dedicated model finds more clauses and leaves very little contract text out, which directly reduces the gaps in the supervisors' compliance review.

## The dedicated model outperforms the general-purpose model on every summary measure

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 1 · Overall results on 17 unseen contracts (2,074 clauses)</div>

| Measure | **Dedicated model (v0.1.3)** | General-purpose model (gpt-4.1-mini) |
|---|---|---|
| Clauses found, per 100 in the contract | **66** | 28 |
| Returned clauses that are correct, per 100 | **78** | 63 |
| Overall score (0–100) | **72** | 39 |
| Contracts where it performs better | **13** (2 equal) | 2 |
| Clauses returned, relative to the contract | **84%** | 45% |

<div class="source">Overall score combines the first two measures (F1 × 100). Both models received identical instructions and contracts and were set to give their most consistent answer. Source: Scalejade evaluation, October 2026.</div>
</div>

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 2 · Clauses found per 100 clauses in the contract</div>
<div class="bars">
  <div class="bar-row"><span class="bar-label">Dedicated model (v0.1.3)</span><span class="bar"><span class="fill ours" style="width:66%"></span></span><span class="bar-val"><b>66</b></span></div>
  <div class="bar-row"><span class="bar-label">General-purpose model (gpt-4.1-mini)</span><span class="bar"><span class="fill gpt" style="width:28%"></span></span><span class="bar-val">28</span></div>
</div>
<div class="source">Source: Scalejade evaluation, October 2026.</div>
</div>

## The advantage grows with contract length, where manual review is hardest

On short contracts both models do reasonably well. As contracts get longer, the general-purpose model increasingly merges clauses or stops part-way through the document. The dedicated model keeps the supervisors' level of detail.

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 3 · Clauses found per 100, by contract length</div>
<div class="bars">
  <div class="bar-group">Short · under 100 clauses (10 contracts)</div>
  <div class="bar-row"><span class="bar-label">Dedicated model</span><span class="bar"><span class="fill ours" style="width:80%"></span></span><span class="bar-val"><b>80</b></span></div>
  <div class="bar-row"><span class="bar-label">General-purpose model</span><span class="bar"><span class="fill gpt" style="width:47%"></span></span><span class="bar-val">47</span></div>
  <div class="bar-group">Medium · 100–199 clauses (3 contracts)</div>
  <div class="bar-row"><span class="bar-label">Dedicated model</span><span class="bar"><span class="fill ours" style="width:54%"></span></span><span class="bar-val"><b>54</b></span></div>
  <div class="bar-row"><span class="bar-label">General-purpose model</span><span class="bar"><span class="fill gpt" style="width:25%"></span></span><span class="bar-val">25</span></div>
  <div class="bar-group">Long · 200 clauses or more (4 contracts)</div>
  <div class="bar-row"><span class="bar-label">Dedicated model</span><span class="bar"><span class="fill ours" style="width:64%"></span></span><span class="bar-val"><b>64</b></span></div>
  <div class="bar-row"><span class="bar-label">General-purpose model</span><span class="bar"><span class="fill gpt" style="width:20%"></span></span><span class="bar-val">20</span></div>
</div>
<div class="source">Source: Scalejade evaluation, October 2026.</div>
</div>

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 4 · Where the general-purpose model stops early: four contracts</div>

| Contract | Clauses in the contract | Found by the general-purpose model | Found by the dedicated model |
|---|---|---|---|
| BJB Mobile Banking | 110 | 4 | **69** |
| Sinarmas E-money | 49 | 4 | **44** |
| OCBC Credit Card | 233 | 19 | **131** |
| SeaBank Mobile Banking | 358 | 42 | **247** |

<div class="source">In every case the general-purpose model ended its answer on its own, well within its output limit; it was not cut off. Source: Scalejade evaluation, October 2026.</div>
</div>

## The lead holds across products and provider types

The dedicated model scores higher for six of the eight product types and for all seven provider types. It is close behind on the other two products, each tested on one or two contracts.

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 5 · Overall score (0–100) by product</div>

| Product | Contracts tested | Dedicated model | General-purpose model |
|---|---|---|---|
| Debit cards | 3 | **94** | 76 |
| E-money (card-based) | 1 | 83 | **86** |
| Payment gateway | 1 | **77** | 33 |
| E-money (app-based) | 2 | **76** | 34 |
| Mobile banking | 5 | **75** | 36 |
| Credit cards | 2 | **68** | 23 |
| Internet banking | 2 | 51 | **53** |
| Mobile and internet banking | 1 | **42** | 32 |

<div class="source">Source: Scalejade evaluation, October 2026.</div>
</div>

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 6 · Overall score (0–100) by provider type</div>

| Provider type | Contracts tested | Dedicated model | General-purpose model |
|---|---|---|---|
| Major state-owned bank | 2 | **87** | 70 |
| Regional development bank | 2 | **84** | 75 |
| Major national private bank | 5 | **79** | 35 |
| National private company | 1 | **77** | 33 |
| Major non-bank e-money provider | 1 | **73** | 39 |
| Major regional development bank | 2 | **66** | 24 |
| Major foreign-owned bank | 4 | **59** | 36 |

<div class="source">Source: Scalejade evaluation, October 2026.</div>
</div>

## The remaining gap is about where clauses are split, not missing content

The dedicated model rarely loses text. **Fewer than 3 in every 100** of the supervisors' clauses are absent from its output altogether. Most of its errors come from splitting a passage at a different point than the supervisors did: several clauses kept together, or one clause divided in two.

The clearest example is **lists of definitions**. In some training contracts the supervisors grouped several definitions into one clause; in others each definition is its own clause. Because the examples point both ways, the model cannot learn a single rule. This explains its weakest result, OCBC Internet Banking, which is one of only two contracts where the general-purpose model scored higher.

<div class="callout" markdown="1">
**Implication.** The next improvements will come mainly from **consistent labelling** and **more labelled contracts**, not from changes to the model itself.
</div>

## How we trained the model

We did not build a language model from scratch. We started from one that already reads Indonesian well and **taught it this one task by example**, using the supervisors' own work.

**1. A strong foundation.** The starting point is **Qwen-SEA-LION**, an open model developed for Southeast Asian languages, including Indonesian. It already understands legal and banking language. What it lacks is the supervisors' way of breaking a contract into clauses.

**2. Learning from the supervisors' own work.** For each of 60 real contracts, the supervisors had already produced the breakdown we want: every clause with its article number, topic and exact wording. Each contract was prepared exactly as the production application reads it, so the model learns from the same text it will see in use.

**3. Teaching by example.** The model read each teaching contract alongside the supervisors' breakdown and adjusted itself, step by step, to produce breakdowns like the supervisors'. We added **a small specialised layer** on top of the foundation model and trained only that layer, about 0.3% of the model's size. The foundation's general knowledge of language stays intact, and the specialised layer can be updated or replaced on its own.

**4. Checking progress and keeping the best version.** Throughout training, the model was regularly tested on 4 contracts set aside for this purpose, which it never learned from. Only the version that scored best on these checks was kept.

**5. A final test on hidden contracts.** The released model was then tested on 17 contracts kept hidden throughout. Those are the results in this report.

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 7 · How the model was trained</div>
<div class="steps">
  <div class="step"><div class="step-n">1</div><div class="step-h">Foundation</div><div class="step-t">Open model that already reads Indonesian (Qwen-SEA-LION)</div></div>
  <div class="step"><div class="step-n">2</div><div class="step-h">Learning material</div><div class="step-t">60 contracts broken down by the supervisors</div></div>
  <div class="step"><div class="step-n">3</div><div class="step-h">Teach by example</div><div class="step-t">39 contracts; a small specialised layer learns the supervisors' method</div></div>
  <div class="step"><div class="step-n">4</div><div class="step-h">Check and keep the best</div><div class="step-t">4 contracts track progress; only the best version is kept</div></div>
  <div class="step"><div class="step-n">5</div><div class="step-h">Final test</div><div class="step-t">17 hidden contracts, compared with gpt-4.1-mini</div></div>
</div>
<div class="source">Source: Scalejade, October 2026.</div>
</div>

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 8 · The contract collection</div>

| Use | Contracts | Labelled clauses |
|---|---|---|
| Teaching the model | 39 | 4,381 |
| Checking progress during training | 4 | 435 |
| Final test (kept hidden until the end) | 17 | 2,074 |
| **Total** | **60** | **6,890** |

<div class="source">Contracts from over 40 banks and payment providers: mobile banking, internet banking, debit and credit cards, e-money, payment gateways and remittance. Every combination of provider type and product appears at least once in the teaching set. Source: Scalejade, October 2026.</div>
</div>

### What we learned along the way

- **Slow and steady learns better.** Our first attempt learned too fast. It began memorising the teaching contracts and got worse on the check contracts, so we stopped it. Teaching at a gentler pace, and keeping only the best-scoring version, fixed this.
- **One careful read is enough.** In each training run, the model performed best after reading each teaching contract about once. Reading them again only made it better at contracts it had already seen.
- **More examples help where they are added.** The latest version learned from 8 more contracts, mostly long mobile-banking and credit-card terms, and improved most on exactly those kinds of contracts.
- **Consistency matters more than volume.** Where the supervisors' examples disagree with each other, as with lists of definitions, extra examples do not help. The model needs one clear rule to follow.

## How the model was tested

**Tested fairly.** Both models received exactly the instructions and contracts the production application sends, and were set to give their single most consistent answer. Every answer was marked against the supervisors' own breakdown using the same rules. None of the 17 test contracts was used in training.

## Limitations

- **Sample size.** The test covers 17 contracts. Several products were tested on only one or two, so results per product are indicative.
- **Strict marking.** A clause split slightly differently from the supervisors' version counts as a miss, even when all its words are present. The model's practical usefulness is somewhat higher than its score suggests.
- **No tailoring of the general-purpose model.** gpt-4.1-mini received the same instructions as the dedicated model, with no examples or additional training. In a looser setting it scored somewhat higher (47 instead of 39), still well below the dedicated model.

## Recommendations

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 9 · Recommended next steps</div>

| # | Action | Owner | Expected impact |
|---|---|---|---|
| 1 | **Agree one labelling rule** for definitions and lists of sub-clauses, and apply it to existing contracts | Supervisors with engineering | The largest single gain in accuracy |
| 2 | **Complete validation of additional contracts**, prioritising e-money, payment gateways and foreign-owned banks | Supervisors | Higher scores on the weakest products |
| 3 | **Always request the model's most consistent answer** in the production application | Engineering | Repeatable, slightly more accurate results |
| 4 | **Put v0.1.3 into production use** | Engineering | Benefits reach the supervisors' review |
| 5 | **Repeat this test for every new version** before release | Engineering | Every improvement is measured |

</div>

## Conclusion

A model trained on the supervisors' own work clearly outperforms a leading general-purpose model at breaking standard-form contracts into clauses. **v0.1.3 finds more than twice as many clauses, is more often correct, and has its largest advantage on the long contracts where manual review is hardest.** With consistent labelling and a larger set of labelled contracts, we expect the remaining gap to the supervisors' own breakdown to narrow further.

## Attachment: the clause-by-clause comparison

The workbook **`pbbi-extraction-clauses-v0.1.3-vs-gpt-4.1-mini.xlsx`**, supplied with this report, shows exactly what each model produced for every clause of the 17 test contracts, next to the supervisors' own version.

<div class="exhibit" markdown="1">
<div class="exhibit-title">Exhibit 10 · What the attachment contains</div>

| Sheet | What it shows |
|---|---|
| **Ringkasan** | The overall results in this report, and a guide to reading the other sheets |
| **Per kontrak** | One line per contract: how many clauses each model found, how many were correct, and which model did better |
| **Perbandingan klausa** | One line per clause in the supervisors' version (article number, topic, wording), with the dedicated model's clause and the general-purpose model's clause beside it |
| **v0.1.3 (fine-tuned) (mentah)** | Everything the dedicated model produced, in its original order |
| **gpt-4.1-mini (mentah)** | Everything the general-purpose model produced, in its original order |

<div class="source">Colour key in <em>Perbandingan klausa</em>: <b>green</b> — the model's clause matches the supervisors' version; <b>red</b> — no match (the model's closest clause is shown, with how similar it is); <b>amber</b> — a clause the model produced that the supervisors did not have. Filters on every column allow a single contract or model to be reviewed.</div>
</div>

<div class="callout" markdown="1">
**Confidential.** The attachment quotes the contracts word for word. Share it only with those authorised to see the source contracts.
</div>

<div class="appendix" markdown="1">

**Appendix: technical reference**

- **Model.** `scalejade/pbbi-clause-extraction-lora` v0.1.3 (release `stable`), a LoRA adapter (r = 16) on Qwen-SEA-LION-v4.5-27B-IT.
- **Measures.** "Clauses found" = recall; "correct" = precision; "overall score" = F1 × 100.
- **Scores.** Both models at temperature 0:
  - v0.1.3: recall 0.658, precision 0.784, F1 0.716.
  - gpt-4.1-mini: recall 0.283, precision 0.632, F1 0.391 (F1 0.470 at its default temperature 1.0).
- **Matching rule.** A clause counts as found when it shares at least 80% of its words with a labelled clause, matched one to one.
- **Detailed technical reports:** `pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini`, `pbbi-extraction-eval-v0.1.3`.

</div>
