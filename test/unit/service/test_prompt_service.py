"""Unit tests for PromptService.build_system_prompt — composition of the base
template with the persona instructions, against a duck-typed fake store — and
for build_system_prompt_from_preset_id — the preset resolution path."""
import pytest

from core.error import NotFoundError
from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion, SystemPromptPreset
from service.prompt_service import PromptService


def _version(template: str = "Base template.") -> PromptVersion:
    return PromptVersion(
        id=1,
        agent_role="reviewer",
        version_label="v1",
        template=template,
        template_hash="h",
        created_at="2026-01-01",
    )


def _instruction(label: str, text: str, type: InstructionType = InstructionType.FOCUS, id: int = 1) -> PromptInstruction:
    return PromptInstruction(id=id, type=type, label=label, instruction=text, created_at="2026-01-01")


def _preset(instruction_ids: list[int] | None = None, agent_role: str = "reviewer", is_active: bool = True) -> SystemPromptPreset:
    return SystemPromptPreset(
        id=10,
        agent_role=agent_role,
        name="severo",
        base_prompt_version="v1",
        instruction_ids=instruction_ids if instruction_ids is not None else [],
        created_at="2026-01-01",
        is_active=is_active,
    )


class _FakeStore:
    def __init__(self, prompt: PromptVersion | None, instructions: list[PromptInstruction] | None = None, preset: SystemPromptPreset | None = None):
        self._prompt = prompt
        self._instructions = instructions or []
        self._preset = preset
        self.requested_labels: list[str] | None = None
        self.requested_ids: list[int] | None = None

    def get_promt_by_role_label(self, agent_role: str, version_label: str):
        return self._prompt

    def get_instructions_by_labels(self, labels: list[str]):
        self.requested_labels = labels
        return self._instructions

    def get_instructions_by_ids(self, ids: list[int]):
        self.requested_ids = ids
        return [instr for instr in self._instructions if instr.id in ids]

    def get_preset(self, preset_id: int):
        return self._preset


class TestBuildSystemPrompt:
    def test_no_labels_returns_the_bare_template(self):
        service = PromptService(store_service=_FakeStore(_version()))
        assert service.build_system_prompt("reviewer", "v1") == "Base template."

    def test_labels_append_the_instructions(self):
        store = _FakeStore(_version(), [
            _instruction("focus_novelty", "Focus on novelty."),
            _instruction("strict", "Be strict.", InstructionType.COMMITMENT),
        ])
        service = PromptService(store_service=store)
        prompt = service.build_system_prompt("reviewer", "v1", ["focus_novelty", "strict"])
        assert prompt.startswith("Base template.")
        assert "- [focus] Focus on novelty." in prompt
        assert "- [commitment] Be strict." in prompt
        assert store.requested_labels == ["focus_novelty", "strict"]

    def test_unknown_labels_fall_back_to_the_bare_template(self):
        service = PromptService(store_service=_FakeStore(_version(), []))
        assert service.build_system_prompt("reviewer", "v1", ["missing"]) == "Base template."

    def test_missing_prompt_raises(self):
        service = PromptService(store_service=_FakeStore(None))
        with pytest.raises(ValueError):
            service.build_system_prompt("reviewer", "v9")


class TestBuildSystemPromptFromPresetId:
    def test_composes_base_and_preset_instructions(self):
        store = _FakeStore(_version(), [_instruction("focus_novelty", "Focus on novelty.", id=3)], _preset([3]))
        service = PromptService(store_service=store)
        prompt = service.build_system_prompt_from_preset_id("reviewer", preset_id=10)
        assert prompt == "Base template.\n\n- [focus] Focus on novelty."
        assert store.requested_ids == [3]

    def test_preset_without_instructions_returns_the_bare_template(self):
        service = PromptService(store_service=_FakeStore(_version(), preset=_preset([])))
        assert service.build_system_prompt_from_preset_id("reviewer", preset_id=10) == "Base template."

    def test_missing_preset_raises_not_found(self):
        service = PromptService(store_service=_FakeStore(_version(), preset=None))
        with pytest.raises(NotFoundError):
            service.build_system_prompt_from_preset_id("reviewer", preset_id=10)

    def test_inactive_preset_raises_not_found(self):
        service = PromptService(store_service=_FakeStore(_version(), preset=_preset(is_active=False)))
        with pytest.raises(NotFoundError):
            service.build_system_prompt_from_preset_id("reviewer", preset_id=10)

    def test_preset_with_missing_base_version_raises_not_found(self):
        service = PromptService(store_service=_FakeStore(None, preset=_preset()))
        with pytest.raises(NotFoundError):
            service.build_system_prompt_from_preset_id("reviewer", preset_id=10)

    def test_missing_instruction_ids_are_dropped(self):
        store = _FakeStore(_version(), [_instruction("focus_novelty", "Focus on novelty.", id=3)], _preset([3, 99]))
        service = PromptService(store_service=store)
        prompt = service.build_system_prompt_from_preset_id("reviewer", preset_id=10)
        assert prompt == "Base template.\n\n- [focus] Focus on novelty."
