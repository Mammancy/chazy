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
from app.models import Base, PracticeRoomMessage
from app.services.realtime_practice_service import connection_manager


class RealtimePracticeRoomTests(unittest.TestCase):
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
            f"sqlite:///{os.path.join(self.temp_dir.name, 'practice-room-realtime-test.db')}",
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
        connection_manager.active_connections.clear()
        connection_manager.participants.clear()
        connection_manager.typing_users.clear()
        self.app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()
        get_settings.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_websocket_connect_disconnect_and_presence(self):
        first, _, _, room = self._practice_room()

        with self.client.websocket_connect(self._ws_url(room["id"], first)) as websocket:
            event = websocket.receive_json()
            self.assertEqual(event["type"], "presence")
            self.assertEqual(event["users"][0]["user_id"], first["user"]["id"])

    def test_websocket_message_broadcast_and_persistence(self):
        first, second, session, room = self._practice_room()

        with self.client.websocket_connect(self._ws_url(room["id"], first)) as first_socket:
            self.assertEqual(first_socket.receive_json()["type"], "presence")
            with self.client.websocket_connect(self._ws_url(room["id"], second)) as second_socket:
                self.assertEqual(second_socket.receive_json()["type"], "presence")
                self.assertEqual(first_socket.receive_json()["type"], "presence")

                first_socket.send_json({"type": "message", "content": "Let us practice interview answers."})
                first_event = first_socket.receive_json()
                second_event = second_socket.receive_json()

                self.assertEqual(first_event["type"], "message")
                self.assertEqual(second_event["type"], "message")
                self.assertEqual(first_event["message"]["content"], "Let us practice interview answers.")
                self.assertEqual(second_event["message"]["sender_user_id"], first["user"]["id"])

        with self.SessionLocal() as db:
            messages = db.scalars(select(PracticeRoomMessage)).all()
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].content, "Let us practice interview answers.")

        history = self.client.get(
            f"/api/v1/practice-sessions/{session['id']}/messages",
            headers=self._auth_header(second),
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["messages"][0]["content"], "Let us practice interview answers.")

    def test_websocket_typing_indicator_broadcast(self):
        first, second, _, room = self._practice_room()

        with self.client.websocket_connect(self._ws_url(room["id"], first)) as first_socket:
            self.assertEqual(first_socket.receive_json()["type"], "presence")
            with self.client.websocket_connect(self._ws_url(room["id"], second)) as second_socket:
                self.assertEqual(second_socket.receive_json()["type"], "presence")
                self.assertEqual(first_socket.receive_json()["type"], "presence")

                second_socket.send_json({"type": "typing", "isTyping": True})
                first_event = first_socket.receive_json()
                second_event = second_socket.receive_json()

                self.assertEqual(first_event["type"], "typing")
                self.assertEqual(second_event["type"], "typing")
                self.assertTrue(first_event["is_typing"])
                self.assertEqual(first_event["user_id"], second["user"]["id"])

    def _practice_room(self) -> tuple[dict, dict, dict, dict]:
        first = self._sign_up("realtime-first@example.com", "Realtime First")
        second = self._sign_up("realtime-second@example.com", "Realtime Second")
        request = self._accepted_request(first, second)
        created = self.client.post(
            "/api/v1/practice-sessions",
            json={
                "request_id": request["id"],
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "duration_minutes": 30,
                "topic": "Interview confidence",
            },
            headers=self._auth_header(first),
        )
        self.assertEqual(created.status_code, 200, created.text)
        session = created.json()
        room = self.client.post(
            f"/api/v1/practice-sessions/{session['id']}/room",
            headers=self._auth_header(first),
        )
        self.assertEqual(room.status_code, 200, room.text)
        return first, second, session, room.json()

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
                "phone_number": f"081{abs(hash(email)) % 10000000:07d}",
                "country": "Nigeria",
                "state": "Kano",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _ws_url(self, room_id: int, auth_body: dict) -> str:
        return f"/ws/practice-rooms/{room_id}?token={auth_body['access_token']}"

    @staticmethod
    def _auth_header(auth_body: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth_body['access_token']}"}


if __name__ == "__main__":
    unittest.main()
