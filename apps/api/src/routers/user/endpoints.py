from fastapi import APIRouter


router = APIRouter(prefix="/user", tags=["user"])


@router.get("/")
async def get_users():
    return {"message": "Hello World"}
