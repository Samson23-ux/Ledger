from typing import Type, TypeVar
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

TRepo = TypeVar("TRepo")

"""
Share a single session across repositories to ensure atomic transactions.
This keeps repositories reusable and prevents services from manually
rebinding each repo to the same session.
"""


class UnitOfWorkRepository:
    def __init__(self, sync_session: Session = None, async_session: AsyncSession = None):
        self._sync_session = sync_session
        self._async_session = async_session

        self._repositories: dict[type, object] = {}

    @property
    def async_session(self) -> AsyncSession:
        return self._async_session

    @property
    def sync_session(self) -> Session:
        return self._sync_session

    def repo(self, repository_cls: Type[TRepo], **kwargs) -> TRepo:
        repo = self._repositories.get(repository_cls)

        if repo is None:
            repo = repository_cls(async_session=self._async_session, **kwargs)
            self._repositories[repository_cls] = repo

        return repo

    async def flush(self):
        await self._async_session.flush()

    async def refresh(self, model):
        await self._async_session.refresh(model)

    async def commit(self):
        await self._async_session.commit()

    async def rollback(self):
        await self._async_session.rollback()
