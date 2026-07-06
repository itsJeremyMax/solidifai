// @vitest-environment jsdom
import { describe, expect, it, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { WorkspaceThumb } from "./WorkspaceThumb";

afterEach(cleanup);

describe("WorkspaceThumb", () => {
  it("renders the captured image when a src is present", () => {
    render(<WorkspaceThumb name="fidget-bracket" src="data:image/png;base64,AAAA" />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe("data:image/png;base64,AAAA");
  });

  it("renders a placeholder (no img) when src is null", () => {
    render(<WorkspaceThumb name="fidget-bracket" src={null} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByTestId("thumb-placeholder")).toBeTruthy();
  });
});
