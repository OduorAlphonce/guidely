from fastapi import APIRouter, HTTPException
from backend.models.record import Query, Answer

router = APIRouter()


@router.post("/", response_model=Answer)
async def search(query: Query):
    return Answer(
        question=query.question,
        answer="Search will be implemented on Day 3.",
        sources=[],
    )
