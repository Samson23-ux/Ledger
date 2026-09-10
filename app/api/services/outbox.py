from app.api.models.outbox import OutBox
from app.api.schemas.outbox import OutBoxCreate
from app.api.repo.outbox import OutBoxRepository


class OutBoxService:
    def __init__(self, out_box_repo: OutBoxRepository):
        self._out_box_repo = out_box_repo

    async def _create_out_box(self, out_box_create: OutBoxCreate):
        self._out_box_repo.add(entity=out_box_create)

    def _update_out_box(self, out_box: OutBox):
        self._out_box_repo.sync_add(model=out_box)
