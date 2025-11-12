from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from crud.project_crud import list_projects, get_project, create_project, update_project, delete_project
from schemas.project_schema import ProjectCreate, ProjectResponse, ProjectUpdate
from core.auth import get_current_user


router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/", response_model=list[ProjectResponse])
def list_all(
    user_id: str | None = None,
    mine: bool = True,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if mine and not user_id:
        user_id = current_user.id
    return list_projects(db, user_id=user_id, skip=skip, limit=limit)


@router.get("/{project_id}", response_model=ProjectResponse)
def read_one(project_id: str, db: Session = Depends(get_db)):
    proj = get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.post("/", response_model=ProjectResponse, status_code=201)
def create(payload: ProjectCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return create_project(db, payload, user_id=current_user.id)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    proj = update_project(db, project_id, payload)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, db: Session = Depends(get_db)):
    ok = delete_project(db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return None
