"""Default system-prompt presets shipped with the code — the single source of
truth, mirroring ``DEFAULT_PROMPT_SEEDS`` / ``DEFAULT_INSTRUCTION_SEEDS``.

A preset references its instructions by DB id, which is only known at runtime:
the seeds therefore declare them by natural key ``(type, label)`` and the
StoreService resolves them into ids at seed time (idempotent upsert by
``(agent_role, name)`` — existing rows are never overwritten). Every role gets
a bare ``default`` preset (base template only), so a graph can be configured
out of the box; the reviewer also gets one exemplar persona bundle.
"""
from models.domain.agent import AgentRole
from models.domain.prompt import InstructionType

from domain.prompt.instruction_default import BENIGN, KNOWLEDGEABLE, RESPONSIBLE

# One seed: (agent_role, name, base_prompt_version, instruction_refs, description)
# with instruction_refs = [(type, label), ...] resolved to ids at seed time.
PresetSeed = tuple[str, str, str, list[tuple[InstructionType, str]], str]

DEFAULT_PRESET_SEEDS: list[PresetSeed] = [
    (
        AgentRole.REVIEWER, "default", "base_v1", [],
        "Default reviewer preset: the base template, no persona instructions",
    ),
    (
        AgentRole.META_REVIEWER, "default", "base_v1", [],
        "Default meta-reviewer preset: the base template, no persona instructions",
    ),
    (
        AgentRole.AREA_CHAIR, "default", "base_v1", [],
        "Default area-chair preset: the base template, no persona instructions",
    ),
    (
        AgentRole.AUTHOR_AGENT, "default", "base_v1", [],
        "Default author preset: the base template, no persona instructions",
    ),
    (
        AgentRole.REVIEWER, "diligent-expert", "base_v1",
        [
            (InstructionType.COMMITMENT, RESPONSIBLE),
            (InstructionType.KNOWLEDGEABILITY, KNOWLEDGEABLE),
            (InstructionType.INTENTION, BENIGN),
        ],
        "Careful expert reviewer: diligent, knowledgeable and constructive",
    ),
]
