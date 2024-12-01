document.addEventListener("DOMContentLoaded", () => {
  // Initialize Bootstrap Popover
  const popoverTrigger = document.getElementById("setWithMap");
  const popover = new bootstrap.Popover(popoverTrigger, {
    trigger: "manual", // Popover will only appear when triggered programmatically
  });

  // Event Listener for "Set with Map" Button
  popoverTrigger.addEventListener("click", () => {
    popover.show(); // Show the popover
    map.once("click", function (e) {
      const { lat, lng } = e.latlng; // Get clicked location coordinates
      document.getElementById("tx_lat").value = lat.toFixed(6); // Update Latitude
      document.getElementById("tx_lon").value = lng.toFixed(6); // Update Longitude

      // Place a marker at the clicked location
      L.marker([lat, lng]).addTo(map);

      popover.hide(); // Hide the popover
    });
  });
});