import { MessageSquare, Terminal as TerminalIcon } from "lucide-react";

/**
 * Interaction surfaces registry — the left pane's tabs. Single source so adding a
 * surface (or enabling Chat) is one entry, not edits across the tab bar. Selection
 * lives in AppShell state (not the URL); `status: "soon"` shows a tab that is not
 * yet selectable.
 */
export type InteractionTab = "terminal" | "chat";

export interface InteractionSurface {
  id: InteractionTab;
  label: string;
  Icon: typeof TerminalIcon;
  status: "active" | "soon";
}

export const INTERACTION_SURFACES: InteractionSurface[] = [
  { id: "chat", label: "Chat", Icon: MessageSquare, status: "soon" },
  { id: "terminal", label: "Terminal", Icon: TerminalIcon, status: "active" },
];
