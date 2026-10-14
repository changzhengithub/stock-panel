from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api import router
from app.chain_api import router as chain_router
from app.chain_updates import start_worker as start_chain_worker
from app.db import migrate
from app.fund_api import router as fund_router
from app.fund_flow import start_worker as start_fund_worker
from app.realtime import start_worker
from app.settings import ROOT


@asynccontextmanager
async def lifespan(app):
    migrate()
    stop = start_worker()
    fund_stop = start_fund_worker()
    chain_stop = start_chain_worker()
    try:
        yield
    finally:
        stop.set()
        fund_stop.set()
        chain_stop.set()


app = FastAPI(title="A 股市场浏览看板", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(fund_router)
app.include_router(chain_router)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "接口不存在")
    directory = (ROOT / "frontend/dist").resolve()
    file = (directory / path).resolve()
    if not file.is_relative_to(directory):
        raise HTTPException(404)
    if file.is_file():
        return FileResponse(file)
    if is_asset_path(path):
        raise HTTPException(404)
    index = directory / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "前端尚未构建，请运行 npm run build")


def is_asset_path(path):
    return path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]
