from uuid import UUID


from app.api.schemas.authorization_codes import AuthCodesCreate
from app.api.repo.authorization_codes import AuthCodeRepository
from app.api.models.authorization_codes import AuthorizationCode


class AuthCodeService:
    def __init__(self, code_repo: AuthCodeRepository):
        self._code_repo = code_repo

    async def _get_auth_code(self, wallet_id: UUID) -> AuthorizationCode | None:
        return await self._code_repo.get_record(wallet_id=wallet_id)

    def _create_auth_code(self, code_create: AuthCodesCreate):
        self._code_repo._create_auth_code(code_create)
