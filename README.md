# Argentina Comeback Analysis

**How rare was Argentina's 3-2 comeback win over Egypt (0-2 down with ~10 minutes left) in the 2026 FIFA World Cup Round of 16 — and does the evidence support the "Argentina is FIFA's golden child" narrative?**

A reproducible, evidence-tiered statistical and counterfactual research project. Every claim is source-linked, every probability is reported with its sample size and uncertainty interval, and every officiating-related result is explicitly labelled conditional/exploratory rather than a finding of bias — see [`Project.md`](Project.md) for the full research contract and evidentiary rules this project holds itself to.

## Start here

- **[`results/analysis_report.md`](results/analysis_report.md)** — the full write-up with all charts, numbers, denominators, and caveats. Start here if you want the findings without running any code.
- **[`article/argentina-comeback-golden-child-updated-v3.pdf`](article/argentina-comeback-golden-child-updated-v3.pdf)** — the latest designed Indonesian article edition, including the direct two-penalty sequence test.
- **[`article/argentina-comeback-golden-child-en-updated-v2.pdf`](article/argentina-comeback-golden-child-en-updated-v2.pdf)** — the matching latest English article edition.
- **[`output/jupyter-notebook/argentina_egypt_comeback_analysis.ipynb`](output/jupyter-notebook/argentina_egypt_comeback_analysis.ipynb)** — the executable notebook. Runs top-to-bottom from a clean kernel against the data already committed in this repo.
- **[`output/jupyter-notebook/opportunity_adjusted_officiating_analysis.ipynb`](output/jupyter-notebook/opportunity_adjusted_officiating_analysis.ipynb)** — the separate opportunity-adjusted analysis of penalties, attacking exposure, fouls, and cards.
- **[`article/argentina-opportunity-adjusted-analysis.pdf`](article/argentina-opportunity-adjusted-analysis.pdf)** — the Indonesian companion article for the opportunity-adjusted findings.
- **[`article/argentina-opportunity-adjusted-analysis-updated.pdf`](article/argentina-opportunity-adjusted-analysis-updated.pdf)** — the latest Indonesian article including formal inference and the Notebook 1 bridge analysis.
- **[`article/argentina-opportunity-adjusted-analysis-en.pdf`](article/argentina-opportunity-adjusted-analysis-en.pdf)** — the English companion article for the opportunity-adjusted findings.
- **[`results/temporal_analysis_manifest.json`](results/temporal_analysis_manifest.json)** — the executed five-minute pre-decision hazard analysis across the separate StatsBomb panels.
- **[`results/bridge_analysis_manifest.json`](results/bridge_analysis_manifest.json)** — the linked state/opportunity model comparison and score-state penalty sensitivity analysis.
- **[`results/comeback_path_summary.csv`](results/comeback_path_summary.csv)** — clean-versus-penalty-assisted comeback classification, with 70/75/78/79/80 minute sensitivity.
- **[`results/comeback_counterfactual.csv`](results/comeback_counterfactual.csv)** — fixed 0-3 score-state sensitivity and the low-support adaptive historical branch.
- **[`Project.md`](Project.md)** — the research specification: estimands, evidence tiers, bias controls, and the interpretation rules every result in this repo follows.

## What's in this repo

| Path | Contents |
| --- | --- |
| `data/raw/` | Vendored source data: FIFA Performance Summary PDFs (focal match + Argentina's 2026 matches), Fjelstul World Cup Database (1930-2022), JGravier Elo ratings |
| `data/processed/` | Canonical, notebook-ready tables produced by the ETL pipeline, including the compact StatsBomb-derived club/international event and snapshot tables (2,379 matches, extracted from StatsBomb Open Data — see `config/sources.json:statsbomb_history`) |
| `data/reference/` | Small, version-controlled seed inputs (manual review templates and compact source-linked extracts) |
| `src/research_etl/` | The ETL/analysis package: extraction, transformation, quality gates, counterfactual simulation, discipline statistics, model validation |
| `tests/` | Test suite (`pytest`) covering every analytical module |
| `results/` | Generated analysis outputs: the write-up, charts, and machine-readable result tables |
| `config/sources.json` | Full data provenance — URLs, pinned commits, license notes, extraction methodology for every source |

## Reproducing the analysis

```powershell
uv sync --extra notebook --extra test
uv run --project . python -m research_etl run --with-statsbomb-history  # includes the pinned broader-baseline cache
uv run --project . python -m research_etl opportunity --all
uv run --project . python -m research_etl comeback-path --with-counterfactual
uv run --project . --extra notebook jupyter execute output/jupyter-notebook/argentina_egypt_comeback_analysis.ipynb
uv run --project . --extra notebook jupyter execute output/jupyter-notebook/opportunity_adjusted_officiating_analysis.ipynb
uv run --with playwright python article/generate_article.py
uv run --with playwright python article/generate_article_english.py
uv run --project . python article/generate_opportunity_article.py
uv run --project . python article/generate_opportunity_article_english.py
uv run --project . --extra test pytest
```

## Headline findings (see the [full report](results/analysis_report.md) for denominators, methods, and caveats)

- **Zero** comparable two-goal, late-game comebacks in 964 men's World Cup matches (1930-2022) at any pre-registered threshold minute — robust across four different era slices, and cross-checked against a selected 2,193-match club-football sample (2 comebacks found — a ~1-in-300-to-1-in-700 rate, still solidly rare, not literally zero).
- Argentina's own modelled win probability while 0-2 down is genuinely uncertain: two legitimate estimation methods disagree by an order of magnitude in the 66'-80' window, both reported rather than cherry-picked — though the World-Cup-only numbers agree with the selected club-football cross-check within ~1 percentage point through minute 82.
- A conditional (non-decision-correctness) sensitivity check shows a disputed disallowed goal would have been a materially meaningful (3-5 percentage point) swing — explicitly not a claim the officiating decision was wrong.
- Argentina's elevated penalty/card rates in 2022 and its penalty-awarded lead in 2026 are real, descriptive, and directionally consistent — but not unique to 2022 (1958, 1982, 1990 show equal-or-higher rates on the same metrics) and not adjusted for the confounds (possession, playing style, opponent quality) that would be required to call this evidence of bias.
- The new five-minute hazard panel covers 2,379 selected StatsBomb matches and uses only pre-window score, spatial attack, foul/card, and event-derived possession features. The club model improves grouped out-of-fold log loss over the null rate (0.0294 vs 0.0309), but this is mechanism evidence, not a finding of officiating bias or decision correctness.
- Formal correlation inference now uses whole-match permutation p-values, match-cluster bootstrap intervals, and Benjamini-Hochberg q-values. The bridge model compares state-only versus opportunity-augmented final-result probabilities and estimates immediate penalty score-state sensitivity without claiming that a decision was correct or biased.
- The comeback-path scan found 2 clean club comebacks from a two-goal deficit at 70' (2/703, 0 penalty-assisted by own shot), no such comeback at the strict 79' cutoff (0/759), and no case with three own penalty shots after the cutoff in the selected StatsBomb sample. The focal Argentina case is clean after 70' and after 79', but at 79' the score was already 1-2 after Romero's 78' goal.
- Without conditioning on a final win, the scan found 2 penalty equalizers versus 19 open-play equalizers among 21 club equalizations at the 70' cutoff; at 79' it found 1 penalty equalizer versus 9 open-play equalizers among 10 equalizations.
- No eligible late two-goal-deficit state in the registered 70/75/78/79/80' cohorts had two same-team penalty-shot events within 10 minutes. The full all-minute club scan did find 8/2,193 such matches, including 5/2,193 with two penalty goals, so the claim is "no relevant late-state analogue," not "never in football history."
- The linked 0-3 counterfactual lowers mean modelled win probability from 0.46% to 0.04% in the club score-state branch and from 0.80% to 0.09% in the World Cup branch. The adaptive branch remains extrapolative because only 75 selected club matches reached a three-goal deficit in the 50'-70' window, with zero wins.

## Data sources and licensing

See [`config/sources.json`](config/sources.json) for the complete provenance record (source URLs, retrieval dates, pinned commits, and license notes) of every dataset used. Historical data is from the [Fjelstul World Cup Database](https://github.com/jfjelstul/worldcup) (CC-BY-SA-4.0) and [JGravier/soccer-elo](https://github.com/JGravier/soccer-elo) (CC-BY-4.0); focal-match and 2026 tournament data is drawn from official FIFA Performance Summary Reports (Tier A).
