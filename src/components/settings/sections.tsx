import type { ReactNode } from "react";
import {
  Download,
  HardDrive,
  Info,
  Keyboard,
  MessageSquareText,
  Printer,
  Puzzle,
  SlidersHorizontal,
  Wrench,
} from "lucide-react";

import ViewportFeatures from "./ViewportFeatures";
import WorkspaceStorage from "./WorkspaceStorage";
import Slicers from "./Slicers";
import Updates from "./Updates";
import Shortcuts from "./Shortcuts";
import About from "./About";
import ManufacturingProfile from "./ManufacturingProfile";
import AgentConfig from "./AgentConfig";
import CustomInstructions from "./CustomInstructions";

const ICON_STROKE = 1.7;

/** A settings section: one sidebar entry + one nested route. */
export interface SettingsSection {
  id: string;
  label: string;
  group: string;
  icon: ReactNode;
  element: ReactNode;
}

/** Simple sections get a `px-6.5` gutter; each section owns its own inner layout. */
function pane(node: ReactNode): ReactNode {
  return <div className="px-6.5">{node}</div>;
}

/**
 * App (global) settings — reachable from the home header gear at `/settings`.
 * Everything here is app-wide: it applies with no workspace open. The
 * "Defaults" group holds the values woven into every workspace (custom
 * instructions + the manufacturing profile's global layer).
 */
export const APP_SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: "viewport",
    label: "Viewport / Features",
    group: "Editor",
    icon: <SlidersHorizontal size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<ViewportFeatures />),
  },
  {
    id: "instructions",
    label: "Custom instructions",
    group: "Defaults",
    icon: <MessageSquareText size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<CustomInstructions scope="global" />),
  },
  {
    id: "manufacturing",
    label: "Manufacturing",
    group: "Defaults",
    icon: <Wrench size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<ManufacturingProfile scope="global" />),
  },
  {
    id: "slicers",
    label: "Slicers",
    group: "App",
    icon: <Printer size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<Slicers />),
  },
  {
    id: "updates",
    label: "Updates",
    group: "App",
    icon: <Download size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<Updates />),
  },
  {
    id: "shortcuts",
    label: "Keyboard shortcuts",
    group: "App",
    icon: <Keyboard size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<Shortcuts />),
  },
  {
    id: "about",
    label: "About",
    group: "App",
    icon: <Info size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<About />),
  },
];

/**
 * Workspace settings — reachable from the editor gear at `/w/:wsPath/settings`.
 * Everything here is scoped to the focused workspace and layers on top of the
 * app-wide defaults (custom instructions, manufacturing). A single group, so the
 * sidebar shows a flat list (SettingsLayout hides the lone group header).
 */
export const WORKSPACE_SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: "instructions",
    label: "Custom instructions",
    group: "Workspace",
    icon: <MessageSquareText size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<CustomInstructions scope="workspace" />),
  },
  {
    id: "skills",
    label: "Agent skills",
    group: "Workspace",
    icon: <Puzzle size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<AgentConfig />),
  },
  {
    id: "manufacturing",
    label: "Manufacturing",
    group: "Workspace",
    icon: <Wrench size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<ManufacturingProfile scope="workspace" />),
  },
  {
    id: "workspace",
    label: "Workspace & storage",
    group: "Workspace",
    icon: <HardDrive size={16} strokeWidth={ICON_STROKE} />,
    element: pane(<WorkspaceStorage />),
  },
];

/** Section ids in order — handy for the index redirect + route generation. */
export const APP_SETTINGS_SECTION_IDS = APP_SETTINGS_SECTIONS.map((s) => s.id);
export const WORKSPACE_SETTINGS_SECTION_IDS = WORKSPACE_SETTINGS_SECTIONS.map((s) => s.id);
