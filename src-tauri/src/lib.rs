pub mod agent_config;
pub mod agent_harness;
pub mod app_config;
pub mod control;
pub mod custom_instructions;
pub mod engine;
pub mod engine_cache;
pub mod engine_fetch;
pub mod engine_pin;
pub mod fabrication;
pub mod fs_guard;
pub mod instances;
pub mod ipc;
pub mod legacy;
pub mod logging;
pub mod manufacturing;
pub mod materials;
pub mod override_authority;
pub mod provision;
mod pty;
pub mod reference_library;
pub mod registry;
pub mod rpc;
pub mod slicers;
pub mod store;
pub mod thumbnails;
pub mod updater;
pub mod watcher;
pub mod workspace_meta;
pub mod workspaces;

use std::sync::Arc;

use agent_harness::HarnessStatusState;
use instances::Instances;
use provision::WorkspaceState;
use pty::PtyState;
use registry::Workspace;
use tauri::{Manager, RunEvent, WindowEvent};

/// Kill every workspace engine (via the registry) and the PTY shell. The registry
/// also drops the held artifact watcher. Called on window-destroy and app exit so
/// no child processes / file watches outlive the app. Also called by the updater
/// before the Windows install handoff, which exits without firing RunEvent::Exit.
pub(crate) fn shutdown(app_handle: &tauri::AppHandle) {
    app_handle.state::<Arc<Instances>>().kill_all();
    app_handle.state::<PtyState>().kill_all();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // webkit2gtk 2.42+ composites through DMABUF, which is broken on the NVIDIA
    // proprietary driver (blank/garbled window and failed WebGL context creation;
    // the most-reported Tauri-on-Linux failure class). Opt out before the webview
    // initializes when that driver is present; an explicit user setting wins.
    #[cfg(target_os = "linux")]
    if std::path::Path::new("/proc/driver/nvidia").exists()
        && std::env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none()
    {
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
    }

    let instances = Arc::new(Instances::default());

    let mut builder = tauri::Builder::default()
        // Registered FIRST (the plugin's requirement): a second launch exits
        // immediately and this callback runs in the surviving instance instead.
        // Two live instances would fight over the control socket, per-workspace
        // engine sockets, and registry writes; the deep-link feature forwards a
        // link-triggered second launch here so the URL still routes in-app.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.unminimize();
                let _ = win.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_updater::Builder::new().build());

    // Native-feel hardening: in release builds, strip browser behaviors from the
    // webview (right-click menu, text selection, reload/print/zoom shortcuts) so the
    // app feels native. Left off in debug builds (`tauri dev`) so devtools, reload,
    // and inspect keep working. The dev/prod boundary is the build profile, same as
    // `windows_subsystem` in main.rs.
    if !cfg!(debug_assertions) {
        builder = builder.plugin(tauri_plugin_prevent_default::init());
    }

    builder
        .manage(PtyState::default())
        .manage(WorkspaceState::default())
        .manage(HarnessStatusState::default())
        .manage(instances.clone())
        .setup(move |app| {
            // Stand up logging first so anything below (and the whole session) is
            // captured to the rolling log file + stderr.
            logging::init(app.handle());
            app.state::<HarnessStatusState>()
                .replace(agent_harness::detect_path_only());

            // Do NOT open a workspace at boot — the frontend shows a launcher and
            // the engine/watcher/provisioner start in `open_workspace`.
            //
            // Best-effort migration for existing users: if the legacy fixed
            // `~/solidifai-workspace` exists and the registry is empty, register it
            // as a "Default workspace" so it shows up in the launcher. No auto-open.
            if let Ok(dir) = app.path().app_config_dir() {
                let _ = std::fs::create_dir_all(&dir);

                // Engine IPC endpoints live under the config dir (user-owned),
                // never under the user-chosen workspace root. Set before any
                // workspace can open.
                provision::init_ipc_dir(&dir);

                // Pull legacy materials/destinations into the unified config dir
                // before anything reads (and re-seeds) them.
                legacy::migrate_into(&dir);

                let mut all = registry::load(&dir);
                if all.is_empty() {
                    if let Some(legacy) = provision::legacy_workspace_root() {
                        if legacy.is_dir() {
                            let now = registry::now_ms();
                            all.push(Workspace {
                                name: "Default workspace".to_string(),
                                path: legacy.to_string_lossy().into_owned(),
                                created_at: now,
                                last_opened_at: None,
                                archived_at: None,
                                description: None,
                                tags: vec![],
                                proposed_name: None,
                                meta_synced_at: None,
                            });
                            let _ = registry::save(&dir, &all);
                        }
                    }
                }
            }

            // Start the host-control channel so the engine can delegate profile
            // writes back to the one Rust writer (manufacturing::write).
            if let Ok(dir) = app.path().app_config_dir() {
                control::start(dir);
            }

            // Stash the handle so reference_library::emit_updated() can fire
            // the event from either the GUI commands or the control-socket thread.
            reference_library::set_app_handle(app.handle().clone());

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // PTY host.
            pty::pty_spawn,
            pty::pty_write,
            pty::pty_resize,
            // Workspace (active-workspace artifact access).
            provision::get_workspace_dir,
            provision::get_export_dir,
            provision::reveal_workspace_dir,
            provision::workspace_has_model,
            provision::read_model_snapshot,
            // Workspace launcher / lifecycle.
            workspaces::list_workspaces,
            workspaces::create_workspace,
            workspaces::default_workspace_dir,
            workspaces::open_workspace,
            workspaces::close_workspace,
            workspaces::close_workspace_tab,
            workspaces::list_open_workspaces,
            workspaces::get_active_workspace,
            workspaces::rename_workspace,
            workspaces::edit_workspace_details,
            workspaces::accept_proposed_name,
            workspaces::dismiss_proposed_name,
            workspaces::delete_workspace,
            workspaces::archive_workspace,
            workspaces::restore_workspace,
            workspaces::pick_directory,
            // Workspace thumbnail cache (home gallery).
            thumbnails::store_workspace_thumbnail,
            thumbnails::list_workspace_thumbnails,
            // Global template store (settings).
            workspaces::get_templates,
            workspaces::save_template,
            workspaces::reset_template,
            // Global app-config store (viewport feature flags).
            workspaces::get_app_config,
            workspaces::set_app_config,
            // Global + workspace material library.
            workspaces::get_global_materials,
            workspaces::set_global_materials,
            workspaces::get_workspace_materials,
            workspaces::set_workspace_materials,
            // Global + workspace manufacturing profile.
            manufacturing::get_global_manufacturing_profile,
            manufacturing::set_global_manufacturing_profile,
            manufacturing::get_workspace_manufacturing_profile,
            manufacturing::set_workspace_manufacturing_profile,
            // Global + workspace custom instructions (woven into AGENTS.md).
            custom_instructions::get_global_custom_instructions,
            custom_instructions::set_global_custom_instructions,
            custom_instructions::get_workspace_custom_instructions,
            custom_instructions::set_workspace_custom_instructions,
            // App-level print destinations (connections), served natively so the
            // Printers page works with no workspace engine.
            fabrication::get_destinations,
            fabrication::set_destinations,
            // Slicer detection, profiles, and the user-overridable binary store.
            slicers::get_slicer_profiles,
            slicers::get_slicer_config,
            slicers::set_slicer_override,
            slicers::pick_slicer_binary,
            // Per-workspace agent config (enabled skills + runtime settings).
            workspaces::list_skills,
            workspaces::get_agent_config,
            workspaces::set_agent_config,
            // Native coding-harness readiness and explicit support refresh.
            workspaces::get_agent_harness_statuses,
            workspaces::refresh_agent_support,
            // Observability: record webview-side uncaught errors in the shell log.
            logging::log_frontend_error,
            // Engine status (lets a late-mounting pill seed itself).
            engine::get_engine_status,
            engine::get_engine_statuses,
            // Engine RPC proxy.
            rpc::engine_execute_script,
            rpc::engine_render,
            rpc::engine_get_model_info,
            rpc::engine_get_params,
            rpc::engine_get_assembly_tree,
            rpc::engine_get_workspace_meta,
            rpc::engine_set_params,
            rpc::engine_export,
            rpc::engine_export_with_override,
            rpc::engine_get_conformance,
            rpc::engine_get_readiness,
            rpc::engine_history,
            rpc::engine_undo,
            rpc::engine_redo,
            rpc::engine_goto,
            rpc::engine_feature_at,
            rpc::engine_set_feature,
            rpc::engine_set_part_material,
            rpc::engine_analyze_dfm,
            rpc::engine_measure,
            rpc::engine_stress_check,
            rpc::engine_tolerance_stack,
            rpc::engine_check_requirements,
            rpc::engine_set_requirements,
            rpc::engine_sweep,
            rpc::engine_optimize,
            rpc::engine_check_motion,
            rpc::engine_converge_to_spec,
            rpc::engine_analyze_import,
            rpc::engine_diff_against,
            rpc::engine_build_report,
            rpc::engine_import_reference,
            rpc::engine_stage_import,
            rpc::engine_get_import_capabilities,
            rpc::engine_remove_import,
            rpc::engine_create_drawing,
            rpc::engine_fab_detect,
            rpc::engine_fab_estimate,
            rpc::engine_fab_orient,
            rpc::engine_fab_open,
            rpc::get_build_brief,
            workspaces::pick_cad_file,
            updater::check_for_update,
            updater::download_and_install,
            updater::relaunch_for_update,
            // Reference library (verified real-world dims Sol learns during grounding).
            reference_library::get_reference_library,
            reference_library::save_reference_entry,
            reference_library::delete_reference_entry,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(move |app_handle, event| match event {
            // Reap on window close/destroy. CloseRequested matters on macOS, where
            // the window can close without firing Exit. (Force-quit can't be caught
            // here; the engine's own parent-death watchdog covers that.)
            RunEvent::WindowEvent {
                event: WindowEvent::CloseRequested { .. } | WindowEvent::Destroyed,
                ..
            } => shutdown(app_handle),
            // ...and on app exit, as a backstop.
            RunEvent::ExitRequested { .. } | RunEvent::Exit => shutdown(app_handle),
            _ => {}
        });
}
