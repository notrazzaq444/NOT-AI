from pydantic import BaseModel, Field
from datetime import datetime

class MemoryRecord(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=4000)
    approved: bool = False
    created_at: datetime | None = None
