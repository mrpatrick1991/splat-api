import { defineStore } from 'pinia';
import { useLocalStorage } from '@vueuse/core';
import { randanimal, randanimalSync } from 'randanimal';
import L from 'leaflet';
import 'leaflet.locatecontrol';
import GeoRasterLayer from 'georaster-layer-for-leaflet';
import parseGeoraster from 'georaster';
import { type Site, type SplatParams } from './types.ts';
import { cloneObject } from './utils.ts';

const useStore = defineStore('store', {
  state() {
    return {
      map: undefined as undefined | L.Map,
      currentMarker: undefined as undefined | L.Marker,
      localSites: useLocalStorage('localSites', [] as Site[]),
      splatParams: <SplatParams>{
        transmitter: {
          name: randanimalSync(),
          tx_lat: 51.102167,
          tx_lon: -114.098667,
          tx_power: 0.1,
          tx_freq: 907.0,
          tx_height: 2.0,
          tx_gain: 2.0
        },
        receiver: {
          rx_sensitivity: -130.0,
          rx_height: 1.0,
          rx_gain: 2.0,
          rx_loss: 2.0
        },
        environment: {
          radio_climate: 'continental_temperate',
          polarization: 'vertical',
          clutter_height: 1.0,
          ground_dielectric: 15.0,
          ground_conductivity: 0.005,
          atmosphere_bending: 301.0
        },
        simulation: {
          situation_fraction: 90.0,
          time_fraction: 90.0,
          simulation_extent: 10.0,
          high_resolution: false
        },
        display: {
          color_scale: 'plasma',
          min_dbm: -130.0,
          max_dbm: -80.0,
          overlay_transparency: 50
        },
      }
    }
  },
  actions: {
    setTxCoords(lat: number, lon: number) {
      this.splatParams.transmitter.tx_lat = lat
      this.splatParams.transmitter.tx_lon = lon
    },
    removeSite(index: number) {
      console.log(this.map.layers)
      this.localSites.splice(index, 1)
      this.map.eachLayer((layer: L.Layer) => {
        if (layer instanceof GeoRasterLayer) {
          this.map.removeLayer(layer);
        }
      });
      this.redrawSites()
    },
    redrawSites() {
      this.localSites.forEach((site: Site) => {
        // Add the new layer to the map
        const rasterLayer = new GeoRasterLayer({
          georaster: {...site}.raster,
          opacity: 0.7,
          noDataValue: 255,
        });
        rasterLayer.addTo(this.map);
      });
      this.map.set
    },
    initMap() {     
      this.map = L.map("map", {
        // center: [51.102167, -114.098667],
        zoom: 10,
        zoomControl: false,
      });
      const position: [number, number] = [this.splatParams.transmitter.tx_lat, this.splatParams.transmitter.tx_lon];
      this.map.setView(position, 10);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap contributors",
      }).addTo(this.map);
      
      L.control.zoom({ position: "topleft" }).addTo(this.map);
      
      // L.control
      //   .locate({
      //     position: "topleft",
      //   })
      //   .addTo(this.map);
      this.currentMarker = L.marker(position).addTo(this.map); // Variable to hold the current marker

      this.redrawSites();
    },
    async runSimulation() {
      console.log('Simulation running...')
      try {
        // Collect input values
        const payload = {
          // Transmitter parameters
          lat: this.splatParams.transmitter.tx_lat,
          lon: this.splatParams.transmitter.tx_lon,
          tx_height: this.splatParams.transmitter.tx_height,
          tx_power: 10 * Math.log10(this.splatParams.transmitter.tx_power) + 30,
          tx_gain: this.splatParams.transmitter.tx_gain,
          frequency_mhz: this.splatParams.transmitter.tx_freq,

          // Receiver parameters
          rx_height: this.splatParams.receiver.rx_height,
          rx_gain: this.splatParams.receiver.rx_gain,
          signal_threshold: this.splatParams.receiver.rx_sensitivity,
          system_loss: this.splatParams.receiver.rx_loss,

          // Environment parameters
          clutter_height: this.splatParams.environment.clutter_height,
          ground_dielectric: this.splatParams.environment.ground_dielectric,
          ground_conductivity: this.splatParams.environment.ground_conductivity,
          atmosphere_bending: this.splatParams.environment.atmosphere_bending,
          radio_climate: this.splatParams.environment.radio_climate,
          polarization: this.splatParams.environment.polarization,

          // Simulation parameters
          radius: this.splatParams.simulation.simulation_extent * 1000,
          situation_fraction: this.splatParams.simulation.situation_fraction,
          time_fraction: this.splatParams.simulation.time_fraction,
          high_resolution: this.splatParams.simulation.high_resolution,

          // Display parameters
          colormap: this.splatParams.display.color_scale,
          min_dbm: this.splatParams.display.min_dbm,
          max_dbm: this.splatParams.display.max_dbm,
        };
    
        console.log("Payload:", payload);
    
        // Send the request to the backend's /predict endpoint
        const predictResponse = await fetch("/predict", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
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

        // FIXME: remove DOM manipulation and just bind to states
        // display spinner to show task is running
        const runButton = document.getElementById("runSimulation") as HTMLButtonElement;
        const spinner = runButton.querySelector(".spinner-border") as HTMLElement;
        const buttonText = runButton!.querySelector(".button-text") as HTMLElement;

        // Show spinner and update text
        spinner.style.display = "inline-block";
        buttonText.textContent = "Running...";
        runButton.disabled = true; // Disable the button

        // Poll for task status and result
        const pollInterval = 1000; // 1 seconds
        const pollStatus = async () => {
          const statusResponse = await fetch(
            `/status/${taskId}`,
          );
          if (!statusResponse.ok) {
            throw new Error("Failed to fetch task status.");
          }
    
          const statusData = await statusResponse.json();
          console.log("Task status:", statusData);
    
          if (statusData.status === "completed") {
            console.log("Simulation completed! Adding result to the map...");

            spinner.style.display = "none";
            buttonText.textContent = "Run Simulation";
            runButton.disabled = false; // Re-enable the button

            // Fetch the GeoTIFF data
            const resultResponse = await fetch(
              `/result/${taskId}`,
            );
            if (!resultResponse.ok) {
              throw new Error("Failed to fetch simulation result.");
            }
            else
            {
              const arrayBuffer = await resultResponse.arrayBuffer();
              const geoRaster = await parseGeoraster(arrayBuffer);
              this.localSites.push({
                params: cloneObject(this.splatParams),
                taskId,
                raster: geoRaster
              });
              this.splatParams.transmitter.name = await randanimal();
              this.redrawSites();
            }
          }
          else if (statusData.status === "failed") {
            console.error("Simulation failed!");
            spinner.style.display = "none"; // Hide spinner
            runButton.disabled = false; // Re-enable the button
          } else {
            setTimeout(pollStatus, pollInterval); // Retry after interval
          }
        };
    
        pollStatus(); // Start polling
      } catch (error) {
        console.error("Error:", error);
      }
    }
  }
});

export { useStore }