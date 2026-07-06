//! engine-pack CLI: invoked by CI build scripts. Subcommands mirror the library
//! so the build and the runtime share one implementation of the format.
use engine_pack::archive::{assemble, write_full, write_pack};
use engine_pack::manifest::Manifest;
use std::path::Path;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    match run(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("engine-pack: {e}");
            ExitCode::FAILURE
        }
    }
}

fn run(args: &[String]) -> anyhow::Result<()> {
    let cmd = args.get(1).map(String::as_str).unwrap_or("");
    match cmd {
        // manifest <dir> <engineRev> <platform> <out.json>
        "manifest" => {
            let (dir, rev, plat, out) =
                (arg(args, 2)?, arg(args, 3)?, arg(args, 4)?, arg(args, 5)?);
            let m = Manifest::build_from_dir(Path::new(dir), rev, plat)?;
            std::fs::write(out, serde_json::to_vec_pretty(&m)?)?;
            println!("{}", m.manifest_hash);
        }
        // full <dir> <manifest.json> <out.tar.zst>
        "full" => {
            let (dir, man, out) = (arg(args, 2)?, arg(args, 3)?, arg(args, 4)?);
            let m: Manifest = serde_json::from_slice(&std::fs::read(man)?)?;
            write_full(Path::new(dir), &m, Path::new(out))?;
        }
        // pack <dir> <manifest.json> <prev_manifest.json> <out.pack.tar.zst>
        "pack" => {
            let (dir, man, prev, out) =
                (arg(args, 2)?, arg(args, 3)?, arg(args, 4)?, arg(args, 5)?);
            let m: Manifest = serde_json::from_slice(&std::fs::read(man)?)?;
            let p: Manifest = serde_json::from_slice(&std::fs::read(prev)?)?;
            let n = write_pack(Path::new(dir), &m, &p, Path::new(out))?;
            println!("{n}");
        }
        // assemble <base|-> <pack> <manifest.json> <dest>
        "assemble" => {
            let (base, pack, man, dest) =
                (arg(args, 2)?, arg(args, 3)?, arg(args, 4)?, arg(args, 5)?);
            let m: Manifest = serde_json::from_slice(&std::fs::read(man)?)?;
            let base = if base == "-" {
                None
            } else {
                Some(Path::new(base))
            };
            assemble(base, Path::new(pack), &m, Path::new(dest))?;
        }
        other => {
            anyhow::bail!("unknown subcommand {other:?}; expected manifest|full|pack|assemble")
        }
    }
    Ok(())
}

fn arg(args: &[String], i: usize) -> anyhow::Result<&str> {
    args.get(i).map(String::as_str).ok_or_else(|| {
        anyhow::anyhow!(
            "missing argument {i} for `{}`",
            args.get(1).map(String::as_str).unwrap_or("")
        )
    })
}
