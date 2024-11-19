import os
import tempfile
import subprocess
from models.coverage import CoveragePredictRequest

def coverage(request: CoveragePredictRequest, tile_dir: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:

        # Create txfile.qth in a temporary directory
        qth_path = os.path.join(tmpdir, "tx.qth")
        with open(qth_path, "w") as qth_file:
            qth_file.write("transmitter\n")
            qth_file.write(f"{request.lat:.6f}\n")
            qth_file.write(f"{request.lon:.6f}\n")
            qth_file.write(f"{request.tx_height:.2f}\n")

        # Create splat.lrp in a temporary directory
        lrp_path = os.path.join(tmpdir, "splat.lrp")  # SPLAT! requires the .lrp file to have this exact name.
        with open(lrp_path, "w") as lrp_file:
            lrp_file.write(f"{request.ground_dielectric:.3f}  ; Earth Dielectric Constant\n")
            lrp_file.write(f"{request.ground_conductivity:.6f}  ; Earth Conductivity\n")
            lrp_file.write(f"{request.atmosphere_bending:.3f}  ; Atmospheric Bending Constant\n")
            lrp_file.write(f"{request.frequency_mhz:.3f}  ; Frequency in MHz\n")
            climate_map = {
                "equatorial": 1,
                "continental_subtropical": 2,
                "maritime_subtropical": 3,
                "desert": 4,
                "continental_temperate": 5,
                "maritime_temperate_land": 6,
                "maritime_temperate_sea": 7,
            }
            polarization_map = {"horizontal": 0, "vertical": 1}
            lrp_file.write(f"{climate_map[request.radio_climate]}  ; Radio Climate\n")
            lrp_file.write(f"{polarization_map[request.polarization]}  ; Polarization\n")
            lrp_file.write("0.50  ; Fraction of situations\n")
            lrp_file.write("0.90  ; Fraction of time\n")
            lrp_file.write(f"{10 ** ((request.tx_power + request.tx_gain - request.system_loss - 30) / 10):.2f}  ; ERP in Watts\n")

        # Prepare SPLAT! command
        command = [
            "splat",
            "-t", "tx.qth",
            "-L", str(request.rxh),
            "-metric",
            "-R", str(request.radius / 1000.0),
            "-sc",
            "-ngs",
            "-N",
            "-o", "output.ppm",
            "-dbm",
            "-db", str(request.signal_threshold),
            "-kml",
            "-no",
            "-d", tile_dir,
        ]

        # Run SPLAT! in the temporary directory
        subprocess.run(
            command,
            cwd=tmpdir,
        )

        ppm_path = os.path.join(tmpdir, "output.ppm")
        with open(ppm_path) as ppm_file:
            ppm_data = ppm_file.read()

        return {
            "ppm_file": ppm_data,
        }
