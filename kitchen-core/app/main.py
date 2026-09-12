from fastapi import FastAPI

from app.routers import client, establishments

app = FastAPI(
    title="Avito.Kitchen — Kitchen Core API",
    description=(
        "MVP API маркетплейса доставки еды: каталог заведений, меню и заказы. "
        "Аутентификация и авторизация намеренно не реализованы в рамках задания."
    ),
    version="0.2.0",
)

app.include_router(establishments.router)
app.include_router(client.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}

