import logging
from models.coverage import CoveragePredictRequest
from splat import coverage  # Replace 'your_module_name' with the actual module name

def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Create a test CoveragePredictRequest object
    test_request = CoveragePredictRequest(
        lat=51.7749,  # Example latitude
        lon=114.4194,  # Example longitude
        tx_power=20.0,  # Example transmitter power in dBm
        tx_height=2.0,  # Example transmitter height above ground in meters
        rxh=1.0,  # Example receiver height above ground in meters
        tx_gain=2.0,  # Example transmitter antenna gain in dB
        rx_gain=2.0,  # Example receiver antenna gain in dB
        radius=20000.0,  # Example model maximum range in meters
        signal_threshold=-130.0,  # Example signal cutoff in dBm
        clutter_height=0.0,  # Example ground clutter height in meters
        frequency_mhz=915.0,  # Example operating frequency in MHz
        ground_dielectric=15.0,  # Example ground dielectric constant
        ground_conductivity=0.005,  # Example ground conductivity in S/m
        atmosphere_bending=301.0,  # Example atmospheric bending constant
        system_loss=0.0,  # Example system loss in dB
        radio_climate="continental_temperate",  # Example radio climate
        polarization="vertical",  # Example signal polarization
    )

    # Set the tile directory (ensure this path is valid in your environment)
    tile_dir = "/Volumes/Gandalf/datasets/sdf/data/sdf"

    # Call the coverage function
    try:
        result = coverage(test_request, tile_dir)
        with open("out.ppm","wb") as f:
            f.write(result["ppm_file"])
            f.close()


    except Exception as e:
        logging.error(f"Error while running coverage: {e}")

if __name__ == "__main__":
    main()