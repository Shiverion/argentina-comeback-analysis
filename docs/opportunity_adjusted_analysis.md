# Opportunity-Adjusted Officiating Analysis

## Purpose

This companion analysis asks whether differences in penalties, fouls, and cards
remain after accounting for measurable attacking opportunity. It complements
the Argentina-Egypt comeback case study; it does not replace its estimands or
turn descriptive event data into a finding of decision correctness, bias, or
intent.

## Estimands

The analysis separates three questions that must not be conflated:

1. **Raw outcome rate:** Which teams receive more penalty kicks, cards, or
   fouls in the observed sample?
2. **Opportunity-adjusted association:** Conditional on pre-specified attacking
   opportunity proxies, which teams have more observed penalty-kick outcomes
   than an out-of-fold model predicts?
3. **Decision correctness or bias:** Whether comparable potential incidents
   were decided differently. This is not identified by the current event
   feeds. It needs a complete denominator of potential box incidents plus
   decision/video evidence under the project's existing evidence protocol.

An opportunity-adjusted residual is an unexplained association, not proof of
preferential officiating.

## Source Lanes

| Lane | Unit | Outcome | Exposure variables | Role |
| --- | --- | --- | --- | --- |
| FIFA PMSR 2026 | Team-match, 96 matches | Official penalties awarded | Possession, xG, attempts, final-third receptions, passing/progression statistics | Official current-tournament descriptive lane |
| StatsBomb World Cup 2018/2022 | Team-match, 128 matches | Regulation penalty kicks (`penalty_shots`) | Pass/carry entries into the box, completed box receipts, non-penalty xG, shots in the box, fouls/cards | Contemporary World Cup event lane |
| StatsBomb history | Team-match, selected club and non-World-Cup international matches | Regulation penalty kicks (`penalty_shots`) | Same event-derived exposure features | Larger mechanism-validation lane |

The lanes are never pooled into a single estimate. Club football can test
whether opportunity variables generally move with penalty outcomes; it cannot
identify FIFA-specific officiating. Non-World-Cup international and World Cup
results remain separate because their selection and competition contexts differ.

## Variable Rules

### Outcomes

- `penalties_awarded`: official FIFA PMSR count, including scored, saved, and
  missed kicks.
- `penalty_shots`: a StatsBomb event proxy for regulation penalty kicks. It is
  not silently treated as identical to an official award count.
- `fouls_committed`, `fouls_suffered`, `yellow_cards`, `second_yellows`, and
  `send_offs`: separate outcomes or descriptive covariates, never collapsed
  into a single disciplinary index.

### Opportunity Features

Primary features are spatial or chance-quality measures, not possession alone:

- `box_entries`: passes/carries that enter the opponent penalty area.
- `box_receipts`: completed ball receipts in the opponent penalty area.
- `non_penalty_xg`: chance quality excluding penalties.
- `non_penalty_shots_in_box`: shots started in the penalty area excluding
  penalty kicks.

PMSR possession preserves the report's contested-possession share. Team
controlled-possession percentages are not forced to sum to 100 without that
third component. StatsBomb `possession_sequence_share` is an event-sequence
share, not an official possession-time measure.

### Deferred Controls

Pre-decision score state, strength difference, referee assignment, and recent
attacking exposure must be measured before the decision event. They are not
included in the initial team-match residual model until a time-aware feature
panel is available. Final-match cards, fouls, and score-dependent statistics
are not inserted as controls because they may be affected by the outcome.

## Time-Aware Extension

The temporal lane now creates one row per team and five-minute window from the
raw event streams. Features are strictly pre-window: score state, red cards,
recent box entries and receipts, recent non-penalty xG, fouls, yellow cards,
and event-derived possession sequence counts. The next-window label is whether
the team has a `penalty_shots` event in that window. Events inside the outcome
window are never used as predictors.

The hazard model is a match-grouped, five-fold out-of-fold logistic model. It
is fit separately for the 2,193 selected club matches, 186 non-World-Cup
international matches, and the 128 World Cup matches. It is compared with the
observed panel-wide event rate using log loss and Brier score. A model that
beats that null baseline only shows that pre-window context contains
predictive information; it does not establish decision correctness, bias, or
intent.

The temporal outputs are `data/processed/*_temporal_features.csv`,
`results/temporal_analysis_manifest.json`, and the out-of-fold prediction and
coefficient tables under `results/`. The notebook exposes the executed model
comparison and the club hazard chart.

## Linked Notebook 1 Bridge

The bridge lane connects the temporal opportunity panel to Notebook 1's
regulation-result estimand. It compares four match-grouped, out-of-fold
multiclass models for each population:

1. `state_only`: time, score difference, red-card state, and home indicator.
2. `spatial_augmented`: state plus box entries, box receipts, non-penalty xG,
   and final-third entries.
3. `possession_augmented`: spatial model plus recent event-derived possession
   sequences.
4. `opportunity_augmented`: possession model plus recent fouls, cards, and
   opponent attacking exposure.

The linked counterfactual changes only `goal_diff_pre` by one goal. It reports
the modelled change in regulation-win probability if a penalty were scored for
the team or for its opponent. A saved penalty is represented by the observed
state, so the result is an immediate score-state sensitivity and not a full
tactical or psychological simulation.

The bridge writes `results/bridge_model_skill.csv`,
`results/bridge_penalty_win_impact.csv`,
`results/bridge_analysis_manifest.json`, and charts 12-13. It does not apply
the opportunity covariates to the 2026 focal probability because the focal
match lacks the same pre-window event-level feed.

## Initial Models

1. Clustered Spearman association between attacking opportunity and the penalty
   outcome, resampling whole matches rather than individual team rows.
2. Match-grouped, five-fold out-of-fold Poisson model with only `box_entries`
   and `non_penalty_xg` as pre-specified partial-adjustment features.
3. Team-level residual table: observed outcome minus out-of-fold expected
   outcome. Argentina is interpreted alongside every team, not selected as the
   only focal residual.

The model has a hard minimum of 40 team-match rows, 10 matches, and 10 nonzero
outcomes. It is explicitly exploratory until score-state, strength, and
referee/time controls are added.

## Publication Gates

- Exactly two teams per match and no duplicate team-match rows.
- Non-negative count metrics and full source provenance.
- PMSR 2026: all 96 reports, 192 team rows, possession balance, and penalty
  reconciliation to the canonical aggregate.
- StatsBomb: pinned commit, two rows per match, and internal bounds such as
  `penalty_fouls_won <= fouls_suffered`.
- Temporal panels: two team rows per match-window, no duplicate keys, signed
  score difference reconciles to its component scores, and outcome labels
  reconcile to their underlying event counts.
- No pooled FIFA, club, and international estimate.
- Articles use only validated notebook outputs and state the outcome definition,
  sample, and remaining decision-level evidence gap.
- Correlation inference records a whole-match permutation p-value, a 95%
  match-cluster bootstrap interval, and a Benjamini-Hochberg q-value across the
  registered correlation family.
