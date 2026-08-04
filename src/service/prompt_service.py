from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion

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
        if not promt_instructions:
            return prompt_version.template

        instructions = "\n".join(f"- [{instr.type}] {instr.instruction}" for instr in promt_instructions)
        return f"{prompt_version.template}\n\n{instructions}"

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
