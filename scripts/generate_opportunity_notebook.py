"""Generate the standalone opportunity-adjusted analysis notebook.

Run after `research_etl opportunity` has built at least the PMSR and World Cup
feature panels. The notebook deliberately reads saved artifacts only; it does
not download source data or refit hidden models.
"""

from __future__ import annotations

import json
from pathlib import Path

import nbformat as nbf
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "jupyter-notebook" / "opportunity_adjusted_officiating_analysis.ipynb"


def markdown(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(source)


def code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(source)


def build_notebook() -> nbf.NotebookNode:
    manifest_path = ROOT / "results" / "opportunity_analysis_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("Run `python -m research_etl opportunity` before generating this notebook.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    temporal_manifest_path = ROOT / "results" / "temporal_analysis_manifest.json"
    temporal_manifest = json.loads(temporal_manifest_path.read_text(encoding="utf-8")) if temporal_manifest_path.exists() else None
    bridge_manifest_path = ROOT / "results" / "bridge_analysis_manifest.json"
    bridge_manifest = json.loads(bridge_manifest_path.read_text(encoding="utf-8")) if bridge_manifest_path.exists() else None
    pmsr = pd.read_csv(ROOT / "data" / "processed" / "pmsr_2026_match_features.csv")
    world_cup = pd.read_csv(ROOT / "data" / "processed" / "statsbomb_world_cup_opportunity_features.csv")
    argentina_pmsr = pmsr.loc[pmsr["team_name"].eq("Argentina")]
    argentina_penalties = int(argentina_pmsr["penalties_awarded"].sum())
    argentina_matches = int(len(argentina_pmsr))
    pmsr_model = next(item for item in manifest["models"] if item["panel"] == "pmsr_2026")
    world_model = next(item for item in manifest["models"] if item["panel"] == "statsbomb_world_cup")
    pmsr_corr = pmsr_model["xg_spearman"]
    wc_corr = world_model["box_entry_spearman"]
    temporal_bullet = ""
    if temporal_manifest:
        temporal_club = next(item for item in temporal_manifest["models"] if item["tier"] == "club")
        temporal_bullet = (
            f"- The time-aware club panel covers **{temporal_club['matches']} matches and {temporal_club['positive_events']} "
            f"penalty-shot events**. Its grouped out-of-fold hazard model has log loss **{temporal_club['oof_log_loss']:.4f}** "
            f"versus **{temporal_club['null_log_loss']:.4f}** for the null rate.\n"
        )
    bridge_bullet = ""
    if bridge_manifest:
        bridge_club = next(item for item in bridge_manifest["models"] if item["tier"] == "club")
        state_log_loss = next(item["log_loss"] for item in bridge_club["models"] if item["variant"] == "state_only")
        opportunity_log_loss = next(item["log_loss"] for item in bridge_club["models"] if item["variant"] == "opportunity_augmented")
        bridge_bullet = (
            f"- The linked club bridge model compares final-result log loss **{state_log_loss:.4f}** for the state-only model "
            f"with **{opportunity_log_loss:.4f}** after adding pre-window opportunity features.\n"
        )

    cells = [
        markdown(
            "# Opportunity-Adjusted Officiating Analysis\n\n"
            "A companion notebook to the Argentina-Egypt comeback case study. "
            "It studies whether penalties, fouls, and cards track measurable attacking opportunity."
        ),
        markdown(
            "## tl;dr\n\n"
            f"- The official 2026 FIFA panel covers **96 matches / 192 team-match rows**. Argentina received "
            f"**{argentina_penalties} penalties in {argentina_matches} matches**, but the tournament contains only "
            "19 official awards, so it supports descriptive association rather than a large adjusted model.\n"
            f"- In the PMSR 2026 panel, the match-clustered Spearman association between xG and penalties awarded is "
            f"**{pmsr_corr['correlation']:.3f}** (95% bootstrap interval {pmsr_corr['lower']:.3f} to {pmsr_corr['upper']:.3f}).\n"
            f"- The 2018/2022 StatsBomb World Cup panel covers **{world_model['matches']} matches / {world_model['rows']} team-match rows**. "
            f"Its association between box entries and regulation penalty kicks is **{wc_corr['correlation']:.3f}** "
            f"(95% bootstrap interval {wc_corr['lower']:.3f} to {wc_corr['upper']:.3f}).\n"
            f"{temporal_bullet}"
            f"{bridge_bullet}"
            "- These are opportunity-adjusted associations, not an adjudication of referee decisions. The initial model "
            "does not include pre-decision score state, strength, referee effects, or a complete denominator of potential box incidents."
        ),
        markdown(
            "## Context & Methods\n\n"
            "### Key Assumptions\n\n"
            "The data lanes are never pooled. FIFA PMSR 2026 measures official penalties awarded; StatsBomb uses "
            "regulation penalty kicks as an event-feed proxy. The principal opportunity features are spatial box entries "
            "and non-penalty xG, not possession alone. Statistics are cluster-bootstrapped by match, and the small Poisson "
            "model is evaluated out-of-fold by complete match.\n\n"
            "See `docs/opportunity_adjusted_analysis.md` for the full estimand, source, and publication contract."
        ),
        code(
            "from pathlib import Path\n"
            "import json\n"
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "from IPython.display import Image, display\n\n"
            "ROOT = Path.cwd()\n"
            "while not (ROOT / 'Project.md').exists():\n"
            "    if ROOT.parent == ROOT:\n"
            "        raise RuntimeError('Run from this repository or a subdirectory.')\n"
            "    ROOT = ROOT.parent\n\n"
            "PROCESSED = ROOT / 'data' / 'processed'\n"
            "RESULTS = ROOT / 'results'\n"
            "manifest = json.loads((RESULTS / 'opportunity_analysis_manifest.json').read_text(encoding='utf-8'))\n"
            "print(manifest['interpretation'])\n"
            "print('Non-pooling rule:', manifest['non_pooling_rule'])"
        ),
        markdown("## Data\n\n### Load the Official and Event-Level Panels"),
        code(
            "pmsr = pd.read_csv(PROCESSED / 'pmsr_2026_match_features.csv')\n"
            "world_cup = pd.read_csv(PROCESSED / 'statsbomb_world_cup_opportunity_features.csv')\n"
            "assert len(pmsr) == 192 and pmsr['match_number'].nunique() == 96\n"
            "assert len(world_cup) == 256 and world_cup['match_id'].nunique() == 128\n"
            "display(pmsr[['match_number', 'team_name', 'opponent_team_name', 'penalties_awarded', 'team_possession_pct', 'xg', 'receptions_final_third']].head(8))\n"
            "display(world_cup[['year', 'team_name', 'opponent_team_name', 'penalty_shots', 'box_entries', 'box_receipts', 'non_penalty_xg', 'fouls_committed', 'yellow_cards']].head(8))"
        ),
        markdown(
            "### Outcome Definition Check\n\n"
            "PMSR's `penalties_awarded` is the official count. StatsBomb's `penalty_shots` is used separately because its "
            "`Foul Won -> penalty` flag does not capture every eventual penalty kick in the feed. The two fields are therefore "
            "never merged or compared as if they were the same measurement."
        ),
        code(
            "reconciliation = world_cup.groupby('year')[['penalty_fouls_won', 'penalty_shots']].sum()\n"
            "reconciliation['difference'] = reconciliation['penalty_shots'] - reconciliation['penalty_fouls_won']\n"
            "display(reconciliation)"
        ),
        markdown(
            "### Formal Correlation Inference\n\n"
            "The correlation table adds a 95% match-cluster bootstrap interval and a whole-match permutation p-value. "
            "The permutation keeps the two team rows together while breaking the alignment between exposure and outcome "
            "clusters. Benjamini-Hochberg q-values control the registered correlation family. Significance is evidence of "
            "association under this design, not causality or officiating bias."
        ),
        code(
            "correlation_path = RESULTS / 'opportunity_correlation_tests.csv'\n"
            "if correlation_path.exists():\n"
            "    correlation_tests = pd.read_csv(correlation_path)\n"
            "    display(correlation_tests)\n"
            "else:\n"
            "    print('Formal correlation tests have not been generated in this run.')"
        ),
        markdown("## Results\n\n### Official 2026 Penalties and Attacking Output"),
        code(
            "pmsr_summary = pd.read_csv(RESULTS / 'opportunity_pmsr_2026_team_summary.csv')\n"
            "display(pmsr_summary.head(12))\n"
            "display(Image(filename=str(RESULTS / 'assets' / '09_pmsr_2026_penalties_vs_xg.png')))"
        ),
        markdown(
            "The scatter is a descriptive diagnostic: xG is a better proxy for attacking threat than total possession, but "
            "the small number of penalty awards prevents a stable multi-covariate 2026-only model."
        ),
        markdown("### World Cup 2018/2022: Box Access and Penalty Kicks"),
        code(
            "world_predictions = pd.read_csv(RESULTS / 'opportunity_statsbomb_world_cup_oof_predictions.csv')\n"
            "world_model = next(item for item in manifest['models'] if item['panel'] == 'statsbomb_world_cup')\n"
            "if world_model['oof_beats_null']:\n"
            "    display(pd.read_csv(RESULTS / 'opportunity_statsbomb_world_cup_team_residuals.csv').head(12))\n"
            "else:\n"
            "    print('The World Cup partial model did not beat its null baseline out-of-fold; residual ranks are withheld.')\n"
            "display(Image(filename=str(RESULTS / 'assets' / '10_statsbomb_world_cup_box_entries_vs_penalty_shots.png')))"
        ),
        markdown(
            "The residual table is an out-of-fold partial adjustment using only box entries and non-penalty xG. "
            "It is useful for identifying where raw penalty counts are not fully explained by those two features, but it is "
            "not a decision-correctness or bias score."
        ),
        markdown("### Optional Broader Baseline"),
        code(
            "history_path = PROCESSED / 'statsbomb_history_opportunity_features.csv'\n"
            "if history_path.exists():\n"
            "    history = pd.read_csv(history_path)\n"
            "    print(history.groupby('competition_tier')['match_id'].nunique())\n"
            "    for tier in sorted(history['competition_tier'].unique()):\n"
            "        residual_path = RESULTS / f'opportunity_statsbomb_{tier}_team_residuals.csv'\n"
            "        if residual_path.exists():\n"
            "            print(f'\\n{tier}')\n"
            "            display(pd.read_csv(residual_path).head(10))\n"
            "else:\n"
            "    print('Broader StatsBomb feature panel has not been generated in this run.')"
        ),
        markdown(
            "## Time-Aware Pre-Decision Hazard\n\n"
            "The temporal extension creates one row for each team and five-minute window. Every predictor is calculated "
            "strictly before that window: score state, recent box entries, recent xG, fouls, cards, and event-derived "
            "possession sequences. The next-window label is whether a StatsBomb penalty shot occurs. This prevents using "
            "the event being explained as its own predictor. Panels remain separate by competition tier, and the model is "
            "evaluated out-of-fold by complete match."
        ),
        code(
            "temporal_manifest_path = RESULTS / 'temporal_analysis_manifest.json'\n"
            "if temporal_manifest_path.exists():\n"
            "    temporal_manifest = json.loads(temporal_manifest_path.read_text(encoding='utf-8'))\n"
            "    temporal_rows = []\n"
            "    for item in temporal_manifest['models']:\n"
            "        temporal_rows.append({\n"
            "            'panel': item['panel'], 'tier': item['tier'], 'matches': item['matches'],\n"
            "            'five_minute_rows': item['rows'], 'penalty_events': item['positive_events'],\n"
            "            'positive_rate': item['positive_rate'], 'oof_log_loss': item['oof_log_loss'],\n"
            "            'null_log_loss': item['null_log_loss'], 'oof_beats_null': item['oof_beats_null'],\n"
            "        })\n"
            "    display(pd.DataFrame(temporal_rows))\n"
            "    club_predictions = pd.read_csv(RESULTS / 'temporal_statsbomb_club_oof_predictions.csv')\n"
            "    club_coefficients = pd.read_csv(RESULTS / 'temporal_statsbomb_club_coefficients.csv')\n"
            "    display(club_coefficients)\n"
            "    display(Image(filename=str(RESULTS / 'assets' / '11_temporal_club_penalty_hazard.png')))\n"
            "else:\n"
            "    print('Temporal panel has not been generated in this run.')"
        ),
        markdown(
            "The hazard result is a mechanism check, not a bias estimate. A model that slightly beats the null means that "
            "pre-window match context contains information about where penalty-shot events occur; it does not establish that "
            "the underlying decision was correct, incorrect, biased, or intentional."
        ),
        markdown(
            "## Bridge to Notebook 1: Outcome Probability and Penalty Impact\n\n"
            "This section uses the same match-state logic as Notebook 1: predict the eventual regulation result from the "
            "state at a given time, keeping complete matches together in every validation fold. It compares a state-only "
            "model with spatial, possession, disciplinary, and opponent-opportunity extensions. The primary counterfactual "
            "changes only `goal_diff_pre` by one goal, representing an immediate penalty goal for the team or for its opponent. "
            "It is a score-state sensitivity estimate, not a full tactical simulation and not a judgment about whether a penalty should have been awarded."
        ),
        code(
            "bridge_manifest_path = RESULTS / 'bridge_analysis_manifest.json'\n"
            "if bridge_manifest_path.exists():\n"
            "    bridge_manifest = json.loads(bridge_manifest_path.read_text(encoding='utf-8'))\n"
            "    bridge_skill = pd.read_csv(RESULTS / 'bridge_model_skill.csv')\n"
            "    bridge_impact = pd.read_csv(RESULTS / 'bridge_penalty_win_impact.csv')\n"
            "    display(bridge_skill[['panel', 'tier', 'variant', 'rows', 'log_loss', 'multiclass_brier', 'accuracy']])\n"
            "    display(bridge_impact.loc[bridge_impact['cohort'].isin(['late_trailing', 'late_two_or_more_down'])].head(20))\n"
            "    display(Image(filename=str(RESULTS / 'assets' / '12_bridge_model_skill.png')))\n"
            "    impact_chart = RESULTS / 'assets' / '13_penalty_win_impact.png'\n"
            "    if impact_chart.exists():\n"
            "        display(Image(filename=str(impact_chart)))\n"
            "else:\n"
            "    print('Bridge analysis has not been generated in this run.')"
        ),
        markdown(
            "The bridge is a linked robustness analysis, not a replacement for Notebook 1's validated World Cup model. "
            "The StatsBomb tiers have different competition populations, and the 2026 focal match does not yet have the "
            "same pre-window event-level covariates. Therefore the bridge results validate mechanism and sensitivity, not a new focal probability."
        ),
        markdown(
            "## Takeaways\n\n"
            "- Possession should be interpreted alongside location and chance-quality measures. A team can control the ball "
            "away from the opponent box, while a lower-possession team can still create many high-leverage entries.\n"
            "- Club, non-World-Cup international, World Cup, and 2026 PMSR findings are linked by common metric definitions "
            "but remain separate estimands.\n"
            "- The time-aware panel now adds score state and recent spatial/event exposure without leaking the outcome window. "
            "The next methodological upgrade is a validated denominator of potential penalty incidents and stronger national-team coverage."
        ),
    ]
    return nbf.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
    )


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(build_notebook(), OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
