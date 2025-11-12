from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.project import Project
from schemas.project_schema import ProjectCreate, ProjectUpdate


def get_project(db: Session, project_id: str):
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(db: Session, user_id: str | None = None, skip: int = 0, limit: int = 100):
    q = db.query(Project)
    if user_id:
        q = q.filter(Project.user_id == user_id)
    return q.order_by(desc(Project.created_at)).offset(skip).limit(limit).all()


def create_project(db: Session, payload: ProjectCreate, user_id: str):
    proj = Project(user_id=user_id, name=payload.name)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def update_project(db: Session, project_id: str, payload: ProjectUpdate):
    proj = get_project(db, project_id)
    if not proj:
        return None
    if payload.name is not None:
        proj.name = payload.name
    if payload.timeline is not None:
        proj.timeline = payload.timeline
    if payload.text_bin_items is not None:
        proj.text_bin_items = payload.text_bin_items
    db.commit()
    db.refresh(proj)
    return proj


def delete_project(db: Session, project_id: str) -> bool:
    proj = get_project(db, project_id)
    if not proj:
        return False
    db.delete(proj)
    db.commit()
    return True
