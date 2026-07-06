import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";

/**
 * Header slot — lets a page publish the chrome it wants (a contextual crumb, a
 * centered region, and right-side actions) into the persistent {@link AppHeader}
 * without the header knowing anything about the page.
 *
 * Implemented as a tiny external store rather than context state on purpose: the
 * publishing page is a descendant of the provider, so context-state updates would
 * re-render the page, which re-creates its JSX, which re-publishes — an infinite
 * loop. With an external store, a write notifies only the header outlets (the
 * subscribers); the page never re-renders from publishing.
 */

interface Slot {
  crumb?: ReactNode;
  /** Centered region (e.g. the docs search). Sits in the flex-1 middle of the bar. */
  center?: ReactNode;
  actions?: ReactNode;
}

interface SlotStore {
  get: () => Slot;
  set: (s: Slot) => void;
  subscribe: (cb: () => void) => () => void;
}

function createStore(): SlotStore {
  let slot: Slot = {};
  const listeners = new Set<() => void>();
  return {
    get: () => slot,
    set: (s) => {
      slot = s;
      listeners.forEach((l) => l());
    },
    subscribe: (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
  };
}

const HeaderSlotContext = createContext<SlotStore | null>(null);

export function HeaderSlotProvider({ children }: { children: ReactNode }) {
  const store = useRef<SlotStore | undefined>(undefined);
  if (!store.current) store.current = createStore();
  return <HeaderSlotContext.Provider value={store.current}>{children}</HeaderSlotContext.Provider>;
}

function useStore(): SlotStore {
  const store = useContext(HeaderSlotContext);
  if (!store) throw new Error("useHeaderSlot/HeaderSlotOutlet used outside HeaderSlotProvider");
  return store;
}

/** A page declares the chrome it wants. Re-published on change, cleared on unmount. */
// eslint-disable-next-line react-refresh/only-export-components
export function useHeaderSlot(slot: Slot) {
  const store = useStore();
  useEffect(() => {
    store.set(slot);
    return () => store.set({});
    // Runs on every render so dynamic crumb/actions (busy flags, names) stay live;
    // cheap because it only notifies the header outlets, never the page.
  });
}

/** Rendered inside AppHeader; shows whatever the current page published. */
export function HeaderSlotOutlet({ which }: { which: "crumb" | "center" | "actions" }) {
  const store = useStore();
  const slot = useSyncExternalStore(store.subscribe, store.get, store.get);
  return <>{slot[which] ?? null}</>;
}
