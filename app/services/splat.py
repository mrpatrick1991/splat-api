import os
import subprocess
import tempfile
import logging
from typing import Literal
import matplotlib.pyplot as plt
import numpy as np
import xml.etree.ElementTree as ET
import rasterio
from rasterio.transform import from_bounds
from PIL import Image

from app.models.CoveragePredictionRequest import CoveragePredictionRequest

logger = logging.getLogger(__name__)


class Splat:
    def __init__(self, splat_path: str, tile_dir: str):
        """
        Initialize the SPLAT! service.

        Args:
            splat_path (str): Path to the SPLAT! binary.
            tile_dir (str): Directory containing .sdf terrain tiles.
        """
        if not os.path.isfile(splat_path):
            raise FileNotFoundError(f"SPLAT! binary not found at '{splat_path}'")
        if not os.path.isdir(tile_dir):
            raise FileNotFoundError(f"Tile directory not found at '{tile_dir}'")

        self.splat_path = splat_path
        self.tile_dir = tile_dir

    def coverage_prediction(self, request: CoveragePredictionRequest) -> bytes:
        """
        Execute a SPLAT! coverage prediction using the provided CoveragePredictRequest.

        Args:
            request (CoveragePredictRequest): The coverage prediction request object.

        Returns:
            bytes: the SPLAT! coverage prediction as a GeoTIFF.

        Raises:
            RuntimeError: If SPLAT! fails to execute.
        """
        logger.debug(f"Coverage prediction request: {request.json()}")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                logger.debug(f"Temporary directory created: {tmpdir}")

                # Create required input files
                qth_path = self._create_qth(
                    path=tmpdir,
                    name="tx",
                    latitude=request.lat,
                    longitude=request.lon,
                    elevation=request.tx_height,
                )
                logger.info(f".qth file created for transmitter.")

                lrp_path = self._create_lrp(
                    path=tmpdir,
                    ground_dielectric=request.ground_dielectric,
                    ground_conductivity=request.ground_conductivity,
                    atmosphere_bending=request.atmosphere_bending,
                    frequency_mhz=request.frequency_mhz,
                    radio_climate=request.radio_climate,
                    polarization=request.polarization,
                    situation_fraction=request.situation_fraction,
                    time_fraction=request.time_fraction,
                    tx_power=request.tx_power,
                    tx_gain=request.tx_gain,
                    system_loss=request.system_loss,
                )
                logger.info(f".lrp file created for propagation parameters.")

                dcf_path = self._create_dcf(
                    path=tmpdir,
                    colormap_name=request.colormap,
                    min_dbm=request.min_dbm,
                    max_dbm=request.max_dbm,
                )
                logger.info(f".dcf file created for signal level color definitions.")

                # SPLAT! execution
                ppm_path = os.path.join(tmpdir, "output.ppm")
                kml_path = os.path.join(tmpdir, "output.kml")

                command = [
                    self.splat_path,
                    "-t",
                    qth_path,
                    "-L",
                    str(request.rxh),
                    "-metric",
                    "-R",
                    str(request.radius / 1000.0),
                    "-sc",
                    "-ngs",
                    "-N",
                    "-o",
                    ppm_path,
                    "-dbm",
                    "-db",
                    str(request.signal_threshold),
                    "-kml",
                    "-d",
                    self.tile_dir,
                ]
                logger.debug(f"Executing SPLAT! command: {' '.join(command)}")

                result = subprocess.run(
                    command,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                logger.debug(f"SPLAT! stdout:\n{result.stdout}")
                logger.debug(f"SPLAT! stderr:\n{result.stderr}")

                if result.returncode != 0:
                    logger.error(
                        f"SPLAT! execution failed with return code {result.returncode}"
                    )
                    raise RuntimeError(
                        f"SPLAT! execution failed with return code {result.returncode}\n"
                        f"Stdout: {result.stdout}\nStderr: {result.stderr}"
                    )

                # Convert results to GeoTIFF
                output_tiff_path = os.path.join(tmpdir, "output.tiff")

                self._create_geotiff(ppm_path, kml_path, dcf_path, output_tiff_path)


                logger.info(f"GeoTIFF created: {output_tiff_path}")

                with open(output_tiff_path, "rb") as output_tiff:
                    output_tiff_data = output_tiff.read()

                logger.info("SPLAT! coverage prediction completed successfully.")
                return output_tiff_data

            except Exception as e:
                logger.error(f"Error during coverage prediction: {e}")
                raise RuntimeError(f"Error during coverage prediction: {e}")

    def _create_qth(
        self, path: str, name: str, latitude: float, longitude: float, elevation: float
    ) -> str:
        """
        Create a SPLAT! .qth file describing a transmitter or receiver site.

        Args:
            path (str): Path to the directory where the .qth file will be created.
            name (str): Name of the site (unused but required for SPLAT!).
            latitude (float): Latitude of the site in degrees.
            longitude (float): Longitude of the site in degrees.
            elevation (float): Elevation (AGL) of the site in meters.
        Returns:
            str: Path to the .qth file
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Directory does not exist: {path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Directory is not writable: {path}")

        qth_path = os.path.join(path, f"{name}.qth")
        logger.debug(f"Creating .qth file at {path} with name '{name}'.")
        # We maintain exactly the format and order generated by SPLAT! by default.
        try:
            contents = (
                f"{name}\n"
                f"{latitude:.6f}\n"
                f"{abs(longitude) if longitude < 0 else 360 - longitude:.6f}\n"  # SPLAT! expects west longitude as a positive number.
                f"{elevation:.2f}\n"
            )
            with open(qth_path, "w") as qth_file:
                qth_file.write(contents)
                logger.info(f".qth file created at {qth_path}")
                logger.debug(f".qth file contents:\n{contents}")
                return qth_path
        except IOError as e:
            logger.error(f"Failed to write .qth file at {qth_path}: {e}")
            raise

    def _create_lrp(
        self,
        path: str,
        ground_dielectric: float,
        ground_conductivity: float,
        atmosphere_bending: float,
        frequency_mhz: float,
        situation_fraction: float,
        time_fraction: float,
        tx_power: float,
        tx_gain: float,
        system_loss: float,
        radio_climate: Literal[
            "equatorial",
            "continental_subtropical",
            "maritime_subtropical",
            "desert",
            "continental_temperate",
            "maritime_temperate_land",
            "maritime_temperate_sea",
        ],
        polarization: Literal["horizontal", "vertical"],
    ) -> str:
        """
        Create a SPLAT! .lrp file describing environment and propagation parameters.

        Args:
            path (str): Path to the directory where the .lrp file will be created.
            ground_dielectric (float): Earth's dielectric constant.
            ground_conductivity (float): Earth's conductivity (Siemens per meter).
            atmosphere_bending (float): Atmospheric bending constant.
            frequency_mhz (float): Frequency in MHz.
            radio_climate (str): Radio climate type.
            polarization (str): Antenna polarization.
            situation_fraction (float): Fraction of situations (percentage, 0-100).
            time_fraction (float): Fraction of time (percentage, 0-100).
            tx_power (float): Transmitter power in dBm.
            tx_gain (float): Transmitter antenna gain in dB.
            system_loss (float): System losses in dB (e.g. cable loss).

        Returns:
            str: path to the .lrp file
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Directory does not exist: {path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Directory is not writable: {path}")

        lrp_path = os.path.join(path, "splat.lrp")
        logger.debug(f"Creating .lrp file at {lrp_path}")

        # Mapping for radio climate and polarization
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

        # Calculate ERP in Watts
        erp_watts = 10 ** ((tx_power + tx_gain - system_loss - 30) / 10)
        logger.debug(
            f"Calculated ERP in Watts: {erp_watts:.2f} "
            f"(tx_power={tx_power}, tx_gain={tx_gain}, system_loss={system_loss})"
        )

        # Generate file contents.
        # We maintain exactly the format and order generated by SPLAT! by default.
        contents = (
            f"{ground_dielectric:.3f}  ; Earth Dielectric Constant\n"
            f"{ground_conductivity:.6f}  ; Earth Conductivity\n"
            f"{atmosphere_bending:.3f}  ; Atmospheric Bending Constant\n"
            f"{frequency_mhz:.3f}  ; Frequency in MHz\n"
            f"{climate_map[radio_climate]}  ; Radio Climate\n"
            f"{polarization_map[polarization]}  ; Polarization\n"
            f"{situation_fraction / 100.0:.2f} ; Fraction of situations\n"
            f"{time_fraction / 100.0:.2f}  ; Fraction of time\n"
            f"{erp_watts:.2f}  ; ERP in Watts\n"
        )
        logger.debug(f"Generated .lrp file contents:\n{contents}")

        try:
            with open(lrp_path, "w") as lrp_file:
                lrp_file.write(contents)
            logger.info(f".lrp file successfully created at {lrp_path}")
            return lrp_path
        except IOError as e:
            logger.error(f"Failed to write .lrp file at {lrp_path}: {e}")
            raise

    def _create_dcf(
        self, path: str, colormap_name: str, min_dbm: float, max_dbm: float
    ) -> str:
        """
        Create a SPLAT! .dcf file controlling the signal level contours using the specified Matplotlib color map.

        Args:
            path (str): Path to the directory where the .lrp file will be created.
            colormap_name (str): The name of the Matplotlib colormap.
            min_dbm (float): The minimum signal strength value for the colormap in dBm.
            max_dbm (float): The maximum signal strength value for the colormap in dBm.

        Returns:
            str: The path to the .dcf file.
        """
        dcf_path = os.path.join(path, "splat.dcf")

        logger.debug(
            f"Creating .dcf file at {dcf_path} using colormap '{colormap_name}'."
        )

        cmap = plt.get_cmap(colormap_name)
        cmap_values = np.linspace(
            max_dbm, min_dbm, 32
        )  # SPLAT! supports only up to 32 discrete color levels.
        cmap_norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)

        # Generate RGB values
        rgb_colors = (cmap(cmap_norm(cmap_values))[:, :3] * 255).astype(int)

        # Map indices to RGB tuples
        gdal_colormap = {i: tuple(rgb) for i, rgb in enumerate(rgb_colors)}

        # We maintain exactly the format and order generated by SPLAT! by default.
        try:
            with open(dcf_path, "w") as dcf_file:
                dcf_file.write(
                    "; SPLAT! Auto-generated DBM Signal Level Color Definition\n"
                )
                dcf_file.write(";\n")
                dcf_file.write("; Format: dBm: red, green, blue\n;\n")
                for value, rgb in zip(cmap_values, gdal_colormap.values()):
                    dcf_file.write(
                        f"{int(value):+4d}: {rgb[0]:3d}, {rgb[1]:3d}, {rgb[2]:3d}\n"
                    )

            logger.info(f".dcf file created successfully at {dcf_path}")
        except IOError as e:
            logger.error(f"Failed to write .dcf file at {dcf_path}: {e}")
            raise

    def _create_geotiff(
        self, ppm_file: str, kml_file: str, dcf_file: str, output_tiff: str
    ) -> str:
        """
        Convert a SPLAT-generated PPM image to a GeoTIFF using geospatial bounds from the generated .kml and the
        color map from the .dcf file.

        Args:
            ppm_file (str): Path to the PPM file generated by SPLAT.
            kml_file (str): Path to the KML file containing geospatial bounds.
            dcf_file (str): Path to the DCF file containing the SPLAT! color map.
            output_tiff (str): Path where the output GeoTIFF will be saved.

        Raises:
            FileNotFoundError: If the PPM, KML, or DCF file is not found.
            ValueError: If the KML file is invalid or contains no geospatial bounds.
            RuntimeError: If GeoTIFF creation or writing fails.

        Returns:
            str: the path to the GeoTIFF file.
        """
        logger.info(f"Starting conversion from SPLAT! output (PPM, KML, DCF) to GeoTIFF.")
        logger.debug(
            f"PPM file: {ppm_file}, KML file: {kml_file}, DCF file: {dcf_file}, output GeoTIFF: {output_tiff}"
        )

        # Extract bounding box from SPLAT KML file
        try:
            logger.debug(f"Extracting bounding box from KML file: {kml_file}")
            tree = ET.parse(kml_file)
            root = tree.getroot()
            namespace = {"kml": "http://earth.google.com/kml/2.1"}
            box = root.find(".//kml:LatLonBox", namespace)

            north = float(box.find("kml:north", namespace).text)
            south = float(box.find("kml:south", namespace).text)
            east = float(box.find("kml:east", namespace).text)
            west = float(box.find("kml:west", namespace).text)

            logger.debug(
                f"Extracted bounding box: north={north}, south={south}, east={east}, west={west}"
            )
        except FileNotFoundError:
            logger.error(f"KML file not found: {kml_file}")
            raise
        except ValueError as e:
            logger.error(f"Error parsing KML file: {kml_file} - {e}")
            raise
        except (TypeError, AttributeError) as e:
            logger.error(f"Invalid geospatial bounds in .kml file: {kml_file} - {e}")
            raise

        # Read SPLAT PPM file
        try:
            logger.debug(f"Reading PPM file: {ppm_file}")
            with Image.open(ppm_file) as img:
                img_array = np.array(img.convert("RGB"))  # Convert to RGB array
                logger.debug(f"PPM image dimensions: {img_array.shape}")
        except FileNotFoundError:
            logger.error(f"PPM file not found: {ppm_file}")
            raise
        except Exception as e:
            logger.error(f"Error reading PPM file: {ppm_file} - {e}")
            raise

        # create GeoTIFF
        try:
            height, width, _ = img_array.shape
            transform = from_bounds(west, south, east, north, width, height)
            logger.debug(f"GeoTIFF transform matrix: {transform}")

            logger.info(f"Creating GeoTIFF: {output_tiff}")
            with rasterio.open(
                output_tiff,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=3,  # 3 bands (RGB)
                dtype="uint8",
                crs="EPSG:4326",
                transform=transform,
                tiled=True,
                compress="lzw"
            ) as dst:
                for i in range(3):
                    dst.write(img_array[:, :, i], i + 1)
                dst.update_tags(description="SPLAT! coverage prediction")
            logger.info(f"GeoTIFF creation successful: {output_tiff}")
            return output_tiff
        except Exception as e:
            logger.error(f"Error during GeoTIFF creation: {output_tiff} - {e}")
            raise RuntimeError(f"Error during GeoTIFF creation: {e}")

if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    # Example test for Splat class
    try:
        splat_service = Splat(
            splat_path="/Users/patrick/Dev/splat/splat",          # Replace with the actual SPLAT! binary path
            tile_dir="/Volumes/Gandalf/datasets/sdf/data/sdf"     # Replace with the actual tile directory
        )

        # Create a test coverage prediction request
        mock_request = CoveragePredictionRequest(
            lat=51.086365064829224,
            lon=-114.12962354548324,
            tx_height=5.0,
            ground_dielectric=15.0,
            ground_conductivity=0.005,
            atmosphere_bending=301.0,
            frequency_mhz=905.0,
            radio_climate="continental_temperate",
            polarization="vertical",
            situation_fraction=90.0,
            time_fraction=90.0,
            tx_power=20.0,
            tx_gain=1.0,
            system_loss=2.0,
            rxh=1.0,
            radius=25000.0,
            colormap="jet",
            min_dbm=-130.0,
            max_dbm=-90.0,
            signal_threshold=-130.0
        )

        # Execute coverage prediction
        logger.info("Starting SPLAT! coverage prediction...")
        result = splat_service.coverage_prediction(mock_request)

        # Save GeoTIFF output for inspection
        output_path = "test_output.tiff"
        with open(output_path, "wb") as output_file:
            output_file.write(result)
        logger.info(f"GeoTIFF saved to: {output_path}")

    except Exception as e:
        logger.error(f"Error during SPLAT! test: {e}")
