from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.modules.auth.models import User


class UserRepository(BaseRepository[User]):
    model = User
    eager_load_options = [selectinload(User.roles)]
    search_columns = [User.email]

    async def get_by_email(self, email: str, *, include_deleted: bool = False) -> User | None:
        if include_deleted:
            stmt = select(User).where(User.email == email)
        else:
            stmt = self._base_select().where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()