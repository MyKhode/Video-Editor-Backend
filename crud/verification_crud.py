from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.verification import Verification
from schemas.verification_schema import VerificationCreate, VerificationUpdate


def get_verification(db: Session, verification_id: str):
    return db.query(Verification).filter(Verification.id == verification_id).first()


def list_verifications(db: Session, identifier: str | None = None, skip: int = 0, limit: int = 100):
    q = db.query(Verification)
    if identifier:
        q = q.filter(Verification.identifier == identifier)
    return q.order_by(desc(Verification.created_at)).offset(skip).limit(limit).all()


def create_verification(db: Session, payload: VerificationCreate):
    ver = Verification(**payload.model_dump())
    db.add(ver)
    db.commit()
    db.refresh(ver)
    return ver


def update_verification(db: Session, verification_id: str, payload: VerificationUpdate):
    ver = get_verification(db, verification_id)
    if not ver:
        return None
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(ver, k, v)
    db.commit()
    db.refresh(ver)
    return ver


def delete_verification(db: Session, verification_id: str) -> bool:
    ver = get_verification(db, verification_id)
    if not ver:
        return False
    db.delete(ver)
    db.commit()
    return True


def get_by_identifier_value(db: Session, identifier: str, value: str):
    return (
        db.query(Verification)
        .filter(Verification.identifier == identifier, Verification.value == value)
        .first()
    )
