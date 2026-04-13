"""Deduction Service — orchestrates AI and local deduction workflows.

Coordinates between LLMService, PromptEngine, and the Project data model
to produce deduction candidates for user review.
"""

import json
import re

from src.models.puzzle import (
    ConfidenceLevel,
    Deduction,
    Project,
    Script,
)
from src.services.llm_service import LLMService
from src.services.prompt_engine import PromptEngine


def _extract_json(raw: str) -> dict:
    """Extract and parse JSON from LLM response that may contain markdown fencing."""
    text = raw.strip()

    # 1. Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try extracting from markdown code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Try finding first { to last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(f"无法从 AI 响应中提取有效 JSON。响应内容: {text[:200]}")


class DeductionService:
    """Orchestrates AI-powered and local elimination-based deductions."""

    def __init__(self):
        self.llm = LLMService()
        self.prompt_engine = PromptEngine()

    async def run_deduction(self, project: Project) -> dict:
        """Run a full AI deduction pass.

        Returns parsed response dict with deductions, new entities, contradictions.
        """
        system_prompt, user_prompt = self.prompt_engine.build_deduction_prompt(project)
        raw = await self.llm.chat(system_prompt, user_prompt)
        return _extract_json(raw)

    async def analyze_script(self, project: Project, script: Script) -> dict:
        """Run a lightweight script analysis.

        Returns parsed response with characters, locations, time refs, direct facts.
        """
        system_prompt, user_prompt = self.prompt_engine.build_script_analysis_prompt(
            project, script
        )
        raw = await self.llm.chat(system_prompt, user_prompt)
        return _extract_json(raw)

    @staticmethod
    def run_cascade(project: Project) -> list[Deduction]:
        """Run local elimination-based cascade deduction (no AI needed).

        Checks two strategies:
        1. For each unfilled (character, time_slot): if only one location is possible → certain.
        2. For each unfilled (location, time_slot): if only one character is possible → certain.

        Returns list of new certain deductions.
        """
        new_deductions: list[Deduction] = []

        # Strategy 1: For each unfilled character+time, check possible locations
        for char in project.characters:
            for ts in project.time_slots:
                # Skip if already has a fact
                if any(
                    f.character_id == char.id and f.time_slot == ts
                    for f in project.facts
                ):
                    continue

                # Find possible locations
                possible = []
                for loc in project.locations:
                    # Is another char confirmed here at this time?
                    occupied = any(
                        f.location_id == loc.id
                        and f.time_slot == ts
                        and f.character_id != char.id
                        for f in project.facts
                    )
                    # Was this rejected?
                    rejected = any(
                        r.character_id == char.id
                        and r.location_id == loc.id
                        and r.time_slot == ts
                        for r in project.rejections
                    )
                    if not occupied and not rejected:
                        possible.append(loc)

                if len(possible) == 1:
                    ded = Deduction(
                        character_id=char.id,
                        location_id=possible[0].id,
                        time_slot=ts,
                        confidence=ConfidenceLevel.certain,
                        reasoning=(
                            f"消元法：在 {ts}，{char.name} 只剩一个可能的地点 "
                            f"{possible[0].name}"
                        ),
                    )
                    new_deductions.append(ded)

        # Strategy 2: For each unfilled location+time, check possible characters
        for loc in project.locations:
            for ts in project.time_slots:
                # Is it already occupied?
                if any(
                    f.location_id == loc.id and f.time_slot == ts
                    for f in project.facts
                ):
                    continue

                possible = []
                for char in project.characters:
                    # Is this char confirmed elsewhere at this time?
                    elsewhere = any(
                        f.character_id == char.id
                        and f.time_slot == ts
                        and f.location_id != loc.id
                        for f in project.facts
                    )
                    # Was this rejected?
                    rejected = any(
                        r.character_id == char.id
                        and r.location_id == loc.id
                        and r.time_slot == ts
                        for r in project.rejections
                    )
                    if not elsewhere and not rejected:
                        possible.append(char)

                if len(possible) == 1:
                    # Check we haven't already deduced this from strategy 1
                    already = any(
                        d.character_id == possible[0].id
                        and d.location_id == loc.id
                        and d.time_slot == ts
                        for d in new_deductions
                    )
                    if not already:
                        ded = Deduction(
                            character_id=possible[0].id,
                            location_id=loc.id,
                            time_slot=ts,
                            confidence=ConfidenceLevel.certain,
                            reasoning=(
                                f"消元法：在 {ts}，{loc.name} 只有 "
                                f"{possible[0].name} 可以在此"
                            ),
                        )
                        new_deductions.append(ded)

        return new_deductions
