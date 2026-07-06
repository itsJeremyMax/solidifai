# Build a self-contained, trimmed engine into src-tauri\engine-dist (Windows).
# Mirror of build-engine-dist.sh. See that file for rationale.
param([string]$PyVer = "3.12")
$ErrorActionPreference = "Stop"
# Fail on native-command (uv, cargo) nonzero exits, not just cmdlet errors.
$PSNativeCommandUseErrorActionPreference = $true
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$Dist = Join-Path $Root "src-tauri\engine-dist"

Write-Host "==> Cleaning previous bundle"
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }

Write-Host "==> Installing standalone CPython $PyVer via uv"
uv python install $PyVer
$env:UV_PYTHON_PREFERENCE = "only-managed"
$PyBin = (uv python find $PyVer)
$PyHome = (Resolve-Path (Split-Path $PyBin)).Path
# Newer uv answers `python find` with a minor-version alias (a junction,
# cpython-3.12-... -> cpython-3.12.13-...). Copy the real install, not the
# junction, or engine-dist stays inside uv's externally managed (PEP 668) tree.
$PyHomeItem = Get-Item $PyHome
if ($PyHomeItem.LinkType) { $PyHome = @($PyHomeItem.Target)[0] }
Write-Host "    managed interpreter: $PyHome"

Write-Host "==> Copying interpreter into engine-dist"
Copy-Item -Recurse $PyHome $Dist
$DistPy = Join-Path $Dist "python.exe"
if (-not (Test-Path $DistPy)) { throw "python.exe missing after copy at $DistPy" }

# Our private copy now: drop the PEP 668 marker so we can install into it.
Get-ChildItem -Path $Dist -Recurse -Filter EXTERNALLY-MANAGED | Remove-Item -Force

Write-Host "==> Installing the engine (locked production deps) into the bundle"
# Locked closure from engine\uv.lock, not a fresh resolution; see the .sh twin.
$Req = Join-Path ([IO.Path]::GetTempPath()) "engine-requirements.txt"
uv export --project "$Root\engine" --frozen --no-dev --no-emit-project -o $Req
uv pip install --python $DistPy -r $Req
uv pip install --python $DistPy --no-deps "$Root\engine"
Remove-Item -Force $Req

Write-Host "==> Pruning dev deps + subsetting VTK"
$SP = (Resolve-Path "$Dist\Lib\site-packages").Path
& $DistPy "$Root\scripts\prune_engine.py" $SP $DistPy

# LGPL/attribution notices must accompany binary distribution; see the .sh twin.
Write-Host "==> Copying third-party license notices into the bundle"
Copy-Item "$Root\scripts\ENGINE-THIRD-PARTY-NOTICES.txt" (Join-Path $Dist "THIRD-PARTY-NOTICES.txt")

Write-Host "==> Smoke test (both entrypoints + a build123d op + a VTK view capture)"
& $DistPy -m solidifai_engine --help | Out-Null
& $DistPy -c "from solidifai_mcp.server import main; print('mcp entrypoint OK')"
& $DistPy -c "import tempfile,pathlib; import OCP; import lib3mf; import build123d as bd; from solidifai_engine import views, exports, dfm; assert bd.Box(1,1,1).volume>0; out=views.capture_smoke(tempfile.mkdtemp()); assert out and all(pathlib.Path(p).exists() for p in out); print('engine smoke OK')"

# --- Content-addressed engine assets (manifest + full archive) + app pin --------
# Mirror of the emission in build-engine-dist.sh. release-build.yml publishes these
# and emits the pack/signature. engineRev only needs to be internally consistent.
Write-Host "==> Emitting engine assets + stamping pin"
function Get-Sha256Hex([string]$s) {
  $sha = [Security.Cryptography.SHA256]::Create()
  ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($s))) -replace '-').ToLower()
}
$Plat = "windows-x86_64"
$Out = if ($env:ENGINE_OUT_DIR) { $env:ENGINE_OUT_DIR } else { Join-Path $Root "engine-out" }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
# uv rather than `python -m pip`: prune strips pip from the bundle, which made
# the dep half of the rev silently hash an empty string.
$Deps = (uv pip freeze --python $DistPy)
if (-not $Deps) { throw "dependency freeze is empty; engineRev would ignore deps" }
$DepRev = (Get-Sha256Hex (($Deps | Sort-Object) -join "`n")).Substring(0,12)
$SrcHashes = (Get-ChildItem -Recurse "$Root\engine" -Filter *.py |
  Where-Object { $_.FullName -notmatch '\\.venv\\' } | Sort-Object FullName |
  ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }) -join "`n"
$EngineRev = "$DepRev$((Get-Sha256Hex $SrcHashes).Substring(0,12))"
$Ep = Join-Path $Root "src-tauri\target\release\engine-pack.exe"
if (-not (Test-Path $Ep)) { cargo build --release --manifest-path "$Root\src-tauri\Cargo.toml" -p engine-pack }
$Man = Join-Path $Out "solidifai-engine-$Plat-$EngineRev.manifest.json"
$ManifestHash = (& $Ep manifest $Dist $EngineRev $Plat $Man)
& $Ep full $Dist $Man (Join-Path $Out "solidifai-engine-$Plat-$EngineRev.full.tar.zst")
# Materialize before iterating: the .sha256 files written inside the loop
# match the enumeration filter and could otherwise be picked up mid-stream.
@(Get-ChildItem -Path $Out -Filter "solidifai-engine-$Plat-*" | Where-Object { $_.Name -notlike '*.sha256' }) |
  ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() | Set-Content "$($_.FullName).sha256" }
"{ ""engineRev"": ""$EngineRev"", ""manifestHash"": ""$ManifestHash"" }" | Set-Content "$Root\src-tauri\engine-pin.json"
Write-Host "    engineRev=$EngineRev manifestHash=$ManifestHash plat=$Plat"

Write-Host "==> Bundle built at $Dist"
