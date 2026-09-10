from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AuthCodeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: UUID
    code: str
    exp_month: str
    exp_year: str
    card_type: str
    country_code: str
    reusable: bool


class AuthCodesCreate(AuthCodeBase):
    pass
