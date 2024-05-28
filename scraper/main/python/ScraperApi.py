import schedule
from fastapi import FastAPI, Depends
from api import Auth, SecureRouter
from services import ApiService

app = FastAPI()

app.include_router(
    SecureRouter.router,
    prefix="/api/v1",
    dependencies=[Depends(Auth.get_user)]
)

# Database server is in a different timezone, so 02:00 is 00:00 in the local timezone
schedule.every().day.at("02:00").do(ApiService.update_cache)

ApiService.update_cache()
