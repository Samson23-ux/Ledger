from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict


from app.api.models.state import TransactionStatus
from app.api.models.transaction_state_events import EntityEnum, SourceEnum


class TransactionStateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: EntityEnum
    transaction_id: UUID
    to_status: TransactionStatus
    source: SourceEnum


class TransactionStateCreate(TransactionStateBase):
    pass


class TransactionStateUpdate(BaseModel):
    entity_type: Optional[EntityEnum] = None
    transaction_id: Optional[UUID] = None
    from_status: Optional[TransactionStatus] = None
    to_status: Optional[TransactionStatus] = None
    source: Optional[SourceEnum] = None
    webhook_event_id: Optional[UUID] = None
