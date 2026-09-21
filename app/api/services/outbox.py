from uuid import UUID
from datetime import datetime, timezone


from app.api.models.enum import OutBoxEnum
from app.api.models.outbox import OutBox
from app.api.schemas.outbox import OutBoxCreate
from app.api.repo.outbox import OutBoxRepository


class OutBoxService:
    def __init__(self, out_box_repo: OutBoxRepository):
        self._out_box_repo = out_box_repo

    async def _create_out_box(self, out_box_create: OutBoxCreate):
        self._out_box_repo.add(entity=out_box_create)

    def _get_outbox_records(self, **filters):
        return self._out_box_repo._get_outbox_records(**filters)

    def _update_outbox_records(self, records: list[dict]):
        self._out_box_repo._update_outbox_records(records)

    def mark_processed_sync(self, out_box_id: UUID):
        """Marks a single outbox row as completed - called by the original
        task (not the outbox poller) once it has actually done the work, so
        a later poll of pending rows skips it instead of redoing it."""
        self._out_box_repo._update_outbox_records(
            [
                {
                    "id": out_box_id,
                    "status": OutBoxEnum.COMPLETED,
                    "processed_at": datetime.now(timezone.utc),
                }
            ]
        )
