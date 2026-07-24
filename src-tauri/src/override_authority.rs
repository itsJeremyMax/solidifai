//! In-memory capability authority for app-approved strict exports.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use hmac::{Hmac, KeyInit, Mac};
use parking_lot::Mutex;
use serde_json::{json, Value};
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

static LIVE_LISTENERS: AtomicUsize = AtomicUsize::new(0);

#[cfg(test)]
pub(crate) static LIFECYCLE_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

struct Pending {
    workspace: String,
    build_id: u64,
    format: String,
    nonce_id: String,
    expires_at: Instant,
}

/// The HMAC key and pending records never leave the Rust process.  The external
/// nonce is opaque and only valid while its matching record is still present.
pub struct OverrideAuthority {
    secret: [u8; 32],
    pending: Mutex<HashMap<String, Pending>>,
    ttl: Duration,
    next: AtomicU64,
    active: AtomicBool,
}

impl OverrideAuthority {
    pub fn new(ttl: Duration) -> Self {
        let mut secret = [0u8; 32];
        getrandom::fill(&mut secret).expect("OS randomness unavailable");
        Self {
            secret,
            pending: Mutex::new(HashMap::new()),
            ttl,
            next: AtomicU64::new(1),
            active: AtomicBool::new(true),
        }
    }

    pub fn issue(&self, workspace: &str, build_id: u64, format: &str) -> String {
        let sequence = self.next.fetch_add(1, Ordering::Relaxed);
        let mut random = [0u8; 16];
        getrandom::fill(&mut random).expect("OS randomness unavailable");
        let id = format!("{:016x}{}", sequence, hex(&random));
        let nonce_id = format!("override-{sequence}");
        let signature = self.sign(&id);
        let now = Instant::now();
        let mut pending = self.pending.lock();
        pending.retain(|_, record| record.expires_at > now);
        pending.insert(
            id.clone(),
            Pending {
                workspace: workspace.to_string(),
                build_id,
                format: format.to_string(),
                nonce_id,
                expires_at: now + self.ttl,
            },
        );
        format!("{id}.{}", hex(&signature))
    }

    /// Validates all claims then removes the record under the same mutex. A failed
    /// scope check leaves the nonce valid for the intended export; a successful
    /// match is irrevocably consumed before the caller can export.
    pub fn consume(
        &self,
        nonce: &str,
        workspace: &str,
        build_id: u64,
        format: &str,
    ) -> Option<String> {
        if !self.active.load(Ordering::Acquire) {
            return None;
        }
        let (id, signature) = nonce.split_once('.')?;
        let signature = decode_hex(signature)?;
        let mut mac = HmacSha256::new_from_slice(&self.secret).ok()?;
        mac.update(id.as_bytes());
        mac.verify_slice(&signature).ok()?;
        let now = Instant::now();
        let mut pending = self.pending.lock();
        pending.retain(|_, record| record.expires_at > now);
        let record = pending.get(id)?;
        if record.workspace != workspace || record.build_id != build_id || record.format != format {
            return None;
        }
        pending.remove(id).map(|record| record.nonce_id)
    }

    fn invalidate(&self) {
        self.active.store(false, Ordering::Release);
        self.pending.lock().clear();
    }

    fn sign(&self, id: &str) -> [u8; 32] {
        let mut mac = HmacSha256::new_from_slice(&self.secret).expect("HMAC accepts fixed key");
        mac.update(id.as_bytes());
        mac.finalize().into_bytes().into()
    }

    #[cfg(test)]
    pub(crate) fn pending_count(&self) -> usize {
        self.pending.lock().len()
    }
}

/// Start an endpoint private to one engine generation. The socket path is never
/// provisioned to MCP; the token is an additional application-layer check on all
/// platforms (including owner-only Unix sockets).
pub struct PrivateOverrideService {
    socket: PathBuf,
    private_dir: Option<PathBuf>,
    transport: crate::ipc::PrivateTransport,
    stopped: Arc<AtomicBool>,
    authority: Arc<OverrideAuthority>,
    listener: Mutex<Option<JoinHandle<()>>>,
    handlers: Arc<Mutex<Vec<JoinHandle<()>>>>,
}

impl PrivateOverrideService {
    pub fn stop(&self) {
        if self.stopped.swap(true, Ordering::AcqRel) {
            return;
        }
        self.authority.invalidate();
        // Wake the blocking accept. The listener sees `stopped` before dispatching
        // this connection, then exits and can be joined below.
        let _ = connect_transport(&self.transport);
        if let Some(listener) = self.listener.lock().take() {
            let _ = listener.join();
        }
        for handler in self.handlers.lock().drain(..) {
            let _ = handler.join();
        }
        let _ = std::fs::remove_file(&self.socket);
        if let Some(dir) = &self.private_dir {
            let _ = std::fs::remove_dir(dir);
        }
    }

    pub fn transport(&self) -> crate::ipc::PrivateTransport {
        self.transport.clone()
    }

    #[cfg(test)]
    fn live_count() -> usize {
        LIVE_LISTENERS.load(Ordering::Acquire)
    }
}

impl Drop for PrivateOverrideService {
    fn drop(&mut self) {
        self.stop();
    }
}

pub fn serve_private(
    sock: &Path,
    authority: Arc<OverrideAuthority>,
) -> Result<PrivateOverrideService, String> {
    serve_private_inner(sock, None, authority)
}

pub fn private_endpoint() -> Result<(PathBuf, PathBuf), String> {
    #[cfg(unix)]
    let root = PathBuf::from("/tmp");
    #[cfg(not(unix))]
    let root = std::env::temp_dir();
    for _ in 0..16 {
        let mut random = [0u8; 24];
        getrandom::fill(&mut random)
            .map_err(|_| "create private override directory".to_string())?;
        let dir = root.join(format!("solidifai-override-{}", hex(&random)));
        let mut builder = std::fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        match builder.create(&dir) {
            Ok(()) => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700))
                        .map_err(|_| "secure private override directory".to_string())?;
                }
                return Ok((dir.clone(), dir.join("authority.sock")));
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err("create private override directory".into()),
        }
    }
    Err("create private override directory".into())
}

pub fn serve_private_endpoint(
    authority: Arc<OverrideAuthority>,
) -> Result<PrivateOverrideService, String> {
    let (dir, socket) = private_endpoint()?;
    match serve_private_inner(&socket, Some(dir.clone()), authority) {
        Ok(service) => Ok(service),
        Err(error) => {
            let _ = std::fs::remove_dir_all(dir);
            Err(error)
        }
    }
}

fn serve_private_inner(
    sock: &Path,
    private_dir: Option<PathBuf>,
    authority: Arc<OverrideAuthority>,
) -> Result<PrivateOverrideService, String> {
    let (listener, transport) = crate::ipc::IpcListener::bind_private(sock)
        .map_err(|e| format!("bind private override control: {e}"))?;
    let stopped = Arc::new(AtomicBool::new(false));
    let listener_stopped = stopped.clone();
    let listener_authority = authority.clone();
    let handlers = Arc::new(Mutex::new(Vec::<JoinHandle<()>>::new()));
    let listener_handlers = handlers.clone();
    LIVE_LISTENERS.fetch_add(1, Ordering::AcqRel);
    let listener = std::thread::spawn(move || {
        loop {
            match listener.accept() {
                Ok((mut stream, transport_token)) => {
                    if listener_stopped.load(Ordering::Acquire) {
                        break;
                    }
                    let stopped = listener_stopped.clone();
                    let authority = listener_authority.clone();
                    listener_handlers
                        .lock()
                        .retain(|handler| !handler.is_finished());
                    listener_handlers.lock().push(std::thread::spawn(move || {
                        let _ = handle_private(
                            &mut stream,
                            transport_token.as_deref(),
                            &authority,
                            &stopped,
                        );
                    }));
                }
                Err(_) if listener_stopped.load(Ordering::Acquire) => break,
                Err(_) => continue,
            }
        }
        LIVE_LISTENERS.fetch_sub(1, Ordering::AcqRel);
    });
    Ok(PrivateOverrideService {
        socket: sock.to_path_buf(),
        private_dir,
        transport,
        stopped,
        authority,
        listener: Mutex::new(Some(listener)),
        handlers,
    })
}

fn handle_private(
    stream: &mut crate::ipc::IpcStream,
    transport_token: Option<&str>,
    authority: &OverrideAuthority,
    stopped: &AtomicBool,
) -> std::io::Result<()> {
    stream.set_read_timeout(Some(Duration::from_millis(100)))?;
    if let Some(expected) = transport_token {
        if !authenticate_private(stream, expected, stopped)? {
            return Ok(());
        }
    }
    let Some(bytes) = read_private_line(stream, stopped, 16 * 1024)? else {
        return Ok(());
    };
    let response = dispatch_private(&String::from_utf8_lossy(&bytes), authority);
    stream.write_all(format!("{response}\n").as_bytes())?;
    stream.flush()
}

fn read_private_line(
    stream: &mut crate::ipc::IpcStream,
    stopped: &AtomicBool,
    max: usize,
) -> std::io::Result<Option<Vec<u8>>> {
    let mut bytes = Vec::new();
    let mut byte = [0u8; 1];
    while !stopped.load(Ordering::Acquire) {
        match stream.read(&mut byte) {
            Ok(0) => return Ok(None),
            Ok(_) if byte[0] == b'\n' => return Ok(Some(bytes)),
            Ok(_) if bytes.len() >= max => return Ok(None),
            Ok(_) => bytes.push(byte[0]),
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock
                ) => {}
            Err(error) => return Err(error),
        }
    }
    Ok(None)
}

fn authenticate_private(
    stream: &mut crate::ipc::IpcStream,
    expected: &str,
    stopped: &AtomicBool,
) -> std::io::Result<bool> {
    let Some(presented) = read_private_line(stream, stopped, 256)? else {
        return Ok(false);
    };
    let expected = expected.as_bytes();
    let mut diff = presented.len() ^ expected.len();
    for (index, &byte) in expected.iter().enumerate() {
        diff |= usize::from(presented.get(index).copied().unwrap_or(0) ^ byte);
    }
    Ok(diff == 0)
}

fn connect_transport(
    transport: &crate::ipc::PrivateTransport,
) -> std::io::Result<crate::ipc::IpcStream> {
    match transport {
        #[cfg(unix)]
        crate::ipc::PrivateTransport::Unix { path } => crate::ipc::connect(path),
        crate::ipc::PrivateTransport::Tcp { address, token } => {
            let mut stream = TcpStream::connect(address)?;
            stream.write_all(format!("{token}\n").as_bytes())?;
            Ok(crate::ipc::IpcStream::Tcp(stream))
        }
        #[cfg(not(unix))]
        crate::ipc::PrivateTransport::Unix { .. } => unreachable!("unix transport on Windows"),
    }
}

fn dispatch_private(line: &str, authority: &OverrideAuthority) -> Value {
    let Ok(request) = serde_json::from_str::<Value>(line) else {
        return json!({"ok": false});
    };
    if request.get("op").and_then(Value::as_str) != Some("consume_export_override") {
        return json!({"ok": false});
    }
    let Some(nonce) = request.get("nonce").and_then(Value::as_str) else {
        return json!({"ok": false});
    };
    let Some(workspace) = request.get("workspaceId").and_then(Value::as_str) else {
        return json!({"ok": false});
    };
    let Some(build_id) = request.get("buildId").and_then(Value::as_u64) else {
        return json!({"ok": false});
    };
    let Some(format) = request.get("format").and_then(Value::as_str) else {
        return json!({"ok": false});
    };
    authority
        .consume(nonce, workspace, build_id, format)
        .map(|nonce_id| json!({"ok": true, "nonceId": nonce_id}))
        .unwrap_or_else(|| json!({"ok": false}))
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if !value.len().is_multiple_of(2) {
        return None;
    }
    (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&value[i..i + 2], 16).ok())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn private_dispatch_rejects_forged_or_wrongly_scoped_requests() {
        let authority = OverrideAuthority::new(Duration::from_secs(60));
        let nonce = authority.issue("/workspace", 4, "stl");
        let forged = dispatch_private(
            r#"{"op":"consume_export_override","token":"wrong","nonce":"x","workspaceId":"/workspace","buildId":4,"format":"stl"}"#,
            &authority,
        );
        assert_eq!(forged["ok"], false);
        let wrong_scope = dispatch_private(
            &json!({"op":"consume_export_override","token":"token","nonce":nonce,"workspaceId":"/workspace","buildId":5,"format":"stl"}).to_string(),
            &authority,
        );
        assert_eq!(wrong_scope["ok"], false);
        let valid = dispatch_private(
            &json!({"op":"consume_export_override","token":"token","nonce":nonce,"workspaceId":"/workspace","buildId":4,"format":"stl"}).to_string(),
            &authority,
        );
        assert_eq!(valid["ok"], true);
        assert_eq!(valid["nonceId"], "override-1");
    }

    #[test]
    fn restart_authority_invalidates_prior_nonce() {
        let old = OverrideAuthority::new(Duration::from_secs(60));
        let nonce = old.issue("/workspace", 4, "stl");
        let restarted = OverrideAuthority::new(Duration::from_secs(60));
        assert!(restarted.consume(&nonce, "/workspace", 4, "stl").is_none());
    }

    #[test]
    fn issue_and_consume_prune_expired_pending_records() {
        let authority = OverrideAuthority::new(Duration::from_millis(1));
        let expired = authority.issue("/workspace", 4, "stl");
        std::thread::sleep(Duration::from_millis(5));
        let live = authority.issue("/workspace", 5, "stl");
        assert_eq!(authority.pending_count(), 1, "issue prunes expired records");
        std::thread::sleep(Duration::from_millis(5));
        assert!(authority.consume(&live, "/workspace", 5, "stl").is_none());
        assert_eq!(
            authority.pending_count(),
            0,
            "consume prunes expired records"
        );
        assert!(authority
            .consume(&expired, "/workspace", 4, "stl")
            .is_none());
    }

    #[test]
    fn stopping_private_service_reaps_listener_and_refuses_old_endpoint() {
        let _guard = LIFECYCLE_TEST_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        let socket = dir.path().join("override.sock");
        let old_authority = Arc::new(OverrideAuthority::new(Duration::from_secs(60)));
        let old_nonce = old_authority.issue("/workspace", 4, "stl");
        let service = serve_private(&socket, old_authority.clone()).unwrap();
        assert_eq!(PrivateOverrideService::live_count(), 1);
        service.stop();
        assert_eq!(PrivateOverrideService::live_count(), 0);
        assert!(!socket.exists());
        assert!(crate::ipc::connect(socket.to_str().unwrap()).is_err());
        assert!(old_authority
            .consume(&old_nonce, "/workspace", 4, "stl")
            .is_none());

        let new_authority = Arc::new(OverrideAuthority::new(Duration::from_secs(60)));
        let new_nonce = new_authority.issue("/workspace", 4, "stl");
        assert!(new_authority
            .consume(&old_nonce, "/workspace", 4, "stl")
            .is_none());
        let replacement = serve_private(&socket, new_authority.clone()).unwrap();
        assert_eq!(PrivateOverrideService::live_count(), 1);
        assert!(new_authority
            .consume(&new_nonce, "/workspace", 4, "stl")
            .is_some());
        replacement.stop();
    }

    #[test]
    fn repeated_private_service_restarts_leave_no_listeners() {
        let _guard = LIFECYCLE_TEST_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        let socket = dir.path().join("override.sock");
        for _ in 0..3 {
            let service = serve_private(
                &socket,
                Arc::new(OverrideAuthority::new(Duration::from_secs(60))),
            )
            .unwrap();
            assert_eq!(PrivateOverrideService::live_count(), 1);
            service.stop();
            assert_eq!(PrivateOverrideService::live_count(), 0);
        }
    }

    #[test]
    fn private_listener_errors_do_not_disclose_its_endpoint() {
        let dir = tempfile::tempdir().unwrap();
        let socket = dir.path().join("missing").join("override.sock");
        let error = match serve_private(
            &socket,
            Arc::new(OverrideAuthority::new(Duration::from_secs(60))),
        ) {
            Ok(_) => panic!("binding below a missing directory must fail"),
            Err(error) => error,
        };
        assert!(!error.contains(socket.to_string_lossy().as_ref()));
    }

    #[test]
    fn private_endpoint_is_random_and_owner_only_outside_app_state() {
        let (first_dir, first_socket) = private_endpoint().unwrap();
        let (second_dir, second_socket) = private_endpoint().unwrap();
        assert_ne!(first_dir, second_dir);
        assert_eq!(first_socket.parent(), Some(first_dir.as_path()));
        assert_eq!(second_socket.parent(), Some(second_dir.as_path()));
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                std::fs::metadata(&first_dir).unwrap().permissions().mode() & 0o777,
                0o700
            );
        }
        std::fs::remove_dir_all(first_dir).unwrap();
        std::fs::remove_dir_all(second_dir).unwrap();
    }

    #[test]
    fn idle_client_cannot_block_valid_private_request_or_stop() {
        let _guard = LIFECYCLE_TEST_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        let socket = dir.path().join("override.sock");
        let authority = Arc::new(OverrideAuthority::new(Duration::from_secs(60)));
        let nonce = authority.issue("/workspace", 4, "stl");
        let service = serve_private(&socket, authority).unwrap();
        let _idle = crate::ipc::connect(socket.to_string_lossy().as_ref()).unwrap();

        let mut valid = crate::ipc::connect(socket.to_string_lossy().as_ref()).unwrap();
        valid
            .write_all(
                json!({
                    "op": "consume_export_override",
                    "nonce": nonce,
                    "workspaceId": "/workspace",
                    "buildId": 4,
                    "format": "stl",
                })
                .to_string()
                .as_bytes(),
            )
            .unwrap();
        valid.write_all(b"\n").unwrap();
        valid
            .set_read_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        let mut response = String::new();
        valid.read_to_string(&mut response).unwrap();
        assert!(response.contains("\"ok\":true"), "response: {response}");

        let start = Instant::now();
        service.stop();
        assert!(
            start.elapsed() < Duration::from_secs(1),
            "stop blocked on idle client"
        );
    }
}
