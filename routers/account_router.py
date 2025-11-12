from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from crud.account_crud import list_accounts, get_account, create_account, update_account, delete_account
from schemas.account_schema import AccountCreate, AccountResponse, AccountUpdate


router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=list[AccountResponse])
def list_all(user_id: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return list_accounts(db, user_id=user_id, skip=skip, limit=limit)


@router.get("/{account_id}", response_model=AccountResponse)
def read_one(account_id: str, db: Session = Depends(get_db)):
    acc = get_account(db, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.post("/", response_model=AccountResponse, status_code=201)
def create(payload: AccountCreate, db: Session = Depends(get_db)):
    return create_account(db, payload)


@router.patch("/{account_id}", response_model=AccountResponse)
def update(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db)):
    acc = update_account(db, account_id, payload)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.delete("/{account_id}", status_code=204)
def delete(account_id: str, db: Session = Depends(get_db)):
    ok = delete_account(db, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return None

