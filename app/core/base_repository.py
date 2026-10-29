import uuid
from typing import Any, Generic, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.strategy_options import _AbstractLoad

from app.common.pagination import PaginatedResult, PaginationParams, apply_search, paginate
from app.common.utils import utc_now
from app.core.exceptions import DependencyExistsError, NotFoundError

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """
    Generic async repository providing common CRUD + list/paginate operations.

    Subclasses MUST declare:
      - model: the SQLAlchemy model class
      - eager_load_options: list of selectinload/joinedload options applied
        to every SELECT, to avoid N+1 queries and MissingGreenlet errors.
      - search_columns: columns eligible for the `search` query param.
      - dependent_checks: callables used to block delete when child rows exist.

    All read/write operations are async and expect an AsyncSession injected
    from the caller (service layer), keeping transaction boundaries at the
    service level.
    """

    model: Type[ModelType]
    eager_load_options: List[_AbstractLoad] = []
    search_columns: List[Any] = []
    soft_delete: bool = True

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Base query builder -------------------------------------------------

    def _base_select(self) -> Select:
        stmt = select(self.model)
        if self.eager_load_options:
            stmt = stmt.options(*self.eager_load_options)
        if self.soft_delete and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    # --- Reads ----------------------------------------------------------------

    async def get_by_id(self, id_: uuid.UUID) -> ModelType | None:
        stmt = self._base_select().where(self.model.id == id_)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, id_: uuid.UUID) -> ModelType:
        obj = await self.get_by_id(id_)
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} with id '{id_}' was not found.")
        return obj

    async def list(
        self,
        params: PaginationParams,
        extra_filters: Optional[List[Any]] = None,
    ) -> PaginatedResult:
        """
        Generic paginated list, applying search across `search_columns`
        and any extra_filters supplied by the calling service (e.g. status).
        """
        stmt = self._base_select()

        if extra_filters:
            for condition in extra_filters:
                stmt = stmt.where(condition)

        stmt = apply_search(stmt, params.search, self.search_columns)

        if hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())

        return await paginate(self.db, stmt, params)

    async def list_all(self, extra_filters: Optional[List[Any]] = None) -> Sequence[ModelType]:
        stmt = self._base_select()
        if extra_filters:
            for condition in extra_filters:
                stmt = stmt.where(condition)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # --- Writes -----------------------------------------------------------

    async def create(self, **kwargs) -> ModelType:
        obj = self.model(**kwargs)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType, **kwargs) -> ModelType:
        for key, value in kwargs.items():
            if value is not None and hasattr(obj, key):
                setattr(obj, key, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """
        Deletes (or soft-deletes) a row, but first checks for dependent
        rows via `assert_no_dependents`. Subclasses override
        `get_dependent_conflicts` to declare which child tables block delete.
        """
        await self.assert_no_dependents(obj)

        if self.soft_delete and hasattr(obj, "deleted_at"):
            obj.deleted_at = utc_now()
            await self.db.flush()
            return

        try:
            await self.db.delete(obj)
            await self.db.flush()
        except IntegrityError as exc:
            # DB-level FK RESTRICT as a backstop even if the app-level
            # check above was bypassed or a race condition occurred.
            await self.db.rollback()
            raise DependencyExistsError(
                f"{self.model.__name__} cannot be deleted because dependent records exist."
            ) from exc

    async def assert_no_dependents(self, obj: ModelType) -> None:
        """
        Override in subclasses to check dependent tables before delete, e.g.:

            async def assert_no_dependents(self, obj):
                stmt = select(func.count()).select_from(ChildModel).where(
                    ChildModel.parent_id == obj.id, ChildModel.deleted_at.is_(None)
                )
                count = (await self.db.execute(stmt)).scalar_one()
                if count > 0:
                    raise DependencyExistsError(
                        f"Cannot delete: {count} dependent Child record(s) exist."
                    )
        """
        return None