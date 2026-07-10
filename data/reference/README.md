# Reference Inputs

These files are version-controlled seed inputs for the ETL pipeline.

- `focal_events_seed.csv` contains the five counted goals plus Messi's saved minute-20 penalty documented in the FIFA performance summary. It remains a partial event timeline, not a substitute for a full licensed event feed.
- `incidents_seed.csv` preserves the three current public claims as `reported` or `unresolved`. Scenario-only sensitivity may use explicit timing assumptions without assessing whether a decision was correct.
- `pmsr_2026_set_plays_extracted.csv` is the compact, source-linked 96-match PMSR census used to reproduce the 2026 team penalty table without vendoring roughly 500 MB of PDFs.
- `pre_match_strength_template.csv` is retained only as a legacy template. The standard ETL now derives complete strength coverage from the pinned JGravier yearly Elo source.
