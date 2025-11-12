from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from crud.session_crud import list_sessions, get_session, get_session_by_token, create_session, update_session, delete_session
from schemas.session_schema import SessionCreate, SessionResponse, SessionUpdate


router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("/", response_model=list[SessionResponse])
def list_all(user_id: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return list_sessions(db, user_id=user_id, skip=skip, limit=limit)


@router.get("/by-token/{token}", response_model=SessionResponse)
def read_by_token(token: str, db: Session = Depends(get_db)):
    s = get_session_by_token(db, token)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.get("/{session_id}", response_model=SessionResponse)
def read_one(session_id: str, db: Session = Depends(get_db)):
    s = get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.post("/", response_model=SessionResponse, status_code=201)
def create(payload: SessionCreate, db: Session = Depends(get_db)):
    return create_session(db, payload)


@router.patch("/{session_id}", response_model=SessionResponse)
def update(session_id: str, payload: SessionUpdate, db: Session = Depends(get_db)):
    s = update_session(db, session_id, payload)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.delete("/{session_id}", status_code=204)
def delete(session_id: str, db: Session = Depends(get_db)):
    ok = delete_session(db, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return None

