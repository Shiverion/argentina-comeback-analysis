# How Rare Was Argentina's Comeback Against Egypt?

## A statistical and counterfactual analysis of a 2026 World Cup Round of 16 match

**Status:** Active exploratory analysis. Historical rarity and a scenario-only timing sensitivity are implemented. Decision correctness remains `not_assessed`; the calibrated secondary model passes the current engineering gate, while sparse focal-state predictions remain support-limited.

The calibrated secondary model now passes the engineering gate, but focal probabilities remain exploratory where the combination of time, score deficit, and strength advantage has fewer than the configured number of nearby historical matches. Passing global calibration is not sufficient evidence for a sparse focal state.

**Scope:** Argentina 3-2 Egypt, FIFA World Cup 2026 Round of 16, Atlanta Stadium, 7 July 2026.

---

## 1. Purpose

This project has two related objectives:

1. Estimate how unusual Argentina's regulation-time win was after Egypt established a two-goal lead late in the match.
2. Estimate how sensitive Argentina's chance of winning was to specific, documented officiating decisions under transparent counterfactual assumptions.

The central question is not whether the match "felt rigged." It is whether a well-specified alternative decision would have produced a materially different distribution of match outcomes. Statistical rarity, disagreement with a decision, and proof of intent are different claims and must remain separate throughout the analysis.

---

## 2. Factual Baseline and Claim Register

### 2.1 Verified match record

The initial factual record should be built from official material before any model is fitted. The FIFA performance summary records the final score as Argentina 3-2 Egypt and lists the five scored goals at 14, 66, 78, 82, and 91 minutes. The CAF match report describes Egypt's 2-0 lead and Argentina's three-goal late recovery.

| Item | Working record | Evidence status |
| --- | --- | --- |
| Match result | Argentina 3-2 Egypt | Official performance summary |
| Egypt's first goal | 14th minute, Yasser Ibrahim | Official performance summary |
| Egypt's second counted goal | 66th minute, Mostafa Zico | Official performance summary |
| Argentina's goals | 78th, 82nd, and 91st minutes | Official performance summary |
| Disallowed Egypt effort | Reported while Egypt led 1-0, before the counted 66th-minute goal | Requires event-feed and video verification |
| Egypt penalty appeals before the winner | Publicly reported claims | Requires event-feed, video, and Laws-of-the-Game review |

The original draft treated the disallowed Egyptian effort as if allowing it would have made the score 3-0. That is not the appropriate immediate counterfactual. Reporting places the disallowed effort while Egypt led 1-0; if the incident is validated, the immediate alternative state is 0-2. Egypt's later counted goal created the observed 0-2 scoreline.

### 2.2 Source hierarchy

The notebook must retain a URL, retrieval date, source tier, and confidence flag for every material assertion.

1. **Tier A - official match evidence:** FIFA performance summary, final match report, official event feed, referee report, and VAR report or audio if released.
2. **Tier B - primary visual evidence:** full-match video and time-aligned broadcast footage.
3. **Tier C - independent technical review:** documented analysis by qualified refereeing specialists that cites the Laws of the Game.
4. **Tier D - reporting and reactions:** federation statements, player or coach comments, and reputable reporting. These identify claims but do not establish decision correctness.
5. **Tier E - public reaction:** social media and fan discussion. These may describe the controversy but are not analytical evidence.

Initial reference points:

- [FIFA Performance Summary, Match 95](https://www.fifatrainingcentre.com/media/native/tournaments/fifa-world-cup/2026/PMSR-M95-ARG-V-EGY.pdf)
- [CAF match report](https://www.cafonline.com/fifa-world-cup/news/brave-egypt-fall-just-short-as-argentina-stage-dramatic-comeback-to-reach-world-cup-quarter-finals/)
- [Reuters/AFP reporting on Egypt's allegations](https://www.aljazeera.com/sports/2026/7/7/egypt-were-cheated-in-world-cup-loss-to-argentina-coach-hassan-says)
- [Independent decision-by-decision discussion](https://www.thenationalnews.com/sport/world-cup-2026/2026/07/08/are-egypt-right-to-blame-officials-and-fifa-for-their-world-cup-exit/)

### 2.3 Claim handling rule

Every disputed incident is represented as a claim with a status, not as a pre-decided advantage. The notebook will distinguish:

- **Observed decision:** what the referee and VAR actually decided.
- **Decision correctness:** whether the decision agrees with the Laws of the Game. This requires video and expert review.
- **Decision direction:** which team would benefit from a proposed alternative.
- **Decision impact:** the modelled outcome difference between the observed and alternative match states.

No claim moves from "reported" to "validated" without a source and a reproducible timestamp.

---

## 3. Research Questions

### Historical rarity

1. Among comparable World Cup matches, how often does a team trailing by two or more goals at 70, 75, 78, and 80 minutes win in regulation time?
2. How does that frequency change after accounting for pre-match team strength, tournament stage, red-card balance, and score differential?
3. Where does Argentina's observed state rank within the distribution of comparable historical match states?

### Match-state probability

4. What were Argentina's probabilities of a regulation win, draw, and regulation loss at the observed 0-2 state and after each counted goal?
5. How well calibrated is the model on held-out tournaments and match-level groups?
6. How sensitive are estimates to the choice of historical sample and model class?

### Officiating counterfactuals

7. Which disputed incidents pass the evidence threshold for a defined alternate state?
8. Conditional on each alternate state, how much does Argentina's regulation-win probability change?
9. Do the results stay directionally consistent over defensible assumptions about timing, penalty conversion, and team strength?

### Interpretation

10. Does the evidence support only a rare comeback, a material outcome sensitivity, or a reproducible one-sided pattern of validated high-leverage decisions?
11. What evidence would be required before making any claim about deliberate manipulation?

---

## 4. Scope Boundaries

This study can estimate historical frequency, model match-state outcome probabilities, and report sensitivity to stated alternate decisions. It cannot infer a referee's intent, FIFA's intent, corruption, or match manipulation from public event data alone.

The project will not:

- Treat a low-probability event as evidence of manipulation.
- Treat a complaint, viral clip, or card count as proof that a decision was wrong.
- Add decision-level impacts as if they were independent causal effects.
- Convert an unverified no-call into a certain penalty goal.
- Present a counterfactual simulation as a replay of the actual later goals and tactics.

---

## 5. Definitions and Estimands

### 5.1 Outcome definitions

The primary outcome is **regulation-time result**: Argentina win, draw, or Egypt win at the end of regulation plus stoppage time. This avoids mixing a match-state comeback with extra time or penalty-shootout advancement.

The secondary outcome is **advancement probability** for knockout matches. It may be estimated only when the historical data identifies extra-time and shootout outcomes.

### 5.2 Historical rarity estimand

For a fixed threshold `t`, reconstruct the score at exactly `t:00` for every eligible match and estimate:

```text
P(regulation win | goal_difference <= -2 at t, competition and sample restrictions)
```

Each match contributes at most one observation for each threshold. This prevents matches with long spells in the same scoreline from being over-weighted. The analysis will report the denominator, numerator, a match-clustered bootstrap confidence interval, and all inclusion rules.

### 5.3 Match-state probability estimand

For state `s` at time `t`, estimate:

```text
P(regulation result in {Argentina win, draw, Egypt win} | s, pre-match strength, context)
```

The state contains elapsed seconds, score difference, red-card difference, stage, neutral-site flag, and pre-match strength differential. Event-pressure features may be added only when they are consistently available for both the focal and historical matches.

### 5.4 Decision-impact estimand

For an incident with observed post-decision state `s_actual` and a validated alternate state `s_alt` at the same event time:

```text
Impact_ARG = P(ARG regulation win | s_actual) - P(ARG regulation win | s_alt)
```

Results are reported in probability points, with uncertainty intervals and a sensitivity table. The sign describes the modelled advantage of the observed state, not the correctness or intention behind the call.

### 5.5 No aggregate "Refereeing Advantage Index"

The original draft proposed summing decision impacts. That is not a valid primary estimand because decisions can share a time window, alter later match states, and interact with each other. The project will instead publish an incident ledger and separate joint scenarios. A descriptive net total may be shown only if it is clearly labelled non-causal and avoids overlapping scenarios.

---

## 6. Data Contract

The analysis should not run on undocumented hand-entered facts. Data files live under `data/raw/`, derived data under `data/processed/`, and model artefacts under `results/`.

### 6.1 Focal event data: `data/raw/focal_events.csv`

Required fields:

```text
match_id,event_id,period,minute,second,elapsed_seconds,team,event_type,outcome,
score_argentina,score_egypt,player,source_url,source_tier,verified,notes
```

Rules:

- Use elapsed seconds rather than a display-minute string for modelling.
- Scores must describe the state after the event when `outcome=confirmed`.
- A disallowed goal remains an event, but must not change the observed score.
- Every score-changing event must reconcile with the final 3-2 score.

### 6.2 Incident register: `data/raw/incidents.csv`

Required fields:

```text
incident_id,event_id,elapsed_seconds,claim,actual_decision,alternate_decision,
actual_state,alternate_state,beneficiary_if_alternate,law_reference,
evidence_status,source_urls,reviewer_a,reviewer_b,review_notes
```

`evidence_status` is one of `reported`, `video_reviewed`, `officially_confirmed`, `unresolved`, or `excluded`. An unresolved incident cannot enter correctness-assessed analysis. A reported incident may enter only a separately labelled scenario-only sensitivity with explicit timing and state assumptions.

### 6.3 Historical event data: `data/raw/historical_match_events.csv`

Required fields:

```text
match_id,tournament,year,stage,period,elapsed_seconds,home_team,away_team,
event_team,event_type,outcome,home_score,away_score,home_red_cards,away_red_cards,
is_neutral,source_name,source_version
```

Coverage must be documented before inference. The baseline analysis should use men's senior international matches with complete regulation-time event timelines. World Cup-only estimates are a clearly labelled smaller-sample subset, not the sole training dataset.

### 6.4 Pre-match strength data: `data/raw/pre_match_strength.csv`

Required fields:

```text
match_id,team,elo_rating,fifa_rank,pre_match_win_odds,source_name,as_of_date
```

Choose one strength representation for the primary model, freeze it before fitting, and retain alternatives for sensitivity checks. Never use ratings or odds published after kickoff.

### 6.5 ETL implementation and run contract

The data contract is implemented by the local `research_etl` package. It preserves external evidence under `data/raw/`, writes canonical notebook inputs under `data/processed/`, records checksums and retrieval metadata under `data/manifests/`, and writes data-quality results to `results/data_quality_report.json`.

```text
FIFA performance summary + manual review inputs -> focal_events.csv + incidents.csv
Fjelstul World Cup match, goal, and booking tables -> historical_match_events.csv + historical_snapshots.csv
Pre-match ratings or odds -> pre_match_strength.csv + model_frame.csv (only after complete coverage)
```

Run the standard pipeline from the project root:

```powershell
uv sync
uv run --project . python -m research_etl run
```

The standard run derives complete historical strength from a pinned yearly Elo source. Reported incidents remain excluded from correctness-assessed analysis, but an explicitly conditional scenario-only lane may evaluate a documented timing grid without claiming that the alternate decision was correct.

---

## 7. Analysis Plan

### 7.1 Stage A: provenance and quality control

1. Build the focal event timeline from the Tier A source.
2. Reconcile every reported incident against the event feed and time-aligned video.
3. Record discrepancies rather than silently choosing a preferred source.
4. Validate unique event IDs, chronological order, legal score transitions, periods, and final score.
5. Freeze a versioned analysis dataset and generate a source manifest with checksums where licensing permits.

### 7.2 Stage B: empirical historical baseline

1. Reconstruct a single state at each predefined threshold for every match.
2. Restrict the primary analysis to regulation time and a documented competition set.
3. Calculate comeback frequency, Wilson or bootstrap intervals, and the raw number of matches.
4. Report both a broad international baseline and a World Cup-only subset.
5. Do not claim an extreme outlier from a small denominator without showing the interval.

### 7.3 Stage C: calibrated win-probability model

Use a simple, interpretable baseline before a flexible model:

- **Baseline:** multinomial logistic regression using elapsed time, score difference, pre-match strength difference, stage, and red-card difference.
- **Secondary model:** calibrated gradient boosting or a time-varying Poisson scoring model.
- **Validation:** tournament-grouped and chronological held-out splits; no observations from the same match in both training and test data.
- **Diagnostics:** log loss, Brier score, calibration curve, class balance, and reliability by late-game score state.

The notebook will not present match-specific probabilities until the model meets predeclared calibration requirements on held-out data. If the historical sample is too small, the result remains exploratory.

### 7.4 Stage D: incident-level counterfactuals

Each validated scenario starts at the incident time, changes only the state implied by the alternative decision, and simulates the remaining match from comparable historical states or a fitted scoring model. It must not simply replay Argentina's later goals.

Before manual decision review is activated, the project may publish `exploratory_conditional` scenarios. These must show every timing and state assumption, set `decision_correctness_status=not_assessed`, and use language of the form "if this alternate state is imposed". They are sensitivity analyses, not findings that the observed decision was wrong.

Primary scenarios, pending validation:

| Scenario | Alternate state | Required evidence |
| --- | --- | --- |
| Observed record | Official timeline as played | Tier A event record |
| Disallowed Egypt goal stands | Replace the observed 1-0 state with 0-2 at the verified incident time | Official event feed plus video/Laws review |
| Egypt penalty is awarded | Branch into goal and miss outcomes using a documented conversion distribution | Validated penalty alternative and tournament-specific conversion data |
| Joint scenario | Apply both alternatives only after the single-scenario assumptions are fixed | Both incidents validated and non-overlap assessed |

The "neutral refereeing" label is avoided because it hides the real counterfactual choice. Each scenario must state exactly what changes and what remains uncertain.

### 7.5 Uncertainty and sensitivity

For every probability estimate, show:

- Sampling uncertainty from match-level bootstrap resampling.
- Model uncertainty across the baseline and secondary model.
- Timing sensitivity when sources disagree on the event second.
- Penalty-conversion sensitivity across a documented plausible range.
- Strength-rating sensitivity across the chosen pre-match ratings.
- A table of assumptions that would reverse the sign or practical magnitude of the estimate.

---

## 8. Bias Controls and Review Protocol

| Risk | Control |
| --- | --- |
| Fan or narrative bias | Blind initial incident coding where feasible; separate source collection from decision assessment. |
| Outcome bias | Include validated high-leverage incidents that could favor either team. |
| Selective time windows | Lock 70, 75, 78, and 80 minutes before seeing historical results. |
| Data availability bias | State missing referee audio, VAR communication, and unavailable event detail as limitations. |
| Model shopping | Define a baseline, secondary model, metrics, and validation split before evaluating the focal match. |
| False precision | Report intervals, denominators, calibration, and sensitivity rather than a single deterministic percentage. |

Manual decision-correctness review is deferred. The active analysis does not infer correctness from a vote: it reports conditional alternate-state sensitivity and sets `decision_correctness_status=not_assessed`. If correctness review is activated later, use a blinded multi-reviewer panel, a structured IFAB rubric, an agreement statistic measured on a larger calibration set, and explicit adjudication rather than relying on two unstructured opinions.

---

## 9. Interpretation Rules

The final discussion must keep these conclusions distinct:

1. **Rare comeback:** The observed state had a low historical or modelled chance of a regulation win.
2. **Material sensitivity:** A specific, validated alternate state changes the estimated probability by a meaningful number of probability points under stated assumptions.
3. **Directional pattern:** Multiple validated high-leverage incidents point in one direction, with joint scenarios and uncertainty disclosed.
4. **Intentional manipulation:** Not identifiable from this analysis alone. It would require direct evidence such as official investigation findings, authenticated communications, or independently verified integrity evidence.

Appropriate conclusion language includes "under the stated alternate-state assumption" and "the evidence is consistent with." It must not say "proved bias," "proved corruption," or "proved rigging" based only on public match data.

---

## 10. Notebook Structure

The companion notebook will contain:

1. Research contract, evidence rules, and reproducibility settings.
2. Source manifest and focal match record.
3. Data-contract validation for focal, incident, historical, and strength files.
4. Timeline reconstruction and score-state checks.
5. Threshold-based historical rarity estimates with intervals.
6. Calibrated three-outcome win-probability model and diagnostics.
7. Observed-state probability curve.
8. Incident ledger with evidence statuses.
9. Single and joint counterfactual simulations with sensitivity analysis.
10. Interpretation template and limitations.

The notebook is executable without external data: it validates the built-in focal record and reports which data-dependent steps remain pending. Once inputs are supplied, it should run top-to-bottom from a clean kernel.

---

## 11. Deliverables and Acceptance Criteria

The completed analysis must include:

- A source-linked, reconciled match timeline.
- A data dictionary and immutable source manifest.
- Historical rarity tables with denominators and uncertainty intervals.
- Held-out calibration diagnostics for every win-probability model used in conclusions.
- An incident ledger that distinguishes reported claims from validated alternatives.
- Counterfactual results with scenario definitions, uncertainty, and sensitivity checks.
- A conclusion that states the level of evidence actually reached and the evidence that remains unavailable.

The analysis is ready for substantive interpretation only when all material incidents have evidence statuses, historical sample coverage is documented, and the probability model passes its validation checks.
