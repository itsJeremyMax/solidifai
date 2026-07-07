//! Fetch a content-addressed engine from the `engine` release when the cache
//! lacks the pinned one. Network + verify + assemble; reuses engine-pack for the
//! format/verify and engine_cache for the atomic swap. `ensure` is generic over a
//! `Transport` so the whole flow tests without a network.

use crate::engine_cache::EngineCache;
use crate::engine_pin::EnginePin;
use engine_pack::manifest::Manifest;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Deserialize)]
pub struct EngineIndex {
    #[serde(rename = "latestRev")]
    pub latest_rev: String,
    pub revs: BTreeMap<String, RevEntry>,
}

#[derive(Deserialize)]
pub struct RevEntry {
    #[serde(default)]
    pub prev: Option<String>,
    pub platforms: BTreeMap<String, PlatformEntry>,
}

#[derive(Deserialize)]
pub struct PlatformEntry {
    pub manifest: String,
    #[serde(rename = "manifestSig")]
    pub manifest_sig: String,
    #[serde(rename = "manifestHash")]
    pub manifest_hash: String,
    pub full: String,
    #[serde(rename = "fullSha256")]
    pub full_sha256: String,
    #[serde(default)]
    pub pack: Option<PackEntry>,
}

#[derive(Deserialize)]
pub struct PackEntry {
    pub from: String,
    pub url: String,
    pub sha256: String,
}

pub struct Download {
    pub manifest_url: String,
    pub sig_url: String,
    pub expected_manifest_hash: String,
    pub archive_url: String,
    pub archive_sha256: String,
    pub use_base: bool,
}

fn resolve_platform<'a>(
    index: &'a EngineIndex,
    pin: &EnginePin,
    platform: &str,
) -> anyhow::Result<&'a PlatformEntry> {
    let rev = index
        .revs
        .get(&pin.engine_rev)
        .ok_or_else(|| anyhow::anyhow!("engineRev {} not in index", pin.engine_rev))?;
    rev.platforms
        .get(platform)
        .ok_or_else(|| anyhow::anyhow!("platform {platform} not in index rev {}", pin.engine_rev))
}

fn full_download(plat: &PlatformEntry) -> Download {
    Download {
        manifest_url: plat.manifest.clone(),
        sig_url: plat.manifest_sig.clone(),
        expected_manifest_hash: plat.manifest_hash.clone(),
        archive_url: plat.full.clone(),
        archive_sha256: plat.full_sha256.clone(),
        use_base: false,
    }
}

/// Pick the smallest archive we can apply: the pack when its `from` matches our
/// current engine rev (the delta base is present), else the full archive.
pub fn plan_download(
    index: &EngineIndex,
    pin: &EnginePin,
    platform: &str,
    current_rev: Option<&str>,
) -> anyhow::Result<Download> {
    let plat = resolve_platform(index, pin, platform)?;
    let pack = plat
        .pack
        .as_ref()
        .filter(|p| current_rev == Some(p.from.as_str()));

    Ok(match pack {
        Some(p) => Download {
            manifest_url: plat.manifest.clone(),
            sig_url: plat.manifest_sig.clone(),
            expected_manifest_hash: plat.manifest_hash.clone(),
            archive_url: p.url.clone(),
            archive_sha256: p.sha256.clone(),
            use_base: true,
        },
        None => full_download(plat),
    })
}

/// The full-archive download for the pinned rev, ignoring any incremental pack.
/// Used to self-heal a failed incremental apply: the full archive is
/// self-contained, so it recovers even when the client's delta base is corrupted
/// (e.g. runtime-mutated bytecode that no longer matches the signed manifest).
pub fn full_fallback(
    index: &EngineIndex,
    pin: &EnginePin,
    platform: &str,
) -> anyhow::Result<Download> {
    Ok(full_download(resolve_platform(index, pin, platform)?))
}

pub trait Transport {
    fn get(&self, url: &str) -> anyhow::Result<Vec<u8>>;

    /// Stream `url` into the file at `dest`, reporting `(downloaded, total)` as
    /// bytes arrive. The default buffers via `get` (one final callback) so test
    /// transports need not implement it; the real transport streams to disk so
    /// the full engine archive never sits in memory.
    fn get_to_file(
        &self,
        url: &str,
        dest: &Path,
        on: &mut dyn FnMut(u64, Option<u64>),
    ) -> anyhow::Result<()> {
        let bytes = self.get(url)?;
        std::fs::write(dest, &bytes)?;
        on(bytes.len() as u64, Some(bytes.len() as u64));
        Ok(())
    }
}

/// Fetch + verify (sha256 + signature + every file) + assemble + atomically
/// install the engine the pin requires. Returns the installed engine dir. The
/// prior engine is untouched on any failure.
#[allow(clippy::too_many_arguments)]
pub fn ensure(
    transport: &dyn Transport,
    cache: &EngineCache,
    index_url: &str,
    pin: &EnginePin,
    platform: &str,
    current_rev: Option<&str>,
    current_dir: Option<&Path>,
    pubkey_b64: &str,
    on_progress: &mut dyn FnMut(u64, Option<u64>),
) -> anyhow::Result<PathBuf> {
    let index: EngineIndex = serde_json::from_slice(&transport.get(index_url)?)?;
    let dl = plan_download(&index, pin, platform, current_rev)?;

    let manifest_bytes = transport.get(&dl.manifest_url)?;
    let sig = String::from_utf8(transport.get(&dl.sig_url)?)?;
    engine_pack::verify::verify_manifest_signature(&manifest_bytes, &sig, pubkey_b64)?;

    let manifest: Manifest = serde_json::from_slice(&manifest_bytes)?;
    if manifest.manifest_hash != pin.manifest_hash
        || manifest.manifest_hash != dl.expected_manifest_hash
    {
        anyhow::bail!("manifest hash disagrees with the pin or the index");
    }

    // Apply the planned archive. If an incremental (base-dependent) apply fails,
    // self-heal by retrying once with the self-contained full archive: the delta
    // base may be corrupted (e.g. runtime-mutated stdlib bytecode that no longer
    // matches the signed manifest), and the full archive does not depend on it.
    let result = download_and_install(transport, cache, &manifest, &dl, current_dir, on_progress);
    if result.is_err() && dl.use_base {
        tracing::warn!(
            "incremental engine update failed, retrying with the full archive: {:#}",
            result.as_ref().unwrap_err()
        );
        let dl_full = full_fallback(&index, pin, platform)?;
        return download_and_install(
            transport,
            cache,
            &manifest,
            &dl_full,
            current_dir,
            on_progress,
        );
    }
    result
}

/// Download `dl`'s archive to disk, verify its sha256, assemble the tree (sourcing
/// unchanged files from `current_dir` when `dl.use_base`), verify every file
/// against `manifest`, and atomically install. The archive is streamed to disk
/// (never buffered in memory) and removed afterward; staging is removed on
/// failure. The prior engine is untouched on any failure.
fn download_and_install(
    transport: &dyn Transport,
    cache: &EngineCache,
    manifest: &Manifest,
    dl: &Download,
    current_dir: Option<&Path>,
    on_progress: &mut dyn FnMut(u64, Option<u64>),
) -> anyhow::Result<PathBuf> {
    // Archive name derived from the manifest hash (unique per engine); staging is
    // unique per attempt. Downloaded straight to disk and verified from there so
    // the multi-hundred-MB archive never sits in memory.
    let staging = cache.staging_dir(&manifest.manifest_hash);
    std::fs::create_dir_all(staging.parent().unwrap())?;
    let archive_path = cache
        .root()
        .join(".staging")
        .join(format!("{}.tar.zst", manifest.manifest_hash));
    if let Err(e) = transport.get_to_file(&dl.archive_url, &archive_path, on_progress) {
        // A failed download must not strand a multi-hundred-MB partial archive
        // until some future successful resolve's gc (never, if the user stays
        // offline). A retry recreates the file from scratch either way.
        let _ = std::fs::remove_file(&archive_path);
        return Err(e);
    }

    let result = (|| {
        let got = engine_pack::hash::sha256_file(&archive_path)?;
        if got != dl.archive_sha256 {
            anyhow::bail!("archive sha256 mismatch");
        }
        let base = dl.use_base.then_some(current_dir).flatten();
        engine_pack::archive::assemble(base, &archive_path, manifest, &staging)?;
        cache.install_verified(&staging, manifest)
    })();
    let _ = std::fs::remove_file(&archive_path);
    if result.is_err() {
        let _ = std::fs::remove_dir_all(&staging);
    }
    result
}

/// Blocking HTTP transport over reqwest (the engine fetch runs on the engine
/// supervisor's background thread, so blocking is fine).
pub struct HttpTransport {
    client: reqwest::blocking::Client,
}

impl Default for HttpTransport {
    fn default() -> Self {
        Self {
            client: reqwest::blocking::Client::new(),
        }
    }
}

impl Transport for HttpTransport {
    fn get(&self, url: &str) -> anyhow::Result<Vec<u8>> {
        let resp = self.client.get(url).send()?.error_for_status()?;
        Ok(resp.bytes()?.to_vec())
    }

    fn get_to_file(
        &self,
        url: &str,
        dest: &Path,
        on: &mut dyn FnMut(u64, Option<u64>),
    ) -> anyhow::Result<()> {
        use std::io::{Read, Write};
        let mut resp = self.client.get(url).send()?.error_for_status()?;
        let total = resp.content_length();
        let mut file = std::io::BufWriter::new(std::fs::File::create(dest)?);
        let mut chunk = [0u8; 65536];
        let mut done: u64 = 0;
        loop {
            let n = resp.read(&mut chunk)?;
            if n == 0 {
                break;
            }
            file.write_all(&chunk[..n])?;
            done += n as u64;
            on(done, total);
        }
        file.flush()?;
        // No Content-Length: the throttle's always-send case is done == total,
        // so emit a final complete report or the progress UI freezes short.
        if total.is_none() {
            on(done, Some(done));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn idx(json: &str) -> EngineIndex {
        serde_json::from_str(json).unwrap()
    }
    fn pin(rev: &str, hash: &str) -> EnginePin {
        serde_json::from_str(&format!(
            r#"{{"engineRev":"{rev}","manifestHash":"{hash}"}}"#
        ))
        .unwrap()
    }

    const INDEX: &str = r#"{
      "latestRev": "r2",
      "revs": {
        "r2": {
          "prev": "r1",
          "platforms": {
            "darwin-aarch64": {
              "manifest": "u/m.json", "manifestSig": "u/m.json.sig", "manifestHash": "h2",
              "full": "u/full.tzst", "fullSha256": "fhash",
              "pack": { "from": "r1", "url": "u/pack.tzst", "sha256": "phash" }
            }
          }
        }
      }
    }"#;

    #[test]
    fn picks_pack_when_current_rev_is_the_pack_base() {
        let d = plan_download(&idx(INDEX), &pin("r2", "h2"), "darwin-aarch64", Some("r1")).unwrap();
        assert!(d.use_base);
        assert_eq!(d.archive_url, "u/pack.tzst");
        assert_eq!(d.archive_sha256, "phash");
    }

    #[test]
    fn picks_full_when_no_current_rev() {
        let d = plan_download(&idx(INDEX), &pin("r2", "h2"), "darwin-aarch64", None).unwrap();
        assert!(!d.use_base);
        assert_eq!(d.archive_url, "u/full.tzst");
    }

    #[test]
    fn picks_full_when_current_rev_is_not_the_pack_base() {
        // client is several revs behind: the pack base does not match -> full archive
        let d = plan_download(&idx(INDEX), &pin("r2", "h2"), "darwin-aarch64", Some("r0")).unwrap();
        assert!(!d.use_base);
        assert_eq!(d.archive_url, "u/full.tzst");
    }

    #[test]
    fn errors_on_unknown_rev_or_platform() {
        assert!(plan_download(&idx(INDEX), &pin("rX", "h"), "darwin-aarch64", None).is_err());
        assert!(plan_download(&idx(INDEX), &pin("r2", "h2"), "win32", None).is_err());
    }

    #[test]
    fn full_fallback_ignores_pack_and_returns_full() {
        // The self-heal path always resolves the self-contained full archive,
        // even when a pack (delta) exists for the current rev.
        let d = full_fallback(&idx(INDEX), &pin("r2", "h2"), "darwin-aarch64").unwrap();
        assert!(!d.use_base);
        assert_eq!(d.archive_url, "u/full.tzst");
        assert_eq!(d.archive_sha256, "fhash");
    }

    #[test]
    fn full_fallback_errors_on_unknown_rev_or_platform() {
        assert!(full_fallback(&idx(INDEX), &pin("rX", "h"), "darwin-aarch64").is_err());
        assert!(full_fallback(&idx(INDEX), &pin("r2", "h2"), "win32").is_err());
    }

    // --- end-to-end self-heal -------------------------------------------------
    // Reuse the real minisign fixture from engine_pack::verify (it signs a
    // files:[] manifest), so `ensure` runs its full verify+assemble+install path
    // without a secret key. An empty manifest assembles to an empty tree that
    // verifies trivially, which lets us isolate the retry control flow.
    use std::cell::RefCell;

    // Exact bytes the fixture signature covers; must be served verbatim as the
    // manifest so the signature verifies.
    const MSG: &[u8] =
        br#"{"engineRev":"r1","platform":"darwin-aarch64","files":[],"manifestHash":"deadbeef"}"#;
    const SIG_B64: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkKUlVUdHNLTEowNFNuRjdlbDAveTJhdEpCb0ZFV2hYTi96V1ZHdTJzQUlBRHVoZDFhelp3OGhuN1hveVo0MWxTdGN5U0xUUSs3VEUweE0zODVybFJBRGZGbTJVWlQ0SDAxN1E0PQp0cnVzdGVkIGNvbW1lbnQ6IHRpbWVzdGFtcDoxNzgwNjQ4ODU3CWZpbGU6ZXBfbXNnLmpzb24KclNrRzZVamtHTXUrZmVBNzA4dnVaWFkzQmxrU1psQ2ZmdDVHSnRVNEZoelhzZ3hOWXpoRnVWeFkxU1hVTENWb0k5NGgwTmlGMm1GUm5uME83M0V6REE9PQo=";
    const PUBKEY_B64: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDE3QTc4NEQzQzlBMkIwRUQKUldUdHNLTEowNFNuRjl5L2ZMd3FmWjhPWFRTNFpFYVJyUkk5ZHNZMVNCLzU3Q2gyUldhUmRucHYK";

    /// URL-keyed transport; records every archive URL streamed so the test can
    /// assert the pack was tried before the full fallback.
    struct MapTransport {
        blobs: std::collections::HashMap<String, Vec<u8>>,
        fetched: RefCell<Vec<String>>,
    }

    impl Transport for MapTransport {
        fn get(&self, url: &str) -> anyhow::Result<Vec<u8>> {
            self.blobs
                .get(url)
                .cloned()
                .ok_or_else(|| anyhow::anyhow!("no blob for {url}"))
        }
        fn get_to_file(
            &self,
            url: &str,
            dest: &Path,
            on: &mut dyn FnMut(u64, Option<u64>),
        ) -> anyhow::Result<()> {
            self.fetched.borrow_mut().push(url.to_string());
            let bytes = self.get(url)?;
            std::fs::write(dest, &bytes)?;
            on(bytes.len() as u64, Some(bytes.len() as u64));
            Ok(())
        }
    }

    #[test]
    fn ensure_self_heals_to_full_when_incremental_fails() {
        let tmp = tempfile::tempdir().unwrap();
        // A real, empty, signed archive: files:[] -> an empty tar.zst whose sha we
        // publish for the full archive. The pack advertises a WRONG sha, so its
        // apply fails at the sha check and the fallback to full must recover.
        let manifest: Manifest = serde_json::from_slice(MSG).unwrap();
        let empty_root = tmp.path().join("empty");
        std::fs::create_dir_all(&empty_root).unwrap();
        let archive = tmp.path().join("full.tar.zst");
        engine_pack::archive::write_pack(&empty_root, &manifest, &manifest, &archive).unwrap();
        let full_sha = engine_pack::hash::sha256_file(&archive).unwrap();
        let archive_bytes = std::fs::read(&archive).unwrap();

        let index_json = serde_json::json!({
            "latestRev": "r1",
            "revs": { "r1": { "prev": "r0", "platforms": {
                "darwin-aarch64": {
                    "manifest": "u/m.json", "manifestSig": "u/m.sig", "manifestHash": "deadbeef",
                    "full": "u/full", "fullSha256": full_sha,
                    "pack": { "from": "r0", "url": "u/pack", "sha256": "00thewrongsha00" }
                }
            }}}
        })
        .to_string();

        let mut blobs = std::collections::HashMap::new();
        blobs.insert("u/index.json".to_string(), index_json.into_bytes());
        blobs.insert("u/m.json".to_string(), MSG.to_vec());
        blobs.insert("u/m.sig".to_string(), SIG_B64.as_bytes().to_vec());
        blobs.insert("u/full".to_string(), archive_bytes.clone());
        blobs.insert("u/pack".to_string(), archive_bytes); // real bytes, wrong advertised sha
        let transport = MapTransport {
            blobs,
            fetched: RefCell::new(Vec::new()),
        };

        let cache = EngineCache::new(tmp.path());
        let base = tmp.path().join("base"); // present so the pack attempt uses_base
        std::fs::create_dir_all(&base).unwrap();

        let dir = ensure(
            &transport,
            &cache,
            "u/index.json",
            &pin("r1", "deadbeef"),
            "darwin-aarch64",
            Some("r0"), // == pack.from -> plan picks the pack (use_base)
            Some(base.as_path()),
            PUBKEY_B64,
            &mut |_, _| {},
        )
        .expect("ensure should self-heal to the full archive");

        assert!(dir.exists(), "installed engine dir should exist");
        assert_eq!(EngineCache::rev_of(&dir).as_deref(), Some("r1"));
        // The pack was attempted first, then the full archive as the fallback.
        assert_eq!(
            *transport.fetched.borrow(),
            vec!["u/pack".to_string(), "u/full".to_string()],
        );
    }
}
