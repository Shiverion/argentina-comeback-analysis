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

All runs ---------------------------------------------------------------> data/manifests/ and results/data_quality_report.json
```

## Source Policy

The pipeline uses three separate lanes, each with a different evidentiary role.

| Lane | Default source | Purpose | Limitation |
| --- | --- | --- | --- |
| Focal match evidence | FIFA Performance Summary | Confirmed score and counted-goal timeline | The PDF is not a complete event feed or a refereeing decision log. |
| Historical rarity baseline | Fjelstul World Cup Database | Match, goal, and booking records for men's World Cups through 2022 | Event timing is minute-resolution and its underlying source is documented by the database author. |
| Optional event enrichment | StatsBomb Open Data | High-resolution JSON for selected 2018 and 2022 World Cup matches | It is intentionally optional because coverage is selective and full download is larger. |
| Team strength | Pinned JGravier yearly Elo snapshot | Required for the historical match-state model | Uses the latest 31 December rating strictly before each match year; focal 2026 strength remains separate. |
| 2026 penalties | FIFA PMSR Set Plays tables | Descriptive penalties-awarded census through the Round of 16 | Different from historical penalty goals scored; never merge the two metrics. |

The Fjelstul database requires CC-BY-SA attribution. StatsBomb requires attribution when publishing work based on its Open Data. The pipeline stores the source URL, retrieval timestamp, checksum, and local path for every downloaded file.

## Run It

From the project root:

```powershell
uv sync
uv run --project . python -m research_etl run
```

The default run downloads the focal FIFA document and the compact historical World Cup tables, installs seed inputs into the manual-review lane without overwriting existing work, normalizes outputs, and writes a quality report.

Optional high-resolution source metadata:

```powershell
uv run --project . python -m research_etl run --with-statsbomb
```

Optional full event JSON download for the configured StatsBomb World Cup seasons:

```powershell
uv run --project . python -m research_etl extract --with-statsbomb-events
```

The full event option is deliberately separate from the ordinary run because it can download many JSON files. It is an enrichment source; it does not replace the broad historical baseline.

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
uv run --project . python -m research_etl run
```

Then execute the notebook from the project root or any nested directory. It resolves the project root by locating `Project.md` and `pyproject.toml`, so it does not create a second `data/` directory beside the notebook.
