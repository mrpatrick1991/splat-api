import gzip
import logging
import math
import os
import io
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Literal, List, Tuple

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from diskcache import Cache

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from PIL import Image

from meshtastic_link_planner.models.CoveragePredictionRequest import CoveragePredictionRequest


logger = logging.getLogger(__name__)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("s3transfer").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class Splat:
    def __init__(
        self,
        splat_path: str,
        cache_dir: str = ".splat_tiles",
        cache_size_gb: float = 1.0,
        bucket_name: str = "elevation-tiles-prod",
        bucket_prefix:str = "v2/skadi"
    ):
        """
        SPLAT! wrapper class. Provides methods for generating SPLAT! RF coverage maps in GeoTIFF format.
        This class automatically downloads and caches the necessary terrain data from AWS:
        https://registry.opendata.aws/terrain-tiles/.

        SPLAT! and its optional utilities (splat, splat-hd, srtm2sdf, srtm2sdf-hd) must be installed
        in the `splat_path` directory and be executable.

        See the SPLAT! documentation: https://www.qsl.net/kd2bd/splat.html
        Additional details: https://github.com/jmcmellen/splat

        Args:
            splat_path (str): Path to the directory containing the SPLAT! binaries.
            cache_dir (str): Directory to store cached terrain tiles.
            cache_size_gb (float): Maximum size of the cache in gigabytes (GB). Defaults to 1.0.
                When the size of the cached tiles exceeds this value, the oldest tiles are deleted
                and will be re-downloaded as required.
            bucket_name (str): Name of the S3 bucket containing terrain tiles. Defaults to the AWS
                open data bucket `elevation-tiles-prod`.
            bucket_prefix (str): Folder in the S3 bucket containing the terrain tiles. Defaults to
                `v2/skadi`, which contains 1-arcsecond terrain data for most of the world.
        """

        # Check the provided SPLAT! path exists
        if not os.path.isdir(splat_path):
            raise FileNotFoundError(
                f"Provided SPLAT! path '{splat_path}' is not a valid directory."
            )

        # SPLAT! binaries
        self.splat_binary = os.path.join(splat_path, "splat")  # core SPLAT! program
        self.splat_hd_binary = os.path.join(
            splat_path, "splat-hd"
        )  # used instead of the splat binary when using the 1-arcsecond / 30 meter resolution terrain data.
        self.srtm2sdf_binary = os.path.join(
            splat_path, "srtm2sdf"
        )  # convert 3-arcsecond resolution srtm .hgt terrain tiles to SPLAT! .sdf terrain tiles.
        self.srtm2sdf_hd_binary = os.path.join(
            splat_path, "srtm2sdf-hd"
        )  # used instead of srtm2sdf when using the 1-arcsecond / 30 meter resolution terrain data.

        # Check the SPLAT! binaries exist and are executable
        if not os.path.isfile(self.splat_binary) or not os.access(
            self.splat_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'splat' binary not found or not executable at '{self.splat_binary}'"
            )
        if not os.path.isfile(self.splat_hd_binary) or not os.access(
            self.splat_hd_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'splat-hd' binary not found or not executable at '{self.splat_hd_binary}'"
            )
        if not os.path.isfile(self.srtm2sdf_binary) or not os.access(
            self.srtm2sdf_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'srtm2sdf_binary' binary not found or not executable at '{self.srtm2sdf_binary}'"
            )
        if not os.path.isfile(self.srtm2sdf_hd_binary) or not os.access(
            self.srtm2sdf_hd_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'srtm2sdf_hd_binary' binary not found or not executable at '{self.srtm2sdf_hd_binary}'"
            )

        self.tile_cache = Cache(
            cache_dir, size_limit=int(cache_size_gb * 1024 * 1024 * 1024)
        )

        self.s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        self.bucket_name = bucket_name
        self.bucket_prefix = bucket_prefix

        logger.info(
            f"Initialized SPLAT! with terrain tile cache at '{cache_dir}' with a size limit of {cache_size_gb} GB."
        )

    def coverage_prediction(self, request: CoveragePredictionRequest) -> bytes:
        """
        Execute a SPLAT! coverage prediction using the provided CoveragePredictionRequest.

        Args:
            request (CoveragePredictionRequest): The coverage prediction request object.

        Returns:
            bytes: the SPLAT! coverage prediction as a GeoTIFF.

        Raises:
            RuntimeError: If SPLAT! fails to execute.
        """
        logger.debug(f"Coverage prediction request: {request.json()}")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                logger.debug(f"Temporary directory created: {tmpdir}")

                # determine the required terrain tiles
                required_tiles = Splat._calculate_required_terrain_tiles(request.lat, request.lon, request.radius)

                # download and convert terrain tiles to SPLAT! sdf
                for tile_name, sdf_name, sdf_hd_name in required_tiles:
                    tile_data = self._download_terrain_tile(tile_name)
                    sdf_data = self._convert_hgt_to_sdf(tile_data, tile_name, high_resolution=request.high_resolution)

                    with open(os.path.join(tmpdir, sdf_hd_name if request.high_resolution else sdf_name), "wb") as sdf_file:
                        sdf_file.write(sdf_data)

                # write transmitter / qth file
                with open(os.path.join(tmpdir, "tx.qth"), "wb") as qth_file:
                    qth_file.write(Splat._create_splat_qth("tx",request.lat,request.lon,request.tx_height))

                # write model parameter / lrp file
                with open(os.path.join(tmpdir,"splat.lrp"), "wb") as lrp_file:
                    lrp_file.write(Splat._create_splat_lrp(
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
                        system_loss=request.system_loss))

                # write colorbar / dcf file
                with open(os.path.join(tmpdir, "splat.dcf"), "wb") as dcf_file:
                    dcf_file.write(Splat._create_splat_dcf(
                        colormap_name=request.colormap,
                        min_dbm=request.min_dbm,
                        max_dbm=request.max_dbm
                    ))

                logger.debug(f"Contents of {tmpdir}: {os.listdir(tmpdir)}")

                splat_command = [
                    (
                        self.splat_hd_binary
                        if request.high_resolution
                        else self.splat_binary
                    ),
                    "-t",
                    "tx.qth",
                    "-L",
                    str(request.rx_height),
                    "-metric",
                    "-R",
                    str(request.radius / 1000.0),
                    "-sc",
                    "-ngs",
                    "-N",
                    "-o",
                    "output.ppm",
                    "-dbm",
                    "-db",
                    str(request.signal_threshold),
                    "-kml",
                ]
                logger.debug(f"Executing SPLAT! command: {' '.join(splat_command)}")

                splat_result = subprocess.run(
                    splat_command,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                logger.debug(f"SPLAT! stdout:\n{splat_result.stdout}")
                logger.debug(f"SPLAT! stderr:\n{splat_result.stderr}")

                if splat_result.returncode != 0:
                    logger.error(
                        f"SPLAT! execution failed with return code {splat_result.returncode}"
                    )
                    raise RuntimeError(
                        f"SPLAT! execution failed with return code {splat_result.returncode}\n"
                        f"Stdout: {splat_result.stdout}\nStderr: {splat_result.stderr}"
                    )

                with open(os.path.join(tmpdir, "output.ppm"), "rb") as ppm_file:
                    with open(os.path.join(tmpdir, "output.kml"), "rb") as kml_file:
                        ppm_data = ppm_file.read()
                        kml_data = kml_file.read()
                        geotiff_data = Splat._create_splat_geotiff(ppm_data,kml_data,request.colormap,request.min_dbm,request.max_dbm)

                logger.info("SPLAT! coverage prediction completed successfully.")
                return geotiff_data

            except Exception as e:
                logger.error(f"Error during coverage prediction: {e}")
                raise RuntimeError(f"Error during coverage prediction: {e}")

    @staticmethod
    def _calculate_required_terrain_tiles(
            lat: float, lon: float, radius: float
    ) -> List[Tuple[str, str, str]]:
        """
        Determine the set of required terrain tiles for the specified area and their corresponding .sdf / -hd.sdf
        filenames. This is used for downloading terrain data for SPLAT! which requires the files to follow a specific
        naming convention.

        Calculates the geographic bounding box based on the provided latitude, longitude, and radius, then
        determines the necessary tiles to cover the area. It returns filenames in the following formats:

            - .hgt.gz files: raw 1 arc-second terrain elevation tiles stored in AWS Open Data / S3.
            - .sdf files: Used for standard resolution (3-arcsecond) terrain data in SPLAT!.
            - .sdf-hd files: Used for high-resolution (1-arcsecond) terrain data in SPLAT!.

        The .hgt.gz filenames have the format:
            <N|S><latitude: 2 digits><E|W><longitude: 3 digits>.hgt.gz
            Example: N35W120.hgt.gz

        The .sdf and .sdf-hd filenames have the format:
            <lat_start>:<lat_end>:<lon_start>:<lon_end>.sdf
            <lat_start>:<lat_end>:<lon_start>:<lon_end>-hd.sdf
            Example: 35:36:-120:-119.sdf, 35:36:-120:-119-hd.sdf

        Args:
            lat (float): Latitude of the center point in degrees.
            lon (float): Longitude of the center point in degrees.
            radius (float): Simulation coverage radius in meters.

        Returns:
            List[Tuple[str, str, str]]: A list of tuples, each containing:
                - .hgt.gz filename (str)
                - Corresponding .sdf filename (str)
                - Corresponding .sdf-hd filename (str)
        """

        earth_radius = 6378137  # meters, approximate.

        # Convert radius to angular distance in degrees
        delta_deg = (radius / earth_radius) * (180 / math.pi)

        # Compute bounding box in degrees
        lat_min = lat - delta_deg
        lat_max = lat + delta_deg
        lon_min = lon - delta_deg / math.cos(math.radians(lat))
        lon_max = lon + delta_deg / math.cos(math.radians(lat))

        # Determine tile boundaries (rounded to 1-degree tiles)
        lat_min_tile = math.floor(lat_min)
        lat_max_tile = math.floor(lat_max)
        lon_min_tile = math.floor(lon_min)
        lon_max_tile = math.floor(lon_max)

        # All tile names within the bounding box
        tile_names = []

        for lat_tile in range(lat_min_tile, lat_max_tile + 1):
            for lon_tile in range(lon_min_tile, lon_max_tile + 1):
                ns = "N" if lat_tile >= 0 else "S"
                ew = "E" if lon_tile >= 0 else "W"
                tile_name = f"{ns}{abs(lat_tile):02d}{ew}{abs(lon_tile):03d}.hgt.gz"

                # .sdf file boundaries
                lat_start = lat_tile
                lon_start = lon_tile
                lat_end = lat_start + 1
                lon_end = lon_start + 1

                # Generate .sdf file names
                sdf_filename = Splat._hgt_filename_to_sdf_filename(tile_name, high_resolution = False)
                sdf_hd_filename = Splat._hgt_filename_to_sdf_filename(tile_name, high_resolution = True)
                tile_names.append((tile_name, sdf_filename, sdf_hd_filename))

        return tile_names

    @staticmethod
    def _create_splat_qth(name: str, latitude: float, longitude: float, elevation: float) -> bytes:
        """
        Generate the contents of a SPLAT! .qth file describing a transmitter or receiver site.

        Args:
            name (str): Name of the site (unused but required for SPLAT!).
            latitude (float): Latitude of the site in degrees.
            longitude (float): Longitude of the site in degrees.
            elevation (float): Elevation (AGL) of the site in meters.

        Returns:
            bytes: The content of the .qth file formatted for SPLAT!.
        """
        logger.debug(f"Generating .qth file content for site '{name}'.")

        try:
            # Create the .qth file content
            contents = (
                f"{name}\n"
                f"{latitude:.6f}\n"
                f"{abs(longitude) if longitude < 0 else 360 - longitude:.6f}\n"  # SPLAT! expects west longitude as a positive number.
                f"{elevation:.2f}\n"
            )
            logger.debug(f"Generated .qth file contents:\n{contents}")
            return contents.encode('utf-8')  # Return as bytes
        except Exception as e:
            logger.error(f"Error generating .qth file content: {e}")
            raise ValueError(f"Failed to generate .qth content: {e}")

    @staticmethod
    def _create_splat_lrp(
            ground_dielectric: float,
            ground_conductivity: float,
            atmosphere_bending: float,
            frequency_mhz: float,
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
            situation_fraction: float,
            time_fraction: float,
            tx_power: float,
            tx_gain: float,
            system_loss: float,

    ) -> bytes:
        """
        Generate the contents of a SPLAT! .lrp file describing environment and propagation parameters.

        Args:
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
            system_loss (float): System losses in dB (e.g., cable loss).

        Returns:
            bytes: The content of the .lrp file formatted for SPLAT!.
        """
        logger.debug("Generating .lrp file content.")

        # Mapping for radio climate and polarization to SPLAT! enumerations
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

        # Generate the content, maintaining the SPLAT! format
        try:
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
            return contents.encode('utf-8')  # Return as bytes
        except Exception as e:
            logger.error(f"Error generating .lrp file content: {e}")
            raise

    @staticmethod
    def _create_splat_dcf(
            colormap_name: str, min_dbm: float, max_dbm: float
    ) -> bytes:
        """
        Generate the content of a SPLAT! .dcf file controlling the signal level contours
        using the specified Matplotlib color map.

        Args:
            colormap_name (str): The name of the Matplotlib colormap.
            min_dbm (float): The minimum signal strength value for the colormap in dBm.
            max_dbm (float): The maximum signal strength value for the colormap in dBm.

        Returns:
            bytes: The content of the .dcf file formatted for SPLAT!.
        """
        logger.debug(
            f"Generating .dcf file content using colormap '{colormap_name}', min_dbm={min_dbm}, max_dbm={max_dbm}."
        )

        try:
            # Generate color map values and normalization
            cmap = plt.get_cmap(colormap_name)
            cmap_values = np.linspace(max_dbm, min_dbm, 32)  # SPLAT! supports up to 32 levels
            cmap_norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)

            # Generate RGB values
            rgb_colors = (cmap(cmap_norm(cmap_values))[:, :3] * 255).astype(int)

            # Prepare .dcf content
            contents = "; SPLAT! Auto-generated DBM Signal Level Color Definition\n;\n"
            contents += "; Format: dBm: red, green, blue\n;\n"
            for value, rgb in zip(cmap_values, rgb_colors):
                contents += f"{int(value):+4d}: {rgb[0]:3d}, {rgb[1]:3d}, {rgb[2]:3d}\n"

            logger.debug(f"Generated .dcf file contents:\n{contents}")
            return contents.encode("utf-8")

        except Exception as e:
            logger.error(f"Error generating .dcf file content: {e}")
            raise ValueError(f"Failed to generate .dcf content: {e}")

    @staticmethod
    def _create_splat_geotiff(
            ppm_bytes: bytes,
            kml_bytes: bytes,
            colormap_name: str,
            min_dbm: float,
            max_dbm: float,
            null_value: int = 255  # Define the null value for transparency
    ) -> bytes:
        """
        Generate GeoTIFF file content from SPLAT! PPM and KML data, with transparency for null areas.

        Args:
            ppm_bytes (bytes): Binary content of the SPLAT-generated PPM file.
            kml_bytes (bytes): Binary content of the KML file containing geospatial bounds.
            colormap_name (str): Name of the matplotlib colormap to use for the GeoTIFF.
            min_dbm (float): Minimum dBm value for the colormap scale.
            max_dbm (float): Maximum dBm value for the colormap scale.
            null_value (int): Pixel value in the PPM that represents null areas. Defaults to 255.

        Returns:
            bytes: The binary content of the resulting GeoTIFF file.

        Raises:
            RuntimeError: If the conversion process fails.
        """
        logger.info("Starting GeoTIFF generation from SPLAT! PPM and KML data.")

        try:
            # Parse KML and extract bounding box
            logger.debug("Parsing KML content.")
            tree = ET.ElementTree(ET.fromstring(kml_bytes))
            namespace = {"kml": "http://earth.google.com/kml/2.1"}
            box = tree.find(".//kml:LatLonBox", namespace)

            north = float(box.find("kml:north", namespace).text)
            south = float(box.find("kml:south", namespace).text)
            east = float(box.find("kml:east", namespace).text)
            west = float(box.find("kml:west", namespace).text)

            logger.debug(
                f"Extracted bounding box: north={north}, south={south}, east={east}, west={west}"
            )

            # Read PPM content
            logger.debug("Reading PPM content.")
            with Image.open(io.BytesIO(ppm_bytes)) as img:
                img_array = np.array(
                    img.convert("L")
                )  # Convert to single-channel grayscale
                img_array = np.clip(img_array, 0, 255).astype("uint8")

            logger.debug(f"PPM image dimensions: {img_array.shape}")

            # Mask null values
            img_array = np.where(img_array == null_value, 255, img_array)  # Optionally set to 0
            no_data_value = null_value

            # Create GeoTIFF using Rasterio
            height, width = img_array.shape
            transform = from_bounds(west, south, east, north, width, height)
            logger.debug(f"GeoTIFF transform matrix: {transform}")

            # Generate colormap with transparency
            cmap = plt.get_cmap(colormap_name, 256)  # Viridis colormap with 256 levels
            cmap_norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)  # Normalize based on dBm range
            cmap_values = np.linspace(min_dbm, max_dbm, 255)

            # Map data values to RGB for visible colors
            rgb_colors = (cmap(cmap_norm(cmap_values))[:, :3] * 255).astype(int)

            # Initialize GDAL-compatible colormap with transparency for null values
            gdal_colormap = {i: tuple(rgb) + (255,) for i, rgb in enumerate(rgb_colors)}

            # Write GeoTIFF to memory
            with io.BytesIO() as buffer:
                with rasterio.open(
                        buffer,
                        "w",
                        driver="GTiff",
                        height=height,
                        width=width,
                        count=1,  # Single-band data
                        dtype="uint8",
                        crs="EPSG:4326",
                        transform=transform,
                        photometric="palette",  # Colormap interpretation
                        compress="lzw",
                        nodata=no_data_value,  # Set NoData value
                ) as dst:
                    dst.write(img_array, 1)  # Write the raster data
                    dst.write_colormap(1, gdal_colormap)  # Attach the colormap

                buffer.seek(0)
                geotiff_bytes = buffer.read()

            logger.info("GeoTIFF generation successful.")
            return geotiff_bytes

        except Exception as e:
            logger.error(f"Error during GeoTIFF generation: {e}")
            raise RuntimeError(f"Error during GeoTIFF generation: {e}")

    def _download_terrain_tile(self, tile_name: str) -> bytes:
        """
        Downloads a terrain tile from the S3 bucket if not found in the local cache.

        This method checks if the requested tile is available in the cache..
        If the tile is not cached, it downloads the tile from the specified S3 bucket,
        stores it in the cache, and returns the tile data.

        Args:
            tile_name (str): The name of the terrain tile to be downloaded.

        Returns:
            bytes: The binary content of the terrain tile.

        Raises:
            Exception: If the tile cannot be downloaded from S3.
        """
        if tile_name in self.tile_cache:
            logger.info(f"Cache hit: {tile_name} found in the local cache.")
            return self.tile_cache[tile_name]

        # Download the tile from S3 if not in cache
        tile_dir_prefix = tile_name[:3]
        s3_key = f"{self.bucket_prefix}/{tile_dir_prefix}/{tile_name}"
        logger.info(f"Downloading {tile_name} from {self.bucket_name}/{s3_key}...")
        try:
            obj = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            tile_data = obj['Body'].read()
            # Store the tile in the cache
            self.tile_cache[tile_name] = tile_data
            return tile_data
        except Exception as e:
            logger.error(f"Failed to download {tile_name} from S3: {e}")
            raise

    @staticmethod
    def _hgt_filename_to_sdf_filename(hgt_filename: str, high_resolution: bool = False) -> str:
            """ helper method to get the expected SPLAT! .sdf filename from the .hgt.gz terrain tile."""
            lat = int(hgt_filename[1:3]) * (1 if hgt_filename[0] == 'N' else -1)
            lon = int(hgt_filename[4:7]) - 1
            lon = 360 - lon if hgt_filename[3] == 'E' else lon
            return f"{lat}:{lat + 1}:{lon}:{lon + 1}{'-hd.sdf' if high_resolution else '.sdf'}"

    def _convert_hgt_to_sdf(self, tile: bytes, tile_name: str, high_resolution: bool = False) -> bytes:
        """
        Converts a .hgt.gz terrain tile (provided as bytes) to a SPLAT! .sdf or -hd.sdf file.

        This method checks if the converted .sdf or -hd.sdf file corresponding to the tile_name
        exists in the cache. If not, the method decompresses the tile, places it in a temporary
        directory, performs the conversion using the SPLAT! utility (srtm2sdf or srtm2sdf-hd),
        and caches the resulting .sdf file.

        Args:
            tile (bytes): The binary content of the .hgt.gz terrain tile.
            tile_name (str): The name of the terrain tile (e.g., N35W120.hgt.gz).
            high_resolution (bool): Whether to generate a high-resolution -hd.sdf file. Defaults to False.

        Returns:
            bytes: The binary content of the converted .sdf or -hd.sdf file.

        Raises:
            RuntimeError: If the conversion fails.
        """

        sdf_filename = Splat._hgt_filename_to_sdf_filename(tile_name, high_resolution)

        # Check cache for converted file
        if sdf_filename in self.tile_cache:
            logger.info(f"Cache hit: {sdf_filename} found in the local cache.")
            return self.tile_cache[sdf_filename]

        # Create temporary working directory
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # Decompress the tile into the temporary directory
                hgt_path = os.path.join(tmpdir, tile_name.replace(".gz", ""))
                logger.info(f"Decompressing {tile_name} into {hgt_path}.")
                with gzip.GzipFile(fileobj=io.BytesIO(tile)) as gz_file:
                    with open(hgt_path, "wb") as hgt_file:
                        hgt_file.write(gz_file.read())

                # Downsample to 3-arcsecond resolution if not in high-resolution mode
                if not high_resolution:
                    try:
                        logger.info(f"Downsampling {hgt_path} to 3-arcsecond resolution.")
                        with rasterio.open(hgt_path) as src:
                            # Apply a scaling factor to transform for 3-arcsecond resolution
                            transform = src.transform * src.transform.scale(3, 3)

                            # Resample data to 3-arcsecond resolution
                            data = src.read(
                                # 3-arcsecond SRTM tiles always have dimensions of 1201x1201 pixels.
                                out_shape=(
                                    src.count,  # Number of bands
                                    1201,   # Downsampled height
                                    1201,   # Downsampled width
                                ),
                                resampling=Resampling.average,
                            )

                            # Update metadata for the new dataset
                            meta = src.meta.copy()
                            meta.update(
                                {
                                    "transform": transform,
                                    "width": 1201,
                                    "height": 1201,
                                }
                            )

                        # Overwrite the temporary file with downsampled data
                        with rasterio.open(hgt_path, "w", **meta) as dst:
                            dst.write(data)

                        logger.info(f"Successfully downsampled {hgt_path}.")
                    except Exception as e:
                        logger.error(f"Failed to downsample {hgt_path}: {e}")
                        raise RuntimeError(f"Downsampling error for {hgt_path}: {e}")

                # Call srtm2sdf or srtm2sdf-hd in the temporary directory
                cmd = self.srtm2sdf_hd_binary if high_resolution else self.srtm2sdf_binary
                logger.info(f"Converting {hgt_path} to {sdf_filename} using {cmd}.")
                result = subprocess.run(
                    [cmd, "-d", "/dev/null", os.path.basename(tile_name.replace(".gz", ""))],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                logger.debug(f"srtm2sdf output:\n{result.stdout}")
                sdf_path = os.path.join(tmpdir, sdf_filename)

                # Ensure the .sdf file was created
                if not os.path.exists(sdf_path):
                    logger.error(f"Expected .sdf file not found: {sdf_path}")
                    raise RuntimeError(f"Failed to generate .sdf file: {sdf_path}")

                # Read and cache the .sdf file
                with open(sdf_path, "rb") as sdf_file:
                    sdf_data = sdf_file.read()
                self.tile_cache[sdf_filename] = sdf_data

                logger.info(f"Successfully converted and cached {sdf_filename}.")
                return sdf_data

            except subprocess.CalledProcessError as e:
                logger.error(f"Subprocess error during conversion of {tile_name}: {e}")
                logger.error(f"stderr: {e.stderr}")
                raise RuntimeError(f"Subprocess error during conversion of {tile_name}: {e}")

            except Exception as e:
                logger.error(f"Error during conversion of {tile_name} to {sdf_filename}: {e}")
                raise RuntimeError(f"Conversion error for {tile_name}: {e}")



if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    try:
        splat_service = Splat(
            splat_path="/Users/patrick/Dev/splat",  # Replace with the actual SPLAT! binary path
        )

        # Create a test coverage prediction request
        test_coverage_request = CoveragePredictionRequest(
            lat=51.062,
            lon=-114.16,
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
            rx_height=1.0,
            radius=50000.0,
            colormap="CMRmap",
            min_dbm=-130.0,
            max_dbm=-80.0,
            signal_threshold=-130.0,
            high_resolution=False,
        )

        # Execute coverage prediction
        logger.info("Starting SPLAT! coverage prediction...")
        result = splat_service.coverage_prediction(test_coverage_request)

        # Save GeoTIFF output for inspection
        output_path = "splat_output.tif"
        with open(output_path, "wb") as output_file:
            output_file.write(result)
        logger.info(f"GeoTIFF saved to: {output_path}")

    except Exception as e:
        logger.error(f"Error during SPLAT! test: {e}")
        raise
