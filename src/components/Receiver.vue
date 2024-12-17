
<template>
    <form novalidate>
        <div class="row g-2">
            <div class="col-6">
                <label for="rx_sensitivity" class="form-label">Sensitivity (dBm)</label>
                <input v-model="receiver.rx_sensitivity" type="number" class="form-control form-control-sm" id="rx_sensitivity" required step="1" min="-150" max="-30" />
            <div class="invalid-feedback">Please enter a valid sensitivity.</div>
            </div>
                <div class="col-6">
                <label for="rx_height" class="form-label">Height AGL (m)</label>
                <input v-model="receiver.rx_height" type="number" class="form-control form-control-sm" id="rx_height" required min="0" step="0.1" />
                <div class="invalid-feedback">Height must be a positive number.</div>
                </div>
            </div>
            <div class="row g-2 mt-2">
                <div class="col-6">
                <label for="rx_gain" class="form-label">Antenna Gain (dB)</label>
                <input v-model="receiver.rx_gain" type="number" class="form-control form-control-sm" id="rx_gain" required min="0" max="30" step="0.1" />
                <div class="invalid-feedback">Gain must be a positive number.</div>
            </div>
            <div class="col-6">
                <label for="rx_loss" class="form-label">Cable Loss (dB)</label>
                <input v-model="receiver.rx_loss" type="number" class="form-control form-control-sm" id="rx_loss" required min="0" max="100" step="0.1" />
                <div class="invalid-feedback">Loss must be a positive number.</div>
            </div>
        </div>
    </form>
</template>

<script setup lang="ts">
    import { useStore } from '../store.ts'
    const receiver = useStore().splatParams.receiver
</script>
