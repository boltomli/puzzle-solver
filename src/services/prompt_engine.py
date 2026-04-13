"""Prompt Engine — assembles system and user prompts for AI deduction.

Uses templates defined in the architecture doc to build structured prompts
that include all project context: characters, locations, facts, rejections, scripts.
"""

from src.models.puzzle import Project, Script
from src.services.config import load_config


class PromptEngine:
    """Builds structured prompts for the AI deduction engine."""

    # Default system prompt (from architecture.md section 2.1)
    DEFAULT_SYSTEM_PROMPT = (
        "You are an expert deduction engine for script-based mystery games. "
        "Your task is to analyze scene scripts, known facts, game rules, and constraints "
        "to deduce which character was at which location at which time.\n\n"
        "CORE RULES:\n"
        "- Only make deductions that are logically supported by the evidence provided.\n"
        "- Clearly distinguish between CERTAIN deductions (only one possibility) and "
        "PROBABLE deductions (most likely but not proven).\n"
        "- Never suggest a deduction that appears in the REJECTED list — those have been "
        "explicitly ruled out.\n"
        "- 严格禁止重复已确认的事实或已被拒绝的推断。只输出全新的、未知的推断。\n"
        "- Pay close attention to GAME RULES — they define hard constraints.\n"
        "- Scripts may describe events OUT OF CHRONOLOGICAL ORDER. Use internal clues "
        "(dialogue references, time mentions, lighting, etc.) to determine actual timing.\n"
        "- Character aliases: A character may be referred to by different names in different "
        "scripts. Use the alias list to unify references.\n"
        "- Scripts may be in any language. Analyze them in their original language and "
        "provide reasoning in Chinese.\n\n"
        "DEDUCTION TECHNIQUES:\n"
        "1. Direct evidence: A script explicitly states a character is at a location at a time.\n"
        "2. Elimination: If all but one character/location are accounted for at a time slot, "
        "the remaining one is determined.\n"
        "3. Temporal reasoning: If a character is seen at Location A at 15:00 and Location B "
        "at 17:00, they could not be at Location C at 15:00 or 17:00.\n"
        "4. Dialogue analysis: Characters may reference where they were, where others were, "
        "or events that constrain placement.\n"
        "5. Contradiction detection: If a proposed placement violates a game rule or known "
        "fact, flag it.\n\n"
        "OUTPUT FORMAT:\n"
        "Respond with a JSON object following the exact schema provided in the user message."
    )

    def build_deduction_prompt(
        self,
        project: Project,
        focus_filter: dict | None = None,
    ) -> tuple[str, str]:
        """Build system + user prompt for a full deduction pass.

        Args:
            project: The project to build the prompt for.
            focus_filter: Optional dict with optional keys:
                - ``character_ids``: list of character IDs to focus on
                - ``location_ids``: list of location IDs to focus on
                - ``time_slots``: list of time slots to focus on
                When provided, the UNFILLED SLOTS section only lists matching cells
                and a FOCUS AREA section is added to guide the AI.

        Returns:
            (system_prompt, user_prompt) tuple.
        """
        config = load_config()
        system_prompt = config.get("system_prompt_override") or self.DEFAULT_SYSTEM_PROMPT
        # Use override only if non-empty
        if not system_prompt.strip():
            system_prompt = self.DEFAULT_SYSTEM_PROMPT

        user_prompt = self._build_user_prompt(project, focus_filter=focus_filter)
        return system_prompt, user_prompt

    def build_script_analysis_prompt(self, project: Project, script: Script) -> tuple[str, str]:
        """Build prompt for analyzing a single new script.

        Returns:
            (system_prompt, user_prompt) tuple.
        """
        system_prompt = (
            "You are an expert script analyzer for mystery games. "
            "Analyze the given script and extract characters, locations, time references, "
            "and direct facts. Respond only with the requested JSON."
        )
        user_prompt = self._build_script_analysis_user_prompt(project, script)
        return system_prompt, user_prompt

    def _build_user_prompt(self, project: Project, focus_filter: dict | None = None) -> str:
        """Assemble the full deduction user prompt."""
        parts: list[str] = []

        # Game info
        parts.append(f"## GAME: {project.name}")
        if project.description:
            parts.append(project.description)

        # Time slots
        parts.append(f"\n## TIME SLOTS\n{', '.join(project.time_slots)}")

        # Characters
        parts.append("\n## CHARACTERS")
        for char in project.characters:
            line = f"- **{char.name}** (ID: {char.id})"
            if char.aliases:
                line += f" — also known as: {', '.join(char.aliases)}"
            if char.description:
                line += f" — {char.description}"
            parts.append(line)

        # Locations
        parts.append("\n## LOCATIONS")
        for loc in project.locations:
            line = f"- **{loc.name}** (ID: {loc.id})"
            if loc.aliases:
                line += f" — also known as: {', '.join(loc.aliases)}"
            parts.append(line)

        # Rules/hints
        parts.append("\n## GAME RULES & HINTS")
        for hint in project.hints:
            parts.append(f"- [{hint.type.value.upper()}] {hint.content}")

        # Confirmed facts
        parts.append("\n## CONFIRMED FACTS")
        for fact in project.facts:
            char = next((c for c in project.characters if c.id == fact.character_id), None)
            loc = next((l for l in project.locations if l.id == fact.location_id), None)
            char_name = char.name if char else fact.character_id
            loc_name = loc.name if loc else fact.location_id
            parts.append(f"- ✅ **{char_name}** was at **{loc_name}** at **{fact.time_slot}**")

        # Rejections
        parts.append("\n## REJECTED DEDUCTIONS (以下推断已被用户明确拒绝，绝对不要再次建议：)")
        for rej in project.rejections:
            char = next((c for c in project.characters if c.id == rej.character_id), None)
            loc = next((l for l in project.locations if l.id == rej.location_id), None)
            char_name = char.name if char else rej.character_id
            loc_name = loc.name if loc else rej.location_id
            parts.append(
                f"- ❌ {char_name} was NOT at {loc_name} at {rej.time_slot} (reason: {rej.reason})"
            )

        # Focus area section (when focus_filter is provided)
        if focus_filter:
            focus_lines: list[str] = []
            filter_char_ids: list[str] = focus_filter.get("character_ids") or []
            filter_loc_ids: list[str] = focus_filter.get("location_ids") or []
            filter_time_slots: list[str] = focus_filter.get("time_slots") or []

            if filter_char_ids:
                char_names = [
                    c.name for c in project.characters if c.id in filter_char_ids
                ]
                if char_names:
                    focus_lines.append(f"- 人物: {', '.join(char_names)}")
            if filter_loc_ids:
                loc_names = [
                    l.name for l in project.locations if l.id in filter_loc_ids
                ]
                if loc_names:
                    focus_lines.append(f"- 地点: {', '.join(loc_names)}")
            if filter_time_slots:
                focus_lines.append(f"- 时间: {', '.join(filter_time_slots)}")

            if focus_lines:
                parts.append("\n## 重点推断范围")
                parts.append("请重点推断以下维度的组合：")
                parts.extend(focus_lines)

        # Unfilled slots (filtered when focus_filter is provided)
        parts.append("\n## UNFILLED SLOTS TO DEDUCE")

        filter_char_ids_set: set[str] = set(
            (focus_filter or {}).get("character_ids") or []
        )
        filter_time_slots_set: set[str] = set(
            (focus_filter or {}).get("time_slots") or []
        )

        for char in project.characters:
            # Skip character if focus filter specifies characters and this one is not in it
            if filter_char_ids_set and char.id not in filter_char_ids_set:
                continue
            for ts in project.time_slots:
                # Skip time slot if focus filter specifies time slots and this one is not in it
                if filter_time_slots_set and ts not in filter_time_slots_set:
                    continue
                has_fact = any(
                    f.character_id == char.id and f.time_slot == ts for f in project.facts
                )
                if not has_fact:
                    parts.append(f"- {char.name} at {ts}: ???")

        # Scripts
        parts.append("\n## SCRIPT EVIDENCE")
        for script in project.scripts:
            parts.append(
                f"\n### Script: \"{script.title or 'Untitled'}\" "
                f"(#{script.metadata.source_order or '?'})"
            )
            if script.metadata.stated_time:
                parts.append(f"Stated time: {script.metadata.stated_time}")
            if script.metadata.stated_location:
                parts.append(f"Stated location: {script.metadata.stated_location}")
            parts.append(f"\n```\n{script.raw_text}\n```")

        # Task instruction
        parts.append("\n---\n## YOUR TASK")
        parts.append("Analyze all evidence above. Produce deductions for unfilled slots.")
        parts.append("Respond with ONLY a JSON object in this format:")
        parts.append(
            '```json\n'
            '{\n'
            '  "deductions": [\n'
            '    {\n'
            '      "character_id": "<uuid>",\n'
            '      "location_id": "<uuid>",\n'
            '      "time_slot": "HH:MM",\n'
            '      "confidence": "certain|high|medium|low",\n'
            '      "reasoning": "Step-by-step explanation",\n'
            '      "supporting_script_ids": ["<uuid>"],\n'
            '      "depends_on_fact_ids": ["<uuid>"]\n'
            '    }\n'
            '  ],\n'
            '  "new_characters_detected": [\n'
            '    {"name": "string", "found_in_script_id": "<uuid>", "context": "string"}\n'
            '  ],\n'
            '  "new_locations_detected": [\n'
            '    {"name": "string", "found_in_script_id": "<uuid>", "context": "string"}\n'
            '  ],\n'
            '  "contradictions_detected": [\n'
            '    {"description": "string", "involved_fact_ids": [], "involved_script_ids": []}\n'
            '  ],\n'
            '  "notes": "string"\n'
            '}\n'
            '```'
        )
        parts.append("Focus on CERTAIN and HIGH confidence deductions first.")

        return "\n".join(parts)

    def _build_script_analysis_user_prompt(self, project: Project, script: Script) -> str:
        """Assemble the script analysis user prompt."""
        parts: list[str] = []

        parts.append("## NEW SCRIPT ANALYSIS")
        parts.append(f'\nA new script has been added to the game "{project.name}".')

        # Known characters
        parts.append("\n### Known Characters")
        for char in project.characters:
            line = f"- {char.name}"
            if char.aliases:
                line += f" (aliases: {', '.join(char.aliases)})"
            parts.append(line)

        # Known locations
        parts.append("\n### Known Locations")
        for loc in project.locations:
            line = f"- {loc.name}"
            if loc.aliases:
                line += f" (aliases: {', '.join(loc.aliases)})"
            parts.append(line)

        # Known time slots
        parts.append(f"\n### Known Time Slots\n{', '.join(project.time_slots)}")

        # Confirmed facts
        parts.append("\n### Confirmed Facts")
        for fact in project.facts:
            char = next((c for c in project.characters if c.id == fact.character_id), None)
            loc = next((l for l in project.locations if l.id == fact.location_id), None)
            char_name = char.name if char else fact.character_id
            loc_name = loc.name if loc else fact.location_id
            parts.append(f"- {char_name} was at {loc_name} at {fact.time_slot}")

        # Game rules & hints
        parts.append("\n### Game Rules & Hints")
        for hint in project.hints:
            parts.append(f"- [{hint.type.value.upper()}] {hint.content}")

        # Other scripts (for cross-reference)
        other_scripts = [s for s in project.scripts if s.id != script.id]
        if other_scripts:
            parts.append("\n### Other Scripts (for cross-reference)")
            for other in other_scripts:
                parts.append(
                    f'\n#### Script: "{other.title or "Untitled"}" '
                    f"(#{other.metadata.source_order or '?'})"
                )
                parts.append(f"```\n{other.raw_text}\n```")

        # New script text
        parts.append(f"\n### New Script Text\n```\n{script.raw_text}\n```")

        # Response format
        parts.append('\nAnalyze this script and respond with ONLY this JSON:')
        parts.append(
            '```json\n'
            '{\n'
            '  "characters_mentioned": [\n'
            '    {\n'
            '      "character_id": "<uuid or null if new>",\n'
            '      "name": "string",\n'
            '      "is_new": true,\n'
            '      "context": "How they appear in the script"\n'
            '    }\n'
            '  ],\n'
            '  "locations_mentioned": [\n'
            '    {\n'
            '      "location_id": "<uuid or null if new>",\n'
            '      "name": "string",\n'
            '      "is_new": true,\n'
            '      "context": "How it appears in the script"\n'
            '    }\n'
            '  ],\n'
            '  "time_references": [\n'
            '    {\n'
            '      "time_slot": "HH:MM or null",\n'
            '      "reference_text": "The text that indicates this time",\n'
            '      "is_explicit": true\n'
            '    }\n'
            '  ],\n'
            '  "direct_facts": [\n'
            '    {\n'
            '      "character_name": "string",\n'
            '      "location_name": "string",\n'
            '      "time_slot": "HH:MM",\n'
            '      "confidence": "certain|high|medium|low",\n'
            '      "evidence": "Quote or explanation from the script"\n'
            '    }\n'
            '  ],\n'
            '  "alias_candidates": [\n'
            '    {\n'
            '      "name_in_script": "string",\n'
            '      "might_be_character_id": "<uuid>",\n'
            '      "reasoning": "Why this might be an alias"\n'
            '    }\n'
            '  ]\n'
            '}\n'
            '```'
        )

        return "\n".join(parts)
