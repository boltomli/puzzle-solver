"""Deduction Service — orchestrates AI and local deduction workflows.

Coordinates between LLMService, PromptEngine, and the Project data model
to produce deduction candidates for user review.
"""

from __future__ import annotations

import json
import re

from loguru import logger

from src.models.puzzle import (
    ConfidenceLevel,
    Deduction,
    Project,
    Script,
    TimeSlot,
)
from src.services.llm_service import LLMService
from src.services.prompt_engine import PromptEngine


def _matches_ts(value: str, ts: TimeSlot) -> bool:
    """Check if a time_slot value matches a TimeSlot (by ID or label for back-compat)."""
    return value == ts.id or value == ts.label


def _extract_json(raw: str) -> dict:
    """Extract and parse JSON from LLM response that may contain markdown fencing."""
    text = raw.strip()

    # 1. Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Try finding first { to last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    logger.error("_extract_json: failed to parse LLM response (len={}): {!r}", len(raw), raw[:300])
    raise ValueError(f"无法从 AI 响应中提取有效 JSON。响应内容: {text[:200]}")


class DeductionService:
    """Orchestrates AI-powered and local elimination-based deductions."""

    def __init__(self):
        self.llm = LLMService()
        self.prompt_engine = PromptEngine()

    async def run_deduction(
        self,
        project: Project,
        ts_by_id: dict[str, TimeSlot] | None = None,
    ) -> dict:
        """Run a full AI deduction pass.

        Args:
            project: The project to run deduction on.
            ts_by_id: Optional pre-built ts.id→TimeSlot map (e.g. from CacheManager).
                Falls back to building from the project if not provided.

        Returns parsed response dict with deductions, new entities, contradictions.
        """
        logger.info(
            "run_deduction: project={!r} chars={} locs={} scripts={} facts={}",
            project.name,
            len(project.characters),
            len(project.locations),
            len(project.scripts),
            len(project.facts),
        )
        system_prompt, user_prompt = self.prompt_engine.build_deduction_prompt(
            project, ts_by_id=ts_by_id
        )
        logger.debug("run_deduction: prompt built (user_prompt_len={})", len(user_prompt))
        try:
            raw = await self.llm.chat(system_prompt, user_prompt)
            result = _extract_json(raw)
            logger.info(
                "run_deduction: got deductions={} new_chars={} new_locs={} contradictions={}",
                len(result.get("deductions", [])),
                len(result.get("new_characters_detected", [])),
                len(result.get("new_locations_detected", [])),
                len(result.get("contradictions_detected", [])),
            )
            return result
        except Exception:
            logger.exception("run_deduction: failed for project={!r}", project.name)
            raise

    async def run_focused_deduction(
        self,
        project: Project,
        focus_filter: dict,
        ts_by_id: dict[str, TimeSlot] | None = None,
    ) -> dict:
        """Run a focused AI deduction pass limited to specific dimensions.

        Similar to run_deduction() but passes focus_filter to PromptEngine so the
        AI only reasons about the selected characters/locations/time_slots.

        Args:
            project: The project to run deduction on.
            focus_filter: Dict with optional keys:
                - ``character_ids``: list of character IDs to focus on
                - ``location_ids``: list of location IDs to focus on
                - ``time_slots``: list of time slots to focus on
            ts_by_id: Optional pre-built ts.id→TimeSlot map (e.g. from CacheManager).
                Falls back to building from the project if not provided.

        Returns:
            Parsed response dict with deductions, new entities, contradictions.
        """
        logger.info(
            "run_focused_deduction: project={!r} focus_filter={}",
            project.name,
            focus_filter,
        )
        system_prompt, user_prompt = self.prompt_engine.build_deduction_prompt(
            project, focus_filter=focus_filter, ts_by_id=ts_by_id
        )
        logger.debug("run_focused_deduction: prompt built (user_prompt_len={})", len(user_prompt))
        try:
            raw = await self.llm.chat(system_prompt, user_prompt)
            result = _extract_json(raw)
            logger.info(
                "run_focused_deduction: got deductions={} new_chars={} new_locs={} contradictions={}",
                len(result.get("deductions", [])),
                len(result.get("new_characters_detected", [])),
                len(result.get("new_locations_detected", [])),
                len(result.get("contradictions_detected", [])),
            )
            return result
        except Exception:
            logger.exception("run_focused_deduction: failed for project={!r}", project.name)
            raise

    async def analyze_script(
        self,
        project: Project,
        script: Script,
        ts_by_id: dict[str, TimeSlot] | None = None,
    ) -> dict:
        """Run a lightweight script analysis.

        Args:
            project: The project to run analysis on.
            script: The script to analyze.
            ts_by_id: Optional pre-built ts.id→TimeSlot map (e.g. from CacheManager).
                Falls back to building from the project if not provided.

        Returns parsed response with characters, locations, time refs, direct facts.
        """
        logger.info(
            "analyze_script: project={!r} script={!r} (len={})",
            project.name,
            script.title or "Untitled",
            len(script.raw_text),
        )
        system_prompt, user_prompt = self.prompt_engine.build_script_analysis_prompt(
            project, script, ts_by_id=ts_by_id
        )
        logger.debug("analyze_script: prompt built (user_prompt_len={})", len(user_prompt))
        try:
            raw = await self.llm.chat(system_prompt, user_prompt)
            result = _extract_json(raw)
            logger.info(
                "analyze_script: got chars={} locs={} time_refs={} direct_facts={}",
                len(result.get("characters_mentioned", [])),
                len(result.get("locations_mentioned", [])),
                len(result.get("time_references", [])),
                len(result.get("direct_facts", [])),
            )
            return result
        except Exception:
            logger.exception("analyze_script: failed for script={!r}", script.title or "Untitled")
            raise

    @staticmethod
    def run_cascade(project: Project) -> list[Deduction]:
        """Run local elimination-based cascade deduction (no AI needed).

        Checks two strategies:
        1. For each unfilled (character, time_slot): if only one location is possible → certain.
        2. For each unfilled (location, time_slot): if only one character is possible → certain.

        Returns list of new certain deductions.
        """
        logger.info(
            "run_cascade: project={!r} chars={} locs={} slots={} facts={}",
            project.name,
            len(project.characters),
            len(project.locations),
            len(project.time_slots),
            len(project.facts),
        )
        new_deductions: list[Deduction] = []

        # Strategy 1: For each unfilled character+time, check possible locations
        for char in project.characters:
            for ts in project.time_slots:
                if any(
                    f.character_id == char.id and _matches_ts(f.time_slot, ts)
                    for f in project.facts
                ):
                    continue

                possible = []
                for loc in project.locations:
                    occupied = any(
                        f.location_id == loc.id
                        and _matches_ts(f.time_slot, ts)
                        and f.character_id != char.id
                        for f in project.facts
                    )
                    rejected = any(
                        r.character_id == char.id
                        and r.location_id == loc.id
                        and _matches_ts(r.time_slot, ts)
                        for r in project.rejections
                    )
                    if not occupied and not rejected:
                        possible.append(loc)

                if len(possible) == 1:
                    ded = Deduction(
                        character_id=char.id,
                        location_id=possible[0].id,
                        time_slot=ts.id,
                        confidence=ConfidenceLevel.certain,
                        reasoning=(
                            f"消元法：在 {ts.label}，{char.name} 只剩一个可能的地点 "
                            f"{possible[0].name}"
                        ),
                    )
                    new_deductions.append(ded)
                    logger.debug(
                        "run_cascade: strategy1 {} @ {} → {}", char.name, ts.label, possible[0].name
                    )

        # Strategy 2: For each unfilled location+time, check possible characters
        for loc in project.locations:
            for ts in project.time_slots:
                if any(
                    f.location_id == loc.id and _matches_ts(f.time_slot, ts) for f in project.facts
                ):
                    continue

                possible = []
                for char in project.characters:
                    elsewhere = any(
                        f.character_id == char.id
                        and _matches_ts(f.time_slot, ts)
                        and f.location_id != loc.id
                        for f in project.facts
                    )
                    rejected = any(
                        r.character_id == char.id
                        and r.location_id == loc.id
                        and _matches_ts(r.time_slot, ts)
                        for r in project.rejections
                    )
                    if not elsewhere and not rejected:
                        possible.append(char)

                if len(possible) == 1:
                    already = any(
                        d.character_id == possible[0].id
                        and d.location_id == loc.id
                        and _matches_ts(d.time_slot, ts)
                        for d in new_deductions
                    )
                    if not already:
                        ded = Deduction(
                            character_id=possible[0].id,
                            location_id=loc.id,
                            time_slot=ts.id,
                            confidence=ConfidenceLevel.certain,
                            reasoning=(
                                f"消元法：在 {ts.label}，{loc.name} 只有 "
                                f"{possible[0].name} 可以在此"
                            ),
                        )
                        new_deductions.append(ded)
                        logger.debug(
                            "run_cascade: strategy2 {} @ {} → {}",
                            possible[0].name,
                            ts.label,
                            loc.name,
                        )

        logger.info("run_cascade: found {} new certain deduction(s)", len(new_deductions))
        return new_deductions
