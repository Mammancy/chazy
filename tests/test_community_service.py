import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base, PronunciationExercise, PronunciationPracticeAttempt, PronunciationPracticeSession, User


class CommunityServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(os.environ, {"JWT_SECRET_KEY": "test-jwt-secret"})
        self.env_patch.start()
        get_settings.cache_clear()

        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'community-test.db')}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False,
        )
        Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app = create_application()
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        get_settings.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_feed_sorts_mixed_timezone_datetimes(self):
        with self.SessionLocal() as db:
            user = User(
                email="community@example.com",
                full_name="Community User",
                password_hash="x",
                is_active=True,
                public_profile_visible=True,
            )
            exercise = PronunciationExercise(
                word="thought",
                phonetic_spelling="thawt",
                difficulty="beginner",
                example_sentences=["I thought about it."],
                pronunciation_tips=["Practice the th sound."],
            )
            db.add_all([user, exercise])
            db.commit()
            db.refresh(user)
            db.refresh(exercise)

            session = PronunciationPracticeSession(
                client_session_id=f"chazy-user-{user.id}",
                user_id=user.id,
                status="completed",
                target_word_count=1,
                current_word_index=1,
                completed_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            )
            db.add(session)
            db.commit()
            db.refresh(session)

            attempt = PronunciationPracticeAttempt(
                practice_session_id=session.id,
                exercise_id=exercise.id,
                user_id=user.id,
                scoring_status="scored",
                score=83,
                feedback="Good practice.",
                created_at=datetime(2026, 6, 1, 9, 5),
            )
            db.add(attempt)
            db.commit()

        response = self.client.get("/api/v1/community/feed?limit=20")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertEqual(body["activities"][0]["type"], "pronunciation_completed")


if __name__ == "__main__":
    unittest.main()
