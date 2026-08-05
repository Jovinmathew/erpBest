# main.py
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_url: str
    api_key: SecretStr
    api_secret: SecretStr

    @property
    def auth_token(self) -> str:
        return f"token {self.api_key.get_secret_value()}:{self.api_secret.get_secret_value()}"


settings = Settings()


class ItemRaw(BaseModel):
    item_code: str
    item_name: str | None = None
    item_group: str | None = None
    stock_uom: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.erp_client = httpx.AsyncClient(
        base_url=settings.api_url,
        headers={"Authorization": settings.auth_token},
        timeout=10.0,
    )
    yield
    await app.state.erp_client.aclose()


app = FastAPI(lifespan=lifespan)


def get_erp_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.erp_client


async def fetch_item_list(client: httpx.AsyncClient) -> list[ItemRaw]:
    params: list[str] = [
        "name",
        "item_name",
        "item_code",
        "item_group",
        "stock_uom",
        "docstatus",
    ]
    resp = await client.get("/api/resource/Item", params={"fields": json.dumps(params)})
    resp.raise_for_status()
    result: list[ItemRaw] = []
    for row in resp.json()["data"]:
        result.append(ItemRaw(**row))
    return result


async def fetch_item(client: httpx.AsyncClient, item_code: str) -> ItemRaw:
    resp = await client.get(f"/api/resource/Item/{item_code}")
    resp.raise_for_status()
    return ItemRaw(**resp.json()["data"])


async def fetch_bin(client: httpx.AsyncClient):
    params: list[str] = ["name", "item_code", "actual_qty", "warehouse"]
    resp = await client.get("/api/resource/Bin", params={"fields": json.dumps(params)})
    resp.raise_for_status()
    result = []
    for row in resp.json()["data"]:
        result.append(row)
    return result


@app.get("/items")
async def list_items(client: httpx.AsyncClient = Depends(get_erp_client)):
    return await fetch_item_list(client)


@app.get("/items/{item_code}")
async def get_item(item_code: str, client: httpx.AsyncClient = Depends(get_erp_client)):
    return await fetch_item(client, item_code)


@app.get("/bin")
async def list_stocks(client: httpx.AsyncClient = Depends(get_erp_client)):
    return await fetch_bin(client)
