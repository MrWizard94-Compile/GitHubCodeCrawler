"""Curated search missions. First mission: feed the self-improvement swarm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SearchSpec:
    """One GitHub code-search run."""

    name: str
    query_text: str
    language: Optional[str] = "python"
    min_stars: int = 100
    extension: Optional[str] = None
    filename: Optional[str] = None
    path: Optional[str] = None
    why: str = ""
    maps_to: str = ""  # which improve-swarm concept this feeds


# Mission 0 — improve the improver (WPAI improve-swarm / evolutionary control plane)
SELF_IMPROVEMENT_SPECS: List[SearchSpec] = [
    SearchSpec(
        name="tournament-selection",
        query_text="tournament_selection fitness",
        language="python",
        min_stars=50,
        why="Survivor selection without always taking pure top-1 (diversity).",
        maps_to="Select-WpaiImproveDiverseTop / survivor ranking",
    ),
    SearchSpec(
        name="nsga-diversity",
        query_text="crowding_distance nsga",
        language="python",
        min_stars=50,
        why="Multi-objective diversity when scores plateau.",
        maps_to="diversity selection + score desaturation",
    ),
    SearchSpec(
        name="elitism-hall-of-fame",
        query_text="HallOfFame elitism",
        language="python",
        min_stars=50,
        why="Never forget proven genes across generations.",
        maps_to="elite.json / Update-WpaiImproveEliteArchive",
    ),
    SearchSpec(
        name="gene-mutation",
        query_text="def mutate crossover",
        language="python",
        min_stars=100,
        why="Mutation/crossover patterns for next-gen catalogs.",
        maps_to="Invoke-WpaiImproveMutate",
    ),
    SearchSpec(
        name="bandit-explore",
        query_text="UCB1 bandit",
        language="python",
        min_stars=50,
        why="Exploration when genes have no outcomes yet.",
        maps_to="explore_bonus in Get-WpaiImproveFitness",
    ),
    SearchSpec(
        name="experiment-tracking",
        query_text="mlflow log_metric trial",
        language="python",
        min_stars=100,
        why="Trial metrics / experiment provenance patterns.",
        maps_to="outcomes.jsonl + evidence tiers",
    ),
    SearchSpec(
        name="self-play-loop",
        query_text="self-improve evaluate",
        language="python",
        min_stars=20,
        why="Outer loop: propose → test → learn.",
        maps_to="Invoke-WpaiImproveUnleash / AutoReview",
    ),
    SearchSpec(
        name="property-test",
        query_text="@given st.integers",
        language="python",
        min_stars=100,
        why="Property-based falsification (Hypothesis library style).",
        maps_to="probe=property-quick / fail-closed checks",
    ),
    SearchSpec(
        name="retry-backoff",
        query_text="exponential_backoff retry",
        language="python",
        min_stars=100,
        why="Reliable probes under rate limits.",
        maps_to="auto-experiment + GitHub crawler client",
    ),
    SearchSpec(
        name="fitness-landscape",
        query_text="def fitness population evolutionary",
        language="python",
        min_stars=50,
        why="Composable fitness evaluation of individuals.",
        maps_to="Get-WpaiImproveFitness v2/v3",
    ),
]


PROFILES: Dict[str, List[SearchSpec]] = {
    "self-improvement": SELF_IMPROVEMENT_SPECS,
    "improve-swarm": SELF_IMPROVEMENT_SPECS,  # alias
}


def get_profile(name: str) -> List[SearchSpec]:
    key = (name or "").strip().lower()
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise KeyError(f"unknown profile {name!r}; choose one of: {known}")
    return list(PROFILES[key])
