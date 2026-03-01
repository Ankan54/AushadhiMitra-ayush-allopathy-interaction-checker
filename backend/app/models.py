from pydantic import BaseModel
from typing import Optional


class InteractionRequest(BaseModel):
    ayush_name: str
    allopathy_name: str


class HealthResponse(BaseModel):
    status: str
    agent_id: str
    agent_alias_id: str
    database: str
