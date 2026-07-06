import type { ReactNode } from "react";
import {
  Download,
  FileCode,
  HardDrive,
  Info,
  Keyboard,
  Printer,
  SlidersHorizontal,
  Wrench,
} from "lucide-react";

import ViewportFeatures from "./ViewportFeatures";
import WorkspaceStorage from "./WorkspaceStorage";
import Slicers from "./Slicers";
import Updates from "./Updates";
import Shortcuts from "./Shortcuts";
import About from "./About";
import Context from "./Context";
import ManufacturingProfile from "./ManufacturingProfile";

const ICON_STROKE = 1.7;

/** A settings section: one sidebar entry + one nested route. */
export interface SettingsSection {
  id: string;
  label: string;
  group: string;
  icon: ReactNode;
  element: ReactNode;
}

/**
 * The settings sections, in order. Adding a section is one entry here — the
 * sidebar groups and the nested routes (global + workspace scope) both derive
 * from this list. Simple sections get a `px-6.5` gutter; Context owns its own
 * full-height layout.
 */
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: "viewport",
    label: "Viewport / Features",
    group: "Editor",
    icon: <SlidersHorizontal size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <ViewportFeatures />
      </div>
    ),
  },
  {
    id: "context",
    label: "Context",
    group: "Workspace",
    icon: <FileCode size={16} strokeWidth={ICON_STROKE} />,
    element: <Context />,
  },
  {
    id: "manufacturing",
    label: "Manufacturing",
    group: "Workspace",
    icon: <Wrench size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <ManufacturingProfile />
      </div>
    ),
  },
  {
    id: "workspace",
    label: "Workspace & storage",
    group: "Workspace",
    icon: <HardDrive size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <WorkspaceStorage />
      </div>
    ),
  },
  {
    id: "slicers",
    label: "Slicers",
    group: "App",
    icon: <Printer size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <Slicers />
      </div>
    ),
  },
  {
    id: "updates",
    label: "Updates",
    group: "App",
    icon: <Download size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <Updates />
      </div>
    ),
  },
  {
    id: "shortcuts",
    label: "Keyboard shortcuts",
    group: "App",
    icon: <Keyboard size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <Shortcuts />
      </div>
    ),
  },
  {
    id: "about",
    label: "About",
    group: "App",
    icon: <Info size={16} strokeWidth={ICON_STROKE} />,
    element: (
      <div className="px-6.5">
        <About />
      </div>
    ),
  },
];

/** Section ids in order — handy for the index redirect + route generation. */
export const SETTINGS_SECTION_IDS = SETTINGS_SECTIONS.map((s) => s.id);
