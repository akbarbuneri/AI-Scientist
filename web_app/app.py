import os
import subprocess
import datetime
import shutil
from threading import Thread

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("AI_SCIENTIST_DB", "sqlite:///web_app.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True, index=True)
    experiment = Column(String)
    model = Column(String)
    num_ideas = Column(Integer)
    status = Column(String, default="running")
    output_path = Column(String)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime)

class Idea(Base):
    __tablename__ = "ideas"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer)
    name = Column(String)
    status = Column(String)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="web_app/templates")


def run_scientist_task(run_id: int, experiment: str, model: str, num_ideas: int):
    session = SessionLocal()
    run = session.get(Run, run_id)
    output_path = os.path.join("results", experiment)
    run.output_path = output_path
    session.commit()
    os.makedirs(output_path, exist_ok=True)
    log_file = os.path.join(output_path, f"run_{run_id}.log")
    cmd = [
        "python",
        "launch_scientist.py",
        "--model",
        model,
        "--experiment",
        experiment,
        "--num-ideas",
        str(num_ideas),
    ]
    with open(log_file, "w") as log_f:
        process = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)
        process.wait()
    run.status = "completed" if process.returncode == 0 else "failed"
    run.end_time = datetime.datetime.utcnow()
    session.commit()
    session.close()


def spawn_task(run_id: int, experiment: str, model: str, num_ideas: int):
    thread = Thread(target=run_scientist_task, args=(run_id, experiment, model, num_ideas))
    thread.daemon = True
    thread.start()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    session = SessionLocal()
    runs = session.query(Run).order_by(Run.id.desc()).all()
    session.close()
    return templates.TemplateResponse("index.html", {"request": request, "runs": runs})


@app.post("/runs/start")
async def start_run(
    background_tasks: BackgroundTasks,
    model: str = Form(...),
    experiment: str = Form(...),
    num_ideas: int = Form(1),
):
    session = SessionLocal()
    run = Run(experiment=experiment, model=model, num_ideas=num_ideas, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    session.close()
    background_tasks.add_task(spawn_task, run.id, experiment, model, num_ideas)
    return {"run_id": run.id}


@app.get("/api/runs/{run_id}")
def api_run_status(run_id: int):
    session = SessionLocal()
    run = session.get(Run, run_id)
    if not run:
        session.close()
        raise HTTPException(status_code=404, detail="Run not found")
    data = {
        "id": run.id,
        "experiment": run.experiment,
        "model": run.model,
        "num_ideas": run.num_ideas,
        "status": run.status,
        "start_time": run.start_time,
        "end_time": run.end_time,
    }
    session.close()
    return data


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: int, request: Request):
    session = SessionLocal()
    run = session.get(Run, run_id)
    if not run:
        session.close()
        raise HTTPException(status_code=404, detail="Run not found")
    files = []
    if run.output_path and os.path.exists(run.output_path):
        files = os.listdir(run.output_path)
    session.close()
    return templates.TemplateResponse(
        "run.html", {"request": request, "run": run, "files": files}
    )


@app.get("/results/{run_id}/{file_name}")
def get_result_file(run_id: int, file_name: str):
    session = SessionLocal()
    run = session.get(Run, run_id)
    if not run:
        session.close()
        raise HTTPException(status_code=404, detail="Run not found")
    file_path = os.path.join(run.output_path, file_name)
    session.close()
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.post("/templates/upload")
async def upload_template(
    experiment: str = Form(...), file: UploadFile = File(...)
):
    dest = os.path.join("templates", experiment, file.filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "uploaded"}

import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import Run, RunStatus

app = FastAPI()
init_db()

RUNS_DIR = os.path.join(os.getcwd(), 'web_runs')
os.makedirs(RUNS_DIR, exist_ok=True)

processes = {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def launch_run(run_id: int, run_dir: str, params: dict):
    cmd = [
        'python', 'launch_scientist.py',
        '--model', params['model_name'],
        '--experiment', params['experiment_name'],
        '--num-ideas', str(params['num_ideas'])
    ]
    with open(os.path.join(run_dir, 'stdout.log'), 'w') as out, \
         open(os.path.join(run_dir, 'stderr.log'), 'w') as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err)
    processes[run_id] = proc

@app.post('/runs/')
async def create_run(model_name: str, experiment_name: str, num_ideas: int, background_tasks: BackgroundTasks):
    db: Session = next(get_db())
    run = Run(model_name=model_name, experiment_name=experiment_name, num_ideas=num_ideas, template_slug=experiment_name)
    db.add(run)
    db.commit()
    db.refresh(run)

    run_dir = os.path.join(RUNS_DIR, str(run.id))
    os.makedirs(run_dir, exist_ok=True)
    background_tasks.add_task(launch_run, run.id, run_dir, {
        'model_name': model_name,
        'experiment_name': experiment_name,
        'num_ideas': num_ideas
    })
    run.status = RunStatus.RUNNING
    db.commit()
    return {'run_id': run.id}

@app.get('/runs/{run_id}/status')
async def run_status(run_id: int):
    db: Session = next(get_db())
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail='Run not found')
    proc = processes.get(run_id)
    if proc and proc.poll() is None:
        run.status = RunStatus.RUNNING
    elif proc and proc.poll() == 0:
        run.status = RunStatus.SUCCESS
    elif proc and proc.poll() is not None:
        run.status = RunStatus.FAILED
    db.commit()
    return {'status': run.status}

@app.get('/runs/{run_id}/log')
async def get_log(run_id: int):
    log_file = os.path.join(RUNS_DIR, str(run_id), 'stdout.log')
    if os.path.exists(log_file):
        return FileResponse(log_file, media_type='text/plain')
    raise HTTPException(status_code=404, detail='Log not found')
