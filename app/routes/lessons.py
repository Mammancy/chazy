from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.lesson import CourseResponse, LessonCompleteResponse, LessonDetailResponse
from app.services.lesson_service import LessonService

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.get("/", response_model=list[CourseResponse])
async def list_courses(
    category: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CourseResponse]:
    return LessonService(db).list_courses(
        user_id=current_user.id,
        category=category,
        difficulty=difficulty,
        search=search,
    )


@router.get("/{lesson_id}", response_model=LessonDetailResponse)
async def get_lesson(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonDetailResponse:
    lesson = LessonService(db).get_lesson(lesson_id, user_id=current_user.id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return lesson


@router.post("/{lesson_id}/complete", response_model=LessonCompleteResponse)
async def complete_lesson(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonCompleteResponse:
    result = LessonService(db).complete_lesson(lesson_id, user_id=current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return result
