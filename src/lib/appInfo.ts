/**
 * appInfo — read-only "about this build" facts for Settings → About (and the
 * Workspace & storage section). Everything is best-effort: each field degrades
 * to a friendly fallback so the page always renders, even before the engine is
 * ready or when running outside the desktop shell.
 *
 * The app version is the single source of truth from the root package.json:
 * tauri.conf.json reads it via "version": "../package.json", and getVersion()
 * returns that same value at runtime.
 */
import { getName, getTauriVersion, getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";

import { getEngineStatus, type EngineStatusEvent } from "./ipc";
import { getActiveWorkspace, tildePath } from "./workspaces";

export const LICENSE = "Apache License 2.0";
export const LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0";
export const CREATOR = "Jeremy Max";

/** A snapshot of the build + runtime facts surfaced in About. */
export interface AppInfo {
  /** Product name (from the Tauri config). */
  name: string;
  /** App version, single-sourced from package.json. */
  version: string;
  /** The Tauri framework version this build links against. */
  tauriVersion: string;
  /** Host OS family (no false precision: the webview freezes the OS version). */
  os: string;
  /** The rendering engine + version powering the webview. */
  webview: string;
  /** Engine lifecycle as a short human label ("Ready · 3.12", "Provisioning…"). */
  engine: string;
  /** Absolute interpreter path the engine resolved to, or null. */
  interpreter: string | null;
  /** Active workspace path, tilde-collapsed, or null when none is open. */
  workspacePath: string | null;
}

/** Host OS family from the user agent. WebKit freezes the version, so we omit it. */
function osLabel(): string {
  const ua = navigator.userAgent;
  if (/Macintosh|Mac OS X/.test(ua)) return "macOS";
  if (/Windows/.test(ua)) return "Windows";
  if (/Linux|X11/.test(ua)) return "Linux";
  return navigator.platform || "Unknown";
}

/** Rendering engine + version (WebKit on macOS/Linux, Chromium via WebView2 on
 *  Windows). Chrome is checked first: WebView2's UA carries both tokens, and its
 *  AppleWebKit/537.36 is frozen compatibility boilerplate, not the real engine. */
function webViewLabel(): string {
  const ua = navigator.userAgent;
  const cr = ua.match(/Chrome\/([\d.]+)/);
  if (cr) return `Chromium ${cr[1]}`;
  const wk = ua.match(/AppleWebKit\/([\d.]+)/);
  if (wk) return `WebKit ${wk[1]}`;
  return "Unknown";
}

function engineLabel(s: EngineStatusEvent | null): string {
  if (!s) return "Not running";
  switch (s.status) {
    case "ready":
      return s.version ? `Ready · ${s.version}` : "Ready";
    case "provisioning":
      return "Provisioning…";
    case "error":
      return s.message ? `Error: ${s.message}` : "Error";
    default:
      return "Unknown";
  }
}

/** Gather every About fact in parallel. Never rejects. */
export async function loadAppInfo(): Promise<AppInfo> {
  const [name, version, tauriVersion, engine, ws] = await Promise.all([
    getName().catch(() => "solidifai"),
    getVersion().catch(() => "—"),
    getTauriVersion().catch(() => "—"),
    getEngineStatus(),
    getActiveWorkspace(),
  ]);
  return {
    name,
    version,
    tauriVersion,
    os: osLabel(),
    webview: webViewLabel(),
    engine: engineLabel(engine),
    interpreter: engine?.interpreter ?? null,
    workspacePath: ws ? tildePath(ws.path) : null,
  };
}

/** A plain-text diagnostics block, ready to paste into a bug report. */
export function buildDiagnostics(info: AppInfo): string {
  const rows: [string, string][] = [
    [info.name, info.version],
    ["Tauri", info.tauriVersion],
    ["OS", info.os],
    ["WebView", info.webview],
    ["Engine", info.engine],
  ];
  if (info.workspacePath) rows.push(["Workspace", info.workspacePath]);
  return rows.map(([k, v]) => `${k.padEnd(12)}${v}`).join("\n");
}

/** Copy text to the clipboard. Returns false (no throw) when blocked. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export async function openLicense(): Promise<void> {
  try {
    await openUrl(LICENSE_URL);
  } catch {
    /* best-effort: a blocked opener shouldn't surface as a crash */
  }
}
