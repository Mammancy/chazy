import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import AchievementAward, Base


class PracticeSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "test-jwt-secret",
                "JWT_ACCESS_TOKEN_MINUTES": "30",
                "JWT_REFRESH_TOKEN_DAYS": "30",
            },
        )
        self.env_patch.start()
        get_settings.cache_clear()

        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'practice-session-test.db')}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, expire_on_commit=False)
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

    def test_create_complete_and_award_xp(self):
        first = self._sign_up("schedule-first@example.com", "Schedule First")
        second = self._sign_up("schedule-second@example.com", "Schedule Second")
        request = self._accepted_request(first, second)

        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
                "topic": "Interview confidence",
                "notes": "Practice clear examples.",
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)
        session = created.json()
        self.assertEqual(session["status"], "scheduled")

        completed = self.client.patch(
            f"/api/v1/practice-sessions/{session['id']}/complete",
            json={"feedback": "Helpful practice with clear speaking goals."},
            headers=self._auth_header(first),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["status"], "completed")
        self.assertEqual(completed.json()["xp_awarded"], 40)

        streak = self.client.get(
            "/api/v1/speaking-challenges/streak",
            params={"session_id": f"chazy-user-{first['user']['id']}"},
            headers=self._auth_header(first),
        )
        self.assertEqual(streak.status_code, 200, streak.text)
        self.assertGreaterEqual(streak.json()["current_streak"], 1)
        self.assertTrue(streak.json()["completed_today"])

        with self.SessionLocal() as db:
            awards = db.scalars(
                select(AchievementAward).where(AchievementAward.category == "practice_session")
            ).all()
            self.assertTrue(any(award.points == 40 for award in awards))
            self.assertTrue(any(award.achievement_key == "partner_practice_1" for award in awards))

    def test_rejects_unaccepted_request_and_cross_user_access(self):
        first = self._sign_up("schedule-cross-first@example.com", "Cross First")
        second = self._sign_up("schedule-cross-second@example.com", "Cross Second")
        third = self._sign_up("schedule-cross-third@example.com", "Cross Third")
        self._public_profile(second)

        pending = self.client.post(
            "/api/v1/speaking-partners/requests",
            json={"receiver_user_id": second["user"]["id"], "message": "Practice?"},
            headers=self._auth_header(first),
        )
        self.assertEqual(pending.status_code, 200, pending.text)

        rejected = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": pending.json()["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 15,
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(rejected.status_code, 400)

        accepted_response = self.client.patch(
            f"/api/v1/speaking-partners/requests/{pending.json()['id']}",
            json={"status": "accepted"},
            headers=self._auth_header(second),
        )
        self.assertEqual(accepted_response.status_code, 200, accepted_response.text)
        accepted = accepted_response.json()
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": accepted["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 15,
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)

        forbidden = self.client.get(
            f"/api/v1/practice-sessions/{created.json()['id']}",
            headers=self._auth_header(third),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_practice_room_lifecycle_and_random_topic(self):
        first = self._sign_up("room-first@example.com", "Room First")
        second = self._sign_up("room-second@example.com", "Room Second")
        request = self._accepted_request(first, second)
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
                "topic": "Leadership practice",
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["id"]

        room = self.client.post(
            f"/api/v1/practice-sessions/{session_id}/room",
            headers=self._auth_header(first),
        )
        self.assertEqual(room.status_code, 200, room.text)
        self.assertEqual(room.json()["status"], "scheduled")
        self.assertTrue(room.json()["room_code"].startswith("CONF-"))

        started = self.client.post(
            f"/api/v1/practice-sessions/{session_id}/room/start",
            headers=self._auth_header(second),
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["status"], "active")
        self.assertIsNotNone(started.json()["started_at"])

        ended = self.client.post(
            f"/api/v1/practice-sessions/{session_id}/room/end",
            headers=self._auth_header(first),
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertEqual(ended.json()["status"], "ended")
        self.assertIsNotNone(ended.json()["ended_at"])

        restarted = self.client.post(
            f"/api/v1/practice-sessions/{session_id}/room/start",
            headers=self._auth_header(first),
        )
        self.assertEqual(restarted.status_code, 400)

        topic = self.client.get("/api/v1/practice-topics/random")
        self.assertEqual(topic.status_code, 200, topic.text)
        self.assertIn(topic.json()["category"], {"Public Speaking", "Interviews", "Daily Conversation", "Leadership"})
        self.assertTrue(topic.json()["prompt"])

    def test_notifications_include_active_practice_room(self):
        first = self._sign_up("notify-first@example.com", "Notify First")
        second = self._sign_up("notify-second@example.com", "Notify Second")
        request = self._accepted_request(first, second)
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
                "topic": "Notification practice",
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["id"]

        started = self.client.post(
            f"/api/v1/practice-sessions/{session_id}/room/start",
            headers=self._auth_header(second),
        )
        self.assertEqual(started.status_code, 200, started.text)

        notifications = self.client.get(
            "/api/v1/notifications",
            headers=self._auth_header(first),
        )
        self.assertEqual(notifications.status_code, 200, notifications.text)
        body = notifications.json()
        self.assertGreaterEqual(body["unread_count"], 1)
        self.assertTrue(
            any(item["type"] == "practice_room_active" and item["session_id"] == session_id for item in body["notifications"])
        )

    def test_cancelled_session_cannot_start_room_or_complete(self):
        first = self._sign_up("room-cancel-first@example.com", "Room Cancel First")
        second = self._sign_up("room-cancel-second@example.com", "Room Cancel Second")
        request = self._accepted_request(first, second)
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["id"]

        cancelled = self.client.patch(
            f"/api/v1/practice-sessions/{session_id}/cancel",
            headers=self._auth_header(first),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)

        room = self.client.post(
            f"/api/v1/practice-sessions/{session_id}/room/start",
            headers=self._auth_header(first),
        )
        self.assertEqual(room.status_code, 400)

        completed = self.client.patch(
            f"/api/v1/practice-sessions/{session_id}/complete",
            json={"feedback": "Trying to complete a cancelled session."},
            headers=self._auth_header(first),
        )
        self.assertEqual(completed.status_code, 400)

    def _accepted_request(self, first: dict, second: dict) -> dict:
        self._public_profile(second)
        request = self.client.post(
            "/api/v1/speaking-partners/requests",
            json={"receiver_user_id": second["user"]["id"], "message": "Practice?"},
            headers=self._auth_header(first),
        )
        self.assertEqual(request.status_code, 200, request.text)
        accepted = self.client.patch(
            f"/api/v1/speaking-partners/requests/{request.json()['id']}",
            json={"status": "accepted"},
            headers=self._auth_header(second),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return accepted.json()

    def _public_profile(self, auth: dict) -> None:
        response = self.client.patch(
            "/api/v1/speaking-partners/me",
            json={"is_public": True, "target_language": "English"},
            headers=self._auth_header(auth),
        )
        self.assertEqual(response.status_code, 200, response.text)

    def _sign_up(self, email: str, full_name: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/signup",
            json={
                "full_name": full_name,
                "email": email,
                "phone_number": f"080{abs(hash(email)) % 10000000:07d}",
                "country": "Nigeria",
                "state": "Kano",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def _auth_header(auth_body: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth_body['access_token']}"}


if __name__ == "__main__":
    unittest.main()
