import os
import tempfile
import argparse
import subprocess
import logging
import xml.etree.ElementTree as ET
from typing import Literal
from pathlib import Path

import yaml
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt

from models.coverage import CoveragePredictRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Splat:
    def __init__(self, splat_path: str, tile_dir: str) -> None:
        """
        Initializes the Splat wrapper and checks environment.

        Args:
            splat_path (str): Path to the SPLAT! binary.
            tile_dir (str): Path to the directory containing .sdf terrain tiles.
        """
        self.splat_path = splat_path
        self.tile_dir = tile_dir
        logger.debug(f"path to the SPLAT! binary: {self.splat_path}")
        logger.debug(f"path to the SPLAT! terrain tile directory: {self.tile_dir}")

        # Check if the SPLAT! binary exists and is executable
        if not os.path.isfile(splat_path) or not os.access(splat_path, os.X_OK):
            raise FileNotFoundError(
                f"SPLAT! binary not found or not executable at path: {splat_path}"
            )

        # Check if the tile directory exists and contains .sdf files
        if not os.path.isdir(tile_dir):
            raise FileNotFoundError(f"Tile directory not found: {tile_dir}")

        sdf_files = [f for f in os.listdir(tile_dir) if f.endswith(".sdf")]
        if not sdf_files:
            raise ValueError(f"No .sdf files found in the tile directory: {tile_dir}")

        logger.debug(f"SPLAT! wrapper init appears OK.")

    def _create_qth(
        self, path: str, name: str, latitude: float, longitude: float, elevation: float
    ):
        """
        Create a SPLAT! .qth file describing a transmitter site.

        Args:
            path (str): Path to the directory where the .qth file will be created.
            name (str): Name of the transmitter site.
            latitude (float): Latitude of the site in degrees.
            longitude (float): Longitude of the site in degrees.
            elevation (float): Elevation (AGL) of the site in meters.
        """
        logger.debug(f"Validating output directory: {path}")
        if not os.path.exists(path):
            logger.debug(f"Directory does not exist: {path}")
            raise FileNotFoundError(f"Directory does not exist: {path}")
        if not os.access(path, os.W_OK):
            logger.debug(f"Directory is not writable: {path}")
            raise PermissionError(f"Directory is not writable: {path}")

        qth_path = os.path.join(path, f"{name}.qth")
        logger.debug(f"Creating .qth file at {path} with name '{name}'.")
        try:
            contents = (
                f"{name}\n"
                f"{latitude:.6f}\n"
                f"{abs(longitude) if longitude < 0 else 360 - longitude:.6f}\n"  # SPLAT! expects west longitude as a positive number.
                f"{elevation:.2f}\n"
            )
            with open(qth_path, "w") as qth_file:
                qth_file.write(contents)
                logger.info(f".qth file successfully created at {qth_path}")
                logger.debug(f".qth file contents:\n{contents}")
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
    ):
        """
        Create a SPLAT! .lrp file describing propagation parameters.

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
        """
        logger.debug(f"Validating output directory: {path}")
        if not os.path.exists(path):
            logger.debug(f"Directory does not exist: {path}")
            raise FileNotFoundError(f"Directory does not exist: {path}")
        if not os.access(path, os.W_OK):
            logger.debug(f"Directory is not writable: {path}")
            raise PermissionError(f"Directory is not writable: {path}")

        lrp_path = os.path.join(path, "splat.lrp")
        logger.info(f"Creating .lrp file at {lrp_path}")

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

        logger.debug(f"Radio climate map: {climate_map}")
        logger.debug(f"Polarization map: {polarization_map}")

        # Calculate ERP in Watts
        erp_watts = 10 ** ((tx_power + tx_gain - system_loss - 30) / 10)
        logger.debug(
            f"Calculated ERP in Watts: {erp_watts:.2f} "
            f"(tx_power={tx_power}, tx_gain={tx_gain}, system_loss={system_loss})"
        )

        # Generate file contents
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
        except IOError as e:
            logger.error(f"Failed to write .lrp file at {lrp_path}: {e}")
            raise

    def _generate_colormap(self, colormap_name: str, min_dbm: float, max_dbm: float, levels: int = 32):
        """
        Generate a color map as a mapping from values to RGB tuples.

        Args:
            colormap_name (str): The name of the Matplotlib colormap to use.
            min_value (float): The minimum value in the range.
            max_value (float): The maximum value in the range.
            levels (int): The number of discrete levels in the color map.

        Returns:
            dict: A mapping from index to RGB tuples (0-255 range).
            list: The corresponding value range for the levels.
        """
        # Get the colormap

        # Validate dBm range
        if min_dbm >= max_dbm:
            logger.error(f"Invalid dBm range: min_dbm={min_dbm}, max_dbm={max_dbm}")
            raise ValueError("min_dbm must be less than max_dbm")

        cmap = plt.get_cmap(colormap_name)
        values = np.linspace(max_dbm, min_dbm, levels)
        norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)

        # Generate RGB values
        rgb_colors = (cmap(norm(values))[:, :3] * 255).astype(int)

        # Map indices to RGB tuples
        gdal_colormap = {i: tuple(rgb) for i, rgb in enumerate(rgb_colors)}
        return gdal_colormap, values

    def _create_dcf(self,dcf_path: str, colormap_name: str, min_dbm: float, max_dbm: float, levels: int = 32):
        """
        Create a .dcf file for SPLAT! using a specified color map.

        Args:
            dcf_path (str): The file path to save the .dcf file.
            colormap_name (str): The name of the Matplotlib colormap.
            min_dbm (float): The minimum dBm value.
            max_dbm (float): The maximum dBm value.
            levels (int): The number of discrete levels in the color map.
        """
        logger.debug(f"Creating .dcf file at {dcf_path} using colormap '{colormap_name}'.")

        colormap, values = self._generate_colormap(colormap_name, min_dbm, max_dbm, levels)

        try:
            with open(dcf_path, "w") as dcf_file:
                dcf_file.write("; SPLAT! Auto-generated DBM Signal Level Color Definition\n")
                dcf_file.write(";\n")
                dcf_file.write("; Format: dBm: red, green, blue\n;\n")

                for value, rgb in zip(values, colormap.values()):
                    dcf_file.write(f"{int(value):+4d}: {rgb[0]:3d}, {rgb[1]:3d}, {rgb[2]:3d}\n")

            logger.info(f".dcf file created successfully at {dcf_path}")
        except IOError as e:
            logger.error(f"Failed to write .dcf file at {dcf_path}: {e}")
            raise


    def _bbox_from_kml(self, kml_file: str):
        """
        Extract bounding box (north, south, east, west) from a SPLAT KML file.

        Args:
            kml_file (str): Path to the SPLAT KML file.

        Returns:
            tuple: A tuple containing (north, south, east, west) in degrees as floats.

        Raises:
            FileNotFoundError: If the KML file is not found.
            ValueError: If the KML file is invalid or missing bounding box information.
        """
        logger.debug(f"Attempting to parse KML file: {kml_file}")
        try:
            tree = ET.parse(kml_file)
            logger.debug(f"KML file parsed successfully: {kml_file}")
        except FileNotFoundError:
            logger.error(f"KML file not found: {kml_file}")
            raise FileNotFoundError(f"KML file not found: {kml_file}")
        except ET.ParseError as e:
            logger.error(f"Failed to parse SPLAT KML file: {kml_file} - {e}")
            raise ValueError(f"Failed to parse SPLAT KML file: {kml_file}")

        root = tree.getroot()
        namespace = {"kml": "http://earth.google.com/kml/2.1"}
        box = root.find(".//kml:LatLonBox", namespace)
        if not box:
            logger.error(f"LatLonBox not found in .kml file: {kml_file}")
            raise ValueError("Could not find LatLonBox in the KML file")

        try:
            north = float(box.find("kml:north", namespace).text)
            south = float(box.find("kml:south", namespace).text)
            east = float(box.find("kml:east", namespace).text)
            west = float(box.find("kml:west", namespace).text)
            logger.debug(
                f"Extracted bounding box from .kml file: north={north}, south={south}, east={east}, west={west}"
            )
        except (TypeError, AttributeError) as e:
            logger.error(f"Invalid geospatial bounds in .kml file: {kml_file} - {e}")
            raise ValueError("Invalid geospatial bounds in the KML file")

        return north, south, east, west

    def _ppm_kml_to_geotiff(
        self, ppm_file: str, kml_file: str, output_tiff: str
    ):
        """
        Convert a SPLAT-generated PPM image to a GeoTIFF using geospatial bounds from the .kml file.

        Args:
            ppm_file (str): Path to the PPM file generated by SPLAT.
            kml_file (str): Path to the KML file containing geospatial bounds.
            output_tiff (str): Path where the output GeoTIFF will be saved.

        Raises:
            FileNotFoundError: If the PPM or KML file is not found.
            ValueError: If the KML file is invalid or contains no geospatial bounds.
            RuntimeError: If GeoTIFF creation or writing fails.
        """
        logger.info(f"Starting conversion from PPM to GeoTIFF.")
        logger.debug(
            f"PPM file: {ppm_file}, KML file: {kml_file}, output GeoTIFF: {output_tiff}"
        )

        # Extract bounding box from SPLAT KML file
        try:
            logger.debug(f"Extracting bounding box from KML file: {kml_file}")
            north, south, east, west = self._bbox_from_kml(kml_file)
            logger.debug(
                f"Extracted bounding box: north={north}, south={south}, east={east}, west={west}"
            )
        except FileNotFoundError:
            logger.error(f"KML file not found: {kml_file}")
            raise
        except ValueError as e:
            logger.error(f"Error parsing KML file: {kml_file} - {e}")
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
                compress="lzw",
                tiled=True,


            ) as dst:
                for i in range(3):
                    dst.write(img_array[:, :, i], i + 1)
                dst.update_tags(description="SPLAT! coverage prediction")
            logger.info(f"GeoTIFF creation successful: {output_tiff}")
        except Exception as e:
            logger.error(f"Error during GeoTIFF creation: {output_tiff} - {e}")
            raise RuntimeError(f"Error during GeoTIFF creation: {e}")

    def coverage_prediction(self, request: CoveragePredictRequest):
        """
        Execute a SPLAT! coverage prediction using the provided CoveragePredictRequest.

        Args:
            request (CoveragePredictRequest): The coverage prediction request object.

        Returns:
            dict: A dictionary containing paths to output files and logs.

        Raises:
            RuntimeError: If SPLAT! fails to execute.
        """
        logger.info("Starting SPLAT! coverage prediction.")
        logger.debug(f"Coverage prediction request: {request.json()}")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                logger.debug(f"Temporary directory created: {tmpdir}")

                # Create required input files
                self._create_qth(
                    path=tmpdir,
                    name="tx",
                    latitude=request.lat,
                    longitude=request.lon,
                    elevation=request.tx_height,
                )
                logger.info(f".qth file created for transmitter.")

                self._create_lrp(
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

                self._create_dcf(
                    path=tmpdir,
                    colormap=request.colormap,
                    min_dbm=request.min_dbm,
                    max_dbm=request.max_dbm,
                )
                logger.info(f".dcf file created for signal level color definitions.")

                # SPLAT! execution
                output_ppm = os.path.join(tmpdir, "output.ppm")
                output_kml = os.path.join(tmpdir, "output.kml")
                command = [
                    self.splat_path,
                    "-t",
                    os.path.join(tmpdir, "tx.qth"),
                    "-L",
                    str(request.rxh),
                    "-metric",
                    "-R",
                    str(request.radius / 1000.0),
                    "-sc",
                    "-ngs",
                    "-N",
                    "-o",
                    output_ppm,
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
                self._ppm_kml_to_geotiff(
                    output_ppm, output_kml, output_tiff_path
                )
                logger.info(f"GeoTIFF created: {output_tiff_path}")

                with open(output_tiff_path, "rb") as output_tiff:
                    output_tiff_data = output_tiff.read()

                # Prepare outputs
                outputs = {
                    "geotiff": output_tiff_data,
                    "log_stdout": result.stdout,
                    "log_stderr": result.stderr,
                }

                logger.info("SPLAT! coverage prediction completed successfully.")
                return outputs

            except Exception as e:
                logger.error(f"Error during coverage prediction: {e}")
                raise RuntimeError(f"Error during coverage prediction: {e}")


def parse_arguments():
    """Parse command-line arguments for SPLAT! Coverage Prediction."""
    parser = argparse.ArgumentParser(description="Run SPLAT! Coverage Prediction CLI")
    parser.add_argument(
        "--scenario",
        type=str,
        required=True,
        help="Path to a YAML scenario file (e.g., scenario.yaml) specifying prediction parameters.",
    )
    parser.add_argument(
        "--splat_path",
        type=str,
        required=True,
        help="Path to the SPLAT! binary file.",
    )
    parser.add_argument(
        "--tile_dir",
        type=str,
        required=True,
        help="Path to the directory containing .sdf terrain tiles.",
    )
    parser.add_argument(
        "--output_tiff",
        type=str,
        required=False,
        default="output.tiff",
        help="Path to save the output GeoTIFF file (default: 'output.tiff').",
    )

    parser.add_argument(
        "--log_level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO).",
    )
    return parser.parse_args()


def main():
    """Main function to run the SPLAT! Coverage Prediction."""
    args = parse_arguments()

    # Configure the logger
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    try:
        # Load scenario from YAML
        scenario_path = Path(args.scenario)
        if not scenario_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {args.scenario}")

        with open(scenario_path, "r") as file:
            scenario_data = yaml.safe_load(file)
        logger.info(f"Loaded scenario from {args.scenario}")

        # Validate and create a CoveragePredictRequest object
        try:
            request = CoveragePredictRequest(**scenario_data)
        except Exception as e:
            logger.error(f"Scenario validation failed: {e}")
            raise

        # Run SPLAT!
        splat = Splat(splat_path=args.splat_path, tile_dir=args.tile_dir)
        logger.info("Running SPLAT! coverage prediction...")
        result = splat.coverage_prediction(request)

        # Save GeoTIFF
        with open(args.output_tiff, "wb") as tiff_file:
            tiff_file.write(result["geotiff"])
        logger.info(f"GeoTIFF saved to {args.output_tiff}")

    except Exception as e:
        logger.error(f"An error occurred during the execution: {e}", exc_info=True)


if __name__ == "__main__":
    main()
