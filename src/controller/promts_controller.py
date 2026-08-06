"""Prompts endpoints — everything under /prompts (prompt-version registry)."""
from fastapi import APIRouter, Depends, HTTPException

from core.container import prompt_service
from models.domain.prompt import InstructionType
from models.controller.prompt import (
    CreateInstructionRequest,
    CreatePresetRequest,
    CreatePromptRequest,
    PresetListResponse,
    PresetResponse,
    PromptInstructionListResponse,
    PromptInstructionResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
    PromptVersionListResponse,
    PromptVersionResponse,
    UpdateInstructionRequest,
    UpdatePresetRequest,
    UpdatePromptRequest,
)

from service.prompt_service import PromptService


router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/list")
def list_prompts(include_inactive: bool = False, service: PromptService = Depends(prompt_service)) -> PromptVersionListResponse:
    """The whole prompt-version registry (active versions only by default)."""
    prompts = service.list_prompts(include_inactive=include_inactive)
    return PromptVersionListResponse.from_response(prompts)


@router.get("/role/{agent_role}")
def list_prompts_by_role(agent_role: str, include_inactive: bool = False, service: PromptService = Depends(prompt_service)) -> PromptVersionListResponse:
    """Every version registered for one agent role."""
    prompts = service.list_prompts(agent_role=agent_role, include_inactive=include_inactive)
    return PromptVersionListResponse.from_response(prompts)


@router.post("/create")
def create_prompt(request: CreatePromptRequest, service: PromptService = Depends(prompt_service)) -> PromptVersionResponse:
    """Register a new immutable prompt version; 409 when (agent_role,
    version_label) already exists."""
    prompt = service.create_prompt(request.agent_role, request.version_label, request.template, request.description)
    if prompt is None:
        raise HTTPException(status_code=409, detail="A prompt version with this (agent_role, version_label) already exists.")
    return PromptVersionResponse.from_response(prompt)


@router.put("/{version_id}")
def update_prompt(version_id: int, request: UpdatePromptRequest, service: PromptService = Depends(prompt_service)) -> PromptVersionResponse:
    """Update the mutable metadata only (description, is_active) — the template
    never changes; 404 when the version does not exist."""
    prompt = service.update_prompt_meta(version_id, request.description, request.is_active)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")
    return PromptVersionResponse.from_response(prompt)


@router.get("/instructions/list")
def list_instructions(type: InstructionType | None = None, include_inactive: bool = False, service: PromptService = Depends(prompt_service)) -> PromptInstructionListResponse:
    """The persona-instruction registry, optionally filtered by axis type."""
    instructions = service.list_instructions(type=type, include_inactive=include_inactive)
    return PromptInstructionListResponse.from_response(instructions)


@router.post("/instructions/create")
def create_instruction(request: CreateInstructionRequest, service: PromptService = Depends(prompt_service)) -> PromptInstructionResponse:
    """Register a new immutable persona instruction; 409 when (type, label)
    already exists."""
    instruction = service.create_instruction(request.type, request.label, request.instruction, request.description, request.agent_role, request.run_id)
    if instruction is None:
        raise HTTPException(status_code=409, detail="An instruction with this (type, label) already exists.")
    return PromptInstructionResponse.from_response(instruction)


@router.put("/instructions/{instruction_id}")
def update_instruction(instruction_id: int, request: UpdateInstructionRequest, service: PromptService = Depends(prompt_service)) -> PromptInstructionResponse:
    """Update the mutable metadata only (description, is_active) — the text
    never changes; 404 when the instruction does not exist."""
    instruction = service.update_instruction_meta(instruction_id, request.description, request.is_active)
    if instruction is None:
        raise HTTPException(status_code=404, detail="Prompt instruction not found.")
    return PromptInstructionResponse.from_response(instruction)


@router.get("/presets/list")
def list_presets(agent_role: str | None = None, include_inactive: bool = False, service: PromptService = Depends(prompt_service)) -> PresetListResponse:
    """The system-prompt preset registry, optionally filtered by role."""
    presets = service.list_presets(agent_role=agent_role, include_inactive=include_inactive)
    return PresetListResponse.from_response(presets)


@router.get("/presets/{preset_id}")
def get_preset(preset_id: int, service: PromptService = Depends(prompt_service)) -> PresetResponse:
    """One preset by id; 404 when it does not exist."""
    preset = service.get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="System prompt preset not found.")
    return PresetResponse.from_response(preset)


@router.post("/presets/create")
def create_preset(request: CreatePresetRequest, service: PromptService = Depends(prompt_service)) -> PresetResponse:
    """Register a new preset; 400 when the base version is not in the role's
    registry, 409 when (agent_role, name) already exists."""
    if not service.prompt_version_exists(request.agent_role, request.base_prompt_version):
        raise HTTPException(status_code=400, detail=f"No prompt version '{request.base_prompt_version}' registered for role '{request.agent_role}'.")
    preset = service.create_preset(request.agent_role, request.name, request.base_prompt_version, request.instruction_ids, request.description)
    if preset is None:
        raise HTTPException(status_code=409, detail="A preset with this (agent_role, name) already exists.")
    return PresetResponse.from_response(preset)


@router.put("/presets/{preset_id}")
def update_preset(preset_id: int, request: UpdatePresetRequest, service: PromptService = Depends(prompt_service)) -> PresetResponse:
    """Update a preset — presets are mutable selections, every field may
    change; 404 on a miss, 400 on an unknown base version, 409 when renaming
    onto an existing (agent_role, name)."""
    existing = service.get_preset(preset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="System prompt preset not found.")
    if request.base_prompt_version is not None and not service.prompt_version_exists(existing.agent_role, request.base_prompt_version):
        raise HTTPException(status_code=400, detail=f"No prompt version '{request.base_prompt_version}' registered for role '{existing.agent_role}'.")
    preset = service.update_preset(preset_id, request.name, request.description, request.base_prompt_version, request.instruction_ids, request.is_active)
    if preset is None:
        raise HTTPException(status_code=409, detail="A preset with this (agent_role, name) already exists.")
    return PresetResponse.from_response(preset)


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int, service: PromptService = Depends(prompt_service)) -> PresetResponse:
    """Remove a preset for good; 404 when it does not exist. Past runs are
    unaffected: they store the composed prompt verbatim."""
    preset = service.get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="System prompt preset not found.")
    service.delete_preset(preset_id)
    return PresetResponse.from_response(preset)



@router.post("/presets/preview")
def preview_preset(request: PromptPreviewRequest, service: PromptService = Depends(prompt_service)) -> PromptPreviewResponse:
    try:
        prompt = service.build_system_prompt_from_preset_id(agent_role=request.agent_role, preset_id=request.preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return PromptPreviewResponse.from_response(prompt)
