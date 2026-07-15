import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { checkEngineVersion } from "./check-engine-version.mjs";

function fixture({
  packageVersion = "1.2.3",
  pyprojectVersion = "1.2.3",
  lockVersion = "1.2.3",
} = {}) {
  const root = mkdtempSync(join(tmpdir(), "solidifai-version-"));
  mkdirSync(join(root, "engine"));
  writeFileSync(join(root, "package.json"), JSON.stringify({ version: packageVersion }));
  writeFileSync(
    join(root, "engine", "pyproject.toml"),
    `[project]\nname = "solidifai-engine"\nversion = "${pyprojectVersion}"\n`,
  );
  writeFileSync(
    join(root, "engine", "uv.lock"),
    `[[package]]\nname = "solidifai-engine"\nversion = "${lockVersion}"\n`,
  );
  return root;
}

function relaxedTomlFixture() {
  const root = mkdtempSync(join(tmpdir(), "solidifai-version-"));
  mkdirSync(join(root, "engine"));
  writeFileSync(join(root, "package.json"), JSON.stringify({ version: "1.2.3" }));
  writeFileSync(
    join(root, "engine", "pyproject.toml"),
    `[project]\nname = "solidifai-engine"\nversion = "1.2.3" # application engine\n`,
  );
  writeFileSync(
    join(root, "engine", "uv.lock"),
    `[[package]]\nname = "other"\nversion = "0.1.0"\n\n[[package]]\nname = "solidifai-engine"\nversion = "1.2.3" # lock metadata\n`,
  );
  return root;
}

test("accepts matching app, engine, and lockfile versions", () => {
  const root = fixture();
  try {
    assert.equal(checkEngineVersion(root), "1.2.3");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("rejects mismatched engine metadata", () => {
  const root = fixture({ lockVersion: "1.2.2" });
  try {
    assert.throws(() => checkEngineVersion(root), /uv\.lock=1\.2\.2/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("accepts TOML whitespace and inline comments", () => {
  const root = relaxedTomlFixture();
  try {
    assert.equal(checkEngineVersion(root), "1.2.3");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("release and watcher configuration covers every tracked metadata location", () => {
  const root = new URL("..", import.meta.url);
  for (const name of ["release-please-config.json", "release-please-config.beta.json"]) {
    const config = JSON.parse(readFileSync(new URL(`../${name}`, import.meta.url), "utf8"));
    const paths = config.packages["."]["extra-files"].map((entry) => entry.path);
    assert.ok(paths.includes("engine/uv.lock"), `${name} must update engine/uv.lock`);
  }
  assert.match(
    readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8"),
    /\*\*\/\.worktrees\/\*\*/,
  );
  assert.match(
    readFileSync(new URL("../.github/workflows/ci.yml", import.meta.url), "utf8"),
    /node --test scripts\/check-engine-version\.test\.mjs/,
  );
  assert.ok(root);
});
