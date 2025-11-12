from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from crud.verification_crud import list_verifications, get_verification, create_verification, update_verification, delete_verification
from schemas.verification_schema import VerificationCreate, VerificationResponse, VerificationUpdate


router = APIRouter(prefix="/verifications", tags=["Verifications"])


@router.get("/", response_model=list[VerificationResponse])
def list_all(identifier: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return list_verifications(db, identifier=identifier, skip=skip, limit=limit)


@router.get("/{verification_id}", response_model=VerificationResponse)
def read_one(verification_id: str, db: Session = Depends(get_db)):
    ver = get_verification(db, verification_id)
    if not ver:
        raise HTTPException(status_code=404, detail="Verification not found")
    return ver


@router.post("/", response_model=VerificationResponse, status_code=201)
def create(payload: VerificationCreate, db: Session = Depends(get_db)):
    return create_verification(db, payload)


@router.patch("/{verification_id}", response_model=VerificationResponse)
def update(verification_id: str, payload: VerificationUpdate, db: Session = Depends(get_db)):
    ver = update_verification(db, verification_id, payload)
    if not ver:
        raise HTTPException(status_code=404, detail="Verification not found")
    return ver


@router.delete("/{verification_id}", status_code=204)
def delete(verification_id: str, db: Session = Depends(get_db)):
    ok = delete_verification(db, verification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Verification not found")
    return None

