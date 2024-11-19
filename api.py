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

from celery_app import celery
import subprocess
import tempfile
import os

@celery.task(name="splat.coverage")
def coverage(request_json: dict):
    """
    Celery task for running SPLAT! coverage prediction.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".qth", delete=False
    ) as tx_file, tempfile.NamedTemporaryFile(
        suffix=".lrp", delete=False
    ) as lrp_file, tempfile.NamedTemporaryFile(
        suffix=".ppm", delete=False
    ) as ppm_file:
        try:
            # Transmitter QTH data
            tx_file.write(f"{request_json['lat']:.6f}\n".encode())
            tx_file.write(f"{request_json['lon']:.6f}\n".encode())
            tx_file.write(f"{request_json['tx_height']:.2f}\n".encode())
            tx_file.flush()

            # LRP file data
            lrp_file.write(f"{request_json['frequency_mhz']:.3f}\n".encode())
            lrp_file.write(f"{request_json['ground_dielectric']:.2f}\n".encode())
            lrp_file.write(f"{request_json['ground_conductivity']:.6f}\n".encode())
            lrp_file.write(f"{request_json['atmosphere_bending']:.1f}\n".encode())
            lrp_file.write(f"{request_json['system_loss']:.1f}\n".encode())

            # Add climate and polarization models
            climate_map = {
                "equatorial": 1,
                "continental_subtropical": 2,
                "maritime_subtropical": 3,
                "desert": 4,
                "continental_temperate": 5,
                "maritime_temperate_land": 6,
                "maritime_temperate_sea": 7,
            }
            polarization_map = {"horizontal": 1, "vertical": 2}
            lrp_file.write(f"{climate_map[request_json['radio_climate']]}\n".encode())
            lrp_file.write(f"{polarization_map[request_json['polarization']]}\n".encode())
            lrp_file.flush()

            # Run SPLAT!
            result = subprocess.run(
                [
                    "splat",
                    "-t", tx_file.name,
                    "-l", lrp_file.name,
                    "-metric",
                    "-R", str(request_json['radius'] / 1000.0),
                    "-ngs",
                    "-N",
                    "-d", "/Volumes/Gandalf/datasets/sdf/data/sdf",  # Replace with actual data directory
                    "-o", ppm_file.name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            # Return the result
            return {
                "stdout": result.stdout.decode(),
                "ppm_file": ppm_file.name,  # Path to output file (optional for debugging)
            }

        except subprocess.CalledProcessError as e:
            logging.error(f"SPLAT! failed: {e.stderr.decode()}")
            raise

        finally:
            os.unlink(tx_file.name)
            os.unlink(lrp_file.name)