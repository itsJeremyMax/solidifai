"""Per-workspace git history backing undo / redo / checkpoints.

Each workspace is a git repo tracking exactly model.py + settings.json (+ the
managed .gitignore). The linear timeline + current position live in
.solidifai/history.json (untracked); git holds the content snapshots. dulwich is
used so no system `git` binary is required.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import cast

from dulwich import porcelain
from dulwich.object_store import tree_lookup_path
from dulwich.objects import Blob, Commit, ObjectID, Tree
from dulwich.refs import Ref
from dulwich.repo import Repo

from solidifai_engine import paths

# Staged on every commit (allowlist mirrors .gitignore). model.py + settings.json
# are what undo/redo restore; .gitignore is staged once and then unchanged.
STAGE = (".gitignore", "model.py", "settings.json")
# Single-model restore (undo/redo) writes exactly these. Assembly workspaces
# restore the FULL recursive fileset from the target commit's tree instead (see
# _restore_assembly_to), because the fileset size changes across commits.
RESTORE = ("model.py", "settings.json")

GITIGNORE = (
    "# solidifai-managed: tracks only the model + its state.\n"
    "/*\n"
    "!/.gitignore\n"
    "!/model.py\n"
    "!/settings.json\n"
)

# Assembly workspaces use a denylist instead of an allowlist so the full
# nested fileset is visible to git without manual enumeration.
GITIGNORE_ASSEMBLY = (
    "# solidifai-managed: assembly workspace.\n"
    "/.solidifai/\n"
    "/.solidifai-cache/\n"
    "/exports/\n"
    "__pycache__/\n"
    "*.pyc\n"
)


def _within_root(root: str, path: str) -> bool:
    """True when ``path`` resolves inside ``root`` (symlinks resolved). Guards the
    restore path against a hand-edited assembly.json whose child.source escapes the
    workspace (``..``, an absolute path, a symlink out). The restore loop both
    writes and DELETES files, so an escaping source must never reach os.remove."""
    root_real = os.path.realpath(root)
    target_real = os.path.realpath(path)
    try:
        return os.path.commonpath([root_real, target_real]) == root_real
    except ValueError:  # different drives / mixed abs+rel on Windows
        return False


def _assembly_fileset(root: str) -> list[str]:
    """Repo-relative files that define an assembly: every assembly.json,
    skeleton.py, and parts/*.py through nested sub-assembly dirs, plus
    settings.json. Walks the manifest tree so only declared nodes are tracked.

    A child.source that escapes ``root`` (a hand-edited or malicious manifest) is
    SKIPPED at the source, so the fileset can never carry an out-of-root path into
    the staging, diff, or restore-deletion code that consumes it."""
    from solidifai_engine.assembly import manifest as manifest_mod

    out: list[str] = []

    def walk(node_dir: str, prefix: str) -> None:
        man = manifest_mod.load_manifest(node_dir)
        out.append(os.path.join(prefix, "assembly.json") if prefix else "assembly.json")
        if man.skeleton:
            out.append(os.path.join(prefix, man.skeleton) if prefix else man.skeleton)
        for child in man.children:
            rel = os.path.join(prefix, child.source) if prefix else child.source
            child_dir = os.path.join(node_dir, child.source)
            if not _within_root(root, child_dir):
                continue  # escaping source: never track, stage, diff, or delete it
            if child.kind == "part":
                out.append(rel)
            else:
                # child.source for a sub-assembly ends with "/" (e.g. "hinge/")
                walk(child_dir, rel.rstrip("/"))

    walk(root, "")
    if os.path.exists(os.path.join(root, "settings.json")):
        out.append("settings.json")
    return out


_IDENTITY = b"solidifai <engine@solidifai.app>"


class History:
    """Git-backed linear history for one workspace root."""

    def __init__(self, root: str):
        self.root = root
        self.dot = os.path.join(root, ".solidifai")
        self.history_json = os.path.join(self.dot, "history.json")
        self._repo: Repo | None = None
        self._branch: Ref = Ref(b"refs/heads/master")
        self.commits: list[str] = []
        self.index: int = -1

    # -- setup --------------------------------------------------------------

    def ensure(self) -> None:
        """Idempotently init the repo + .gitignore and load the timeline."""
        fresh = not os.path.isdir(os.path.join(self.root, ".git"))
        if fresh:
            porcelain.init(self.root)
        gi = os.path.join(self.root, ".gitignore")
        if not os.path.exists(gi):
            is_assembly = os.path.exists(os.path.join(self.root, "assembly.json"))
            template = GITIGNORE_ASSEMBLY if is_assembly else GITIGNORE
            with open(gi, "w", encoding="utf-8") as f:
                f.write(template)
        self._repo = Repo(self.root)
        if fresh:
            # New workspace repos default to `main`, not dulwich's `master`.
            with contextlib.suppress(Exception):
                self._git.refs.set_symbolic_ref(Ref(b"HEAD"), Ref(b"refs/heads/main"))
        # dulwich never auto-gc's, but disable it defensively so a user running
        # system `git gc` can't prune redo commits orphaned by edit-after-undo.
        try:
            config = self._git.get_config()
            config.set((b"gc",), b"auto", b"0")
            config.write_to_path()
        except Exception:
            pass
        ref = self._git.refs.read_ref(Ref(b"HEAD"))  # e.g. b"ref: refs/heads/master"
        if ref and ref.startswith(b"ref: "):
            self._branch = Ref(ref[len(b"ref: ") :])
        self._load_timeline()

    def ensure_assembly_gitignore(self) -> None:
        """Switch the workspace .gitignore to the assembly (denylist) template.

        A workspace that starts empty gets the single-model allowlist gitignore at
        ensure() time, which ignores skeleton.py / parts/ / sub-assembly dirs. When
        the workspace later becomes an assembly (set_skeleton), the staging add would
        silently skip those files. Rewrite to the denylist template so the whole
        nested fileset is trackable. Idempotent; safe to call on every set_skeleton."""
        gi = os.path.join(self.root, ".gitignore")
        try:
            if os.path.exists(gi):
                with open(gi, encoding="utf-8") as f:
                    current = f.read()
            else:
                current = ""
        except OSError:
            current = ""
        if current == GITIGNORE_ASSEMBLY:
            return
        with open(gi, "w", encoding="utf-8") as f:
            f.write(GITIGNORE_ASSEMBLY)

    def enabled(self) -> bool:
        return self._repo is not None

    @property
    def _git(self) -> Repo:
        """The repo, asserting it exists. Internal callers run after ensure()."""
        if self._repo is None:
            raise RuntimeError("History.ensure() must run before using the repo.")
        return self._repo

    # -- timeline persistence ----------------------------------------------

    def _load_timeline(self) -> None:
        try:
            with open(self.history_json, encoding="utf-8") as f:
                data = json.load(f)
            self.commits = [str(s) for s in data["commits"]]
            self.index = int(data["index"])
        except (OSError, ValueError, KeyError, TypeError):
            self._rebuild_timeline_from_git()
        self._clamp()

    def _rebuild_timeline_from_git(self) -> None:
        self.commits = []
        sha: ObjectID | None
        try:
            sha = self._git.head()
        except KeyError:
            self.index = -1
            return
        chain = []
        while sha is not None:
            chain.append(sha.decode("ascii"))
            parents = cast(Commit, self._git[sha]).parents
            sha = parents[0] if parents else None
        self.commits = list(reversed(chain))
        self.index = len(self.commits) - 1

    def _save_timeline(self) -> None:
        os.makedirs(self.dot, exist_ok=True)
        tmp = paths.write_temp_json(
            self.history_json, {"commits": self.commits, "index": self.index}
        )
        paths.atomic_finalize(tmp, self.history_json)

    def _clamp(self) -> None:
        self.index = (
            (len(self.commits) - 1)
            if not self.commits
            else max(0, min(self.index, len(self.commits) - 1))
        )

    # -- commit -------------------------------------------------------------

    def _stage(self) -> None:
        if os.path.exists(os.path.join(self.root, "assembly.json")):
            rels = _assembly_fileset(self.root)
            rels.append(".gitignore")
        else:
            rels = list(STAGE)
        present = [
            os.path.join(self.root, p) for p in rels if os.path.exists(os.path.join(self.root, p))
        ]
        if present:
            porcelain.add(self._git, present)

    def _tracked_paths(self) -> list[str]:
        """Repo-relative paths currently tracked in the git index (test/inspection)."""
        return [p.decode() if isinstance(p, bytes) else p for p in self._git.open_index()]

    def commit(self, message: str, *, amend: bool) -> str | None:
        """Commit the tracked files. ``amend`` at the tip replaces the tip commit;
        otherwise create a new commit, dropping any redo stack."""
        if self._repo is None:
            return None
        self._stage()
        at_tip = self.index == len(self.commits) - 1
        if amend and at_tip and self.commits:
            sha = porcelain.commit(
                self._repo,
                message=message.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
                amend=True,
            ).decode("ascii")
            self.commits[-1] = sha
        else:
            sha = porcelain.commit(
                self._repo,
                message=message.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
            ).decode("ascii")
            del self.commits[self.index + 1 :]  # drop redo stack (no-op at tip)
            self.commits.append(sha)
            self.index = len(self.commits) - 1
        self._save_timeline()
        return sha

    # -- navigation ---------------------------------------------------------

    def _blob_at(self, sha: str, path: str) -> bytes | None:
        commit = cast(Commit, self._git[sha.encode("ascii")])
        try:
            _mode, blob_sha = tree_lookup_path(
                self._git.get_object, commit.tree, path.encode("ascii")
            )
        except KeyError:
            return None
        return cast(Blob, self._git[blob_sha]).data

    def _tree_blobs(self, sha: str) -> dict[str, bytes]:
        """Every blob in the commit's tree as ``{repo-relative path: bytes}``.
        Walks nested trees so an assembly's parts/ and sub-assembly dirs are all
        included. This is the exact content of the snapshot, used to restore the
        whole fileset (the assembly path) rather than a fixed allowlist."""
        commit = cast(Commit, self._git[sha.encode("ascii")])
        out: dict[str, bytes] = {}

        def walk(tree_sha: bytes, prefix: str) -> None:
            tree = cast(Tree, self._git[tree_sha])
            for entry in tree.items():
                name = entry.path.decode("utf-8")
                rel = f"{prefix}/{name}" if prefix else name
                obj = self._git[entry.sha]
                if isinstance(obj, Tree):
                    walk(entry.sha, rel)
                else:
                    out[rel] = cast(Blob, obj).data

        walk(commit.tree, "")
        return out

    def _restore_to(self, idx: int) -> None:
        sha = self.commits[idx]
        is_assembly = os.path.exists(os.path.join(self.root, "assembly.json"))
        if is_assembly:
            self._restore_assembly_to(sha)
        else:
            for path in RESTORE:
                data = self._blob_at(sha, path)
                abspath = os.path.join(self.root, path)
                if data is not None:
                    with open(abspath, "wb") as f:
                        f.write(data)
                elif os.path.exists(abspath):
                    os.remove(abspath)  # file absent in this snapshot -> match it
        # Move the branch so a later commit parents on this state (editor undo).
        self._git.refs[self._branch] = ObjectID(sha.encode("ascii"))
        self.index = idx
        self._save_timeline()

    def _restore_assembly_to(self, sha: str) -> None:
        """Restore the full assembly fileset to match commit ``sha`` EXACTLY.

        The fileset grows and shrinks across commits (parts added/removed), so a
        plain allowlist checkout would leave a since-added part orphaned on disk
        when stepping back over its "add". This writes every blob in the target
        tree and then deletes any assembly file present on disk but absent from
        the target snapshot, so undo of an add removes the file and undo of a
        remove brings it back."""
        target = self._tree_blobs(sha)
        # Files the assembly convention currently tracks on disk (the live
        # working tree). Orphans = these minus the target snapshot. Computed
        # before any write so a manifest rewrite below cannot hide an orphan.
        # _assembly_fileset already drops out-of-root sources; the per-path guard
        # below is defense in depth in case an escaping path ever reaches here.
        current = set(_assembly_fileset(self.root))
        for rel, data in target.items():
            abspath = os.path.join(self.root, rel)
            parent = os.path.dirname(abspath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(abspath, "wb") as f:
                f.write(data)
        removed_dirs: set[str] = set()
        for rel in current - set(target):
            abspath = os.path.join(self.root, rel)
            if not _within_root(self.root, abspath):
                continue  # never delete outside the workspace, whatever the source
            with contextlib.suppress(OSError):
                os.remove(abspath)
                removed_dirs.add(os.path.dirname(abspath))
        self._prune_empty_dirs(removed_dirs)

    def _prune_empty_dirs(self, dirs: set[str]) -> None:
        """Remove now-empty directories that held a just-deleted orphan, walking UP
        toward (but never reaching) the root while each dir is empty and still inside
        the workspace. Scoped to ``dirs`` ONLY -- it never blanket-walks the root, so
        unrelated empty user directories (which git cannot restore) are left alone."""
        root_real = os.path.realpath(self.root)
        for start in dirs:
            cur = start
            # Climb only through the directories implicated by the removed files.
            while cur and os.path.realpath(cur) != root_real and _within_root(self.root, cur):
                try:
                    if os.listdir(cur):
                        break  # still has contents (other files/dirs): stop here
                    os.rmdir(cur)
                except OSError:
                    break
                cur = os.path.dirname(cur)

    def can_undo(self) -> bool:
        return self.index > 0

    def can_redo(self) -> bool:
        return 0 <= self.index < len(self.commits) - 1

    def undo(self) -> bool:
        if not self.can_undo():
            return False
        self._restore_to(self.index - 1)
        return True

    def redo(self) -> bool:
        if not self.can_redo():
            return False
        self._restore_to(self.index + 1)
        return True

    def goto(self, idx: int) -> bool:
        if self._repo is None or not (0 <= idx < len(self.commits)) or idx == self.index:
            return False
        self._restore_to(idx)
        return True

    # -- compliance sidecar -------------------------------------------------
    # Small JSON files in .solidifai/compliance/<sha>.json, untracked by git.
    # Stores {met, total, allMet, pass_map} snapped at checkpoint time.

    def _compliance_path(self, sha: str) -> str:
        return os.path.join(self.dot, "compliance", f"{sha}.json")

    def write_compliance(self, sha: str, data: dict) -> None:
        """Persist a compliance summary for the given commit SHA."""
        d = os.path.join(self.dot, "compliance")
        os.makedirs(d, exist_ok=True)
        p = self._compliance_path(sha)
        tmp = paths.write_temp_json(p, data)
        paths.atomic_finalize(tmp, p)

    def read_compliance(self, sha: str) -> dict | None:
        """Return the stored compliance summary for ``sha``, or None if absent."""
        p = self._compliance_path(sha)
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    # -- listing ------------------------------------------------------------

    def entries(self) -> list[dict]:
        out = []
        for i, sha in enumerate(self.commits):
            try:
                c = cast(Commit, self._git[sha.encode("ascii")])
                message = c.message.decode("utf-8", "replace").strip()
                ctime = int(c.commit_time)
            except KeyError:
                message, ctime = "(missing)", 0
            out.append(
                {
                    "index": i,
                    "sha": sha,
                    "message": message,
                    "time": ctime,
                    "current": i == self.index,
                    "compliance": self.read_compliance(sha),
                }
            )
        return out
