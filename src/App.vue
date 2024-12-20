<template>
  <div>
    <nav class="navbar navbar-dark bg-dark fixed-top">
      <div class="container-fluid">
        <a class="navbar-brand" href="#">
          <img src="/logo.svg" alt="Meshtastic Logo" width="30" height="30" class="d-inline">
          Meshtastic Site Planner
        </a>
        <button class="navbar-toggler" type="button" data-bs-toggle="offcanvas" data-bs-target="#offcanvasDarkNavbar" aria-controls="offcanvasDarkNavbar" aria-label="Toggle navigation">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="offcanvas offcanvas-end text-bg-dark show" tabindex="-1" id="offcanvasDarkNavbar" aria-labelledby="offcanvasDarkNavbarLabel" data-bs-backdrop="false">
          <div class="offcanvas-header">
            <h5 class="offcanvas-title" id="offcanvasDarkNavbarLabel">Site Parameters</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas" aria-label="Close"></button>
          </div>
          <div class="offcanvas-body">
            <ul class="navbar-nav">
              <li class="nav-item dropdown">
                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="true">Site / Transmitter</a>
                <ul class="dropdown-menu dropdown-menu-dark p-3 show">
                  <li>
                    <Transmitter />
                  </li>
                </ul>
              </li>
              <li class="nav-item dropdown">
                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="false">Receiver</a>
                <ul class="dropdown-menu dropdown-menu-dark p-3">
                  <li>
                    <Receiver />
                  </li>
                </ul>
              </li>
              <li class="nav-item dropdown">
                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="false">Environment</a>
                <ul class="dropdown-menu dropdown-menu-dark p-3">
                  <li>
                    <Environment />
                  </li>
                </ul>
              </li>
              <li class="nav-item dropdown">
                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="false">Simulation Options</a>
                <ul class="dropdown-menu dropdown-menu-dark p-3">
                  <li>
                    <Simulation />
                  </li>
                </ul>
              </li>
              <li class="nav-item dropdown">
              <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="true">
                Display
              </a>
            <ul class="dropdown-menu dropdown-menu-dark p-3 show">
            <li>
              <Display />
            </li>
            </ul>
            </li>
            </ul>
            <div class="mt-3 d-flex gap-2">
              <button :disabled="store.simulationState === 'running'" @click="store.runSimulation" type="button" class="btn btn-success btn-sm" id="runSimulation">
                <span :class="{ 'd-none': store.simulationState !== 'running' }" class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                <span class="button-text">{{ buttonText() }}</span>
              </button>
            </div>
            <ul class="list-group mt-3">
              <li class="list-group-item d-flex justify-content-between align-items-center" v-for="(site, index) in store.$state.localSites" :key="site.taskId">
                <span>{{ site.params.transmitter.name }}</span>
                <button type="button" @click="store.removeSite(index)" class="btn-close" aria-label="Close"></button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </nav>
    <div id="map" ref="map">
    </div>
  </div>
</template>

<script setup lang="ts">
import "leaflet/dist/leaflet.css"
import "bootstrap/dist/css/bootstrap.min.css"
import "bootstrap/dist/js/bootstrap.bundle.min.js"
import Transmitter from "./components/Transmitter.vue"
import Receiver from "./components/Receiver.vue"
import Environment from "./components/Environment.vue"
import Simulation from "./components/Simulation.vue"
import Display from "./components/Display.vue"

import { useStore } from './store.ts'
const store = useStore()
const buttonText = () => {
  if ('running' === store.simulationState) {
    return 'Running'
  } else if ('failed' === store.simulationState) {
    return 'Failed'
  } else {
    return 'Run Simulation'
  }
}
</script>

<style>
.leaflet-div-icon {
  background: transparent;
  border: none !important;
}
/* .leaflet-layer,
.leaflet-control-zoom-in,
.leaflet-control-zoom-out,
.leaflet-control-attribution {
  filter: invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%);
} */

</style>
