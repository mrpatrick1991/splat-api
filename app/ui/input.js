document.addEventListener("DOMContentLoaded", () => {
  // Initialize Bootstrap Popover
  const popoverTrigger = document.getElementById("setWithMap");
  const popover = new bootstrap.Popover(popoverTrigger, {
    trigger: "manual", // Popover will only appear when triggered programmatically
  });

  let lat = parseFloat(document.getElementById("tx_lat").value);
  let lng = parseFloat(document.getElementById("tx_lon").value);
  let currentMarker = L.marker([lat, lng]).addTo(map); // Variable to hold the current marker

  // Event Listener for "Set with Map" Button
  popoverTrigger.addEventListener("click", () => {
    popover.show(); // Show the popover
    map.once("click", function (e) {
      let { lat, lng } = e.latlng; // Get clicked location coordinates
      lng = ((((lng + 180) % 360) + 360) % 360) - 180;
      document.getElementById("tx_lat").value = lat.toFixed(6); // Update Latitude
      document.getElementById("tx_lon").value = lng.toFixed(6); // Update Longitude

      // Remove the existing marker if it exists
      if (currentMarker) {
        map.removeLayer(currentMarker);
      }

      // Add a new marker at the clicked location
      currentMarker = L.marker([lat, lng]).addTo(map);

      popover.hide(); // Hide the popover
    });
  });

  // Event Listener for "Center on Coordinates" Button
  document.querySelector(".btn-secondary").addEventListener("click", () => {
    const lat = parseFloat(document.getElementById("tx_lat").value);
    const lon = parseFloat(document.getElementById("tx_lon").value);

    if (!isNaN(lat) && !isNaN(lon)) {
      map.setView([lat, lon], map.getZoom()); // Center map on the coordinates
    } else {
      alert("Please enter valid Latitude and Longitude values.");
    }
  });
});

document.getElementById('runSimulation').addEventListener('click', async () => {
  try {
    // Collect input values
    const payload = {
      lat: parseFloat(document.getElementById('tx_lat').value),
      lon: parseFloat(document.getElementById('tx_lon').value),
      tx_height: parseFloat(document.getElementById('tx_height').value),
      tx_power: parseFloat(document.getElementById('tx_power').value),
      tx_gain: parseFloat(document.getElementById('tx_gain').value),
      frequency_mhz: parseFloat(document.getElementById('tx_freq').value),
      rx_height: parseFloat(document.getElementById('rx_height').value),
      rx_gain: parseFloat(document.getElementById('rx_gain').value),
      signal_threshold: parseFloat(document.getElementById('rx_sensitivity').value),
      clutter_height: parseFloat(document.getElementById('clutter_height').value),
      ground_dielectric: parseFloat(document.getElementById('ground_dielectric').value),
      ground_conductivity: parseFloat(document.getElementById('ground_conductivity').value),
      atmosphere_bending: parseFloat(document.getElementById('atmosphere_bending').value),
      radius: parseFloat(document.getElementById('simulation_extent').value),
      system_loss: 0.0, // Default value; add input if needed
      radio_climate: document.getElementById('radio_climate').value,
      polarization: document.getElementById('polarization').value,
      situation_fraction: parseFloat(document.getElementById('situation_fraction').value),
      time_fraction: parseFloat(document.getElementById('time_fraction').value),
      colormap: document.getElementById('color_scale').value,
      min_dbm: parseFloat(document.getElementById('min_dbm').value),
      max_dbm: parseFloat(document.getElementById('max_dbm').value),
      high_resolution: document.getElementById('high_resolution').checked,
    };

    console.log('Payload:', payload); // Debugging the payload

    // Send the request to the backend's /predict endpoint
    const predictResponse = await fetch('http://localhost:8000/predict', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!predictResponse.ok) {
      const errorDetails = await predictResponse.text();
      throw new Error(`Failed to start prediction: ${errorDetails}`);
    }

    const predictData = await predictResponse.json();
    const taskId = predictData.task_id;

    console.log(`Prediction started with task ID: ${taskId}`);

    // Polling logic remains the same...
  } catch (error) {
    console.error('Error:', error);
    alert(`An error occurred: ${error.message}`);
  }
});
