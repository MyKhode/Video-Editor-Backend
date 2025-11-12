from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.session import Session as SessionModel
from schemas.session_schema import SessionCreate, SessionUpdate


def get_session(db: Session, session_id: str):
    return db.query(SessionModel).filter(SessionModel.id == session_id).first()


def get_session_by_token(db: Session, token: str):
    return db.query(SessionModel).filter(SessionModel.token == token).first()


def list_sessions(db: Session, user_id: str | None = None, skip: int = 0, limit: int = 100):
    q = db.query(SessionModel)
    if user_id:
        q = q.filter(SessionModel.user_id == user_id)
    return q.order_by(desc(SessionModel.created_at)).offset(skip).limit(limit).all()


def create_session(db: Session, payload: SessionCreate):
    s = SessionModel(
        user_id=payload.user_id,
        token=payload.token,
        expires_at=payload.expires_at,
        ip_address=payload.ip_address,
        user_agent=payload.user_agent,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_session(db: Session, session_id: str, payload: SessionUpdate):
    s = get_session(db, session_id)
    if not s:
        return None
    if payload.expires_at is not None:
        s.expires_at = payload.expires_at
    if payload.ip_address is not None:
        s.ip_address = payload.ip_address
    if payload.user_agent is not None:
        s.user_agent = payload.user_agent
    db.commit()
    db.refresh(s)
    return s


def delete_session(db: Session, session_id: str) -> bool:
    s = get_session(db, session_id)
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True

