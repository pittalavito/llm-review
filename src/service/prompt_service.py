from core.error import NotFoundError
from core.observability import LogPrefix, log_warning

from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion, SystemPromptPreset

from service.store_service import StoreService


class PromptService:

    def __init__(self, store_service: StoreService):
        self._store_service = store_service

    def build_system_prompt(self, agent_role: str, promt_label: str, instruction_labels: list[str] | None = None) -> str:
        """Retrieve the system prompt for the given agent role and prompt label,
        appending the requested persona instructions to the base template."""
        prompt_version: PromptVersion = self._store_service.get_promt_by_role_label(agent_role=agent_role, version_label=promt_label)

        if prompt_version is None or prompt_version.template is None:
            raise ValueError(f"No prompt found for role '{agent_role}' and version '{promt_label}'.")

        promt_instructions: list[PromptInstruction] = self._store_service.get_instructions_by_labels(instruction_labels) if instruction_labels else []
        return self._compose(prompt_version, promt_instructions)

    def build_system_prompt_from_preset_id(self, agent_role: str, preset_id: int) -> str | None:
        preset = self._get_active_preset(preset_id)
        instructions = self._resolve_preset_instructions(preset)
        prompt_version = self._store_service.get_promt_by_role_label(agent_role=agent_role, version_label=preset.base_prompt_version)
        if prompt_version is None or prompt_version.template is None:
            raise NotFoundError(f"Preset '{preset.name}': no prompt found for role '{agent_role}' and version '{preset.base_prompt_version}'.")
        return self._compose(prompt_version, instructions)

    def _get_active_preset(self, preset_id: int) -> SystemPromptPreset:
        preset = self._store_service.get_preset(preset_id)
        if preset is None:
            raise NotFoundError(f"System prompt preset {preset_id} not found.")
        if not preset.is_active:
            raise NotFoundError(f"System prompt preset '{preset.name}' (id {preset_id}) is inactive.")
        return preset

    def _resolve_preset_instructions(self, preset: SystemPromptPreset) -> list[PromptInstruction]:
        """The preset's instructions by id; dangling ids are dropped with a
        warning — the same forgiveness list_by_labels applies to unknown labels."""
        if not preset.instruction_ids:
            return []
        instructions = self._store_service.get_instructions_by_ids(preset.instruction_ids)
        missing = set(preset.instruction_ids) - {instr.id for instr in instructions}
        if missing:
            log_warning(LogPrefix.PROMPT_SERVICE, f"Preset '{preset.name}' references missing instruction ids: {sorted(missing)}")
        return instructions

    @staticmethod
    def _compose(prompt_version: PromptVersion, instructions: list[PromptInstruction]) -> str:
        if not instructions:
            return prompt_version.template
        lines = "\n".join(f"- [{instr.type}] {instr.instruction}" for instr in instructions)
        return f"{prompt_version.template}\n\n{lines}"

    # ------------------------------------------------------------------
    # Prompt-version registry

    def list_prompts(self, agent_role: str | None = None, include_inactive: bool = False) -> list[PromptVersion]:
        return self._store_service.list_prompts(agent_role=agent_role, include_inactive=include_inactive)

    def create_prompt(self, agent_role: str, version_label: str, template: str, description: str | None = None) -> PromptVersion | None:
        return self._store_service.create_prompt(agent_role, version_label, template, description)

    def update_prompt_meta(self, version_id: int, description: str | None = None, is_active: bool | None = None) -> PromptVersion | None:
        return self._store_service.update_prompt_meta(version_id, description, is_active)

    # ------------------------------------------------------------------
    # Persona-instruction registry

    def list_instructions(self, type: InstructionType | None = None, include_inactive: bool = False) -> list[PromptInstruction]:
        return self._store_service.list_instructions(type=type, include_inactive=include_inactive)

    def create_instruction(self, type: InstructionType, label: str, instruction: str, description: str | None = None, agent_role: str | None = None, run_id: str | None = None) -> PromptInstruction | None:
        return self._store_service.create_instruction(type, label, instruction, description, agent_role, run_id)

    def update_instruction_meta(self, instruction_id: int, description: str | None = None, is_active: bool | None = None) -> PromptInstruction | None:
        return self._store_service.update_instruction_meta(instruction_id, description, is_active)

    # ------------------------------------------------------------------
    # System prompt presets

    def list_presets(self, agent_role: str | None = None, include_inactive: bool = False) -> list[SystemPromptPreset]:
        return self._store_service.list_presets(agent_role=agent_role, include_inactive=include_inactive)

    def get_preset(self, preset_id: int) -> SystemPromptPreset | None:
        return self._store_service.get_preset(preset_id)

    def create_preset(self, agent_role: str, name: str, base_prompt_version: str, instruction_ids: list[int] | None = None, description: str | None = None) -> SystemPromptPreset | None:
        return self._store_service.create_preset(agent_role, name, base_prompt_version, instruction_ids, description)

    def update_preset(self, preset_id: int, name: str | None = None, description: str | None = None, base_prompt_version: str | None = None, instruction_ids: list[int] | None = None, is_active: bool | None = None) -> SystemPromptPreset | None:
        return self._store_service.update_preset(preset_id, name, description, base_prompt_version, instruction_ids, is_active)

    def delete_preset(self, preset_id: int) -> bool:
        return self._store_service.delete_preset(preset_id)

    def prompt_version_exists(self, agent_role: str, version_label: str) -> bool:
        """True when (agent_role, version_label) is registered, active or not —
        used to validate a preset's base reference on create/update."""
        return self._store_service.get_promt_by_role_label(agent_role, version_label, only_active=False) is not None
