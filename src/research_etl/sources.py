from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from research_etl.paths import ProjectPaths


class SourceError(RuntimeError):
    """Raised when an external source cannot be fetched or read safely."""


USER_AGENT = "argentina-egypt-research-etl/0.1 (+local-research-pipeline)"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(paths: ProjectPaths) -> dict[str, Any]:
    if not paths.config_file.exists():
        raise SourceError(f"Missing source configuration: {paths.config_file}")
    return json.loads(paths.config_file.read_text(encoding="utf-8"))


def write_json_atomic(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)


def download_file(
    *,
    source_id: str,
    url: str,
    destination: Path,
    root: Path,
    force: bool = False,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Fetch one immutable source file with an atomic local write and checksum."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    status = "downloaded"
    if destination.exists() and not force:
        status = "cached"
    else:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        temporary = destination.with_suffix(destination.suffix + ".partial")
        try:
            with urlopen(request, timeout=timeout_seconds) as response, temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        except (HTTPError, URLError, TimeoutError) as error:
            temporary.unlink(missing_ok=True)
            raise SourceError(f"Could not fetch {source_id} from {url}: {error}") from error
        temporary.replace(destination)

    return {
        "source_id": source_id,
        "url": url,
        "path": str(destination.relative_to(root)).replace("\\", "/"),
        "status": status,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "retrieved_at": utc_now(),
    }


def seed_manual_inputs(paths: ProjectPaths, *, force: bool = False) -> list[dict[str, Any]]:
    """Copy versioned templates into the manual-review lane without overwriting work."""

    paths.ensure_directories()
    seeds = {
        "focal_events_seed.csv": "focal_events_reviewed.csv",
        "incidents_seed.csv": "incidents_reviewed.csv",
    }
    records: list[dict[str, Any]] = []
    for source_name, target_name in seeds.items():
        source = paths.reference_dir / source_name
        target = paths.raw_dir / "manual" / target_name
        if not source.exists():
            raise SourceError(f"Missing versioned reference input: {source}")
        if target.exists() and not force:
            status = "preserved"
        else:
            shutil.copy2(source, target)
            status = "seeded"
        records.append(
            {
                "source_id": f"reference_{source.stem}",
                "url": f"file://{str(source.relative_to(paths.root)).replace('\\', '/')}",
                "path": str(target.relative_to(paths.root)).replace("\\", "/"),
                "status": status,
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
                "retrieved_at": utc_now(),
            }
        )
    return records


def stage_reference_file(
    paths: ProjectPaths,
    *,
    source_id: str,
    reference: Path,
    destination: Path,
) -> dict[str, Any]:
    """Stage a compact versioned source snapshot without treating it as manual input."""

    if not reference.exists():
        raise SourceError(f"Missing versioned reference input: {reference}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(reference)
    if destination.exists() and sha256_file(destination) == source_hash:
        status = "cached"
    else:
        shutil.copy2(reference, destination)
        status = "staged"
    return {
        "source_id": source_id,
        "url": f"file://{str(reference.relative_to(paths.root)).replace('\\', '/')}",
        "path": str(destination.relative_to(paths.root)).replace("\\", "/"),
        "status": status,
        "bytes": destination.stat().st_size,
        "sha256": source_hash,
        "retrieved_at": utc_now(),
    }


def extract_sources(
    paths: ProjectPaths,
    *,
    include_statsbomb: bool = False,
    include_statsbomb_events: bool = False,
    include_statsbomb_history: bool = False,
    force_download: bool = False,
) -> list[dict[str, Any]]:
    """Extract source files required by the pipeline and persist a run manifest."""

    if include_statsbomb_events and not include_statsbomb:
        include_statsbomb = True

    paths.ensure_directories()
    config = load_config(paths)
    # Download refreshes must never reset human-reviewed inputs. Only `init
    # --force` is allowed to replace those files with versioned seeds.
    records = seed_manual_inputs(paths, force=False)

    focal = config["focal_match"]
    records.append(
        download_file(
            source_id=focal["source_id"],
            url=focal["url"],
            destination=paths.root / focal["target"],
            root=paths.root,
            force=force_download,
        )
    )

    historical = config["historical_world_cup"]
    for filename in historical["files"]:
        records.append(
            download_file(
                source_id=historical["source_id"],
                url=f"{historical['base_url']}/{filename}",
                destination=paths.root / historical["target_dir"] / filename,
                root=paths.root,
                force=force_download,
            )
        )

    strength = config["team_strength"]
    records.append(
        download_file(
            source_id=strength["source_id"],
            url=strength["url"],
            destination=paths.root / strength["target"],
            root=paths.root,
            force=force_download,
        )
    )

    pmsr = config["pmsr_2026"]
    records.append(
        stage_reference_file(
            paths,
            source_id=pmsr["source_id"],
            reference=paths.root / pmsr["reference_target"],
            destination=paths.root / pmsr["raw_target"],
        )
    )

    focal_strength = config["focal_team_strength"]
    records.append(
        stage_reference_file(
            paths,
            source_id=focal_strength["source_id"],
            reference=paths.root / focal_strength["reference_target"],
            destination=paths.root / focal_strength["raw_target"],
        )
    )

    if include_statsbomb:
        records.extend(
            _extract_statsbomb(
                paths,
                config["statsbomb_open_data"],
                include_events=include_statsbomb_events,
                force=force_download,
            )
        )

    if include_statsbomb_history:
        records.extend(
            _extract_statsbomb_history(
                paths,
                config["statsbomb_history"],
                force=force_download,
            )
        )

    write_json_atomic(
        {
            "pipeline": "research_etl.extract",
            "created_at": utc_now(),
            "records": records,
        },
        paths.manifests_dir / "extraction_manifest.json",
    )
    return records


def _extract_statsbomb(
    paths: ProjectPaths,
    source: dict[str, Any],
    *,
    include_events: bool,
    force: bool,
) -> list[dict[str, Any]]:
    """Optionally stage high-resolution StatsBomb World Cup JSON files."""

    target_dir = paths.root / source["target_dir"]
    records = [
        download_file(
            source_id=source["source_id"],
            url=f"{source['base_url']}/competitions.json",
            destination=target_dir / "competitions.json",
            root=paths.root,
            force=force,
        )
    ]

    for season_id in source["season_ids"]:
        matches_path = target_dir / "matches" / str(source["competition_id"]) / f"{season_id}.json"
        records.append(
            download_file(
                source_id=source["source_id"],
                url=f"{source['base_url']}/matches/{source['competition_id']}/{season_id}.json",
                destination=matches_path,
                root=paths.root,
                force=force,
            )
        )
        if not include_events:
            continue

        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        for match in matches:
            match_id = match["match_id"]
            records.append(
                download_file(
                    source_id=source["source_id"],
                    url=f"{source['base_url']}/events/{match_id}.json",
                    destination=target_dir / "events" / f"{match_id}.json",
                    root=paths.root,
                    force=force,
                )
            )
    return records


def _extract_statsbomb_history(
    paths: ProjectPaths,
    source: dict[str, Any],
    *,
    force: bool,
) -> list[dict[str, Any]]:
    """Cache the pinned metadata and event streams for the broader baseline."""

    target_dir = paths.root / source["raw_target_dir"]
    records = [
        download_file(
            source_id=source["source_id"],
            url=f"{source['base_url']}/competitions.json",
            destination=target_dir / "competitions.json",
            root=paths.root,
            force=force,
        )
    ]
    for pair in source["pairs"]:
        competition_id = int(pair["competition_id"])
        season_id = int(pair["season_id"])
        matches_path = target_dir / "matches" / str(competition_id) / f"{season_id}.json"
        records.append(
            download_file(
                source_id=source["source_id"],
                url=f"{source['base_url']}/matches/{competition_id}/{season_id}.json",
                destination=matches_path,
                root=paths.root,
                force=force,
            )
        )
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        for match in matches:
            match_id = match["match_id"]
            records.append(
                download_file(
                    source_id=source["source_id"],
                    url=f"{source['base_url']}/events/{match_id}.json",
                    destination=target_dir / "events" / f"{match_id}.json",
                    root=paths.root,
                    force=force,
                )
            )
    return records
