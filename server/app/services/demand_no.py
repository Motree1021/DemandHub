from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from app.db.models import DemandNoSeq


async def next_no(db, type_code: str, biz_date: date) -> str:
    statement = insert(DemandNoSeq).values(biz_date=biz_date, type_code=type_code, seq=1)
    await db.execute(statement.on_duplicate_key_update(seq=DemandNoSeq.seq + 1))
    value = (await db.execute(select(DemandNoSeq.seq).where(
        DemandNoSeq.biz_date == biz_date, DemandNoSeq.type_code == type_code))).scalar_one()
    return f"{type_code}-{biz_date:%Y%m%d}-{value:03d}"
