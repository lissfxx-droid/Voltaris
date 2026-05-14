"""FastAPI entry: HTTP CRUD for projects + run trigger + file read + WS mount."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, projects, runner, ws
from .providers import selected_provider_name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="PCB System Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ws.router)


# --- HTTP models ---------------------------------------------------------------

class CreateProjectIn(BaseModel):
    name: str


class StartRunIn(BaseModel):
    message: str


# --- Routes --------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "agent_provider": selected_provider_name()}


@app.get("/projects")
async def get_projects():
    return await projects.list_projects()


@app.post("/projects", status_code=201)
async def post_project(body: CreateProjectIn):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    return await projects.create_project(body.name)


@app.get("/projects/{project_id}")
async def get_project_detail(project_id: str):
    proj = await projects.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    proj["files"] = await projects.list_files(project_id)
    proj["active_run"] = bool(runner.get_active(project_id))
    proj["agent_provider"] = selected_provider_name()
    return proj


@app.delete("/projects/{project_id}", status_code=204)
async def delete_project_endpoint(project_id: str):
    ok = await projects.delete_project(project_id)
    if not ok:
        raise HTTPException(404, "project not found")


@app.get("/projects/{project_id}/files/{fname}")
async def get_file(project_id: str, fname: str):
    content = await projects.read_file(project_id, fname)
    if content is None:
        raise HTTPException(404, "file not found")
    return {"name": fname, "content": content}


@app.get("/projects/{project_id}/runs")
async def get_runs(project_id: str):
    proj = await projects.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return await db.list_runs(project_id)


@app.post("/projects/{project_id}/runs", status_code=202)
async def start_run(project_id: str, body: StartRunIn):
    try:
        handle = await runner.start_run(project_id, body.message)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {
        "run_id": handle.run_id,
        "project_id": project_id,
        "status": "started",
        "agent_provider": handle.provider.name,
    }


@app.post("/projects/{project_id}/runs/cancel")
async def cancel_run(project_id: str):
    handle = runner.get_active(project_id)
    if not handle:
        raise HTTPException(404, "no active run for this project")
    await handle.cancel()
    return {"run_id": handle.run_id, "status": "cancelling"}


@app.get("/projects/{project_id}/messages")
async def get_messages(project_id: str, since: int = 0):
    return await db.list_messages(project_id, since_seq=since)
