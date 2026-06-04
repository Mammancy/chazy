import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.session import get_db
from app.main import create_application
from app.models import Base
from app.services.voice_room_service import voice_room_signaling_manager


class VoiceRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'voice-room-test.db')}",
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
        voice_room_signaling_manager.active_connections.clear()
        self.app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()
        get_settings.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_voice_room_relays_offer_answer_ice_and_mute_events(self):
        first, second, room = self._practice_room()

        with self.client.websocket_connect(self._ws_url(room["id"], first)) as first_socket:
            with self.client.websocket_connect(self._ws_url(room["id"], second)) as second_socket:
                join_event = first_socket.receive_json()
                self.assertEqual(join_event["type"], "join")
                self.assertEqual(join_event["sender_user_id"], second["user"]["id"])

                second_socket.send_json({"type": "offer", "sdp": {"type": "offer", "sdp": "fake-offer"}})
                offer = first_socket.receive_json()
                self.assertEqual(offer["type"], "offer")
                self.assertEqual(offer["sender_user_id"], second["user"]["id"])

                first_socket.send_json({"type": "answer", "sdp": {"type": "answer", "sdp": "fake-answer"}})
                answer = second_socket.receive_json()
                self.assertEqual(answer["type"], "answer")

                second_socket.send_json({"type": "ice-candidate", "candidate": {"candidate": "fake"}})
                candidate = first_socket.receive_json()
                self.assertEqual(candidate["type"], "ice-candidate")

                first_socket.send_json({"type": "mute"})
                mute = second_socket.receive_json()
                self.assertEqual(mute["type"], "mute")

    def test_voice_room_rejects_non_participant(self):
        first, _, room = self._practice_room()
        third = self._sign_up("voice-third@example.com", "Voice Third")
        with self.assertRaises(Exception):
            self.client.websocket_connect(self._ws_url(room["id"], third)).__enter__()
        self.assertTrue(first)

    def _practice_room(self) -> tuple[dict, dict, dict]:
        first = self._sign_up("voice-first@example.com", "Voice First")
        second = self._sign_up("voice-second@example.com", "Voice Second")
        request = self._accepted_request(first, second)
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
                "topic": "Voice practice",
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)
        room = self.client.post(
            f"/api/v1/practice-sessions/{created.json()['id']}/room/start",
            headers=self._auth_header(first),
        )
        self.assertEqual(room.status_code, 200, room.text)
        return first, second, room.json()

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
                "phone_number": f"095{abs(hash(email)) % 10000000:07d}",
                "country": "Nigeria",
                "state": "Kano",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _ws_url(self, room_id: int, auth_body: dict) -> str:
        return f"/ws/voice-rooms/{room_id}?token={auth_body['access_token']}"

    @staticmethod
    def _auth_header(auth_body: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth_body['access_token']}"}


if __name__ == "__main__":
    unittest.main()
