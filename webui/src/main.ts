import { createApp } from "vue";
import ElementPlus from "element-plus";

import App from "./App.vue";
import router from "./router";
import { restoreSessionToken } from "./stores/session";
import "./styles/element.scss";
import "./styles/main.scss";

restoreSessionToken();

createApp(App).use(router).use(ElementPlus).mount("#app");
