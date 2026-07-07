// @vitest-environment jsdom
import { renderHook, act, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/ipc/references", () => ({
  getReferenceLibrary: vi.fn(),
  saveReferenceEntry: vi.fn(),
  deleteReferenceEntry: vi.fn(),
  onReferenceLibraryUpdated: vi.fn(async () => () => {}),
}));

import * as ipc from "../lib/ipc/references";
import { useReferences } from "./useReferences";

const SEED = [
  {
    id: "usb-c",
    category: "port-cutout",
    dims_mm: { cutout: [9.2, 3.4] },
    source: "https://usb.org",
  },
];
const USER = [
  {
    id: "raspberry-pi-5",
    category: "sbc",
    dims_mm: { pcb: [85, 56, 1.4] },
    source: "https://rpi.com",
    origin: "learned" as const,
    verified_in: "cyberdeck",
    verified_at: "2026-06-11",
  },
];

beforeEach(() => {
  vi.mocked(ipc.getReferenceLibrary).mockResolvedValue({ seed: SEED, user: USER });
});

describe("useReferences", () => {
  it("loads and merges seed + user with shadow flags", async () => {
    const { result } = renderHook(() => useReferences());
    await waitFor(() => expect(result.current.entries.length).toBe(2));
    const pi = result.current.entries.find((e) => e.id === "raspberry-pi-5");
    expect(pi?.origin).toBe("learned");
    const usbc = result.current.entries.find((e) => e.id === "usb-c");
    expect(usbc?.builtin).toBe(true);
  });

  it("a user entry with a seed id shadows the seed entry", async () => {
    vi.mocked(ipc.getReferenceLibrary).mockResolvedValue({
      seed: SEED,
      user: [{ ...USER[0], id: "usb-c" }],
    });
    const { result } = renderHook(() => useReferences());
    await waitFor(() => expect(result.current.entries.length).toBe(1));
    expect(result.current.entries[0].builtin).toBe(false);
    expect(result.current.entries[0].shadowsSeed).toBe(true);
  });

  it("reloads when the updated event fires", async () => {
    let fire: () => void = () => {};
    vi.mocked(ipc.onReferenceLibraryUpdated).mockImplementation(async (h) => {
      fire = h;
      return () => {};
    });
    const { result } = renderHook(() => useReferences());
    await waitFor(() => expect(result.current.entries.length).toBe(2));
    vi.mocked(ipc.getReferenceLibrary).mockResolvedValue({ seed: SEED, user: [] });
    act(() => fire());
    await waitFor(() => expect(result.current.entries.length).toBe(1));
  });
});
