from models.domain.agent import AgentRole
from models.domain.prompt import InstructionType
from domain.prompt.instruction_default import ALL, RESPONSIBLE, KNOWLEDGEABLE, BENIGN, ICLR

PresetSeed = tuple[str, str, str, list[tuple[InstructionType, str]], str]

DEFAULT_PRESET_SEEDS: list[PresetSeed] = [
    (
        AgentRole.REVIEWER,
        "default",
        "iclr_v1",
        [
            (InstructionType.COMMITMENT, RESPONSIBLE),
            (InstructionType.KNOWLEDGEABILITY, KNOWLEDGEABLE),
            (InstructionType.INTENTION, BENIGN),
            (InstructionType.VENUE, ICLR),
            (InstructionType.FOCUS, ALL),
        ],
        "Campaign RQ1/RQ2 reviewer: neutral persona (diligent, expert, constructive), ICLR venue",
    ),
    (
        AgentRole.META_REVIEWER,
        "default",
        "iclr_v1",
        [(InstructionType.VENUE, ICLR)],
        "Campaign meta-reviewer: base template, ICLR venue",
    ),
    (
        AgentRole.AREA_CHAIR,
        "default",
        "iclr_v1",
        [(InstructionType.VENUE, ICLR)],
        "Campaign area chair: base template, ICLR venue",
    ),
    (
        AgentRole.AUTHOR_AGENT,
        "default",
        "iclr_v1",
        [],
        "Campaign author: the base template, no persona instructions",
    ),
]
