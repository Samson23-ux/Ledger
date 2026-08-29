from typing import Type, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession

TRepo = TypeVar("TRepo")

"""
Share a single session across repositories to ensure atomic transactions.
This keeps repositories reusable and prevents services from manually
rebinding each repo to the same session.
"""


class UnitOfWorkRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repositories: dict[type, object] = {}

    @property
    def session(self) -> AsyncSession:
        return self._session

    def repo(self, repository_cls: Type[TRepo], **kwargs) -> TRepo:
        repo = self._repositories.get(repository_cls)

        if repo is None:
            repo = repository_cls(async_session=self._session, **kwargs)
            self._repositories[repository_cls] = repo

        return repo

    async def flush(self):
        await self._session.flush()

    async def refresh(self, model):
        await self._session.refresh(model)

    async def commit(self):
        await self._session.commit()

    async def rollback(self):
        await self._session.rollback()
