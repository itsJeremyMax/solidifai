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

/// Pick the smallest archive we can apply: the pack when its `from` matches our
/// current engine rev (the delta base is present), else the full archive.
pub fn plan_download(
    index: &EngineIndex,
    pin: &EnginePin,
    platform: &str,
    current_rev: Option<&str>,
) -> anyhow::Result<Download> {
    let rev = index
        .revs
        .get(&pin.engine_rev)
        .ok_or_else(|| anyhow::anyhow!("engineRev {} not in index", pin.engine_rev))?;
    let plat = rev.platforms.get(platform).ok_or_else(|| {
        anyhow::anyhow!("platform {platform} not in index rev {}", pin.engine_rev)
    })?;

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
        None => Download {
            manifest_url: plat.manifest.clone(),
            sig_url: plat.manifest_sig.clone(),
            expected_manifest_hash: plat.manifest_hash.clone(),
            archive_url: plat.full.clone(),
            archive_sha256: plat.full_sha256.clone(),
            use_base: false,
        },
    })
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
        engine_pack::archive::assemble(base, &archive_path, &manifest, &staging)?;
        cache.install_verified(&staging, &manifest)
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
}
