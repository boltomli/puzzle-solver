# Puzzle Solver — Architecture & Design Document

## Table of Contents
1. [Data Model Overview](#1-data-model-overview)
2. [AI Prompt Strategy](#2-ai-prompt-strategy)
3. [Deduction Workflow](#3-deduction-workflow)
4. [Edge Cases & Considerations](#4-edge-cases--considerations)

---

## 1. Data Model Overview

Full JSON Schema: [`data-model.json`](./data-model.json)

### Entity Relationship Summary

```
Project (root)
├── time_slots[]          — predefined time slots (e.g., "15:00", "16:00")
├── characters[]          — Character { id, name, aliases[], status, description }
├── locations[]           — Location  { id, name, aliases[], description }
├── scripts[]             — Script    { id, title, raw_text, metadata }
├── facts[]               — Fact      { character_id, location_id, time_slot, source_type, evidence }
├── rejections[]          — Rejection { character_id, location_id, time_slot, reason }
├── deductions[]          — Deduction { character_id, location_id, time_slot, confidence, reasoning, status }
└── hints[]               — Hint      { type: rule|hint|constraint, content, applies_to }
```

### Key Design Decisions

**Solution Grid**: The core puzzle is a 3D assignment: `Character × Location × Time`. Each `Fact` pins one cell in this grid. The goal is to fill the entire grid.

**Constraint model**: Game rules typically enforce:
- Each character is at exactly ONE location per time slot
- Each location has at most ONE character per time slot (configurable — some games allow multiple)

These are stored as `Hint` entries with `type: "rule"`.

**Progressive discovery**: Characters and locations may be discovered as new scripts are added. Each has a `discovered_in_script_id` field for provenance. The `status` field on Character handles uncertain identities (`confirmed`, `suspected`, `unknown`).

**Rejection as negative constraint**: Every rejected deduction becomes a `Rejection` record. These are critical — they prevent the AI from re-suggesting the same wrong answer and provide signal about what ISN'T true.

**Source tracking**: Every `Fact` tracks its `source_type` (script_explicit, user_input, ai_deduction, game_hint) and `source_evidence` for auditability.

---

## 2. AI Prompt Strategy

### 2.1 System Prompt

```
You are an expert deduction engine for script-based mystery games. Your task is to analyze scene scripts, known facts, game rules, and constraints to deduce which character was at which location at which time.

CORE RULES:
- Only make deductions that are logically supported by the evidence provided.
- Clearly distinguish between CERTAIN deductions (only one possibility) and PROBABLE deductions (most likely but not proven).
- Never suggest a deduction that appears in the REJECTED list — those have been explicitly ruled out.
- Pay close attention to GAME RULES — they define hard constraints.
- Scripts may describe events OUT OF CHRONOLOGICAL ORDER. Use internal clues (dialogue references, time mentions, lighting, etc.) to determine actual timing.
- Character aliases: A character may be referred to by different names in different scripts. Use the alias list to unify references.

DEDUCTION TECHNIQUES:
1. Direct evidence: A script explicitly states a character is at a location at a time.
2. Elimination: If all but one character/location are accounted for at a time slot, the remaining one is determined.
3. Temporal reasoning: If a character is seen at Location A at 15:00 and Location B at 17:00, they could not be at Location C at 15:00 or 17:00.
4. Dialogue analysis: Characters may reference where they were, where others were, or events that constrain placement.
5. Contradiction detection: If a proposed placement violates a game rule or known fact, flag it.

OUTPUT FORMAT:
Respond with a JSON object following the exact schema provided in the user message.
```

### 2.2 User Prompt Template — Deduction Request

```
## GAME: {{project.name}}
{{project.description}}

## TIME SLOTS (chronological order)
{{project.time_slots | join(", ")}}

## CHARACTERS
{{#each characters}}
- **{{name}}** (ID: {{id}}){{#if aliases}} — also known as: {{aliases | join(", ")}}{{/if}}{{#if description}} — {{description}}{{/if}}
{{/each}}

## LOCATIONS
{{#each locations}}
- **{{name}}** (ID: {{id}}){{#if aliases}} — also known as: {{aliases | join(", ")}}{{/if}}{{#if description}} — {{description}}{{/if}}
{{/each}}

## GAME RULES & HINTS
{{#each hints}}
- [{{type | uppercase}}] {{content}}
{{/each}}

## CONFIRMED FACTS (these are TRUE — do not contradict)
{{#each facts}}
- ✅ **{{character.name}}** was at **{{location.name}}** at **{{time_slot}}** (source: {{source_evidence}})
{{/each}}

## REJECTED DEDUCTIONS (these are FALSE — do NOT re-suggest)
{{#each rejections}}
- ❌ {{character.name}} was NOT at {{location.name}} at {{time_slot}} (reason: {{reason}})
{{/each}}

## UNFILLED SLOTS
The following character-time combinations still need a location:
{{#each unfilled_slots}}
- {{character.name}} at {{time_slot}}: ???
{{/each}}

## SCRIPT EVIDENCE
{{#each scripts}}
### Script: "{{title}}" (added: #{{metadata.source_order}})
{{#if metadata.stated_time}}Stated time: {{metadata.stated_time}}{{/if}}
{{#if metadata.stated_location}}Stated location: {{metadata.stated_location}}{{/if}}

```
{{raw_text}}
```

{{/each}}

---

## YOUR TASK
Analyze all the scripts, facts, rejections, and rules above. Produce new deductions for unfilled slots.

Respond with ONLY a JSON object in this exact format:
```json
{
  "deductions": [
    {
      "character_id": "<uuid>",
      "location_id": "<uuid>",
      "time_slot": "HH:MM",
      "confidence": "certain|high|medium|low",
      "reasoning": "Step-by-step explanation of how you reached this conclusion",
      "supporting_script_ids": ["<uuid>", ...],
      "depends_on_fact_ids": ["<uuid>", ...]
    }
  ],
  "new_characters_detected": [
    {
      "name": "string",
      "found_in_script_id": "<uuid>",
      "context": "How this character is referenced"
    }
  ],
  "new_locations_detected": [
    {
      "name": "string",
      "found_in_script_id": "<uuid>",
      "context": "How this location is referenced"
    }
  ],
  "contradictions_detected": [
    {
      "description": "Description of the contradiction",
      "involved_fact_ids": ["<uuid>", ...],
      "involved_script_ids": ["<uuid>", ...]
    }
  ],
  "notes": "Any observations, ambiguities, or suggestions for the player"
}
```

Focus on CERTAIN and HIGH confidence deductions first. Include MEDIUM/LOW only if no higher-confidence options exist.
```

### 2.3 User Prompt Template — Script Analysis (on new script addition)

This is a lighter prompt used when a new script is added, to extract basic info before a full deduction pass:

```
## NEW SCRIPT ANALYSIS

A new script has been added to the game "{{project.name}}".

### Known Characters
{{#each characters}}
- {{name}}{{#if aliases}} (aliases: {{aliases | join(", ")}}){{/if}}
{{/each}}

### Known Locations
{{#each locations}}
- {{name}}{{#if aliases}} (aliases: {{aliases | join(", ")}}){{/if}}
{{/each}}

### Known Time Slots
{{project.time_slots | join(", ")}}

### New Script Text
```
{{script.raw_text}}
```

Analyze this script and respond with ONLY this JSON:
```json
{
  "characters_mentioned": [
    {
      "character_id": "<uuid or null if new>",
      "name": "string",
      "is_new": true/false,
      "context": "How they appear in the script"
    }
  ],
  "locations_mentioned": [
    {
      "location_id": "<uuid or null if new>",
      "name": "string",
      "is_new": true/false,
      "context": "How it appears in the script"
    }
  ],
  "time_references": [
    {
      "time_slot": "HH:MM or null",
      "reference_text": "The text that indicates this time",
      "is_explicit": true/false
    }
  ],
  "direct_facts": [
    {
      "character_name": "string",
      "location_name": "string",
      "time_slot": "HH:MM",
      "confidence": "certain|high|medium|low",
      "evidence": "Quote or explanation from the script"
    }
  ],
  "alias_candidates": [
    {
      "name_in_script": "string",
      "might_be_character_id": "<uuid>",
      "reasoning": "Why this might be an alias"
    }
  ]
}
```
```

### 2.4 Prompt Assembly Strategy

**Token budget management**: Scripts can be long. The prompt assembler should:

1. **Always include**: System prompt, game rules/hints, all facts, all rejections, unfilled slots
2. **Prioritize scripts by relevance**: If context window is tight, include scripts that mention characters/locations in unfilled slots first
3. **Summarize vs. raw**: For very long scripts, offer the AI a summary + key quotes rather than the full text
4. **Batch by gap**: If many unfilled slots exist, focus the AI on a subset (e.g., one time slot at a time) to improve quality

**Language handling**: The system prompt and structural framing are in English, but script `raw_text` may be in any language (Chinese, Japanese, etc.). The system prompt should note: "Scripts may be in any language. Analyze them in their original language and provide reasoning in the user's preferred language."

---

## 3. Deduction Workflow

### 3.1 State Machine

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    ▼                                  │
┌─────────┐   ┌─────────┐   ┌──────────┐   ┌─────────┴───┐
│  IDLE    │──▶│ ANALYZE │──▶│ REVIEW   │──▶│   UPDATE    │
│         │   │ (AI)    │   │ (User)   │   │  (Persist)  │
└─────────┘   └─────────┘   └──────────┘   └─────────────┘
     ▲                            │
     │                            │
     └────────────────────────────┘
              (all reviewed)
```

**States:**

| State | Description |
|-------|-------------|
| **IDLE** | No pending deductions. User can: add scripts, add facts manually, add hints, trigger deduction |
| **ANALYZE** | AI is processing. System sends prompt with all context. Returns deduction candidates. |
| **REVIEW** | User reviews AI deductions one by one (or in batch). Can: Accept → Fact, Reject → Rejection, Skip → stays Pending |
| **UPDATE** | Accepted deductions become Facts, rejected become Rejections. State persists. Returns to IDLE or triggers re-analysis. |

### 3.2 Trigger Conditions

| Trigger | When | Behavior |
|---------|------|----------|
| **Manual** | User clicks "Analyze" / "Deduce" button | Full deduction pass on all unfilled slots |
| **After script added** | User adds a new script | Light analysis (script parsing) → optional full deduction |
| **After fact confirmed** | User confirms a new fact (manual or from deduction) | Optional auto-re-analyze since new constraints exist |
| **After rejection** | User rejects a deduction | Do NOT auto-re-analyze immediately (to allow batch rejections) |

### 3.3 Deduction Review Flow

```
For each deduction (sorted by confidence: certain → high → medium → low):

1. Display to user:
   ┌──────────────────────────────────────────────────┐
   │ 💡 Deduction (confidence: HIGH)                  │
   │                                                   │
   │ Character: Alice                                  │
   │ Location:  Library                                │
   │ Time:      15:00                                  │
   │                                                   │
   │ Reasoning:                                        │
   │ In Script #3, Bob says "I saw Alice reading in   │
   │ the library before the meeting at 16:00." Since   │
   │ the meeting at 16:00 is confirmed, Alice must     │
   │ have been at the Library at 15:00.                │
   │                                                   │
   │ Supporting scripts: Script #3, Script #1          │
   │ Depends on facts: Alice@MeetingRoom@16:00         │
   │                                                   │
   │   [✅ Accept]  [❌ Reject]  [⏭ Skip]              │
   └──────────────────────────────────────────────────┘

2. On Accept:
   - Create Fact from deduction
   - Mark deduction status = "accepted"
   - Check if this new fact enables cascade deductions

3. On Reject:
   - Prompt user for rejection reason (optional but encouraged)
   - Create Rejection record
   - Mark deduction status = "rejected"

4. On Skip:
   - Leave as "pending" for later review
```

### 3.4 Confidence Level Definitions

| Level | Meaning | Typical Source |
|-------|---------|----------------|
| **certain** | Logically guaranteed. No other possibility exists. | Direct script statement, or elimination with all other slots filled |
| **high** | Very strong evidence, but minor ambiguity possible. | Strong dialogue evidence + constraint reasoning |
| **medium** | Reasonable inference but relies on interpretation. | Indirect dialogue, temporal inference with gaps |
| **low** | Speculative. Based on weak signals or heuristic. | Character tendencies, vague references |

### 3.5 Using Rejections as Negative Constraints

Rejections are critical for the constraint solver. They work in two ways:

1. **Direct exclusion**: "Character X was NOT at Location Y at Time Z" — eliminates one cell in the grid
2. **Inference amplification**: Combined with positive facts and game rules, rejections can force new certain deductions via elimination

Example:
- Time 15:00 has 3 possible locations: Library, Kitchen, Garden
- Alice is confirmed at Library at 15:00 (Fact)
- Bob at Kitchen at 15:00 was rejected (Rejection)
- Game rule: each location has exactly one person per time slot
- Therefore: Bob must be at Garden at 15:00 → **certain** deduction

### 3.6 Cascade Deduction

When a new Fact is added, the system should optionally check for "obvious" cascades:

```
function checkCascade(newFact, project):
    for each unfilled (character, time_slot) pair:
        possible_locations = all_locations
        remove locations where another character is confirmed at this time
        remove locations in rejection list for this character+time
        if only 1 possible_location remains:
            create Deduction(confidence="certain", reasoning="elimination")
    
    for each unfilled (location, time_slot) pair:
        possible_characters = all_characters
        remove characters confirmed elsewhere at this time
        remove characters in rejection list for this location+time
        if only 1 possible_character remains:
            create Deduction(confidence="certain", reasoning="elimination")
```

This cascade logic can run locally (no AI needed) for elimination-based deductions, saving API calls.

---

## 4. Edge Cases & Considerations

### 4.1 Non-Chronological Scripts
Scripts may describe events out of order. The AI must rely on internal evidence (time references in dialogue, cause-effect relationships) rather than script order. The `metadata.source_order` field tracks input order but is NOT assumed to be chronological.

### 4.2 Alias Resolution
A character might be called "the tall man" in one script and "Mr. Smith" in another. The system:
- Stores aliases on Character objects
- The AI's script analysis prompt explicitly asks for alias candidates
- User confirms alias merges manually (to avoid wrong auto-merges)

### 4.3 Multiple Characters at One Location
Some games allow multiple characters at the same location at the same time. This is controlled by a game rule (`Hint` with `type: "rule"`). The default rule assumes 1:1 mapping, but can be relaxed.

### 4.4 Partial Time Information
A script might say "in the afternoon" without specifying an exact time slot. The AI should map vague references to the nearest matching time slots and flag the ambiguity.

### 4.5 Contradictions
The AI prompt explicitly asks for contradiction detection. If the AI finds that confirmed facts contradict each other or a game rule, it should flag this in `contradictions_detected`. The UI should prominently display contradictions for user resolution.

### 4.6 Large Script Volumes
For games with many scripts, the prompt may exceed token limits. Strategy:
1. Always include all facts, rejections, and hints (these are compact)
2. Include full text of the N most relevant scripts (those mentioning unfilled characters/locations)
3. Include summaries of remaining scripts
4. If still too large, split into multiple focused deduction passes (by time slot or character group)

### 4.7 Progressive Discovery Workflow
Typical user session flow:

```
1. Create project → set name, time_slots, initial hints/rules
2. Add first script → AI extracts characters, locations, direct facts
3. User confirms/edits extracted entities
4. User confirms obvious direct facts
5. Add more scripts → repeat extraction
6. Trigger full deduction → AI analyzes all evidence
7. Review deductions → accept/reject
8. Repeat 5-7 until grid is complete
```

### 4.8 Undo/History
Consider tracking a history of actions for undo capability:
- `FactAdded`, `FactRemoved`
- `DeductionAccepted`, `DeductionRejected`
- `ScriptAdded`
- `CharacterMerged` (alias resolution)

This is not in the core model but recommended as a future enhancement.

### 4.9 Grid Visualization Support
The data model naturally maps to a grid view:
- **Rows**: Characters
- **Columns**: Time slots
- **Cells**: Location (from Facts) or "?" (unfilled) or candidates (from pending Deductions)

The UI should color-code by source: green for script-explicit facts, blue for AI-confirmed deductions, yellow for pending deductions.

### 4.10 Multi-language Script Support
Scripts may be in Chinese, Japanese, English, or any other language. The system prompt instructs the AI to analyze scripts in their original language. The `reasoning` field in deductions should be in the user's preferred language (can be set as a project-level preference, defaulting to the language of the UI).

---

## Appendix A: Example Data

```json
{
  "id": "proj-001",
  "name": "Murder at Willowbrook Manor",
  "description": "A murder mystery set in a country estate. Determine where each guest was at each hour.",
  "time_slots": ["14:00", "15:00", "16:00", "17:00", "18:00"],
  "characters": [
    {
      "id": "char-001",
      "name": "Lady Victoria",
      "aliases": ["Victoria", "Lady V"],
      "status": "confirmed"
    },
    {
      "id": "char-002",
      "name": "Colonel Mustard",
      "aliases": ["The Colonel"],
      "status": "confirmed"
    },
    {
      "id": "char-003",
      "name": "Dr. Chen",
      "aliases": ["The Doctor"],
      "status": "confirmed"
    }
  ],
  "locations": [
    { "id": "loc-001", "name": "Library" },
    { "id": "loc-002", "name": "Kitchen" },
    { "id": "loc-003", "name": "Garden" }
  ],
  "hints": [
    {
      "id": "hint-001",
      "type": "rule",
      "content": "Each character is at exactly one location per time slot. Each location has at most one character per time slot."
    },
    {
      "id": "hint-002",
      "type": "hint",
      "content": "Lady Victoria never enters the Kitchen."
    }
  ],
  "facts": [
    {
      "id": "fact-001",
      "character_id": "char-001",
      "location_id": "loc-001",
      "time_slot": "14:00",
      "source_type": "script_explicit",
      "source_evidence": "Script #1: 'Lady Victoria was reading in the Library at 2 PM.'",
      "source_script_ids": ["script-001"]
    }
  ],
  "rejections": [
    {
      "id": "rej-001",
      "character_id": "char-002",
      "location_id": "loc-003",
      "time_slot": "15:00",
      "reason": "Colonel Mustard's knee injury prevents him from walking to the Garden — mentioned in Script #2"
    }
  ],
  "deductions": [
    {
      "id": "ded-001",
      "character_id": "char-003",
      "location_id": "loc-002",
      "time_slot": "14:00",
      "confidence": "high",
      "reasoning": "Script #2 mentions Dr. Chen was preparing tea. The only place with tea facilities is the Kitchen. Since Lady Victoria is confirmed in the Library at 14:00 and the Colonel denies being in the Kitchen, Dr. Chen must have been in the Kitchen at 14:00.",
      "supporting_script_ids": ["script-002"],
      "depends_on_fact_ids": ["fact-001"],
      "status": "pending",
      "batch_id": "batch-001"
    }
  ]
}
```

## Appendix B: API Response Schema (for AI output parsing)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DeductionResponse",
  "type": "object",
  "required": ["deductions"],
  "properties": {
    "deductions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["character_id", "location_id", "time_slot", "confidence", "reasoning"],
        "properties": {
          "character_id": { "type": "string" },
          "location_id": { "type": "string" },
          "time_slot": { "type": "string", "pattern": "^\\d{2}:\\d{2}$" },
          "confidence": { "type": "string", "enum": ["certain", "high", "medium", "low"] },
          "reasoning": { "type": "string" },
          "supporting_script_ids": { "type": "array", "items": { "type": "string" } },
          "depends_on_fact_ids": { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "new_characters_detected": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "found_in_script_id": { "type": "string" },
          "context": { "type": "string" }
        }
      }
    },
    "new_locations_detected": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "found_in_script_id": { "type": "string" },
          "context": { "type": "string" }
        }
      }
    },
    "contradictions_detected": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "description": { "type": "string" },
          "involved_fact_ids": { "type": "array", "items": { "type": "string" } },
          "involved_script_ids": { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "notes": { "type": "string" }
  }
}
```
