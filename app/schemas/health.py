from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    version: str
    email: dict | None = None
