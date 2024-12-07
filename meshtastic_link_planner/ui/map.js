const map = L.map("map", {
  zoomControl: false, // Disable the default zoom control
}).setView([51.102167, -114.098667], 10);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "© OpenStreetMap contributors",
}).addTo(map);

L.control.zoom({ position: "topleft" }).addTo(map);

var lc = L.control
  .locate({
    position: "topleft",
  })
  .addTo(map);
