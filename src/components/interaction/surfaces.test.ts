import { describe, it, expect } from "vitest";
import { INTERACTION_SURFACES } from "./surfaces";

describe("interaction surfaces registry", () => {
  it("has terminal active and chat marked soon", () => {
    const byId = Object.fromEntries(INTERACTION_SURFACES.map((s) => [s.id, s.status]));
    expect(byId.terminal).toBe("active");
    expect(byId.chat).toBe("soon");
  });
});
