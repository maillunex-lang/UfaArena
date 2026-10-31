from sqlalchemy.orm import Session

from ..models import AuditEvent


def audit(db: Session, user_id: str | None, action: str, ip: str | None = None, **details) -> None:
    db.add(AuditEvent(user_id=user_id, action=action, details=details, ip=ip))
