import { createApp } from "vue";
import {
  ElAlert,
  ElButton,
  ElConfigProvider,
  ElEmpty,
  ElInput,
  ElOption,
  ElOptionGroup,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSkeleton,
  ElTable,
  ElTableColumn,
} from "element-plus";
import "element-plus/dist/index.css";
import "./style.css";
import App from "./App.vue";
import { router } from "./router";
const app = createApp(App).use(router);
for (const [name, component] of Object.entries({
  ElAlert,
  ElButton,
  ElConfigProvider,
  ElEmpty,
  ElInput,
  ElOption,
  ElOptionGroup,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSkeleton,
  ElTable,
  ElTableColumn,
}))
  app.component(name, component);
app.mount("#app");
