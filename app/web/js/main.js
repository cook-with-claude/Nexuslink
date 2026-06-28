// Entry point: register routes, start the hash router.

import { register, startRouter } from "./router.js";
import { initCommandPalette } from "./command-palette.js";
import { loginScreen } from "./screens/login.js";
import { dashboardScreen } from "./screens/dashboard.js";
import { datasetsScreen } from "./screens/datasets.js";
import { importScreen } from "./screens/import.js";
import { targetsScreen } from "./screens/targets.js";
import { resultsScreen } from "./screens/results.js";
import { passwordScreen } from "./screens/password.js";

register("#/login", loginScreen, { auth: false });
register("#/dashboard", dashboardScreen);
register("#/datasets", datasetsScreen);
register("#/import", importScreen);
register("#/datasets/:id/targets", targetsScreen);
register("#/targets/:id/result", resultsScreen);
register("#/change-password", passwordScreen);

initCommandPalette();
startRouter();
