from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.practice_room import PracticeTopicResponse
from app.services.practice_room_service import PracticeRoomService

router = APIRouter(prefix="/practice-topics", tags=["practice-topics"])


@router.get("/random", response_model=PracticeTopicResponse)
async def random_practice_topic(db: Session = Depends(get_db)) -> PracticeTopicResponse:
    return PracticeRoomService(db).random_topic()
