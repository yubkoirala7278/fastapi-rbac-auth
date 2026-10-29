from typing import Any, Generic, Sequence, TypeVar

from pydantic import BaseModel

from app.common.pagination import PaginatedResult

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Success"
    data: T | None = None


class ApiErrorResponse(BaseModel):
    success: bool = False
    message: str
    detail: Any | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard envelope for list endpoints.

    Example:
        {
          "data": [ {...}, {...} ],
          "total": 2,
          "page": 1,
          "per_page": "all",
          "total_pages": 1
        }
    """

    data: Sequence[T]
    total: int
    page: int
    per_page: int | str
    total_pages: int

    @classmethod
    def from_result(cls, result: PaginatedResult, serializer=None) -> "PaginatedResponse":
        """
        Build a PaginatedResponse from a PaginatedResult (see common/pagination.py).
        `serializer` is an optional callable applied to each row (e.g. a Pydantic
        DTO's `.model_validate`), useful when the ORM rows need to be converted
        to response DTOs explicitly.
        """
        rows = [serializer(row) for row in result.data] if serializer else result.data
        return cls(
            data=rows,
            total=result.total,
            page=result.page,
            per_page=result.per_page,
            total_pages=result.total_pages,
        )