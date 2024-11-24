import gzip
import logging
import math
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import List, Literal

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from diskcache import Cache

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from PIL import Image
from rasterio.transform import from_bounds

from app.models.CoveragePredictionRequest import CoveragePredictionRequest


logger = logging.getLogger(__name__)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("s3transfer").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

class Splat:
    def __init__(self, splat_path: str, cache_path: str = ".tile_cache", cache_size_gb:float = 1.0):
        """
        Initialize the SPLAT! wrapper.

        Args:
            splat_path (str): Path to the directory containing the SPLAT! binaries.
            cache_path (str): Directory to store cached .sdf terrain tiles.
            cache_size_gb (float): Maximum size of the cache in gigabytes (GB) Defaults to 1.0.
        """
        # Check the provided path exists
        if not os.path.isdir(splat_path):
            raise FileNotFoundError(f"Provided path '{splat_path}' is not a valid directory.")

        # Construct full paths to the SPLAT! binaries
        splat_binary = os.path.join(splat_path, "splat")
        splat_hd_binary = os.path.join(splat_path, "splat-hd")
        srtm2sdf_binary = os.path.join(splat_path,"srtm2sdf")
        srtm2sdf_hd_binary = os.path.join(splat_path,"srtm2sdf-hd")

        # Check binaries exist and are executable
        if not os.path.isfile(splat_binary) or not os.access(splat_binary, os.X_OK):
            raise FileNotFoundError(f"'splat' binary not found or not executable at '{splat_binary}'")
        if not os.path.isfile(splat_hd_binary) or not os.access(splat_hd_binary, os.X_OK):
            raise FileNotFoundError(f"'splat-hd' binary not found or not executable at '{splat_hd_binary}'")
        if not os.path.isfile(srtm2sdf_binary) or not os.access(srtm2sdf_binary, os.X_OK):
            raise FileNotFoundError(f"'srtm2sdf_binary' binary not found or not executable at '{srtm2sdf_binary}'")
        if not os.path.isfile(srtm2sdf_hd_binary) or not os.access(srtm2sdf_hd_binary, os.X_OK):
            raise FileNotFoundError(f"'srtm2sdf_hd_binary' binary not found or not executable at '{srtm2sdf_hd_binary}'")

        self.splat_binary = splat_binary
        self.splat_hd_binary = splat_hd_binary
        self.srtm2sdf_binary = srtm2sdf_binary
        self.srtm2sdf_hd_binary = srtm2sdf_hd_binary

        cache_size_bytes = int(cache_size_gb * 1024 * 1024 * 1024)  # GB to bytes
        self.cache = Cache(cache_path, size_limit=cache_size_bytes)
        self.cache_path = cache_path
        logger.info(
            f"Initialized terrain tile cache at '{cache_path}' with a size limit of {cache_size_gb} GB ({cache_size_bytes} bytes)."
        )

    def _required_srtm_tiles(self, lat: float, lon: float, radius: float) -> dict[str, list[str]]:
        """
        Determine the set of SRTM terrain tiles needed to cover a given area and their corresponding .sdf filenames.

        Args:
            lat (float): Latitude of the center point in degrees.
            lon (float): Longitude of the center point in degrees.
            radius (float): Radius in meters.

        Returns:
            dict[str, list[str]]: A dictionary containing:
                - "tiles": List of required .hgt.gz tile filenames.
                - "sdf": List of corresponding .sdf filenames.
                - "sdf-hd": List of corresponding .sdf filenames for the 1-arcsecond data.
        """
        earth_radius = 6378137

        # Convert radius to angular distance in degrees
        delta_deg = (radius / earth_radius) * (180 / math.pi)

        # Compute bounding box in degrees
        lat_min = lat - delta_deg
        lat_max = lat + delta_deg
        lon_min = lon - delta_deg / math.cos(math.radians(lat))
        lon_max = lon + delta_deg / math.cos(math.radians(lat))

        # Determine the tile boundaries (rounded to 1-degree tiles)
        lat_min_tile = math.floor(lat_min)
        lat_max_tile = math.floor(lat_max)
        lon_min_tile = math.floor(lon_min)
        lon_max_tile = math.floor(lon_max)

        # All tile names within the bounding box
        tiles = []
        sdf_filenames = []
        sdf_hd_filenames = []

        for lat_tile in range(lat_min_tile, lat_max_tile + 1):
            for lon_tile in range(lon_min_tile, lon_max_tile + 1):
                ns = "N" if lat_tile >= 0 else "S"
                ew = "E" if lon_tile >= 0 else "W"
                tile_name = f"{ns}{abs(lat_tile):02d}{ew}{abs(lon_tile):03d}.hgt.gz"
                tiles.append(tile_name)

                # Calculate .sdf boundaries
                lat_start = lat_tile
                lon_start = lon_tile
                lat_end = lat_start + 1
                lon_end = lon_start + 1

                # Generate .sdf names
                sdf_filenames.append(f"{lat_start}:{lat_end}:{lon_start}:{lon_end}.sdf")
                sdf_hd_filenames.append(f"{lat_start}:{lat_end}:{lon_start}:{lon_end}-hd.sdf")

        return {"tiles": tiles, "sdf": sdf_filenames, "sdf-hd": sdf_hd_filenames}

    def _download_srtm_tiles(self, lat: float, lon: float, radius: float, path: str, high_resolution: bool = False):
        """
        Download, decompress, and convert SRTM tiles to .sdf format.

        Args:
            lat (float): Latitude of the center point in degrees.
            lon (float): Longitude of the center point in degrees.
            radius (float): Radius in meters.
            path (str): Directory to save the final .sdf files.
            high_resolution (bool): Whether to generate high-resolution .sdf files.

        Returns:
            None
        """
        # Ensure the output directory exists
        os.makedirs(path, exist_ok=True)
        logger.debug(f"Ensured cache directory exists at {path}")

        # Determine required tiles
        tile_info = self._required_srtm_tiles(lat, lon, radius)
        required_tiles = tile_info["tiles"]
        sdf_files = tile_info["sdf-hd"] if high_resolution else tile_info["sdf"]

        # Create a list of tiles and their corresponding .sdf filenames
        tiles_and_sdfs = [(tile, sdf) for tile, sdf in zip(required_tiles, sdf_files)]

        # Initialize S3 client
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        bucket_name = "elevation-tiles-prod"
        bucket_prefix = "v2/skadi"

        for tile_name, sdf_file in tiles_and_sdfs:
            # Check if the .sdf file is already in the cache
            print("looking for SDF file: ", sdf_file)
            sdf_path = os.path.join(path, sdf_file)
            print("looking for SDF path: ", sdf_path)

            if os.path.exists(sdf_path):
                logger.info(f"Cache hit: {sdf_file} already exists.")
                continue

            # Download the .hgt.gz file
            compressed_path = os.path.join(path, tile_name)
            decompressed_path = compressed_path.replace(".gz", "")
            try:
                tile_dir_prefix = tile_name[:3]
                s3_key = f"{bucket_prefix}/{tile_dir_prefix}/{tile_name}"
                logger.info(f"Downloading {tile_name} from {bucket_name}/{s3_key}...")
                s3.download_file(bucket_name, s3_key, compressed_path)
                logger.debug(f"Downloaded {tile_name} to {compressed_path}")
            except Exception as e:
                logger.error(f"Failed to download {tile_name}: {e}")
                raise RuntimeError(f"Failed to download {tile_name}: {e}")

            # Decompress the .hgt.gz file
            try:
                logger.info(f"Decompressing {compressed_path}...")
                with gzip.open(compressed_path, "rb") as f_in:
                    with open(decompressed_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                        logger.debug(f"Decompressed {tile_name} to {decompressed_path}")
            except Exception as e:
                logger.error(f"Failed to decompress {compressed_path}: {e}")
                raise RuntimeError(f"Failed to decompress {compressed_path}: {e}")

            # Convert the .hgt file to .sdf
            try:
                cmd = "srtm2sdf-hd" if high_resolution else "srtm2sdf"
                logger.info(f"Converting {decompressed_path} to {sdf_file} using {cmd}...")
                subprocess.run(
                    [cmd, "-d", "/dev/null", tile_name.replace(".gz", "")],
                    check=True,
                    cwd=path,
                )

                # Downsample if not high resolution
                if not high_resolution:
                    try:
                        logger.info(f"Downsampling {decompressed_path} to 3-arcsecond resolution.")
                        with rasterio.open(decompressed_path) as src:
                            # Apply a scaling factor to transform for 3-arcsecond resolution
                            transform = src.transform * src.transform.scale(3, 3)

                            # Resample data to 3-arcsecond resolution
                            data = src.read(
                                out_shape=(
                                    src.count,  # Number of bands
                                    src.height // 3,  # Downsampled height
                                    src.width // 3,  # Downsampled width
                                ),
                                resampling=Resampling.average,
                            )

                            # Update metadata for the new dataset
                            meta = src.meta.copy()
                            meta.update({
                                "transform": transform,
                                "width": src.width // 3,
                                "height": src.height // 3,
                            })

                        # Overwrite the original file destructively with downsampled data
                        with rasterio.open(decompressed_path, "w", **meta) as dst:
                            dst.write(data)

                        logger.info(f"Successfully downsampled and overwrote {decompressed_path}.")
                    except Exception as e:
                        logger.error(f"Failed to downsample {decompressed_path}: {e}")
                        raise RuntimeError(f"Failed to downsample {decompressed_path}: {e}")

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to convert {decompressed_path} to .sdf: {e}")
                raise RuntimeError(f"Failed to convert {decompressed_path} to .sdf: {e}")

            # Cleanup intermediate files
            try:
                os.remove(compressed_path)
                os.remove(decompressed_path)
                logger.debug(f"Cleaned up temporary files for {tile_name}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary files for {tile_name}: {e}")

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

                self._download_srtm_tiles(request.lat, request.lon, request.radius, self.cache_path, request.high_resolution)

                logger.debug(f"Contents of {tmpdir}: {os.listdir(tmpdir)}")

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
                    self.splat_hd_binary if request.high_resolution else self.splat_binary,
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
                    os.path.abspath(self.cache_path),
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

                self._create_geotiff(
                    ppm_path,
                    kml_path,
                    output_tiff_path,
                    request.colormap,
                    request.min_dbm,
                    request.max_dbm,
                )
                shutil.copy(ppm_path, "/Users/patrick/Downloads/output.ppm")

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
        self,
        ppm_file: str,
        kml_file: str,
        output_tiff: str,
        colormap_name: str,
        min_dbm: float,
        max_dbm: float,
    ) -> str:
        """
        Convert a SPLAT-generated PPM image to a GeoTIFF using geospatial bounds from the generated .kml and embed
        a color table for proper rendering in GIS viewers.

        Args:
            ppm_file (str): Path to the PPM file generated by SPLAT.
            kml_file (str): Path to the KML file containing geospatial bounds.
            output_tiff (str): Path where the output GeoTIFF will be saved.
            colormap_name (str): Name of the colormap used for the GeoTIFF.
            min_dbm (float): Minimum dBm value for the color scale.
            max_dbm (float): Maximum dBm value for the color scale.

        Returns:
            str: the path to the GeoTIFF file.
        """
        logger.info(f"Starting conversion from SPLAT! output (PPM, KML) to GeoTIFF.")
        logger.debug(
            f"PPM file: {ppm_file}, KML file: {kml_file}, output GeoTIFF: {output_tiff}"
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
        except Exception as e:
            logger.error(f"Error parsing KML file: {kml_file} - {e}")
            raise

        # Read SPLAT PPM file
        try:
            logger.debug(f"Reading PPM file: {ppm_file}")
            with Image.open(ppm_file) as img:
                img_array = np.array(
                    img.convert("L")
                )  # Convert to single-channel grayscale
                img_array = np.clip(img_array, 0, 255).astype(
                    "uint8"
                )  # Ensure uint8 values
            logger.debug(f"PPM image dimensions: {img_array.shape}")
        except Exception as e:
            logger.error(f"Error reading PPM file: {ppm_file} - {e}")
            raise

        # Create GeoTIFF with Rasterio
        try:
            height, width = img_array.shape
            transform = from_bounds(west, south, east, north, width, height)
            logger.debug(f"GeoTIFF transform matrix: {transform}")

            # Generate colormap from Matplotlib
            cmap = plt.get_cmap(colormap_name)
            cmap_values = np.linspace(min_dbm, max_dbm, 256)
            cmap_norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)
            rgb_colors = (cmap(cmap_norm(cmap_values))[:, :3] * 255).astype(int)

            # Build GDAL-compatible colormap
            gdal_colormap = {i: tuple(rgb) for i, rgb in enumerate(rgb_colors)}

            logger.info(f"Creating GeoTIFF: {output_tiff}")
            with rasterio.open(
                output_tiff,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=1,  # Single-band data with colormap
                dtype="uint8",
                crs="EPSG:4326",
                transform=transform,
                compress="lzw",
            ) as dst:
                dst.write(img_array, 1)  # Write grayscale data
                dst.write_colormap(
                    1, gdal_colormap
                )  # Attach colormap to the first band
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
            splat_path="/Users/patrick/Dev/splat",  # Replace with the actual SPLAT! binary path
        )

        # Create a test coverage prediction request
        test_request = CoveragePredictionRequest(
            lat=51.08631115040277,
            lon=-114.12940896854595,
            tx_height=5.0,
            ground_dielectric=15.0,
            ground_conductivity=0.005,
            atmosphere_bending=301.0,
            frequency_mhz=905.0,
            radio_climate="continental_temperate",
            polarization="vertical",
            situation_fraction=90.0,
            time_fraction=90.0,
            tx_power=30.0,
            tx_gain=2.0,
            system_loss=2.0,
            rxh=1.0,
            radius=1000.0,
            colormap="jet",
            min_dbm=-130.0,
            max_dbm=-80.0,
            signal_threshold=-130.0,
            high_resolution=True
        )

        # Execute coverage prediction
        logger.info("Starting SPLAT! coverage prediction...")
        result = splat_service.coverage_prediction(test_request)

        # Save GeoTIFF output for inspection
        output_path = "splat_output.tif"
        with open(output_path, "wb") as output_file:
            output_file.write(result)
        logger.info(f"GeoTIFF saved to: {output_path}")

    except Exception as e:
        logger.error(f"Error during SPLAT! test: {e}")
