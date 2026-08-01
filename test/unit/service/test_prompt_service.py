"""Unit tests for PromptService.build_system_prompt — composition of the base
template with the persona instructions, against a duck-typed fake store."""
import pytest

from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion
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


def _instruction(label: str, text: str, type: InstructionType = InstructionType.FOCUS) -> PromptInstruction:
    return PromptInstruction(id=1, type=type, label=label, instruction=text, created_at="2026-01-01")


class _FakeStore:
    def __init__(self, prompt: PromptVersion | None, instructions: list[PromptInstruction] | None = None):
        self._prompt = prompt
        self._instructions = instructions or []
        self.requested_labels: list[str] | None = None

    def get_promt_by_role_label(self, agent_role: str, version_label: str):
        return self._prompt

    def get_instructions_by_labels(self, labels: list[str]):
        self.requested_labels = labels
        return self._instructions


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
