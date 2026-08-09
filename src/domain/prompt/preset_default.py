from models.domain.agent import AgentRole
from models.domain.prompt import InstructionType
from domain.prompt.instruction_default import ICLR, VENUE_BAR

PresetSeed = tuple[str, str, str, list[tuple[InstructionType, str]], str]

DEFAULT_PRESET_SEEDS: list[PresetSeed] = [
    (
        AgentRole.REVIEWER,
        "iclr_v1",
        "iclr_v2",
        [
            (InstructionType.VENUE, ICLR),
        ],
        "Campaign reviewer: base template, ICLR venue",
    ),
    (
        AgentRole.META_REVIEWER,
        "iclr_v1",
        "iclr_v2",
        [(InstructionType.VENUE, ICLR)],
        "Campaign meta-reviewer: base template, ICLR venue",
    ),
    (
        AgentRole.AREA_CHAIR,
        "iclr_v1",
        "iclr_v2",
        [(InstructionType.VENUE, ICLR)],
        "Campaign area chair: base template, ICLR venue",
    ),
    (
        AgentRole.AUTHOR_AGENT,
        "iclr_v1",
        "iclr_v2",
        [],
        "Campaign author: the base template, no persona instructions",
    ),
]
