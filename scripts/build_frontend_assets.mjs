import { build, context } from "esbuild";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const frontendDir = path.join(repoRoot, "frontend");
const staticSourceCssPath = path.join(repoRoot, "static", "styles.css");
const staticOutputDir = "/mnt/storage/static";
const versionPattern = /FANIC_ASSET_VERSION:\s*([A-Za-z0-9._-]+)/;

function parseArgs(argv) {
  return {
    dev: argv.includes("--dev"),
    watch: argv.includes("--watch"),
  };
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function stemFromFileName(fileName) {
  return fileName.endsWith(".ts") ? fileName.slice(0, -3) : fileName;
}

async function extractVersionFromFile(filePath) {
  const text = await fs.readFile(filePath, "utf-8");
  const lines = text.split(/\r?\n/).slice(0, 30).join("\n");
  const match = lines.match(versionPattern);
  return match ? match[1] : "0";
}

async function listFrontendEntries() {
  const names = await fs.readdir(frontendDir);
  return names.filter((name) => name.endsWith(".ts")).sort();
}

async function loadAssetVersions(entryFiles) {
  const versions = {};
  for (const entryFile of entryFiles) {
    const stem = stemFromFileName(entryFile);
    versions[stem] = await extractVersionFromFile(path.join(frontendDir, entryFile));
  }
  versions.styles = await extractVersionFromFile(staticSourceCssPath);
  return versions;
}

async function removeMatchingFiles(dirPath, matcher) {
  const names = await fs.readdir(dirPath);
  await Promise.all(
    names
      .filter((name) => matcher(name))
      .map((name) => fs.unlink(path.join(dirPath, name))),
  );
}

async function writeVersionedCss(stylesVersion) {
  const cssTarget = path.join(staticOutputDir, `styles.v${stylesVersion}.css`);
  await removeMatchingFiles(
    staticOutputDir,
    (name) => name.startsWith("styles.v") && name.endsWith(".css") && name !== path.basename(cssTarget),
  );
  await fs.copyFile(staticSourceCssPath, cssTarget);

  const unversionedCss = path.join(staticOutputDir, "styles.css");
  if (await fileExists(unversionedCss)) {
    await fs.unlink(unversionedCss);
  }
}

async function rewriteVersionedJs(entryFiles, versions) {
  for (const entryFile of entryFiles) {
    const stem = stemFromFileName(entryFile);
    const sourceFile = path.join(staticOutputDir, `${stem}.js`);
    const targetName = `${stem}.v${versions[stem]}.js`;
    const targetFile = path.join(staticOutputDir, targetName);

    await removeMatchingFiles(
      staticOutputDir,
      (name) => name.startsWith(`${stem}.v`) && name.endsWith(".js") && name !== targetName,
    );

    if (await fileExists(sourceFile)) {
      await fs.copyFile(sourceFile, targetFile);
      await fs.unlink(sourceFile);
    }
  }
}

async function postProcess(entryFiles, versions) {
  await writeVersionedCss(versions.styles);
  await rewriteVersionedJs(entryFiles, versions);
}

function buildOptions(entryPoints, isDev, onEnd) {
  return {
    entryPoints,
    bundle: true,
    minify: !isDev,
    sourcemap: isDev,
    target: "es2022",
    platform: "browser",
    format: "iife",
    outdir: staticOutputDir,
    plugins: [
      {
        name: "versioned-assets",
        setup(builder) {
          builder.onEnd(onEnd);
        },
      },
    ],
  };
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const entryFiles = await listFrontendEntries();
  const entryPoints = entryFiles.map((fileName) => path.join(frontendDir, fileName));
  const versions = await loadAssetVersions(entryFiles);

  const onEnd = async (result) => {
    if (result.errors.length > 0) {
      return;
    }
    await postProcess(entryFiles, versions);
  };

  const options = buildOptions(entryPoints, args.dev, onEnd);

  if (args.watch) {
    const ctx = await context(options);
    await ctx.watch();
    return;
  }

  await build(options);
}

run().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
