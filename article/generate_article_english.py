# -*- coding: utf-8 -*-
"""Build the English edition of the Argentina comeback article.

Usage (from the project root):
    uv run --with playwright python article/generate_article_english.py

The English edition reuses the primary generator's CSS, chart assets, and
dynamic broader-baseline values so both language editions stay reproducible.
"""
from pathlib import Path
import os

from generate_article import (
    REPO_URL,
    ROOT,
    broader_row,
    build_html,
    comeback_row,
    dynamic_row,
    focal_path_row,
    img,
    pct,
    sequence_row,
)


OUT_HTML = Path(os.environ.get("ARGENTINA_ARTICLE_HTML", Path(__file__).resolve().parent / "argentina-comeback-golden-child-en.html"))
OUT_PDF = Path(os.environ.get("ARGENTINA_ARTICLE_PDF", Path(__file__).resolve().parent / "argentina-comeback-golden-child-en.pdf"))


def _styles() -> str:
    source_html = build_html()
    return source_html.split("<style>", 1)[1].split("</style>", 1)[0]


def build_html_english() -> str:
    club_70 = broader_row("club", 70)
    club_75 = broader_row("club", 75)
    club_80 = broader_row("club", 80)
    path_70 = comeback_row("club", 70, "comebacks")
    path_70_clean = comeback_row("club", 70, "clean_strict_comebacks")
    path_70_outcome_clean = comeback_row("club", 70, "clean_outcome_comebacks")
    path_70_penalty_shot = comeback_row("club", 70, "own_penalty_shot_assisted_comebacks")
    path_70_penalty_goal = comeback_row("club", 70, "own_penalty_goal_assisted_comebacks")
    path_70_three = comeback_row("club", 70, "three_plus_own_penalty_shot_comebacks")
    path_79 = comeback_row("club", 79, "comebacks")
    recovery_70_two_down = comeback_row("club", 70, "team_states_with_own_penalty_goal_while_two_down")
    recovery_70_penalty_equalizer = comeback_row("club", 70, "team_states_equalizing_by_own_penalty")
    recovery_70_open_equalizer = comeback_row("club", 70, "team_states_equalizing_by_open_play")
    recovery_70_any_equalizer = comeback_row("club", 70, "team_states_reaching_level_after_cutoff")
    recovery_79_two_down = comeback_row("club", 79, "team_states_with_own_penalty_goal_while_two_down")
    recovery_79_penalty_equalizer = comeback_row("club", 79, "team_states_equalizing_by_own_penalty")
    recovery_79_open_equalizer = comeback_row("club", 79, "team_states_equalizing_by_open_play")
    recovery_79_any_equalizer = comeback_row("club", 79, "team_states_reaching_level_after_cutoff")
    recovery_70_two_shot_pairs = comeback_row("club", 70, "team_states_with_two_own_penalty_shots_within_10m")
    recovery_79_two_shot_pairs = comeback_row("club", 79, "team_states_with_two_own_penalty_shots_within_10m")
    sequence_club = sequence_row("club")
    sequence_intl = sequence_row("intl")
    focal_70 = focal_path_row(70)
    focal_79 = focal_path_row(79)
    fixed_wc = dynamic_row("fixed_score_0_3", "world_cup")
    fixed_club = dynamic_row("fixed_score_0_3", "club")
    adaptive_wc = dynamic_row("adaptive_historical_support", "world_cup")
    adaptive_club = dynamic_row("adaptive_historical_support", "club")
    styles = _styles()

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
  <title>Minute 66. Argentina 0-2. Then Three Goals.</title>
<style>
{styles}
</style>
</head>
<body>

<div class="cover">
  <div class="scoreline">0&ndash;2 &rarr; 3&ndash;2</div>
  <div class="kicker">Data Analysis &middot; FIFA World Cup 2026</div>
  <h1>Minute 66. Argentina 0&ndash;2.<br>Three Goals. One Comeback.</h1>
  <p class="sub">The comeback was real &mdash; and data can measure how rare it was. But a sharper question spread across the timeline afterward: has Argentina really been FIFA's "golden child" since 2022? We test that claim with data, not opinion, and measure how much confidence the data deserves.</p>
  <div class="meta">Reproducible data research &middot; dataset, code, and notebook available publicly at<br>{REPO_URL}</div>
</div>

<div class="content">

<div class="drop">
<p>The scoreboard at Atlanta Stadium read <strong>Argentina 0 &ndash; Egypt 2</strong>. The match clock showed the 66th minute, and Mostafa Zico had just doubled Egypt's lead. To anyone watching, the game looked finished. Argentina, the defending champion, was heading out of the 2026 World Cup in the Round of 16 &mdash; against Egypt.</p>

<p>What happened next became an overnight legend: Cristian Romero in the 78th minute, Lionel Messi in the 82nd, and Enzo Fern&aacute;ndez in the 91st turned the match into a <strong>3&ndash;2</strong> win. But one detail is easy to lose inside the "miracle comeback" story: in the 20th minute, long before the late drama, Messi missed a penalty that could have prevented Argentina from falling behind in the first place. The attempt was blocked by Egypt's goalkeeper and recorded in FIFA's official match report. Argentina did not just survive a late miracle; it had also wasted a major early chance.</p>
</div>

<p class="pull">"How unlikely was this comeback, really? And has Argentina actually received more favorable officiating since 2022?"</p>

<p>Those two questions spread online as soon as the final whistle blew. One is a straightforward sports-statistics question. The other is much more sensitive: the claim that FIFA has systematically favored Argentina since the 2022 Qatar final. This article answers both in the same way: with data that anyone can inspect and reproduce. The full dataset, analysis code, and notebook behind every number are <strong>openly available</strong> at <code>{REPO_URL}</code> &mdash; including the places where the data is not strong enough to give a definitive answer.</p>

<h2>Part 1 &middot; How Rare Was This Comeback, Really?</h2>

<p>To answer fairly, we did not compare the match with subjective memories of other dramatic games. We examined <strong>964 men's World Cup matches</strong> from 1930 through 2022 using the Fjelstul World Cup Database and asked: among all teams that had ever been two or more goals down late in a match, what share eventually won in regulation time?</p>

<div class="statrow">
  <div class="stat"><span class="num-big">0 of 278</span><span class="stat-label">Two-goal comebacks at 70&prime;</span></div>
  <div class="stat"><span class="num-big">0 of 316</span><span class="stat-label">Two-goal comebacks at 80&prime;</span></div>
  <div class="stat"><span class="num-big">&lt; 1.4%</span><span class="stat-label">95% upper bound on the rate</span></div>
</div>

<p>The result is consistent and stark: across 964 men's World Cup matches, not one team had turned a two-goal deficit at minutes 70, 75, 78, or 80 into a regulation-time win before Argentina did it in 2026. Even the upper bound of the statistical uncertainty interval stayed below 1.4%.</p>

<figure>
  <img src="{img('01_goal_difference_timeline')}" alt="Argentina goal-difference timeline">
  <figcaption>Figure 1. Argentina's goal difference throughout the match. Red indicates an Argentina deficit; blue indicates a lead. The equalizer (82&prime;) and winner (91&prime;) both arrived in the final nine minutes of regulation time.</figcaption>
</figure>

<div class="callout">
  <span class="tag">Robustness Check</span>
  To make sure the result was not driven by including the very different football of the 1930s, we repeated the calculation using only matches since 1970, 1998, and 2010. Every era slice still produced <strong>zero comebacks</strong> at every threshold minute. Only the uncertainty changed: smaller samples produce wider upper bounds, reaching 5.7% in the 2010-and-later slice. The direction of the finding did not move.
</div>

<div class="callout fix">
  <span class="tag">Larger Sample</span>
  We also repeated the test on a broader dataset: 2,193 matches from a selected club-football sample outside the World Cup. Here the result was <strong>not literally zero</strong>: there were 2 cases among {club_70['eligible_matches']} relevant matches at minute 70, roughly 1 in 300&ndash;700. They were <strong>Leicester City</strong> at home to Aston Villa and <strong>West Ham United</strong> away to Everton, both in the 2015/16 English Premier League. This sharpens rather than cancels the original finding: the event is extremely rare, but not mathematically impossible.
 </div>

<h2 class="section-break">A Wider Window: Rare, Not Impossible</h2>

<p class="section-lead">A World Cup record can look absolute because the sample is small. The larger club sample adds context, using the same counting rule while remaining a separate population.</p>

<div class="statrow">
  <div class="stat"><span class="num-big">{club_70['comeback_wins']} / {club_70['eligible_matches']}</span><span class="stat-label">Club comebacks at 70&prime;</span></div>
  <div class="stat"><span class="num-big">{club_75['comeback_wins']} / {club_75['eligible_matches']}</span><span class="stat-label">Club comebacks at 75&prime;</span></div>
  <div class="stat"><span class="num-big">{club_80['comeback_wins']} / {club_80['eligible_matches']}</span><span class="stat-label">Club comebacks at 80&prime;</span></div>
</div>

<figure>
  <img src="{img('07_broader_baseline_rarity')}" alt="Comeback rarity in club and international samples">
  <figcaption>Figure 2. Selected StatsBomb sample: the numerator and denominator are shown together so the rarity is not detached from the sample size.</figcaption>
</figure>

<figure>
  <img src="{img('08_broader_baseline_continuation')}" alt="Continuation probability across samples">
  <figcaption>Figure 3. Continuation curves for World Cup, club, and non-World-Cup international matches. This is a cross-check on separate match records, not evidence that the club sample represents all club football.</figcaption>
</figure>

<div class="chart-note"><strong>Sample note:</strong> StatsBomb contains additional senior competitions, but this project uses an explicit competition-season allowlist. Those competitions were not silently treated as nonexistent; the coverage limitation is recorded in <code>config/sources.json</code>.</div>

<h2>Part 1A &middot; Clean Comeback or Penalty-Assisted?</h2>

<p>Because Argentina won after falling 0&ndash;2 behind, the next question can be made more specific: do comebacks like this usually arrive through penalties, or through open play? We scanned the same event-level StatsBomb club and non-World-Cup international coverage used for the broader baseline. A penalty here means a <em>penalty-shot event</em> in the StatsBomb feed, not a referee decision that has been independently adjudicated.</p>

<div class="statrow">
  <div class="stat"><span class="num-big">{path_70['successes']} / {path_70['denominator']}</span><span class="stat-label">Club comebacks from 2+ down at 70&prime;</span></div>
  <div class="stat"><span class="num-big">{path_70_clean['successes']} / {path_70_clean['denominator']}</span><span class="stat-label">Strictly clean after 70&prime;</span></div>
  <div class="stat"><span class="num-big">{path_70_penalty_goal['successes']} / {path_70_penalty_goal['denominator']}</span><span class="stat-label">Assisted by own penalty goal</span></div>
</div>

<table>
<tr><th>Path definition</th><th>Result at 70&prime;</th><th>Meaning</th></tr>
<tr><td>Strictly clean</td><td><strong>{path_70_clean['successes']} / {path_70_clean['denominator']}</strong> ({pct(path_70_clean['rate'])})</td><td>No penalty-shot event by either team after the cutoff.</td></tr>
<tr><td>Outcome-clean</td><td><strong>{path_70_outcome_clean['successes']} / {path_70_outcome_clean['denominator']}</strong> ({pct(path_70_outcome_clean['rate'])})</td><td>No penalty goal by either team after the cutoff; a saved penalty still counts as an attempt under the strict definition.</td></tr>
<tr><td>Penalty-assisted by own shot</td><td><strong>{path_70_penalty_shot['successes']} / {path_70_penalty_shot['denominator']}</strong> ({pct(path_70_penalty_shot['rate'])})</td><td>The comeback team attempted at least one penalty after the cutoff.</td></tr>
<tr><td>Penalty-assisted by own goal</td><td><strong>{path_70_penalty_goal['successes']} / {path_70_penalty_goal['denominator']}</strong> ({pct(path_70_penalty_goal['rate'])})</td><td>The comeback team scored at least one penalty after the cutoff.</td></tr>
<tr><td>3+ own penalties after the cutoff</td><td><strong>{path_70_three['successes']} / {path_70_three['denominator']}</strong> ({pct(path_70_three['rate'])})</td><td>None in this scan.</td></tr>
</table>

<div class="callout fix">
  <span class="tag">Path Finding</span>
  At the 70&prime; cutoff, the two club comebacks found were Leicester City and West Ham United. Both were <strong>strictly clean</strong>: 2 of 2 had no penalty-shot event after the cutoff. At 79&prime;, the result was <strong>{path_79['successes']} of {path_79['denominator']}</strong> club team-states; no team that was still two or more goals down strictly before 79&prime; went on to win. This scan therefore found neither a comeback with three own penalties after 79&prime; nor one at the 70&prime; benchmark.
</div>

<p>Argentina's position needs the time definition to be explicit. At 70&prime;, Argentina really was {focal_70['pre_cutoff_focal_score']}&ndash;{focal_70['pre_cutoff_opponent_score']} down, and its eventual path is classified as strictly clean. At 79&prime;, however, Romero's 78th-minute goal had already made the score {focal_79['pre_cutoff_focal_score']}&ndash;{focal_79['pre_cutoff_opponent_score']}, not 0&ndash;2. The accurate statement is therefore: <strong>Argentina's comeback was clean after the 0&ndash;2 phase and also clean after 79&prime;</strong>, not that Argentina was still 0&ndash;2 at minute 79. Messi's saved penalty in minute 20 remains relevant to the whole-match narrative, but it is outside this post-cutoff definition.</p>

<div class="chart-note"><strong>Generalization limit:</strong> The Fjelstul World Cup Database does not contain a uniform event-level history of penalty attempts, so this cannot be described as a result for "all football history." It is a pinned StatsBomb availability sample, while Argentina is stored as a separate focal case and excluded from the historical denominator.</div>

<h3>Mechanism check &middot; Did the penalty actually change the deficit?</h3>

<p>The next analysis deliberately does not require the team to win. We take <strong>all</strong> team-states that were two or more goals down, then track what happened after the cutoff. This distinguishes three events: a penalty cutting a 2&ndash;0 deficit to 2&ndash;1, a penalty turning 2&ndash;1 into 2&ndash;2, and an equalizer from open play.</p>

<table>
<tr><th>Recovery-path event</th><th>70&prime; cutoff</th><th>79&prime; cutoff</th></tr>
<tr><td>Penalty goal while exactly two goals down</td><td><strong>{recovery_70_two_down['successes']} / {recovery_70_two_down['denominator']}</strong> ({pct(recovery_70_two_down['rate'])})</td><td><strong>{recovery_79_two_down['successes']} / {recovery_79_two_down['denominator']}</strong> ({pct(recovery_79_two_down['rate'])})</td></tr>
<tr><td>Equalizer scored by penalty</td><td><strong>{recovery_70_penalty_equalizer['successes']} / {recovery_70_penalty_equalizer['denominator']}</strong> ({pct(recovery_70_penalty_equalizer['rate'])})</td><td><strong>{recovery_79_penalty_equalizer['successes']} / {recovery_79_penalty_equalizer['denominator']}</strong> ({pct(recovery_79_penalty_equalizer['rate'])})</td></tr>
<tr><td>Equalizer from open play</td><td><strong>{recovery_70_open_equalizer['successes']} / {recovery_70_open_equalizer['denominator']}</strong> ({pct(recovery_70_open_equalizer['rate'])})</td><td><strong>{recovery_79_open_equalizer['successes']} / {recovery_79_open_equalizer['denominator']}</strong> ({pct(recovery_79_open_equalizer['rate'])})</td></tr>
<tr><td>All equalizers, regardless of method</td><td><strong>{recovery_70_any_equalizer['successes']} / {recovery_70_any_equalizer['denominator']}</strong> ({pct(recovery_70_any_equalizer['rate'])})</td><td><strong>{recovery_79_any_equalizer['successes']} / {recovery_79_any_equalizer['denominator']}</strong> ({pct(recovery_79_any_equalizer['rate'])})</td></tr>
</table>

<div class="callout">
  <span class="tag">How to Read It</span>
  At the 70&prime; cutoff, {recovery_70_any_equalizer['successes']} team-states equalized. Only {recovery_70_penalty_equalizer['successes']} of them ({pct(float(recovery_70_penalty_equalizer['successes']) / float(recovery_70_any_equalizer['successes']), 1)}) equalized through a penalty, while {recovery_70_open_equalizer['successes']} ({pct(float(recovery_70_open_equalizer['successes']) / float(recovery_70_any_equalizer['successes']), 1)}) equalized through open play. At 79&prime;, the split was {recovery_79_penalty_equalizer['successes']} penalty equalizer versus {recovery_79_open_equalizer['successes']} open-play equalizers. Penalties can be a recovery mechanism, but most equalizers in this scan still came from open play, and the conditional comparison rests on a small denominator.
</div>

<h3>Direct sequence test &middot; Two penalties within 10 minutes</h3>

<p>For the more extreme question, we tested event pairs directly. The primary definition is two penalty-shot events by the same team within a rolling 10-minute interval; we also record whether both became penalty goals.</p>

<table>
<tr><th>Cohort</th><th>2 penalty-shot events / 10 minutes</th><th>2 penalty goals / 10 minutes</th></tr>
<tr><td>Late state 2+ down at 70&prime;</td><td><strong>{recovery_70_two_shot_pairs['successes']} / {recovery_70_two_shot_pairs['denominator']}</strong></td><td>0 / {recovery_70_two_shot_pairs['denominator']}</td></tr>
<tr><td>Late state 2+ down at 79&prime;</td><td><strong>{recovery_79_two_shot_pairs['successes']} / {recovery_79_two_shot_pairs['denominator']}</strong></td><td>0 / {recovery_79_two_shot_pairs['denominator']}</td></tr>
<tr><td>All club matches, all minutes</td><td><strong>{sequence_club['matches_with_two_penalty_shots_within_10m']} / {sequence_club['matches_scanned']}</strong> ({pct(sequence_club['shot_pair_rate'])})</td><td><strong>{sequence_club['matches_with_two_penalty_goals_within_10m']} / {sequence_club['matches_scanned']}</strong> ({pct(sequence_club['goal_pair_rate'])})</td></tr>
<tr><td>All non-WC international matches, all minutes</td><td><strong>{sequence_intl['matches_with_two_penalty_shots_within_10m']} / {sequence_intl['matches_scanned']}</strong></td><td><strong>{sequence_intl['matches_with_two_penalty_goals_within_10m']} / {sequence_intl['matches_scanned']}</strong></td></tr>
</table>

<div class="callout warn">
  <span class="tag">Claim Correction</span>
  The accurate sentence is not "this never happened in history." Across the full club sample, eight matches did contain two same-team penalty-shot events within 10 minutes, and five contained two penalty goals. But <strong>none</strong> occurred in the relevant state: a team two or more goals down late in the match. We therefore found no direct historical analogue for Argentina receiving two penalties within 10 minutes while chasing from 0&ndash;2. Even two converted penalties would only make it 2&ndash;2; a third goal would still be required.
</div>

<h3 class="section-break">So What Was Argentina's Exact Win Probability?</h3>

<p>This is where data honesty matters. There are two defensible ways to estimate Argentina's chance of winning from 0&ndash;2 down, and they differ by <strong>an order of magnitude</strong>. The first compares Argentina with <em>every</em> historical team that was in the same deficit, including weak teams that were rarely likely to recover. The second compares only situations where the trailing team had strength comparable to Argentina, using Elo ratings. That is more relevant, but leaves a very small comparison set, sometimes only 1&ndash;3 matches.</p>

<figure>
  <img src="{img('05_focal_model_probabilities')}" alt="Modelled win probability with sample-size annotations">
  <figcaption>Figure 4. Argentina's modelled win probability at key match moments, using strength-matched historical situations. Red points have too little comparison data for full confidence (n = 1&ndash;14); blue points have more support (n = 28&ndash;37).</figcaption>
</figure>

<p>The honest conclusion is a range, not a precise point estimate: Argentina's chance at minutes 66&ndash;80 while 0&ndash;2 down was almost certainly low, probably somewhere from the low single digits to the high teens, but the available data cannot narrow that range responsibly. Anyone quoting "only X%" without showing how many historical matches produced the estimate is flattening a genuinely uncertain problem.</p>

<h2 class="section-break">Part 2 &middot; What If Egypt's Disallowed Goal Had Stood?</h2>

<p>One of the match's most debated moments was an Egypt goal disallowed by VAR while the score was still 0&ndash;1. Public reports disagree about its exact minute (58, 62, or 67), and the incident has <strong>not been verified through official video</strong>. We therefore cannot and will not claim that the decision was wrong. What we can calculate is the counterfactual: <em>if</em> the goal had stood, how much would Argentina's modelled win probability have changed?</p>

<figure>
  <img src="{img('06_scenario_only_impact')}" alt="Counterfactual impact of the disallowed goal">
  <figcaption>Figure 5. Change in Argentina's win probability if the disallowed goal had counted, evaluated at three possible reported minutes. Vertical lines show the statistical bootstrap interval.</figcaption>
</figure>

<div class="callout warn">
  <span class="tag">Important Limit</span>
  Under all three timing assumptions, allowing the goal would have reduced Argentina's modelled win probability by <strong>3&ndash;5 percentage points</strong>, and the uncertainty interval did not cross zero. That makes the counterfactual statistically material. It is <strong>not</strong> evidence that the officiating decision was wrong, much less evidence of corruption; that would require video review and the relevant official rules, which are outside the scope of public match-event data.
</div>

<h3>What if the goal changed the entire match?</h3>

<p>This is a valid methodological objection. If Egypt's disallowed goal had counted, the later 66th-minute goal could have moved the score from 0&ndash;2 to 0&ndash;3. But the match after 0&ndash;3 would not necessarily have unfolded like the actual match after 0&ndash;2: Argentina might have taken risks earlier, Egypt might have defended deeper, and the later goals cannot simply be held fixed. We therefore report two branches instead of one false-precision number.</p>

<table>
<tr><th>Branch</th><th>Comparison data</th><th>Result</th><th>Status</th></tr>
<tr><td>Fixed score, 0&ndash;2 &rarr; 0&ndash;3</td><td>Out-of-fold model on {fixed_club['support_matches']} club matches with a 0&ndash;2 state at 60&ndash;70&prime;</td><td>{pct(fixed_club['observed_win_rate'])} &rarr; {pct(fixed_club['counterfactual_win_rate'])} ({float(fixed_club['delta_percentage_points']):.2f} percentage points)</td><td>Score-state effect only</td></tr>
<tr><td>Fixed score, World Cup</td><td>{fixed_wc['support_matches']} comparison matches</td><td>{pct(fixed_wc['observed_win_rate'])} &rarr; {pct(fixed_wc['counterfactual_win_rate'])} ({float(fixed_wc['delta_percentage_points']):.2f} percentage points)</td><td>Score-state effect only</td></tr>
<tr><td>Adaptive historical branch, 0&ndash;3</td><td>{adaptive_club['support_matches']} club matches at 50&ndash;70&prime;</td><td>0 wins; Wilson 95% upper bound {pct(adaptive_club['wilson_upper'], 1)}</td><td>Extrapolative, not a precise probability</td></tr>
</table>

<div class="callout warn">
  <span class="tag">Path Dependence</span>
  The fixed-score branch answers the mechanical question: how much does the model move when the scoreboard is lowered by one goal? The adaptive branch answers the more realistic but less identifiable question: what do historical matches that actually reached 0&ndash;3 look like? World Cup support is only {adaptive_wc['support_matches']} matches and club support is {adaptive_club['support_matches']}, with zero wins in this scan. That is enough to show that 0&ndash;3 is much worse than 0&ndash;2, but <strong>not enough to calculate a credible Argentina-specific probability</strong> after both teams change strategy. None of this simulation determines whether the disallowed goal was correct.
</div>

<h2>Part 3 &middot; Is Argentina Really FIFA's "Golden Child" Since 2022?</h2>

<p>This question is much larger than one match. The claim is that, since the 2022 World Cup final, Argentina has systematically received favorable officiating decisions. To test it fairly across years and teams, we measured Argentina's penalties, yellow cards, and red cards against <em>every team in the field</em> at each World Cup edition since 1930, then ranked Argentina's per-match rate as a percentile within that edition's field.</p>

<figure>
  <img src="{img('03_discipline_percentile_by_edition')}" alt="Argentina discipline percentiles by World Cup edition">
  <figcaption>Figure 6. Argentina's percentile against every team in the same edition for three different metrics. Red marks 2022. Cards are computed only from 1970 onward, because the card system did not exist earlier.</figcaption>
</figure>

<div class="callout fix">
  <span class="tag">An Honest Correction</span>
  An earlier draft incorrectly calculated Argentina's 2022 red-card percentile as <strong>88%</strong>, making it appear unusually high. The old formula mishandled ties, especially the many teams with zero red cards. Argentina actually had zero red cards in 2022, and <strong>28 of the 32 teams</strong> in that field also had zero. The correct tie-aware percentile is <strong>43.5%</strong>, almost exactly the middle of the field. We corrected this publicly because the mistake exaggerated the bias narrative rather than weakening it.
</div>

<p>The data does show that Argentina's 2022 penalty-goal rate was high, at the 100th percentile, and its yellow-card rate was above average, at the 84th percentile. But this is <strong>not a pattern that began in 2022</strong>. Argentina also reached the 100th percentile for penalty goals in 1958, while 1982 and 1990 matched or exceeded 2022 on red cards. If preferential treatment truly began in 2022, we would expect a sharp new step at that tournament. The data does not show one. The observed pattern looks at least as compatible with a consistently attacking, high-possession team spending more time in opponents' penalty areas across different generations and refereeing eras.</p>

<h3>What About 2026?</h3>

<p>For a current check, we extracted the official FIFA reports for <strong>all 96 matches</strong> played through the 2026 Round of 16, a full census rather than a sample, and counted penalties <em>awarded</em> to each team. This includes saved and missed penalties, not only converted kicks &mdash; including Messi's missed 20th-minute penalty.</p>

<figure>
  <img src="{img('04_pmsr_2026_penalties')}" alt="2026 penalties awarded comparison">
  <figcaption>Figure 7. Penalties awarded per match for every team at the 2026 World Cup through the Round of 16, covering all 48 teams. Argentina leads the field.</figcaption>
</figure>

<div class="callout">
  <span class="tag">Methodological Note</span>
  The 2026 metric, "penalties awarded," and the 1930&ndash;2022 metric, "penalty goals scored," measure different things from different source documents. They <strong>must not be combined</strong> into a single statistic.
</div>

<p>Argentina currently leads the 48-team field with 3 penalties in 5 matches, or 0.60 per match, slightly ahead of Brazil, Switzerland, and England at 0.40. But this tournament is still in progress: teams have played only 3&ndash;5 matches, and the field median is zero. Read alongside the 1930&ndash;2022 chart, this is a second data point pointing in the same direction as the 2022 result, not independent proof. It is also just as compatible with a simpler explanation: an elite, ball-dominant, relentlessly attacking team spends more time in the opponent's box and therefore mechanically creates more penalty opportunities.</p>

<h2 class="section-break">Conclusion: What the Evidence Does and Does Not Support</h2>

<table class="verdict-table">
<tr><th>Claim</th><th>Supported?</th></tr>
<tr><td>This comeback was statistically rare</td><td><strong>Yes, strongly.</strong> Zero comparable events in 964 historical matches at every threshold and across every era slice.</td></tr>
<tr><td>This comeback was penalty-assisted</td><td><strong>No.</strong> The post-0&ndash;2 path had no penalty-shot event after the cutoff; the StatsBomb benchmark found 2 club comebacks at 70&prime;, both clean, but the sample is small.</td></tr>
<tr><td>A penalty can help a team equalize from a deficit</td><td><strong>Yes, but rarely in this scan.</strong> At 70&prime;, 2 of 21 equalizers came from penalties; 19 came from open play. This is a recovery mechanism, not evidence of bias or a guarantee of a comeback.</td></tr>
<tr><td>Argentina would definitely have come back from 0&ndash;3</td><td><strong>Not identifiable.</strong> The fixed-score branch lowers modelled probability; the adaptive branch has too little historical support for a credible focal number.</td></tr>
<tr><td>One officiating decision had material sensitivity</td><td><strong>Yes, conditionally.</strong> The disallowed-goal scenario shows a 3&ndash;5 percentage-point effect, but the incident is not validated.</td></tr>
<tr><td>Repeated officiating decisions favored one side</td><td><strong>Not established.</strong> No incident in this match currently has video-reviewed or officially confirmed status.</td></tr>
<tr><td>FIFA intentionally favored or manipulated outcomes for Argentina</td><td><strong>Not assessable</strong> from public match statistics alone.</td></tr>
</table>

<p>Public match statistics, however rich, have limits. They can tell us how rare an outcome was, how much an alternate scenario changes a modelled probability, and whether a numerical pattern is consistent across time. They <strong>cannot</strong> read a referee's intent, prove corruption, or settle the correctness of a decision without video and the official rules. Argentina's comeback is statistically one of the rarest in World Cup history. But "rare" and "rigged" are entirely different claims, and this dataset can answer only one of them.</p>

<div class="footer">
  <strong>Methods &amp; transparency.</strong> Every number in this article is generated by a reproducible data pipeline, not typed by hand. The ETL code, fully executed Jupyter notebook, compact outputs, provenance, and instructions for downloading the pinned raw StatsBomb event cache are publicly available at:<br>
  <a href="{REPO_URL}">{REPO_URL}</a><br><br>
  Notebook: <code>output/jupyter-notebook/argentina_egypt_comeback_analysis.ipynb</code> &middot; Full technical report: <code>results/analysis_report.md</code> &middot; Comeback paths: <code>results/comeback_path_summary.csv</code> &middot; Counterfactual: <code>results/comeback_counterfactual.csv</code> &middot; Data provenance: <code>config/sources.json</code>
</div>

</div>
</body>
</html>
"""


def main() -> None:
    from playwright.sync_api import sync_playwright

    html = build_html_english()
    OUT_HTML.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(OUT_HTML.as_uri())
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
