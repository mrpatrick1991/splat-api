from fastapi import FastAPI, HTTPException, BackgroundTasks
from celery.result import AsyncResult
from celery_app import celery

import logging
import os
import subprocess
import tempfile
import time
import json
import requests
import uuid
from tasks.splat import coverage
from models.coverage import CoveragePredictRequest


logging.basicConfig(level=logging.INFO)
app = FastAPI()

@app.post("/coverage")
def predict_coverage(request: CoveragePredictRequest):
    try:
        task = coverage.delay(request.dict())
        return {"job_id": task.id, "message": "SPLAT! coverage prediction started."}
    except Exception as e:
        logging.error(f"Failed to submit SPLAT! task: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start coverage prediction.")


@app.get("/status/{job_id}")
def get_splat_task_status(job_id: str):
    try:
        result = AsyncResult(job_id)
        if result.state == "PENDING":
            return {"status": "PENDING", "result": None}
        elif result.state == "STARTED":
            return {"status": "STARTED", "result": None}
        elif result.state == "SUCCESS":
            return {"status": "SUCCESS", "result": result.result}
        elif result.state == "FAILURE":
            return {"status": "FAILURE", "error": str(result.info)}
        else:
            return {"status": result.state}
    except Exception as e:
        logging.error(f"Failed to fetch task status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch task status.")

