from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
async def health(db=Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "UP", "db": "UP"}
    except Exception:
        return JSONResponse({"status": "DOWN", "db": "DOWN"}, status_code=503)
