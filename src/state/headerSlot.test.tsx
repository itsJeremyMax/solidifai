// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { HeaderSlotProvider, HeaderSlotOutlet, useHeaderSlot } from "./headerSlot";

afterEach(cleanup);

function Page() {
  useHeaderSlot({ crumb: <span>crumb-x</span>, actions: <button>act-x</button> });
  return <div>page-body</div>;
}

describe("headerSlot", () => {
  it("renders a page's published crumb + actions into the outlet", async () => {
    render(
      <HeaderSlotProvider>
        <header>
          <HeaderSlotOutlet which="crumb" />
          <HeaderSlotOutlet which="actions" />
        </header>
        <Page />
      </HeaderSlotProvider>,
    );
    expect(await screen.findByText("crumb-x")).toBeTruthy();
    expect(screen.getByText("act-x")).toBeTruthy();
    expect(screen.getByText("page-body")).toBeTruthy();
  });

  it("clears the slot when the publishing page unmounts", async () => {
    function Wrapper({ show }: { show: boolean }) {
      return (
        <HeaderSlotProvider>
          <header>
            <HeaderSlotOutlet which="crumb" />
          </header>
          {show && <Page />}
        </HeaderSlotProvider>
      );
    }
    const { rerender } = render(<Wrapper show={true} />);
    expect(await screen.findByText("crumb-x")).toBeTruthy();
    rerender(<Wrapper show={false} />);
    expect(screen.queryByText("crumb-x")).toBeNull();
  });
});
