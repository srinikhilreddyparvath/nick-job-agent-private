from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ApplicationRecord
from app.models.application import ApplicationRead

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationRead])
def list_applications(db: Session = Depends(get_db)):
    return db.scalars(select(ApplicationRecord).order_by(ApplicationRecord.updated_at.desc())).all()

