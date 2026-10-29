from dataclasses import dataclass, field
from typing import Any, Sequence

from fastapi import Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PER_PAGE = 15
MAX_PER_PAGE = 500


@dataclass
class PaginationParams:
    """
    Shared query-param contract for all list endpoints.

    - page: 1-indexed page number (ignored when per_page == "all")
    - per_page: int between 1 and MAX_PER_PAGE, or the literal "all"
    - search: optional free-text search term
    """

    page: int = 1
    per_page: int | str = DEFAULT_PER_PAGE
    search: str | None = None

    @property
    def is_fetch_all(self) -> bool:
        return isinstance(self.per_page, str) and self.per_page.lower() == "all"

    @property
    def limit(self) -> int | None:
        return None if self.is_fetch_all else int(self.per_page)

    @property
    def offset(self) -> int:
        if self.is_fetch_all:
            return 0
        return (self.page - 1) * int(self.per_page)


def pagination_params(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    per_page: str = Query(
        default=str(DEFAULT_PER_PAGE),
        description=f"Rows per page (1-{MAX_PER_PAGE}), or 'all' to fetch every row",
    ),
    search: str | None = Query(default=None, description="Free-text search"),
) -> PaginationParams:
    """
    FastAPI dependency: validates and normalizes pagination query params.
    """
    if per_page.strip().lower() == "all":
        normalized_per_page: int | str = "all"
    else:
        try:
            value = int(per_page)
        except ValueError:
            value = DEFAULT_PER_PAGE
        normalized_per_page = max(1, min(value, MAX_PER_PAGE))

    return PaginationParams(
        page=max(1, page),
        per_page=normalized_per_page,
        search=search,
    )


@dataclass
class PaginatedResult:
    data: Sequence[Any]
    total: int
    page: int
    per_page: int | str
    total_pages: int


def apply_search(stmt: Select, search: str | None, columns: Sequence[Any]) -> Select:
    """
    Applies a case-insensitive OR search across multiple columns.

    Usage:
        stmt = apply_search(stmt, params.search, [Model.name, Model.email])
    """
    if not search or not columns:
        return stmt
    pattern = f"%{search.strip()}%"
    conditions = [col.ilike(pattern) for col in columns]
    return stmt.where(or_(*conditions))


async def paginate(
    db: AsyncSession,
    stmt: Select,
    params: PaginationParams,
) -> PaginatedResult:
    """
    Executes a count query + a paginated (or full) data query for the given
    base statement, and returns a normalized PaginatedResult.

    `stmt` should already have filters (status/search/joins) applied;
    this function only applies ordering-agnostic limit/offset and counts.
    """
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    if not params.is_fetch_all:
        stmt = stmt.limit(params.limit).offset(params.offset)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    if params.is_fetch_all:
        total_pages = 1 if total > 0 else 0
        page = 1
    else:
        per_page_int = int(params.per_page)
        total_pages = (total + per_page_int - 1) // per_page_int if total > 0 else 0
        page = params.page

    return PaginatedResult(
        data=rows,
        total=total,
        page=page,
        per_page=params.per_page,
        total_pages=total_pages,
    )