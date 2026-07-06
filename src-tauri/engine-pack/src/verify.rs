use crate::hash::sha256_file;
use crate::manifest::{EntryKind, Manifest};
use minisign_verify::{PublicKey, Signature};
use std::collections::BTreeSet;
use std::path::Path;
use walkdir::WalkDir;

/// Verify `root` is exactly the tree `manifest` describes — every entry matches
/// and no extra files (the archive is only sha-bound, so the signed manifest rules).
pub fn verify_tree(root: &Path, manifest: &Manifest) -> anyhow::Result<()> {
    let mut expected: BTreeSet<&str> = BTreeSet::new();
    for entry in &manifest.files {
        expected.insert(entry.path.as_str());
        let p = root.join(&entry.path);
        match entry.kind {
            EntryKind::File => {
                let want = entry.sha256.as_deref().unwrap_or("");
                let got = sha256_file(&p)
                    .map_err(|e| anyhow::anyhow!("missing file {}: {e}", entry.path))?;
                if got != want {
                    anyhow::bail!("hash mismatch for {}: {} != {}", entry.path, got, want);
                }
            }
            EntryKind::Symlink => {
                let target = std::fs::read_link(&p)
                    .map_err(|e| anyhow::anyhow!("missing symlink {}: {e}", entry.path))?
                    .to_string_lossy()
                    .replace('\\', "/");
                if Some(target.as_str()) != entry.target.as_deref() {
                    anyhow::bail!("symlink target mismatch for {}", entry.path);
                }
            }
        }
    }
    // reject anything on disk not in the manifest (dirs are implied by paths)
    for entry in WalkDir::new(root).min_depth(1) {
        let entry = entry?;
        if entry.file_type().is_dir() && !entry.path_is_symlink() {
            continue;
        }
        let rel = entry
            .path()
            .strip_prefix(root)?
            .to_string_lossy()
            .replace('\\', "/");
        if !expected.contains(rel.as_str()) {
            anyhow::bail!("unexpected file not in manifest: {rel}");
        }
    }
    Ok(())
}

/// Verify a detached minisign signature over `manifest_bytes`.
///
/// `pubkey_b64` is the value embedded in `tauri.conf.json`
/// `plugins.updater.pubkey` — base64 of the minisign public-key *file* (a
/// comment line plus the key line). `sig_b64` is base64 of the minisign `.minisig`
/// text, exactly what `tauri signer sign` writes to the `.sig` sidecar. We reuse
/// the app's existing updater key, so the engine and the app share one trust
/// anchor. Returns Ok(()) iff the signature is valid for these exact bytes.
pub fn verify_manifest_signature(
    manifest_bytes: &[u8],
    sig_b64: &str,
    pubkey_b64: &str,
) -> anyhow::Result<()> {
    // The embedded pubkey is base64 of the two-line .pub file; the key is its
    // last non-empty line.
    let pub_file = String::from_utf8(base64_decode(pubkey_b64)?)
        .map_err(|_| anyhow::anyhow!("pubkey is not utf-8 after base64 decode"))?;
    let key_line = pub_file
        .lines()
        .rev()
        .find(|l| !l.trim().is_empty())
        .ok_or_else(|| anyhow::anyhow!("empty pubkey"))?
        .trim();
    let pk = PublicKey::from_base64(key_line)
        .map_err(|e| anyhow::anyhow!("bad minisign pubkey: {e}"))?;

    let sig_text = String::from_utf8(base64_decode(sig_b64)?)
        .map_err(|_| anyhow::anyhow!("signature is not utf-8 after base64 decode"))?;
    let sig = Signature::decode(&sig_text).map_err(|e| anyhow::anyhow!("bad signature: {e}"))?;

    pk.verify(manifest_bytes, &sig, false)
        .map_err(|e| anyhow::anyhow!("signature verification failed: {e}"))?;
    Ok(())
}

/// Standard base64 decode (alphabet `A-Za-z0-9+/`, padding/newlines ignored).
/// Kept local to avoid pulling a base64 crate for one call site.
fn base64_decode(s: &str) -> anyhow::Result<Vec<u8>> {
    const T: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut lut = [255u8; 256];
    for (i, &c) in T.iter().enumerate() {
        lut[c as usize] = i as u8;
    }
    let mut out = Vec::new();
    let mut buf = 0u32;
    let mut bits = 0u32;
    for &c in s.trim().as_bytes() {
        if c == b'=' || c == b'\n' || c == b'\r' || c == b' ' {
            continue;
        }
        let v = lut[c as usize];
        if v == 255 {
            anyhow::bail!("invalid base64 byte {c:#x}");
        }
        buf = (buf << 6) | v as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod sig_tests {
    use super::*;

    // A real fixture produced by `tauri signer` with a throwaway key:
    //   key:  tauri signer generate -p "" -w key
    //   sig:  tauri signer sign -f key -p "" msg.json
    // MSG is the exact 83 bytes that were signed.
    const PUBKEY_B64: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDE3QTc4NEQzQzlBMkIwRUQKUldUdHNLTEowNFNuRjl5L2ZMd3FmWjhPWFRTNFpFYVJyUkk5ZHNZMVNCLzU3Q2gyUldhUmRucHYK";
    const SIG_B64: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkKUlVUdHNLTEowNFNuRjdlbDAveTJhdEpCb0ZFV2hYTi96V1ZHdTJzQUlBRHVoZDFhelp3OGhuN1hveVo0MWxTdGN5U0xUUSs3VEUweE0zODVybFJBRGZGbTJVWlQ0SDAxN1E0PQp0cnVzdGVkIGNvbW1lbnQ6IHRpbWVzdGFtcDoxNzgwNjQ4ODU3CWZpbGU6ZXBfbXNnLmpzb24KclNrRzZVamtHTXUrZmVBNzA4dnVaWFkzQmxrU1psQ2ZmdDVHSnRVNEZoelhzZ3hOWXpoRnVWeFkxU1hVTENWb0k5NGgwTmlGMm1GUm5uME83M0V6REE9PQo=";
    const MSG: &[u8] =
        br#"{"engineRev":"r1","platform":"darwin-aarch64","files":[],"manifestHash":"deadbeef"}"#;

    #[test]
    fn accepts_valid_signature() {
        verify_manifest_signature(MSG, SIG_B64, PUBKEY_B64)
            .expect("valid tauri signature accepted");
    }

    #[test]
    fn rejects_tampered_message() {
        let mut tampered = MSG.to_vec();
        let last = tampered.len() - 2; // flip a byte inside "deadbeef"
        tampered[last] ^= 0x01;
        assert!(verify_manifest_signature(&tampered, SIG_B64, PUBKEY_B64).is_err());
    }

    #[test]
    fn rejects_wrong_key() {
        // A different (valid-shape) key must not verify this signature.
        let other = "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXkKUldRZjZMUkNHQTlpNTNtbFllY080SXpUNTFUR1Bwdld1Y05TQ2gxQ0JNMFFUYUxuNzNZN0dGTzMK";
        assert!(verify_manifest_signature(MSG, SIG_B64, other).is_err());
    }
}
