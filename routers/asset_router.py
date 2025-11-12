from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from crud.asset_crud import list_assets, get_asset, create_asset, update_asset, soft_delete_asset, delete_asset
from schemas.asset_schema import AssetCreate, AssetResponse, AssetUpdate


router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("/", response_model=list[AssetResponse])
def list_all(
    user_id: str | None = None,
    project_id: str | None = None,
    include_deleted: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return list_assets(db, user_id=user_id, project_id=project_id, include_deleted=include_deleted, skip=skip, limit=limit)


@router.get("/{asset_id}", response_model=AssetResponse)
def read_one(asset_id: str, db: Session = Depends(get_db)):
    asset = get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("/", response_model=AssetResponse, status_code=201)
def create(payload: AssetCreate, db: Session = Depends(get_db)):
    return create_asset(db, payload)


@router.patch("/{asset_id}", response_model=AssetResponse)
def update(asset_id: str, payload: AssetUpdate, db: Session = Depends(get_db)):
    asset = update_asset(db, asset_id, payload)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.delete("/{asset_id}", status_code=204)
def delete(asset_id: str, soft: bool = True, db: Session = Depends(get_db)):
    if soft:
        ok = soft_delete_asset(db, asset_id)
    else:
        ok = delete_asset(db, asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Asset not found")
    return None

