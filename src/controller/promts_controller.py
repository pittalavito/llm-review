"""Prompts endpoints — everything under /prompts (prompt-version registry)."""
from fastapi import APIRouter, Depends, HTTPException

from core.container import prompt_service
from models.controller.prompt import (
    CreateInstructionRequest,
    CreatePromptRequest,
    PromptInstructionListResponse,
    PromptInstructionResponse,
    PromptVersionListResponse,
    PromptVersionResponse,
    UpdateInstructionRequest,
    UpdatePromptRequest,
)
from models.domain.prompt import InstructionType
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
    instruction = service.create_instruction(request.type, request.label, request.instruction, request.description, request.agent_role)
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
