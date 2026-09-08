from sqlalchemy.orm import Session

from ..models import User

DEMO_USER_ID = "demo-user"
DEMO_USER_NAME = "수영"


def ensure_demo_user(db: Session) -> User:
    user = db.get(User, DEMO_USER_ID)
    if user is None:
        user = User(id=DEMO_USER_ID, name=DEMO_USER_NAME)
        db.add(user)
        db.commit()
    return user


def reset_demo_user(db: Session) -> User:
    """Delete the demo user and recreate it in one transaction.

    Dependent rows go with it through ON DELETE CASCADE, so a failure anywhere
    rolls back to the previous state instead of leaving the demo half-erased.
    """
    try:
        existing = db.get(User, DEMO_USER_ID)
        if existing is not None:
            db.delete(existing)
            db.flush()
        user = User(id=DEMO_USER_ID, name=DEMO_USER_NAME)
        db.add(user)
        db.commit()
        return user
    except Exception:
        db.rollback()
        raise
