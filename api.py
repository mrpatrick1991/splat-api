from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal

import logging
import os
import subprocess
import tempfile
import time
import json
import requests 

logging.basicConfig(level=logging.INFO)
app = FastAPI()


class PredictRequest(BaseModel):
    """
    Expected input payload for the /area endpoint, including optional LRP parameters.
    """

    lat: float = Field(
        ge=-90, le=90, description="Transmitter latitude in degrees (-90 to 90)"
    )
    lon: float = Field(
        ge=-180,
        le=180,
        description="Transmitter longitude in degrees (-180 to 180)",
    )
    tx_power: float = Field(ge=1, description="Transmitter power in dBm (>= 1 dBm)")
    tx_height: float = Field(
        1, ge=1, description="Transmitter height above ground in meters (>= 1 m)"
    )
    rxh: float = Field(
        1, ge=1, description="Receiver height above ground in meters (>= 1 m)"
    )
    tx_gain: float = Field(1, ge=0, description="Transmitter antenna gain in dB (>= 0)")
    rx_gain: float = Field(1, ge=0, description="Receiver antenna gain in dB (>= 0)")
    radius: float = Field(
        1000.0, ge=1, description="Model maximum range in meters (>= 1 m)"
    )
    signal_threshold: float = Field(
        -100, le=0, description="Signal strength cutoff in dBm (<= 0)"
    )
    clutter_height: float = Field(
        0, ge=0, description="Ground clutter height in meters (>= 0)"
    )

    frequency_mhz: float = Field(
        905.0, ge=20, le=30000, description="Operating frequency in MHz (20-30000 MHz)"
    )

    ground_dielectric: Optional[float] = Field(
        15.0, ge=1, description="Ground dielectric constant (default: 15.0)"
    )
    ground_conductivity: Optional[float] = Field(
        0.005, ge=0, description="Ground conductivity in S/m (default: 0.005)"
    )
    atmosphere_bending: Optional[float] = Field(
        301.0,
        ge=0,
        description="Atmospheric bending constant in N-units (default: 301.0)",
    )
    system_loss: Optional[float] = Field(
        0.0, ge=0, description="System loss in dB (default: 0.0)"
    )

    radio_climate: Optional[
        Literal[
            "equatorial",
            "continental_subtropical",
            "maritime_subtropical",
            "desert",
            "continental_temperate",
            "maritime_temperate_land",
            "maritime_temperate_sea",
        ]
    ] = Field(
        "continental_temperate",
        description="Radio climate, e.g., 'equatorial', 'continental_temperate' (default: 'continental_temperate')",
    )

    polarization: Optional[Literal["horizontal", "vertical"]] = Field(
        "vertical",
        description="Polarization of the signal, 'horizontal' or 'vertical' (default: 'vertical')",
    )


@app.post("/area")
def area(request: PredictRequest):
    # Create temporary .qth and .lrp files
    with tempfile.NamedTemporaryFile(
        suffix=".qth", delete=False
    ) as tx_file, tempfile.NamedTemporaryFile(suffix=".lrp", delete=False) as lrp_file:

        try:
            # Write transmitter QTH data
            tx_file.write(f"{request.lat:.6f}\n".encode())
            tx_file.write(f"{request.lon:.6f}\n".encode())
            tx_file.write(f"{request.tx_height:.2f}\n".encode())
            tx_file.flush()

            # Write LRP file data
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

            lrp_file.write(f"{climate_map[request.radio_climate]}\n".encode())
            lrp_file.write(f"{polarization_map[request.polarization]}\n".encode())
            lrp_file.flush()

            # Run SPLAT! in area mode
            result = subprocess.run(
                [
                    "splat",
                    "-t",
                    tx_file.name,
                    "-l",
                    lrp_file.name,
                    "-metric",
                    "-R",
                    request.radius,
                    "-sc",
                    "-ngs",
                    "-no",
                    "-N",
                    "-kml",
                    "-d",
                    "/data/sdf/", # REPLACE ME
                    "-o",
                    "output.ppm",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        except subprocess.CalledProcessError as e:
            return {"error": "SPLAT! failed", "details": e.stderr.decode()}

        finally:
            # Clean up temporary files
            os.unlink(tx_file.name)
            os.unlink(lrp_file.name)

        return {"message": "Prediction completed", "stdout": result.stdout.decode()}


if __name__ == "__main__":
    test_data = {
        "lat": 37.7749,
        "lon": -122.4194,
        "tx_power": 30.0,
        "tx_height": 50.0,
        "tx_gain": 10.0,
        "rx_gain": 5.0,
        "radius": 1500.0,
        "signal_threshold": -90,
        "clutter_height": 1.5,
        "frequency_mhz": 905.0,
        "ground_dielectric": 15.0,
        "ground_conductivity": 0.005,
        "atmosphere_bending": 301.0,
        "system_loss": 0.0,
        "radio_climate": "continental_temperate",
        "polarization": "vertical",
    }

    base_url = "http://127.0.0.1:8000/area"

    response = requests.post(base_url, json=test_data)

    if response.status_code == 200:
        print("Response received successfully!")
        print(json.dumps(response.json(), indent=4))
    else:
        print(f"Failed with status code {response.status_code}")
        print(response.text)
