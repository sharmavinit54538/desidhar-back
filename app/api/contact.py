from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/contact", tags=["contact"])


class ContactIn(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    message: str


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def send_contact(data: ContactIn, db: AsyncSession = Depends(get_db)):
    return {"message": "Your message has been received. We will get back to you soon."}