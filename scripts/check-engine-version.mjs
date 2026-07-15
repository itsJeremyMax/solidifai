import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

function versionIn(text, source) {
  const match = text.match(/^\s*version\s*=\s*"([^"]+)"(?:\s*#.*)?\s*$/m);
  if (!match) throw new Error(`Could not read ${source} version`);
  return match[1];
}

function engineLockVersion(text) {
  const block = text
    .split(/^\s*\[\[package\]\]\s*$/m)
    .find((candidate) => /^\s*name\s*=\s*"solidifai-engine"(?:\s*#.*)?\s*$/m.test(candidate));
  const match = block?.match(/^\s*version\s*=\s*"([^"]+)"(?:\s*#.*)?\s*$/m);
  if (!match) throw new Error("Could not read solidifai-engine version from uv.lock");
  return match[1];
}

export function checkEngineVersion(root) {
  const packageVersion = JSON.parse(readFileSync(join(root, "package.json"), "utf8")).version;
  const pyprojectVersion = versionIn(
    readFileSync(join(root, "engine", "pyproject.toml"), "utf8"),
    "pyproject.toml",
  );
  const lockVersion = engineLockVersion(readFileSync(join(root, "engine", "uv.lock"), "utf8"));
  const versions = {
    "package.json": packageVersion,
    "pyproject.toml": pyprojectVersion,
    "uv.lock": lockVersion,
  };
  if (new Set(Object.values(versions)).size !== 1) {
    throw new Error(
      `Engine version mismatch: ${Object.entries(versions)
        .map(([file, version]) => `${file}=${version}`)
        .join(", ")}`,
    );
  }
  return packageVersion;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = join(fileURLToPath(new URL("..", import.meta.url)));
  process.stdout.write(`Engine version ${checkEngineVersion(root)} is synchronized.\n`);
}
