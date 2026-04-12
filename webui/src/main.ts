import { createApp } from "vue";
import ElementPlus from "element-plus";

import App from "./App.vue";
import router from "./router";
import { restoreSessionToken } from "./stores/session";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "diff2html/bundles/css/diff2html.min.css";
import "juxtaposejs/build/css/juxtapose.css";
import "prismjs/themes/prism.css";
import "prismjs/plugins/line-numbers/prism-line-numbers.css";
import "./styles/element.scss";
import "./styles/main.scss";

restoreSessionToken();

createApp(App).use(router).use(ElementPlus).mount("#app");
