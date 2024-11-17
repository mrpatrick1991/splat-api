from fastapi import FastAPI, HTTPException, BackgroundTasks
from models.coverage import CoveragePredictRequest

import logging
import os
import subprocess
import tempfile
import time
import json
import requests
import uuid

logging.basicConfig(level=logging.INFO)
app = FastAPI()

@app.post("/coverage")
def coverage(request: CoveragePredictRequest, background_tasks: BackgroundTasks):
    request_json = json.dumps(request.dict(), indent=4)
    logging.info(f"Received coverage prediction request:\n{request_json}")

    def run_splat(request: CoveragePredictRequest, job_id: str):

        # Create temporary .qth and .lrp files, which represent the transmitter site and model parameters in SPLAT!
        with tempfile.NamedTemporaryFile(
            suffix=".qth", delete=False
        ) as tx_file, tempfile.NamedTemporaryFile(
            suffix=".lrp", delete=False
        ) as lrp_file, tempfile.NamedTemporaryFile(
            suffix=".ppm", delete=False
        ) as ppm_file:  # Create a temporary file to store the SPLAT! output

            try:
                # Transmitter QTH data
                tx_file.write(f"{request.lat:.6f}\n".encode())
                tx_file.write(f"{request.lon:.6f}\n".encode())
                tx_file.write(f"{request.tx_height:.2f}\n".encode())
                tx_file.flush()

                # LRP file data
                lrp_file.write(f"{request.frequency_mhz:.3f}\n".encode())
                lrp_file.write(f"{request.ground_dielectric:.2f}\n".encode())
                lrp_file.write(f"{request.ground_conductivity:.6f}\n".encode())
                lrp_file.write(f"{request.atmosphere_bending:.1f}\n".encode())
                lrp_file.write(f"{request.system_loss:.1f}\n".encode())

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

                # Add the climate and polarization models to the LRP file
                lrp_file.write(f"{climate_map[request.radio_climate]}\n".encode())
                lrp_file.write(f"{polarization_map[request.polarization]}\n".encode())
                lrp_file.flush()

                # Run SPLAT! in coverage prediction mode
                print("running SPLAT!")
                result = subprocess.run(
                    [
                        "splat",
                        "-t",  # tx.qth file
                        tx_file.name,
                        "-l",  # lrp file - model parameters
                        lrp_file.name,
                        "-metric",  # use metric units
                        "-R",  # maximum radius in kilometers
                        str(request.radius / 1000.0),
                        "-ngs",  # Suppress greyscale rendering of terrain tiles
                        "-N",  # Suppress site or obstruction reports
                        "-d",  # Terrain tile data directory
                        "/Volumes/Gandalf/datasets/sdf/data/sdf",  # REPLACE ME - local testing
                        "-o",  # Output .ppm file name
                        ppm_file.name,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )

            except subprocess.CalledProcessError as e:
                logging.error("SPLAT! failed, details: " + e.stderr.decode())
                return {"error": "SPLAT! failed", "details": e.stderr.decode()}

            finally:
                # Clean up temporary files
                os.unlink(tx_file.name)
                os.unlink(lrp_file.name)

            return {"message": "SPLAT! coverage prediction completed.", "stdout": result.stdout.decode()}

    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_splat, request, job_id)
    return {"job_id": job_id, "message": "SPLAT! coverage prediction started."}
