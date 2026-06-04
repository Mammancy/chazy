from datetime import datetime

from pydantic import BaseModel


class NotificationItemResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    href: str
    priority: str
    created_at: datetime
    session_id: int | None = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItemResponse]
    unread_count: int
