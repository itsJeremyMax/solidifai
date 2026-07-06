//! Boundary validation for filesystem paths the webview hands to engine
//! commands (export / import / drawing targets).
//!
//! These targets are intentionally user-chosen via native Save/Open dialogs
//! (export to anywhere, import from anywhere), so we deliberately do NOT confine
//! them to the workspace. The primary controls against a misbehaving frontend
//! are the Content-Security-Policy (which blocks the XSS that could forge such a
//! call) and the native dialogs themselves. This is defense-in-depth at the IPC
//! boundary: reject only malformed input before forwarding it to the engine.

use std::path::PathBuf;

/// Validate a path supplied by the webview for a read/write command. Rejects
/// empty paths, embedded NUL (which would corrupt OS/CString calls), and
/// non-absolute paths (dialogs and the workspace fallbacks always produce
/// absolute paths, so a relative one signals malformed input).
pub fn validate_outgoing_path(path: &str) -> Result<PathBuf, String> {
    if path.is_empty() {
        return Err("path must not be empty".to_string());
    }
    if path.contains('\0') {
        return Err("path contains an invalid NUL byte".to_string());
    }
    let p = PathBuf::from(path);
    if !p.is_absolute() {
        return Err("path must be absolute".to_string());
    }
    Ok(p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_absolute_paths() {
        #[cfg(unix)]
        let ok = "/Users/me/Desktop/model.stl";
        #[cfg(windows)]
        let ok = r"C:\Users\me\Desktop\model.stl";
        assert!(validate_outgoing_path(ok).is_ok());
    }

    #[test]
    fn rejects_empty() {
        assert!(validate_outgoing_path("").is_err());
    }

    #[test]
    fn rejects_nul_byte() {
        assert!(validate_outgoing_path("/tmp/evil\0.stl").is_err());
    }

    #[test]
    fn rejects_relative() {
        assert!(validate_outgoing_path("../../etc/passwd").is_err());
        assert!(validate_outgoing_path("model.stl").is_err());
    }
}
