from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.asset import Asset
from schemas.asset_schema import AssetCreate, AssetUpdate


def get_asset(db: Session, asset_id: str):
    return db.query(Asset).filter(Asset.id == asset_id).first()


def list_assets(
    db: Session,
    user_id: str | None = None,
    project_id: str | None = None,
    include_deleted: bool = False,
    skip: int = 0,
    limit: int = 100,
):
    q = db.query(Asset)
    if user_id:
        q = q.filter(Asset.user_id == user_id)
    if project_id is not None:
        q = q.filter(Asset.project_id == project_id)
    if not include_deleted:
        q = q.filter(Asset.deleted_at.is_(None))
    return q.order_by(desc(Asset.created_at)).offset(skip).limit(limit).all()


def create_asset(db: Session, payload: AssetCreate):
    asset = Asset(
        user_id=payload.user_id,
        project_id=payload.project_id,
        original_name=payload.original_name,
        storage_key=payload.storage_key,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        width=payload.width,
        height=payload.height,
        duration_seconds=payload.duration_seconds,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, asset_id: str, payload: AssetUpdate):
    asset = get_asset(db, asset_id)
    if not asset:
        return None
    if payload.project_id is not None:
        asset.project_id = payload.project_id
    if payload.width is not None:
        asset.width = payload.width
    if payload.height is not None:
        asset.height = payload.height
    if payload.duration_seconds is not None:
        asset.duration_seconds = payload.duration_seconds
    db.commit()
    db.refresh(asset)
    return asset


def soft_delete_asset(db: Session, asset_id: str) -> bool:
    asset = get_asset(db, asset_id)
    if not asset:
        return False
    asset.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True


def delete_asset(db: Session, asset_id: str) -> bool:
    asset = get_asset(db, asset_id)
    if not asset:
        return False
    db.delete(asset)
    db.commit()
    return True


def find_asset_by_name_project_user(db: Session, user_id: str, project_id: str | None, original_name: str):
    q = db.query(Asset).filter(Asset.user_id == user_id, Asset.original_name == original_name)
    if project_id is not None:
        q = q.filter(Asset.project_id == project_id)
    return q.order_by(desc(Asset.created_at)).first()


def find_asset_by_storage_key(db: Session, user_id: str, project_id: str | None, storage_key: str):
    q = db.query(Asset).filter(Asset.user_id == user_id, Asset.storage_key == storage_key)
    if project_id is not None:
        q = q.filter(Asset.project_id == project_id)
    return q.order_by(desc(Asset.created_at)).first()
