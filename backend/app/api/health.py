from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Returns 200 if the app is running and the database is reachable."""
    db.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected"}
