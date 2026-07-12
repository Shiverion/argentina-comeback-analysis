"""Structured match-summary metrics from FIFA 2026 PMSR PDFs."""

from __future__ import annotations

from io import BytesIO
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from pypdf import PdfReader

from research_etl.pmsr import validate_pmsr_extract
from research_etl.sources import SourceError, USER_AGENT


PMSR_MATCH_FEATURE_COLUMNS = {
    "match_number",
    "tournament_name",
    "year",
    "team_name",
    "opponent_team_name",
    "penalties_awarded",
    "goals",
    "team_possession_pct",
    "contested_possession_pct",
    "xg",
    "attempts_at_goal",
    "shots_on_target",
    "total_passes",
    "completed_passes",
    "pass_completion_pct",
    "completed_line_breaks",
    "defensive_line_breaks",
    "receptions_final_third",
    "crosses",
    "ball_progressions",
    "defensive_pressures",
    "direct_pressures",
    "forced_turnovers",
    "second_balls",
    "source_name",
    "source_version",
    "source_url",
}

PMSR_FEATURE_VERSION = "pmsr_match_summary_v1"


def fetch_pmsr_pdf(url: str) -> bytes:
    """Fetch a single official report without persisting the unvendored PDF."""

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"})
    try:
        with urlopen(request, timeout=90) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        raise SourceError(f"Could not fetch PMSR match summary from {url}: {error}") from error


def _numbers(text: str, pattern: str, label: str, *, cast: Callable[[str], float | int]) -> tuple[float | int, ...]:
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        raise SourceError(f"Could not parse {label} from FIFA PMSR match-summary page.")
    return tuple(cast(value) for value in match.groups())


def parse_pmsr_match_summary_text(text: str, expected_teams: list[str]) -> dict[str, dict[str, float | int]]:
    """Parse one PMSR match-summary page using the displayed team order.

    FIFA represents possession as team-controlled possession for both sides plus
    a separate contested component. The contested percentage is preserved and
    must not be silently reassigned to either team.
    """

    text = text.replace("\x00", "")
    if "Match Summary - Key Statistics" not in text:
        raise SourceError("PMSR does not contain a Match Summary - Key Statistics page.")
    header = text.split("Possession", maxsplit=1)[0]
    team_positions = {team: header.find(team) for team in expected_teams}
    if len(expected_teams) != 2 or any(position < 0 for position in team_positions.values()):
        raise SourceError(f"Could not identify both expected teams in PMSR header: {expected_teams}")
    left_team, right_team = sorted(expected_teams, key=lambda team: team_positions[team])

    possession = re.search(
        r"Possession\s+Total\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+Total",
        text,
        flags=re.DOTALL,
    )
    if not possession:
        raise SourceError("Could not parse possession values from FIFA PMSR match-summary page.")
    left_possession, contested_possession, right_possession = map(float, possession.groups())
    pairs = {
        "goals": _numbers(text, r"(\d+)\s+Goals\s+(\d+)", "goals", cast=int),
        "xg": _numbers(
            text,
            r"(\d+(?:\.\d+)?)\s+xG \(Expected Goals\)\s+(\d+(?:\.\d+)?)",
            "xG",
            cast=float,
        ),
        "attempts_at_goal": _numbers(
            text,
            r"(\d+)\s+\((\d+)\)\s+Attempts at Goal \(On Target\)\s+(\d+)\s+\((\d+)\)",
            "attempts at goal",
            cast=int,
        ),
        "total_passes": _numbers(
            text,
            r"(\d+)\s+\((\d+)\)\s+Total Passes \(Complete\)\s+(\d+)\s+\((\d+)\)",
            "total passes",
            cast=int,
        ),
        "pass_completion_pct": _numbers(
            text,
            r"(\d+)\s+%\s+Pass Completion %\s+(\d+)\s+%",
            "pass completion",
            cast=int,
        ),
        "completed_line_breaks": _numbers(
            text, r"(\d+)\s+Completed Line Breaks\s+(\d+)", "completed line breaks", cast=int
        ),
        "defensive_line_breaks": _numbers(
            text, r"(\d+)\s+Defensive Line Breaks\s+(\d+)", "defensive line breaks", cast=int
        ),
        "receptions_final_third": _numbers(
            text,
            r"(\d+)\s+Receptions in the Final Third\s+(\d+)",
            "final-third receptions",
            cast=int,
        ),
        "crosses": _numbers(text, r"(\d+)\s+Crosses\s+(\d+)", "crosses", cast=int),
        "ball_progressions": _numbers(
            text, r"(\d+)\s+Ball Progressions\s+(\d+)", "ball progressions", cast=int
        ),
        "defensive_pressures": _numbers(
            text,
            r"(\d+)\s+\((\d+)\)\s+Defensive Pressures Applied \(Direct Pressures\)\s+(\d+)\s+\((\d+)\)",
            "defensive pressures",
            cast=int,
        ),
        "forced_turnovers": _numbers(
            text, r"(\d+)\s+Forced Turnovers\s+(\d+)", "forced turnovers", cast=int
        ),
        "second_balls": _numbers(text, r"(\d+)\s+Second Balls\s+(\d+)", "second balls", cast=int),
    }

    def team_metrics(side: int, possession_pct: float) -> dict[str, float | int]:
        return {
            "team_possession_pct": possession_pct,
            "contested_possession_pct": contested_possession,
            "goals": pairs["goals"][side],
            "xg": pairs["xg"][side],
            "attempts_at_goal": pairs["attempts_at_goal"][side * 2],
            "shots_on_target": pairs["attempts_at_goal"][side * 2 + 1],
            "total_passes": pairs["total_passes"][side * 2],
            "completed_passes": pairs["total_passes"][side * 2 + 1],
            "pass_completion_pct": pairs["pass_completion_pct"][side],
            "completed_line_breaks": pairs["completed_line_breaks"][side],
            "defensive_line_breaks": pairs["defensive_line_breaks"][side],
            "receptions_final_third": pairs["receptions_final_third"][side],
            "crosses": pairs["crosses"][side],
            "ball_progressions": pairs["ball_progressions"][side],
            "defensive_pressures": pairs["defensive_pressures"][side * 2],
            "direct_pressures": pairs["defensive_pressures"][side * 2 + 1],
            "forced_turnovers": pairs["forced_turnovers"][side],
            "second_balls": pairs["second_balls"][side],
        }

    return {
        left_team: team_metrics(0, left_possession),
        right_team: team_metrics(1, right_possession),
    }


def parse_pmsr_match_summary(pdf_bytes: bytes, expected_teams: list[str]) -> dict[str, dict[str, float | int]]:
    """Locate and parse the first official match-summary page in one PMSR PDF."""

    reader = PdfReader(BytesIO(pdf_bytes))
    for page in reader.pages:
        text = page.extract_text() or ""
        if "Match Summary - Key Statistics" in text:
            return parse_pmsr_match_summary_text(text, expected_teams)
    raise SourceError("PMSR PDF contains no Match Summary - Key Statistics page.")


def build_pmsr_2026_match_features(
    extraction: pd.DataFrame,
    *,
    pdf_loader: Callable[[str], bytes] = fetch_pmsr_pdf,
) -> pd.DataFrame:
    """Build a complete two-team-per-match FIFA 2026 summary panel.

    All 96 source PDFs are required. Unvendored PDFs are fetched in memory so
    the compact processed table remains reproducible without committing about
    500 MB of source documents.
    """

    cleaned = validate_pmsr_extract(extraction)
    rows: list[dict[str, object]] = []
    for match_number, match_rows in cleaned.groupby("match_number", sort=True):
        source_urls = match_rows["source_url"].drop_duplicates().tolist()
        if len(source_urls) != 1:
            raise SourceError(f"PMSR match {match_number} has inconsistent source URLs.")
        expected_teams = match_rows["team"].tolist()
        summary = parse_pmsr_match_summary(pdf_loader(source_urls[0]), expected_teams)
        penalty_lookup = match_rows.set_index("team")["penalties_awarded"].to_dict()
        for team_name in expected_teams:
            opponent_team = next(name for name in expected_teams if name != team_name)
            rows.append(
                {
                    "match_number": int(match_number),
                    "tournament_name": "2026 FIFA World Cup",
                    "year": 2026,
                    "team_name": team_name,
                    "opponent_team_name": opponent_team,
                    "penalties_awarded": int(penalty_lookup[team_name]),
                    **summary[team_name],
                    "source_name": "FIFA Post-Match Summary Report",
                    "source_version": PMSR_FEATURE_VERSION,
                    "source_url": source_urls[0],
                }
            )
    return pd.DataFrame(rows).sort_values(["match_number", "team_name"], kind="stable").reset_index(drop=True)
