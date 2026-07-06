//! Cross-platform local IPC endpoints for the engine RPC and control channels.
//!
//! Unix: an AF_UNIX socket at the given path, owner-only (mode 0600). Windows
//! has no AF_UNIX support in std or CPython, so there the *path* is a small
//! file holding `127.0.0.1:<port>\n<token>`: the listener binds a loopback TCP
//! port and writes the file, and clients read it, connect, and send the token
//! as their first line (a bare loopback port would be reachable by any local
//! process). ACLs on the pointer file gate access the way socket modes do on
//! unix, because every endpoint lives in a user-owned directory: the control
//! socket and the per-workspace engine endpoints are all under the app config
//! dir (provision.rs `IPC_DIR`), never under the user-chosen workspace root.
//! Readiness semantics match unix: the path
//! appears once the listener is up. The Python twin is
//! `engine/solidifai_engine/ipc.py`.
//!
//! The TCP flavor compiles and is tested on every platform (only the
//! platform-default `bind`/`connect` choice is cfg-gated), so unix CI
//! exercises the exact code Windows runs.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
#[cfg(unix)]
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::time::Duration;

pub enum IpcStream {
    #[cfg(unix)]
    Unix(UnixStream),
    Tcp(TcpStream),
}

impl IpcStream {
    pub fn set_read_timeout(&self, d: Option<Duration>) -> std::io::Result<()> {
        match self {
            #[cfg(unix)]
            Self::Unix(s) => s.set_read_timeout(d),
            Self::Tcp(s) => s.set_read_timeout(d),
        }
    }
    pub fn set_write_timeout(&self, d: Option<Duration>) -> std::io::Result<()> {
        match self {
            #[cfg(unix)]
            Self::Unix(s) => s.set_write_timeout(d),
            Self::Tcp(s) => s.set_write_timeout(d),
        }
    }
}

impl Read for IpcStream {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        match self {
            #[cfg(unix)]
            Self::Unix(s) => s.read(buf),
            Self::Tcp(s) => s.read(buf),
        }
    }
}

impl Write for IpcStream {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        match self {
            #[cfg(unix)]
            Self::Unix(s) => s.write(buf),
            Self::Tcp(s) => s.write(buf),
        }
    }
    fn flush(&mut self) -> std::io::Result<()> {
        match self {
            #[cfg(unix)]
            Self::Unix(s) => s.flush(),
            Self::Tcp(s) => s.flush(),
        }
    }
}

pub enum IpcListener {
    #[cfg(unix)]
    Unix(UnixListener),
    Tcp {
        listener: TcpListener,
        token: String,
    },
}

impl IpcListener {
    /// Bind the platform-default listener for `path`.
    pub fn bind(path: &Path) -> std::io::Result<Self> {
        #[cfg(unix)]
        {
            Self::bind_unix(path)
        }
        #[cfg(not(unix))]
        {
            Self::bind_tcp(path)
        }
    }

    #[cfg(unix)]
    fn bind_unix(path: &Path) -> std::io::Result<Self> {
        let _ = std::fs::remove_file(path); // stale socket from a prior run
        let listener = UnixListener::bind(path)?;
        // Owner-only: these are write-capable control surfaces, so they must
        // not depend on the parent dir's mode for access control.
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
        Ok(Self::Unix(listener))
    }

    /// TCP flavor, available on every platform so unix tests cover it.
    pub fn bind_tcp(path: &Path) -> std::io::Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        let token = new_token()?;
        let tmp = path.with_extension("tmp");
        std::fs::write(&tmp, format!("{}\n{}\n", listener.local_addr()?, token))?;
        std::fs::rename(&tmp, path)?; // atomic: a reader never sees half a file
        Ok(Self::Tcp { listener, token })
    }

    /// Block for the next connection. Returns the stream plus the token the
    /// client must present as its first line (None on unix, where the socket
    /// mode is the access control). Callers verify via [`authenticate`] on the
    /// connection's own thread, so a stalling client can't block accepts.
    pub fn accept(&self) -> std::io::Result<(IpcStream, Option<String>)> {
        match self {
            #[cfg(unix)]
            Self::Unix(l) => l.accept().map(|(s, _)| (IpcStream::Unix(s), None)),
            Self::Tcp { listener, token } => listener
                .accept()
                .map(|(s, _)| (IpcStream::Tcp(s), Some(token.clone()))),
        }
    }
}

/// Connect to the platform-default listener at `path`.
pub fn connect(path: &str) -> std::io::Result<IpcStream> {
    #[cfg(unix)]
    {
        Ok(IpcStream::Unix(UnixStream::connect(path)?))
    }
    #[cfg(not(unix))]
    {
        connect_tcp(path)
    }
}

/// TCP flavor, available on every platform so unix tests cover it. Reads the
/// address + token from the pointer file and sends the token line immediately.
pub fn connect_tcp(path: &str) -> std::io::Result<IpcStream> {
    let content = std::fs::read_to_string(path)?;
    let mut lines = content.lines();
    let addr = lines.next().unwrap_or_default().trim();
    let token = lines.next().unwrap_or_default().trim();
    let mut stream = TcpStream::connect(addr)?;
    if !token.is_empty() {
        stream.write_all(format!("{token}\n").as_bytes())?;
    }
    Ok(IpcStream::Tcp(stream))
}

/// Consume and verify the client's token line. Returns Ok(true) when it
/// matches, Ok(false) when it doesn't (caller drops the connection). The
/// caller must have set a read timeout first.
pub fn authenticate(stream: &mut IpcStream, expected: &str) -> std::io::Result<bool> {
    let mut buf = Vec::with_capacity(64);
    let mut byte = [0u8; 1];
    loop {
        match stream.read(&mut byte) {
            Ok(0) => return Ok(false),
            Ok(_) => {
                if byte[0] == b'\n' {
                    break;
                }
                buf.push(byte[0]);
                if buf.len() > 256 {
                    return Ok(false);
                }
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    // Constant-time compare: fold every byte so timing never leaks how long a
    // prefix matched (hmac.compare_digest is the Python-twin equivalent).
    let presented = String::from_utf8_lossy(&buf);
    let presented = presented.trim().as_bytes();
    let expected = expected.as_bytes();
    let mut diff = presented.len() ^ expected.len();
    for (i, &e) in expected.iter().enumerate() {
        diff |= usize::from(presented.get(i).copied().unwrap_or(0) ^ e);
    }
    Ok(diff == 0)
}

fn new_token() -> std::io::Result<String> {
    let mut bytes = [0u8; 16];
    getrandom::fill(&mut bytes).map_err(std::io::Error::other)?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tcp_pointer_file_round_trip_with_token() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ep.sock");
        let listener = IpcListener::bind_tcp(&path).unwrap();

        let content = std::fs::read_to_string(&path).unwrap();
        let mut lines = content.lines();
        assert!(lines.next().unwrap().starts_with("127.0.0.1:"));
        assert_eq!(lines.next().unwrap().len(), 32, "hex token");

        let path_str = path.to_string_lossy().into_owned();
        let server = std::thread::spawn(move || {
            let (mut stream, token) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            assert!(authenticate(&mut stream, token.as_deref().unwrap()).unwrap());
            let mut b = [0u8; 3];
            stream.read_exact(&mut b).unwrap();
            stream.write_all(b"pong").unwrap();
        });
        let mut c = connect_tcp(&path_str).unwrap();
        c.write_all(b"abc").unwrap();
        let mut resp = [0u8; 4];
        c.read_exact(&mut resp).unwrap();
        assert_eq!(&resp, b"pong");
        server.join().unwrap();
    }

    #[test]
    fn tcp_rejects_wrong_token() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ep.sock");
        let listener = IpcListener::bind_tcp(&path).unwrap();
        let addr = std::fs::read_to_string(&path)
            .unwrap()
            .lines()
            .next()
            .unwrap()
            .to_string();

        let server = std::thread::spawn(move || {
            let (mut stream, token) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            authenticate(&mut stream, token.as_deref().unwrap()).unwrap()
        });
        let mut c = TcpStream::connect(addr).unwrap();
        c.write_all(b"not-the-token\n").unwrap();
        assert!(!server.join().unwrap(), "wrong token must not authenticate");
    }
}
