"""
Signal Coverage Prediction API

Provides endpoints to predict radio signal coverage
using the ITM (Irregular Terrain Model) via SPLAT! (https://github.com/jmcmellen/splat).

Endpoints:
    - /predict: Accepts a signal coverage prediction request and starts a background task.
    - /status/{task_id}: Retrieves the status of a given prediction task.
    - /result/{task_id}: Retrieves the result (GeoTIFF file) of a given prediction task.
"""

import redis
import matplotlib.pyplot as plt
import numpy as np
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4
from app.services.splat import Splat
from app.models.CoveragePredictionRequest import CoveragePredictionRequest
from app.models.ColorbarRequest import ColorbarRequest
import logging
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Redis client for binary data
redis_client = redis.StrictRedis(host="127.0.0.1", port=6379, decode_responses=False)

# Initialize SPLAT service
splat_service = Splat(splat_path="/Users/patrick/Dev/splat")

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware to allow requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

def run_splat(task_id: str, request: CoveragePredictionRequest):
    """
    Execute the SPLAT! coverage prediction and store the resulting GeoTIFF data in Redis.

    Args:
        task_id (str): UUID identifier for the task.
        request (CoveragePredictionRequest): The parameters for the SPLAT! prediction.

    Workflow:
        - Runs the SPLAT! coverage prediction.
        - Stores the resulting GeoTIFF data and the task status ("completed") in Redis.
        - On failure, stores the task status as "failed" and logs the error in Redis.

    Raises:
        Exception: If SPLAT! fails during execution.
    """
    try:
        logger.info(f"Starting SPLAT! coverage prediction for task {task_id}.")
        geotiff_data = splat_service.coverage_prediction(request)

        # Log before storing in Redis
        logger.info(f"Storing result in Redis for task {task_id}")
        redis_client.setex(task_id, 3600, geotiff_data)
        redis_client.setex(f"{task_id}:status", 3600, "completed")
        logger.info(f"Task {task_id} marked as completed.")
    except Exception as e:
        logger.error(f"Error in SPLAT! task {task_id}: {e}")
        redis_client.setex(f"{task_id}:status", 3600, "failed")
        redis_client.setex(f"{task_id}:error", 3600, str(e))
        raise

@app.post("/predict")
async def predict(payload: CoveragePredictionRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """
    Predict signal coverage using SPLAT!.
    Accepts a CoveragePredictionRequest and processes it in the background.

    - Generates a unique task ID.
    - Sets the initial task status to "processing" in Redis.
    - Adds the `run_splat` function to the background task queue.

    Args:
        payload (CoveragePredictionRequest): The parameters required for the SPLAT! coverage prediction.
        background_tasks (BackgroundTasks): FastAPI background tasks.

    Returns:
        JSONResponse: A response containing the unique task ID to track the prediction progress.
    """
    task_id = str(uuid4())
    redis_client.setex(f"{task_id}:status", 3600, "processing")
    background_tasks.add_task(run_splat, task_id, payload)
    return JSONResponse({"task_id": task_id})

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Retrieve the status of a given SPLAT! task.

    - Checks Redis for the task status.
    - Returns "processing", "completed", or "failed" based on the status.
    - Returns a 404 error if the task ID is not found.

    Args:
        task_id (str): The unique identifier for the task.

    Returns:
        JSONResponse: The task status or an error message if the task is not found.
    """
    status = redis_client.get(f"{task_id}:status")
    if not status:
        logger.warning(f"Task {task_id} not found in Redis.")
        return JSONResponse({"error": "Task not found"}, status_code=404)

    return JSONResponse({"task_id": task_id, "status": status.decode("utf-8")})

@app.get("/result/{task_id}")
async def get_result(task_id: str):
    """
    Retrieve SPLAT! task status or GeoTIFF result.

    - Checks the task status in Redis.
    - If "completed," retrieves the GeoTIFF data and serves it as a downloadable file.
    - If "failed," returns the error message stored in Redis.
    - If "processing", indicate the same in the response.

    Args:
        task_id (str): The unique identifier for the task.

    Returns:
        JSONResponse: Task status if the task is still "processing" or "failed."
        StreamingResponse: A downloadable GeoTIFF file if the task is "completed."
    """
    status = redis_client.get(f"{task_id}:status")
    if not status:
        logger.warning(f"Task {task_id} not found in Redis.")
        return JSONResponse({"error": "Task not found"}, status_code=404)

    status = status.decode("utf-8")
    if status == "completed":
        geotiff_data = redis_client.get(task_id)
        if not geotiff_data:
            logger.error(f"No data found for completed task {task_id}.")
            return JSONResponse({"error": "No result found"}, status_code=500)

        geotiff_file = io.BytesIO(geotiff_data)
        return StreamingResponse(
            geotiff_file,
            media_type="image/tiff",
            headers={"Content-Disposition": f"attachment; filename={task_id}.tif"}
        )
    elif status == "failed":
        error = redis_client.get(f"{task_id}:error")
        return JSONResponse({"status": "failed", "error": error.decode("utf-8")})

    logger.info(f"Task {task_id} is still processing.")
    return JSONResponse({"status": "processing"})


@app.post("/colorbar")
async def get_colorbar(payload: ColorbarRequest):
    """
    Generate a colorbar based on the provided colormap, min_dbm, and max_dbm.

    Args:
        payload (ColorbarRequest): Contains colormap name, min_dbm, and max_dbm.

    Returns:
        JSONResponse: A list of RGB values representing the colorbar.
    """
    try:
        # Create a colormap with 256 levels
        cmap = plt.get_cmap(payload.colormap_name, 256)

        # Normalize values between min_dbm and max_dbm
        cmap_norm = plt.Normalize(vmin=payload.min_dbm, vmax=payload.max_dbm)
        # Generate evenly spaced values in the range
        cmap_values = np.linspace(payload.min_dbm, payload.max_dbm, 256)

        # Map data values to RGB values and scale to 0-255
        rgba_colors = cmap(cmap_norm(cmap_values))  # RGBA values
        rgb_colors = (rgba_colors[:, :3] * 255).astype(int)  # Convert to RGB and scale

        # Convert to a list of RGB tuples
        rgb_color_list = [tuple(map(int, color)) for color in rgb_colors]

        return JSONResponse({"colorbar": rgb_color_list})
    except Exception as e:
        logger.error(f"Failed to generate colorbar: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)