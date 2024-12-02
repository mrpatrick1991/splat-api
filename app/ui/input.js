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
