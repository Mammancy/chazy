from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.lesson import CourseResponse, LessonDetailResponse
from app.services.lesson_service import LessonService

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.get("/", response_model=list[CourseResponse])
async def list_courses(
    category: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> list[CourseResponse]:
    return LessonService().list_courses(
        category=category,
        difficulty=difficulty,
        search=search,
    )


@router.get("/{lesson_id}", response_model=LessonDetailResponse)
async def get_lesson(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
) -> LessonDetailResponse:
    lesson = LessonService().get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return lesson
