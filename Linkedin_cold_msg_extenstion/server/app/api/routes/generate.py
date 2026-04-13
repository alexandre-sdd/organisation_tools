from fastapi import APIRouter

from ...models import GenerateRequest, GenerateResponse
from ...services.generation_service import GenerationService

router = APIRouter()
generation_service = GenerationService()


@router.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest) -> GenerateResponse:
    return await generation_service.generate(payload)
