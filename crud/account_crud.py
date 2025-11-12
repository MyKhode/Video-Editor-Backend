from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.account import Account
from schemas.account_schema import AccountCreate, AccountUpdate


def get_account(db: Session, account_id: str):
    return db.query(Account).filter(Account.id == account_id).first()


def list_accounts(db: Session, user_id: str | None = None, skip: int = 0, limit: int = 100):
    q = db.query(Account)
    if user_id:
        q = q.filter(Account.user_id == user_id)
    return q.order_by(desc(Account.created_at)).offset(skip).limit(limit).all()


def create_account(db: Session, payload: AccountCreate):
    acc = Account(**payload.model_dump())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def update_account(db: Session, account_id: str, payload: AccountUpdate):
    acc = get_account(db, account_id)
    if not acc:
        return None
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(acc, k, v)
    db.commit()
    db.refresh(acc)
    return acc


def delete_account(db: Session, account_id: str) -> bool:
    acc = get_account(db, account_id)
    if not acc:
        return False
    db.delete(acc)
    db.commit()
    return True

