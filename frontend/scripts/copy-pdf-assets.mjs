import { cpSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const target = resolve(root, "dist/pdf-assets");
mkdirSync(target, { recursive: true });
for (const folder of ["cmaps", "standard_fonts", "wasm"]) {
  cpSync(
    resolve(root, "node_modules/pdfjs-dist", folder),
    resolve(target, folder),
    { recursive: true },
  );
}
