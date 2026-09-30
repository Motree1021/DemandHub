from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.core.result import ok
from app.standards import loader

router = APIRouter(prefix="/standards", tags=["standards"])


@router.get("")
async def list_standards(user=Depends(get_current_user)):
    return ok([{"code": std.type, "type": std.type, "name": std.name, "version": std.version} for std in loader.load_all().values()])


@router.get("/{type_code}")
async def get_standard(type_code: str, user=Depends(get_current_user)):
    return ok(loader.get(type_code).model_dump(mode="json", by_alias=True))
