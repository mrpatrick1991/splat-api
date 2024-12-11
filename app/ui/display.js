import { useStore } from "./store.js";
const { watch, onMounted } = Vue;

export default {
    setup() {
        const display = useStore().splatParams.display;

        const renderColorbar = async () => {
            try {
                const response = await fetch("http://127.0.0.1:8080/colorbar", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        colormap: display.color_scale,
                        min_dbm: display.min_dbm,
                        max_dbm: display.max_dbm,
                    }),
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                const colorbar = data.colorbar;

                const canvas = document.getElementById("colorbar");
                if (!canvas) {
                    throw new Error("Canvas element not found");
                }

                const ctx = canvas.getContext("2d");
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                for (let i = 0; i < colorbar.length; i++) {
                    const [r, g, b] = colorbar[i];
                    ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
                    ctx.fillRect(i, 0, 1, canvas.height);
                }
            } catch (error) {
                console.error("Error in renderColorbar:", error);
            }
        };

        // Debug watched values
        watch(
            () => [display.color_scale, display.min_dbm, display.max_dbm],
            (newValues, oldValues) => {
                console.log("Values changed:", { newValues, oldValues });
                renderColorbar();
            },
            { immediate: true } // Ensure the function is triggered initially
        );

        // Trigger renderColorbar when the component mounts
        onMounted(() => {
            renderColorbar();
        });

        return { display, renderColorbar };
    },
    template: `
       <form novalidate>
    <div class="row g-2">
        <div class="col-6">
            <label for="min_dbm" class="form-label">Minimum dBm</label>
            <input v-model="display.min_dbm" type="number" class="form-control form-control-sm" id="min_dbm" required step="0.1" />
            <div class="invalid-feedback">Minimum dBm must be provided (default: -130.0).</div>
        </div>
        <div class="col-6">
            <label for="max_dbm" class="form-label">Maximum dBm</label>
            <input v-model="display.max_dbm" type="number" class="form-control form-control-sm" id="max_dbm" required step="0.1" />
            <div class="invalid-feedback">Maximum dBm must be provided (default: -30.0).</div>
        </div>
    </div>
    <div class="row g-2 mt-2">
        <div class="col-6">
            <label for="color_scale" class="form-label">Color Scale</label>
            <select v-model="display.color_scale" id="color_scale" class="form-select form-select-sm" required>
                <option value="plasma" selected>Plasma</option>
                <option value="CMRmap">CMR map</option>
                <option value="cool">Cool</option>
                <option value="rainbow">Rainbow</option>
                <option value="viridis">Viridis</option>
                <option value="turbo">Turbo</option>
                <option value="cividis">Cividis</option>
                <option value="jet">Jet</option>
            </select>
            <div class="invalid-feedback">Please select a color scale.</div>
        </div>
        <div class="col-6">
            <label for="overlay_transparency" class="form-label">Transparency (%)</label>
            <input v-model="display.overlay_transparency" type="number" class="form-control form-control-sm" id="overlay_transparency" required min="0" max="100" step="1" />
            <div class="invalid-feedback">Transparency must be between 0 and 100 (default: 50).</div>
        </div>
    </div>
    <div class="mt-3 text-center">
        <!-- Colorbar and Labels -->
        <div>
            <canvas id="colorbar" width="256" height="30" style="border: 1px solid #ccc; display: block; margin: 0 auto;"></canvas>
        </div>
        <div class="d-flex justify-content-between mt-1">
            <!-- Minimum dBm Label -->
            <span class="badge bg-primary">{{ display.min_dbm }} dBm</span>
            <!-- Maximum dBm Label -->
            <span class="badge bg-primary">{{ display.max_dbm }} dBm</span>
        </div>
    </div>
</form>
`
};
