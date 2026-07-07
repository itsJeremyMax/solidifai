/**
 * useAppVersion — the running app version (e.g. "0.1.2"), resolved once from
 * Tauri's `getVersion`. Returns "" until it resolves. Used to show "you're on X"
 * next to an available update.
 */
import { useEffect, useRef, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";

export function useAppVersion(): string {
  const [version, setVersion] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    void getVersion()
      .then((v) => {
        if (mounted.current) setVersion(v);
      })
      .catch(() => {});
    return () => {
      mounted.current = false;
    };
  }, []);
  return version;
}
