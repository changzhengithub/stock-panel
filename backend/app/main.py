from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api import router
from app.db import migrate
from app.settings import ROOT


@asynccontextmanager
async def lifespan(app):
    migrate()
    yield


app = FastAPI(title="A 股市场浏览看板", version="0.1.0", lifespan=lifespan)
app.include_router(router)


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
