import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import Transmitter from './components/Transmitter.vue';
import Receiver from './components/Receiver.vue';
import Environment from './components/Environment.vue';
import Simulation from './components/Simulation.vue';
import Display from './components/Display.vue';
import { useStore } from './store/store.js';

const pinia = createPinia();
const app = createApp(App);

app.use(pinia);
app.component('Transmitter', Transmitter);
app.component('Receiver', Receiver);
app.component('Environment', Environment);
app.component('Simulation', Simulation);
app.component('Display', Display);

app.mount('#app');
