    def _geotiff_to_h3_geojson(self, geotiff_path: str, h3_resolution: int):
        """
        Converts a GeoTIFF file to an H3-based GeoJSON with automatic downsampling.

        Args:
            geotiff_path (str): Path to the input GeoTIFF file.
            h3_resolution (int): H3 resolution for sampling.

        Returns:
            dict: GeoJSON FeatureCollection.
        """
        logger.info("Starting GeoTIFF to H3 GeoJSON conversion.")
        logger.debug(f"GeoTIFF path: {geotiff_path}, H3 resolution: {h3_resolution}")

        with rasterio.open(geotiff_path) as src:
            # Calculate geo_area in square meters using CRS
            bounds = src.bounds
            if src.crs.is_geographic:
                # Reproject bounds to meters using EPSG:3857 (Web Mercator)
                left, bottom = rasterio.warp.transform(src.crs, 'EPSG:3857', [bounds.left], [bounds.bottom])
                right, top = rasterio.warp.transform(src.crs, 'EPSG:3857', [bounds.right], [bounds.top])
                geo_area = (right[0] - left[0]) * (top[0] - bottom[0])
            else:
                # CRS is already in meters
                geo_area = (bounds.right - bounds.left) * (bounds.top - bounds.bottom)

            logger.debug(f"GeoTIFF geographic bounds: {bounds}")
            logger.debug(f"Calculated GeoTIFF area in square meters: {geo_area}")

            # Calculate pixel area in square meters
            pixel_area = geo_area / (src.width * src.height)
            logger.debug(f"Pixel area in square meters: {pixel_area}")

            # Determine scaling factor for downsampling
            h3_cell_area = h3.average_hexagon_area(h3_resolution, unit="m^2")
            scaling_factor = (h3_cell_area / pixel_area) ** 0.5
            target_width = max(1, int(src.width / scaling_factor))
            target_height = max(1, int(src.height / scaling_factor))
            logger.info(
                f"Calculated downsampling dimensions: target_width={target_width}, target_height={target_height}"
            )

            # Downsample the data
            data = src.read(
                1,
                out_shape=(1, target_height, target_width),
                resampling=Resampling.average,
            )

            # Update the transform for downsampled data
            transform = src.transform * src.transform.scale(
                (src.width / target_width), (src.height / target_height)
            )

        logger.info("Processing pixels to calculate H3 indices.")

        h3_data = {}
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                pixel_value = data[i, j]
                if np.isnan(pixel_value) or pixel_value == 255:  # Skip nodata values and SPLAT!'s "255"
                    continue

                lon, lat = rasterio.transform.xy(transform, i, j, offset="center")
                h3_index = h3.latlng_to_cell(lat, lon, h3_resolution)

                if h3_index not in h3_data:
                    h3_data[h3_index] = []
                h3_data[h3_index].append(pixel_value)

        # Aggregate values for each H3 cell and filter out empty cells
        h3_aggregated = {h: np.mean(v) for h, v in h3_data.items() if len(v) > 0}

        # Create GeoJSON features
        features = []
        for h3_index, value in h3_aggregated.items():
            if not np.isnan(value):  # Ensure no invalid values are included
                h3_boundary = [
                    (lng, lat) for lat, lng in h3.cell_to_boundary(h3_index)
                ]  # GeoJSON-friendly order
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [h3_boundary],
                    },
                    "properties": {
                        "h3_index": h3_index,
                        "dBm": value,
                    },
                }
                features.append(feature)

        logger.info(f"Created {len(features)} GeoJSON features with valid data.")
        return {
            "type": "FeatureCollection",
            "features": features,
        }


                # Optionally save H3 GeoJSON
        if args.output_h3:
            geojson_path = args.output_tiff.replace(".tiff", ".geojson")
            with open(geojson_path, "w") as geojson_file:
                json.dump(result["h3_geojson"], geojson_file, indent=4)
            logger.info(f"H3 GeoJSON saved to {geojson_path}")

                output_h3: bool = Field(
        False,
        description="Return the coverage map as a H3-based GeoJSON (default: False).",
    )
    h3_resolution: int = Field(
        8,
        description="H3 resolution for the H3-based GeoJson (default: 8).",
    )
    parser.add_argument(
        "--output_h3",
        action="store_true",
        help="If specified, generate H3-based GeoJSON output.",
    )                # Optionally generate H3 GeoJSON
                if request.output_h3:
                    logger.info(f"Generating H3 GeoJSON at resolution {request.h3_resolution}")
                    output_geojson = self._geotiff_to_h3_geojson(
                        output_tiff_path, request.h3_resolution
                    )
                    outputs["h3_geojson"] = output_geojson
                    logger.info("H3 GeoJSON generation completed.")


                    import os
import tempfile
import argparse
import subprocess
import xml.etree.ElementTree as ET  # For parsing KML files
from typing import Literal
from osgeo import gdal  # For GeoTIFF handling
from PIL import Image  # For handling PPM files
import numpy as np  # For array manipulations
import matplotlib.pyplot as plt  # For creating color maps
from scipy.ndimage import gaussian_filter

from models.coverage import CoveragePredictRequest


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
        if not os.path.exists(path):
            raise FileNotFoundError(f"Directory does not exist: {path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Directory is not writable: {path}")

        qth_path = os.path.join(path, f"{name}.qth")

        try:
            with open(qth_path, "w") as qth_file:
                qth_file.write(f"{name}\n")
                qth_file.write(f"{latitude:.6f}\n")
                qth_file.write(
                    f"{abs(longitude) if longitude < 0 else 360-longitude:.6f}\n" # SPLAT! expects west longitude as a positive number.
                )
                qth_file.write(f"{elevation:.2f}\n")
        except IOError as e:
            raise IOError(f"Failed to write .qth file at {qth_path}: {e}")

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
        # Check if the directory exists and is writable
        if not os.path.exists(path):
            raise FileNotFoundError(f"Directory does not exist: {path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Directory is not writable: {path}")

        lrp_path = os.path.join(path, "splat.lrp")

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

        # Validate mappings
        if radio_climate not in climate_map:
            raise ValueError(f"Invalid radio climate: {radio_climate}")
        if polarization not in polarization_map:
            raise ValueError(f"Invalid polarization: {polarization}")

        # Calculate ERP in Watts
        erp_watts = 10 ** ((tx_power + tx_gain - system_loss - 30) / 10)

        try:
            # Write the .lrp file
            with open(lrp_path, "w") as lrp_file:
                lrp_file.write(
                    f"{ground_dielectric:.3f}  ; Earth Dielectric Constant\n"
                )
                lrp_file.write(f"{ground_conductivity:.6f}  ; Earth Conductivity\n")
                lrp_file.write(
                    f"{atmosphere_bending:.3f}  ; Atmospheric Bending Constant\n"
                )
                lrp_file.write(f"{frequency_mhz:.3f}  ; Frequency in MHz\n")
                lrp_file.write(f"{climate_map[radio_climate]}  ; Radio Climate\n")
                lrp_file.write(f"{polarization_map[polarization]}  ; Polarization\n")
                lrp_file.write(
                    f"{situation_fraction / 100.0:.2f} ; Fraction of situations\n"
                )
                lrp_file.write(f"{time_fraction / 100.0:.2f}  ; Fraction of time\n")
                lrp_file.write(f"{erp_watts:.2f}  ; ERP in Watts\n")
        except IOError as e:
            raise IOError(f"Failed to write .lrp file at {lrp_path}: {e}")

    def _create_dcf(self, path: str, colormap: str, min_dbm: int, max_dbm: int):
        """
        Create a SPLAT! .dcf file to control output colors using a matplotlib colormap.

        Args:
            path (str): The directory path to save the .dcf file.
            colormap (str): The name of the matplotlib colormap (e.g., 'viridis', 'plasma', 'jet').
            min_dbm (int): The minimum dBm value for the range.
            max_dbm (int): The maximum dBm value for the range.

        Raises:
            ValueError: If `min_dbm` is greater than or equal to `max_dbm`.
        """

        dcf_path = os.path.join(path, "splat.dcf")

        if min_dbm >= max_dbm:
            raise ValueError("min_dbm must be less than max_dbm")

        # Create an evenly spaced range of dBm values (up to 32 levels as per SPLAT! limits) in descending order
        dbm_values = np.linspace(max_dbm, min_dbm, 32)

        # Get the colormap
        cmap = plt.get_cmap(colormap)

        # Normalize the dBm range to [0, 1] for the colormap
        norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)

        # Map the dBm values to RGB colors
        rgb_colors = (cmap(norm(dbm_values))[:, :3] * 255).astype(
            int
        )  # Convert to 0-255 range

        # Write the .dcf file
        try:
            with open(dcf_path, "w") as dcf_file:
                dcf_file.write(
                    "; SPLAT! Auto-generated DBM Signal Level Color Definition\n"
                )
                dcf_file.write(";\n")
                dcf_file.write(
                    "; Format for the parameters held in this file is as follows:\n"
                )
                dcf_file.write(";    dBm: red, green, blue\n")
                dcf_file.write(";\n")
                dcf_file.write(
                    "; A total of 32 contour regions may be defined in this file.\n;\n"
                )

                # Write entries in descending order
                for dbm, (r, g, b) in zip(dbm_values, rgb_colors):
                    dcf_file.write(f"{int(dbm):+4d}: {r:3d}, {g:3d}, {b:3d}\n")

        except IOError as e:
            raise IOError(f"Failed to write .dcf file at {dcf_path}: {e}")

        # Debugging: Print the written file to the console for verification
        with open(dcf_path, "r") as dcf_file:
            print(dcf_file.read())

    def _ppm_kml_to_geotiff(self, ppm_file: str, kml_file: str, output_tiff: str, blur_sigma: float = 1.0):
        """
        Convert a SPLAT-generated .ppm image to a GeoTIFF using geospatial bounds from the .kml file.

        Args:
            ppm_file (str): Path to the .ppm file generated by SPLAT.
            kml_file (str): Path to the .kml file containing the geospatial bounds generated by SPLAT.
            output_tiff (str): Path where the output GeoTIFF will be saved.
            blur_sigma (float): Standard deviation for Gaussian blur applied to the output GeoTIFF image.
        Raises:
            ValueError: If the .kml file does not contain valid geospatial bounds.
            FileNotFoundError: If the .ppm or .kml file cannot be found or read.
        """

        def bbox_from_kml(kml_file):
            """Extract bounding box (north, south, east, west) from a SPLAT KML file."""
            try:
                tree = ET.parse(kml_file)
            except FileNotFoundError:
                raise FileNotFoundError(f"KML file not found: {kml_file}")
            except ET.ParseError:
                raise ValueError(f"Failed to parse KML file: {kml_file}")

            root = tree.getroot()
            namespace = {"kml": "http://earth.google.com/kml/2.1"}
            box = root.find(".//kml:LatLonBox", namespace)
            if not box:
                raise ValueError("Could not find LatLonBox in the KML file")
            try:
                north = float(box.find("kml:north", namespace).text)
                south = float(box.find("kml:south", namespace).text)
                east = float(box.find("kml:east", namespace).text)
                west = float(box.find("kml:west", namespace).text)
            except (TypeError, AttributeError):
                raise ValueError("Invalid geospatial bounds in the KML file")
            return north, south, east, west

        # Extract geospatial bounds from KML
        try:
            north, south, east, west = bbox_from_kml(kml_file)
        except Exception as e:
            raise ValueError(f"Error extracting bounding box from KML: {e}")

        # Read the .ppm file and extract dimensions and color data
        try:
            with Image.open(ppm_file) as img:
                width, height = img.size
                img = img.convert("RGB")  # Ensure image is in RGB mode
                img_array = np.array(img)  # Convert to NumPy array for manipulation

                # Apply Gaussian blur to each channel
                blurred_img_array = np.empty_like(img_array)
                for i in range(3):  # RGB channels
                    blurred_img_array[:, :, i] = gaussian_filter(img_array[:, :, i], sigma=blur_sigma)
                img_array = blurred_img_array

        except FileNotFoundError:
            raise FileNotFoundError(f"PPM file not found: {ppm_file}")
        except Exception as e:
            raise ValueError(f"Error reading PPM file: {e}")

        # Define geotransformation matrix for GeoTIFF
        geotransform = [
            west,  # Top-left x (longitude of the left side)
            (east - west) / width,  # Pixel width
            0,  # Rotation (0 if North is up)
            north,  # Top-left y (latitude of the top side)
            0,  # Rotation (0 if North is up)
            (south - north) / height,  # Pixel height (negative if North is up)
        ]

        # Initialize GDAL GeoTIFF driver and create dataset
        try:
            driver = gdal.GetDriverByName("GTiff")
            dataset = driver.Create(
                output_tiff, width, height, 3, gdal.GDT_Byte
            )  # 3 bands for RGB
            if not dataset:
                raise RuntimeError(f"Failed to create GeoTIFF file at {output_tiff}")
        except Exception as e:
            raise RuntimeError(f"GDAL initialization or GeoTIFF creation failed: {e}")

        try:
            # Set geotransformation and projection
            dataset.SetGeoTransform(geotransform)
            dataset.SetProjection("EPSG:4326")  # WGS 84

            # Write the RGB bands
            dataset.GetRasterBand(1).WriteArray(img_array[:, :, 0])  # Red channel
            dataset.GetRasterBand(2).WriteArray(img_array[:, :, 1])  # Green channel
            dataset.GetRasterBand(3).WriteArray(img_array[:, :, 2])  # Blue channel

            # Flush and close the dataset
            dataset.FlushCache()
            dataset = None

        except Exception as e:
            raise RuntimeError(f"Error writing data to GeoTIFF: {e}")

    def coverage_prediction(self, request: CoveragePredictRequest):
        """
        Execute a SPLAT! coverage prediction using the provided CoveragePredictRequest.

        Args:
            request (CoveragePredictRequest): The coverage prediction request object.

        Returns:
            dict: A dictionary containing the contents of output files and logs.

        Raises:
            RuntimeError: If SPLAT! fails to execute.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # Create required input files
                self._create_qth(
                    path=tmpdir,
                    name="tx",
                    latitude=request.lat,
                    longitude=request.lon,
                    elevation=request.tx_height,
                )
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
                self._create_dcf(
                    path=tmpdir,
                    colormap=request.colormap,
                    min_dbm=request.min_dbm,
                    max_dbm=request.max_dbm
                )

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

                # Run SPLAT!
                result = subprocess.run(
                    command,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    raise RuntimeError(
                        f"SPLAT! execution failed with return code {result.returncode}\n"
                        f"Stdout: {result.stdout}\nStderr: {result.stderr}"
                    )

                # Convert results to GeoTIFF
                output_tiff = os.path.join(tmpdir, "output.tiff")
                self._ppm_kml_to_geotiff(output_ppm, output_kml, output_tiff,request.blur_sigma)

                with open(output_tiff, "rb") as tiff_file:
                    tiff_bytes = tiff_file.read()

                # Return output files and logs
                return {
                    "geotiff": tiff_bytes,
                    "log_stdout": result.stdout,
                    "log_stderr": result.stderr,
                }
            except Exception as e:
                raise RuntimeError(f"Error during coverage prediction: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test SPLAT! Coverage Prediction")
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
    args = parser.parse_args()

    # Test CoveragePredictRequest
    test_request = CoveragePredictRequest(
        lat=51.08648106432428,  # Example latitude
        lon=-114.12951032280874,  # Example longitude
        tx_height=20.0,  # Transmitter height in meters
        ground_dielectric=15.0,  # Example dielectric constant
        ground_conductivity=0.005,  # Example ground conductivity
        atmosphere_bending=301.0,  # Atmospheric bending constant
        frequency_mhz=905.0,  # Example frequency in MHz
        radio_climate="continental_temperate",  # Example climate
        polarization="vertical",  # Vertical polarization
        situation_fraction=50.0,  # Fraction of situations (percentage)
        time_fraction=90.0,  # Fraction of time (percentage)
        tx_power=20.0,  # Transmitter power in dBm
        tx_gain=2.0,  # Transmitter antenna gain in dB
        system_loss=2.0,  # System losses in dB
        rxh=1.0,  # Receiver height in meters
        radius=20000.0,  # Coverage radius in meters
        signal_threshold=-130.0,  # Receiver sensitivity threshold in dBm,
        colormap="viridis",
        min_dbm=-130,
        max_dbm=-90,
        blur_sigma=0.0
    )

    try:
        splat = Splat(splat_path=args.splat_path, tile_dir=args.tile_dir)
        result = splat.coverage_prediction(test_request)

        # Print the logs
        print("SPLAT! Stdout:", result["log_stdout"])
        print("SPLAT! Stderr:", result["log_stderr"])

        # Save the GeoTIFF for verification
        with open(args.output_tiff, "wb") as f:
            f.write(result["geotiff"])
        print(f"GeoTIFF saved to {args.output_tiff}")

    except Exception as e:
        print("An error occurred during the test:", str(e))





                # Debugging: Print the written file to the console for verification
        with open(dcf_path, "r") as dcf_file:
            print(dcf_file.read())
