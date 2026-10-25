from functools import wraps
from fastapi import HTTPException, status
from app.models.user import User, Role


def require_role(required_role: Role):
    def decorator(func):
        @wraps(func)
        async def wrapper(current_user: User = None, *args, **kwargs):
            if current_user.role != required_role:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
            return await func(current_user=current_user, *args, **kwargs)
        return wrapper
    return decorator