from fastapi import APIRouter

from app.routes.achievements import router as achievements_router
from app.routes.admin_analytics import router as admin_analytics_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.conversation_scenario import router as conversation_scenario_router
from app.routes.fluency_dashboard import router as fluency_dashboard_router
from app.routes.health import router as health_router
from app.routes.learning_analytics import router as learning_analytics_router
from app.routes.placement_assessment import router as placement_assessment_router
from app.routes.pronunciation import router as pronunciation_router
from app.routes.recommendations import router as recommendations_router
from app.routes.speaking_challenge import router as speaking_challenge_router
from app.routes.vocabulary_notebook import router as vocabulary_notebook_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(achievements_router)
api_router.include_router(admin_analytics_router)
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(conversation_scenario_router)
api_router.include_router(placement_assessment_router)
api_router.include_router(pronunciation_router)
api_router.include_router(speaking_challenge_router)
api_router.include_router(learning_analytics_router)
api_router.include_router(fluency_dashboard_router)
api_router.include_router(recommendations_router)
api_router.include_router(vocabulary_notebook_router)
