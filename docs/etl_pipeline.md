# Research ETL Pipeline

`research_etl` is the reproducible data path for the Argentina-Egypt research notebook. It separates evidence collection from model-ready data, records source provenance, and blocks the win-probability model when an input is incomplete.

## What It Produces

```text
FIFA performance summary ----> data/raw/fifa/ --------------------------+
Versioned review templates --> data/raw/manual/ ------------------------+--> data/processed/focal_events.csv
                                                                        +--> data/processed/incidents.csv

Fjelstul World Cup data -----> data/raw/fjelstul/ --> normalized events +--> data/processed/historical_match_events.csv
                                                             snapshots  +--> data/processed/historical_snapshots.csv

Pinned yearly Elo source ----> data/raw/jgravier/ ---------------------+--> data/processed/pre_match_strength.csv
                                                                        +--> data/processed/model_frame.csv

Versioned PMSR census -------> data/raw/fifa/ ---------------------------> data/processed/pmsr_2026_team_penalties.csv

StatsBomb history cache --------> data/raw/statsbomb_history/ -------------> data/processed/statsbomb_historical_match_events.csv
                                                                             +--> data/processed/statsbomb_historical_snapshots.csv
                                                                             +--> data/processed/statsbomb_history_match_audit.csv

All runs ---------------------------------------------------------------> data/manifests/ and results/data_quality_report.json
```

## Source Policy

The pipeline uses three separate lanes, each with a different evidentiary role.

| Lane | Default source | Purpose | Limitation |
| --- | --- | --- | --- |
| Focal match evidence | FIFA Performance Summary | Confirmed score and counted-goal timeline | The PDF is not a complete event feed or a refereeing decision log. |
| Historical rarity baseline | Fjelstul World Cup Database | Match, goal, and booking records for men's World Cups through 2022 | Event timing is minute-resolution and its underlying source is documented by the database author. |
| Broader baseline | StatsBomb Open Data | Explicitly listed selected male senior club and non-World-Cup international releases | The sample is availability-selected; the raw event cache is large and is not committed. |
| Team strength | Pinned JGravier yearly Elo snapshot | Required for the historical match-state model | Uses the latest 31 December rating strictly before each match year; focal 2026 strength remains separate. |
| 2026 penalties | FIFA PMSR Set Plays tables | Descriptive penalties-awarded census through the Round of 16 | Different from historical penalty goals scored; never merge the two metrics. |

The Fjelstul database requires CC-BY-SA attribution. StatsBomb requires attribution when publishing work based on its Open Data. The pipeline stores the source URL, retrieval timestamp, checksum, and local path for every downloaded file.

## Run It

From the project root:

```powershell
uv sync --extra notebook --extra test
uv run --project . python -m research_etl run
```

The default run downloads the focal FIFA document and the compact historical World Cup tables, preserves committed broader-baseline artifacts, installs seed inputs into the manual-review lane without overwriting existing work, normalizes outputs, and writes a quality report.

Rebuild the broader baseline from the pinned StatsBomb source. This downloads the configured competition metadata and every match event stream into a local cache, then creates the compact event, snapshot, and audit tables:

```powershell
uv run --project . python -m research_etl run --with-statsbomb-history
```

The 53 competition-season pairs are explicit in `config/sources.json`; no discovery-by-current-API behavior is used. The raw cache is ignored by Git, while the compact outputs and their checksums are committed.

Optional high-resolution source metadata for the separate World Cup enrichment lane:

```powershell
uv run --project . python -m research_etl extract --with-statsbomb-events
```

The World Cup event option is deliberately separate from the broader-baseline run because it downloads a different configured source lane.

## Manual Review Inputs

After the first run, review these files before using counterfactual results:

```text
data/raw/manual/focal_events_reviewed.csv
data/raw/manual/incidents_reviewed.csv
```

`focal_events_reviewed.csv` begins with five confirmed goals and Messi's saved penalty. Add only source-linked event records and preserve score transitions. `incidents_reviewed.csv` begins with reported claims. These claims may enter only configured scenario-only sensitivity until a future correctness-review phase is activated.

Historical strength is derived automatically from the pinned source. The canonical processed columns are:

```text
match_id,team,elo_rating,fifa_rank,pre_match_win_odds,source_name,as_of_date
```

The pipeline creates `model_frame.csv` only when every historical match has both teams covered, every `elo_rating` is numeric, and each source date is strictly before the match year. Team aliases are explicit in `config/sources.json`.

## Quality Gates

`validate` writes `data/processed/data_quality_report.json` and `results/data_quality_report.json`. It checks:

- Required columns and controlled incident statuses.
- Focal event uniqueness, chronology, legal score transitions, and the 3-2 reconciliation.
- Historical event keys, chronological order, score monotonicity, and regulation-period scope.
- One historical snapshot per match and registered threshold.
- StatsBomb history census by tier, duplicate keys, pinned source version, exact threshold coverage, metadata score reconciliation, and extra-time exceptions.
- Model-frame readiness, strength key uniqueness, numeric Elo ratings, and coverage of both teams in every match.

Run it independently after manual changes:

```powershell
uv run --project . python -m research_etl validate
uv run --project . python -m research_etl status
```

Warnings are intentional gates, not silent fallbacks. Reported incidents may enter only the explicitly labelled scenario-only sensitivity lane; they remain unavailable for decision-correctness conclusions.

`run --force` re-downloads external sources but never resets human-reviewed CSVs. Only `init --force` may deliberately restore versioned manual seeds.

## Notebook Integration

The companion notebook reads `data/processed/` and the pipeline's run manifest. Run the pipeline before opening the modelling sections:

```powershell
uv run --project . python -m research_etl run --with-statsbomb-history
```

Then execute the notebook from the project root or any nested directory. It resolves the project root by locating `Project.md` and `pyproject.toml`, so it does not create a second `data/` directory beside the notebook.

## Opportunity-Adjusted Analysis Lane

The opportunity-adjusted officiating analysis is separate from the Argentina-Egypt case-study notebook. It uses compact, team-match feature panels and does not pool club, non-World-Cup international, World Cup, and 2026 FIFA PMSR populations into one estimate.

Build the first two panels (2018/2022 World Cup event features plus all 96 official 2026 PMSR match summaries):

```powershell
uv run --project . python -m research_etl opportunity --with-statsbomb-world-cup --with-pmsr-2026
```

The command writes `statsbomb_world_cup_opportunity_features.csv` and `pmsr_2026_match_features.csv` to `data/processed/`, then validates their team-match grain and reconciliation checks. The PMSR command fetches unvendored reports in memory and preserves their exact per-match source URLs in the compact output.

Build the separate 2,379-match StatsBomb club/non-World-Cup-international panel only when the larger source cache is required:

```powershell
uv run --project . python -m research_etl opportunity --with-statsbomb-history
```

This broader download is intentionally explicit because the raw event cache is several GB. Its `club` and `intl` rows are available for mechanism validation, not for a combined FIFA-officiating estimate.

Build the time-aware pre-decision panels and hazard outputs from the same pinned
event cache:

```powershell
uv run --project . python -m research_etl opportunity --with-statsbomb-temporal
```

This writes one row per team and five-minute window to
`data/processed/statsbomb_history_temporal_features.csv` and
`data/processed/statsbomb_world_cup_temporal_features.csv`. The predictors use
only events before each window; penalty events inside the window are labels.
The command writes grouped out-of-fold predictions, coefficients, a chart, and
`results/temporal_analysis_manifest.json`. It also writes formal correlation
tests, the Notebook 1 bridge model, penalty win-probability sensitivities, and
robustness comparisons under `results/`. Use `--all` to rebuild the original
opportunity panels, PMSR panel, and linked lanes together.

Build the comeback-path classification and the linked Egypt 0-3 branches from
the cached history and existing bridge predictions:

```powershell
uv run --project . python -m research_etl comeback-path --with-counterfactual
```

This writes `results/comeback_path_cases.csv` and
`results/comeback_path_summary.csv`. The primary clean-path cutoff is 79:00,
with 70, 75, 78, and 80 included for sensitivity. The focal Argentina row is
stored separately and excluded from historical denominators. The command also
writes `results/comeback_counterfactual.csv`: its fixed branch changes only
the score state in out-of-fold bridge predictions, while its adaptive branch
reports historical three-goal-deficit support and Wilson bounds without
pretending to identify tactical adaptation.

`results/comeback_path_summary.csv` also contains outcome-independent recovery
metrics: penalty goals while exactly two goals down, penalty equalizers,
open-play equalizers, and all equalizers. These metrics include teams that
eventually drew or lost; they are not restricted to final comebacks.

The command also writes `results/penalty_sequence_summary.csv`. This performs
a second, all-minute regulation-time scan: two same-team penalty-shot events
within a rolling 10-minute interval, and two penalty goals within that
interval. It must be interpreted separately from the late two-goal-deficit
cohort because the full-match scan includes ordinary score states.
