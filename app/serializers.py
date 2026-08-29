from datetime import datetime


from app.api.models.user import User


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "type": user.type.value,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email or "",
        "hashed_password": user.hashed_password or "",
        "google_id": user.google_id or "",
        "google_email": user.google_email or "",
        "is_active": "1" if user.is_active else "0",
        "is_verified": "1" if user.is_verified else "0",
        "created_at": user.created_at.isoformat(),
    }


def _deserialize_cached_user(cached: dict) -> User:
    return User(
        id=cached["id"],
        type=cached["type"],
        first_name=cached["first_name"],
        last_name=cached["last_name"],
        email=cached["email"] or None,
        hashed_password=cached["hashed_password"] or None,
        google_id=cached["google_id"] or None,
        google_email=cached["google_email"] or None,
        is_active=bool(cached["is_active"]),
        is_verified=bool(cached["is_verified"]),
        created_at=datetime.fromisoformat(cached["created_at"]),
    )
