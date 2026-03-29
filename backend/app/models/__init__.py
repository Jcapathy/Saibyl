from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SaibylBaseModel(BaseModel):
    model_config = {"from_attributes": True}


class TimestampedModel(SaibylBaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
