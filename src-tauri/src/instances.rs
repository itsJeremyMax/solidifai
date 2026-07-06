//! Live-instance registry: one engine per open workspace, keyed by WsId (the
//! canonical root path). Owns the focused pointer and the single held artifact
//! watcher (only the focused tab has a viewport). See the multi-workspace-tabs spec.

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::Mutex;

use crate::engine::EngineState;
use crate::watcher::WatcherState;

/// A workspace identity: its canonical root path string.
pub type WsId = String;

/// The live-instance registry (managed state).
#[derive(Default)]
pub struct Instances {
    /// One engine supervisor state per open workspace.
    engines: Mutex<HashMap<WsId, Arc<EngineState>>>,
    /// The workspace whose viewport/RPC/watcher is currently live.
    focused: Mutex<Option<WsId>>,
    /// The single artifact watcher, retargeted to the focused workspace.
    watcher: Mutex<Option<WatcherState>>,
}

impl Instances {
    /// Get the engine for `id`, creating an idle one if absent. The returned Arc is
    /// the one stored in the map (so callers and the supervisor share it).
    pub fn ensure(&self, id: impl Into<WsId>) -> Arc<EngineState> {
        let id = id.into();
        self.engines
            .lock()
            .entry(id)
            .or_insert_with(|| Arc::new(EngineState::default()))
            .clone()
    }

    /// Get-or-create the engine for `id`; the bool is true if it was newly inserted.
    /// Atomic under a single lock so concurrent opens of a new workspace can't both
    /// decide to spawn.
    pub fn ensure_new(&self, id: impl Into<WsId>) -> (Arc<EngineState>, bool) {
        use std::collections::hash_map::Entry;
        let id = id.into();
        let mut engines = self.engines.lock();
        match engines.entry(id) {
            Entry::Occupied(e) => (e.get().clone(), false),
            Entry::Vacant(v) => {
                let e = Arc::new(EngineState::default());
                v.insert(e.clone());
                (e, true)
            }
        }
    }

    /// The engine for `id`, if it is live.
    pub fn get(&self, id: &str) -> Option<Arc<EngineState>> {
        self.engines.lock().get(id).cloned()
    }

    /// Set the focused workspace (does not start/stop anything; callers retarget the
    /// watcher separately via [`set_watcher`]).
    pub fn set_focus(&self, id: impl Into<WsId>) {
        *self.focused.lock() = Some(id.into());
    }

    /// Clear the focused workspace (back to the launcher / no viewport).
    pub fn clear_focus(&self) {
        *self.focused.lock() = None;
    }

    /// The currently focused workspace id, if any.
    pub fn focused_id(&self) -> Option<WsId> {
        self.focused.lock().clone()
    }

    /// The focused workspace's engine, if a workspace is focused and live.
    pub fn focused_engine(&self) -> Option<Arc<EngineState>> {
        let id = self.focused.lock().clone()?;
        self.engines.lock().get(&id).cloned()
    }

    /// The focused workspace's engine socket (once its engine has started).
    pub fn focused_socket(&self) -> Option<String> {
        self.focused_engine().and_then(|e| e.socket())
    }

    /// The engine socket for a specific workspace id, if it is live (and its engine
    /// has started). Lets metadata writes route to the TARGET workspace's own engine
    /// rather than the focused one.
    pub fn socket_for(&self, id: &str) -> Option<String> {
        self.engines.lock().get(id).and_then(|e| e.socket())
    }

    /// Replace the held watcher (dropping the old one stops the old watch).
    pub fn set_watcher(&self, w: Option<WatcherState>) {
        *self.watcher.lock() = w;
    }

    /// Remove an instance from the registry, killing its engine. If it was focused,
    /// focus is cleared. Returns the removed engine Arc (already killed).
    pub fn remove(&self, id: &str) -> Option<Arc<EngineState>> {
        let engine = self.engines.lock().remove(id);
        if let Some(ref e) = engine {
            e.kill();
        }
        let mut focused = self.focused.lock();
        if focused.as_deref() == Some(id) {
            *focused = None;
        }
        engine
    }

    /// Kill every engine + drop the watcher. Called on window-destroy / app exit.
    pub fn kill_all(&self) {
        for (_, e) in self.engines.lock().drain() {
            e.kill();
        }
        *self.focused.lock() = None;
        *self.watcher.lock() = None;
    }

    /// The set of open workspace ids (sorted for deterministic tests).
    pub fn open_ids(&self) -> Vec<WsId> {
        let mut ids: Vec<WsId> = self.engines.lock().keys().cloned().collect();
        ids.sort();
        ids
    }

    /// Snapshot of every live engine's last status, tagged with its workspace id
    /// (the registry key, so it always matches the frontend's open-tab paths). Lets
    /// the switcher seed per-tab dots after a frontend reload (engines don't re-emit).
    pub fn all_statuses(&self) -> Vec<crate::engine::EngineStatus> {
        self.engines
            .lock()
            .iter()
            .map(|(id, e)| {
                let mut s = e.current_status();
                s.ws_id = id.clone(); // force the wsId to the registry key
                s
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ensure_is_idempotent_and_returns_same_engine() {
        let reg = Instances::default();
        let a1 = reg.ensure("/ws/a");
        let a2 = reg.ensure("/ws/a");
        assert!(
            Arc::ptr_eq(&a1, &a2),
            "ensure must return the same engine Arc"
        );
        assert_eq!(reg.open_ids(), vec!["/ws/a".to_string()]);
    }

    #[test]
    fn focus_tracks_the_focused_engine() {
        let reg = Instances::default();
        reg.ensure("/ws/a");
        reg.ensure("/ws/b");
        assert!(reg.focused_engine().is_none(), "no focus set yet");
        reg.set_focus("/ws/b");
        let f = reg.focused_engine().expect("focused engine");
        assert!(Arc::ptr_eq(&f, &reg.ensure("/ws/b")));
    }

    #[test]
    fn remove_drops_only_that_instance() {
        let reg = Instances::default();
        reg.ensure("/ws/a");
        reg.ensure("/ws/b");
        reg.set_focus("/ws/a");
        let removed = reg.remove("/ws/a");
        assert!(removed.is_some());
        assert_eq!(reg.open_ids(), vec!["/ws/b".to_string()]);
        assert!(
            reg.focused_engine().is_none(),
            "removing the focused tab clears focus"
        );
    }

    #[test]
    fn socket_for_is_none_for_unknown_or_unstarted_engine() {
        let reg = Instances::default();
        assert!(
            reg.socket_for("/ws/missing").is_none(),
            "unknown workspace has no socket"
        );
        // A live-but-unstarted engine (no socket bound yet) also yields None.
        reg.ensure("/ws/a");
        assert!(
            reg.socket_for("/ws/a").is_none(),
            "an engine that has not started has no socket yet"
        );
    }

    #[test]
    fn kill_all_empties_the_registry() {
        let reg = Instances::default();
        reg.ensure("/ws/a");
        reg.ensure("/ws/b");
        reg.set_focus("/ws/a");
        reg.kill_all();
        assert!(reg.open_ids().is_empty());
        assert!(reg.focused_engine().is_none());
    }
}
