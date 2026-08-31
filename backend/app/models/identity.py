from pydantic import BaseModel


class IdentityFieldMapping(BaseModel):
    field_label: str
    value: str | None = None
    requires_human_review: bool = False
    reason: str
