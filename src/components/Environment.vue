<template>
    <form novalidate>
        <div class="row g-2">
            <div class="col-6">
                <label for="radio_climate" class="form-label">Radio Climate</label>
                <select v-model="environment.radio_climate" id="radio_climate" class="form-select form-select-sm" required>
                    <option value="equatorial">Equatorial</option>
                    <option value="continental_subtropical">Continental Subtropical</option>
                    <option value="maritime_subtropical">Maritime Subtropical</option>
                    <option value="desert">Desert</option>
                    <option value="continental_temperate">Continental Temperate</option>
                    <option value="maritime_temperate_land">Maritime Temperate (Land)</option>
                    <option value="maritime_temperate_sea">Maritime Temperate (Sea)</option>
                </select>
                <div class="invalid-feedback">Please select a radio climate.</div>
            </div>
            <div class="col-6">
                <label for="polarization" class="form-label">Polarization</label>
                <select v-model="environment.polarization" id="polarization" class="form-select form-select-sm" required>
                    <option value="horizontal">Horizontal</option>
                    <option value="vertical">Vertical</option>
                </select>
                <div class="invalid-feedback">Please select a polarization type.</div>
            </div>
            <div class="col-6">
                <label for="clutter_height" class="form-label">Clutter Height <br />(m)</label>
                <input v-model="environment.clutter_height" type="number" class="form-control form-control-sm" id="clutter_height" required min="0" step="0.1" />
                <div class="invalid-feedback">Height must be >= 0 (default: 1.0).</div>
            </div>
            <div class="col-6">
                <label for="ground_dielectric" class="form-label">Ground Dielectric (V/m)</label>
                <input v-model="environment.ground_dielectric" type="number" class="form-control form-control-sm" id="ground_dielectric" required min="1" step="0.1" />
                <div class="invalid-feedback">Dielectric constant must be >= 1 (default: 15.0).</div>
            </div>
            <div class="col-6">
                <label for="ground_conductivity" class="form-label">Ground Conductivity (S/m)</label>
                <input v-model="environment.ground_conductivity" type="number" class="form-control form-control-sm" id="ground_conductivity" required min="0" step="0.001" />
                <div class="invalid-feedback">Conductivity must be >= 0 (default: 0.005).</div>
            </div>
            <div class="col-6">
                <label for="atmosphere_bending" class="form-label">Atmospheric Bending (N-units)</label>
                <input v-model="environment.atmosphere_bending" type="number" class="form-control form-control-sm" id="atmosphere_bending" required min="0" step="0.1" />
                <div class="invalid-feedback">Bending constant must be >= 0 (default: 301.0).</div>
            </div>
        </div>
    </form>
</template>

<script setup lang="ts">
import { useStore } from '../store.ts'
const environment = useStore().splatParams.environment;
</script>
