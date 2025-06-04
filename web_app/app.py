import os
import subprocess
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
