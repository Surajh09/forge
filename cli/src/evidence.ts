import { execFileSync } from "node:child_process";

/**
 * Evidence collection from the developer machine (phase-2 §9).
 *
 * Forge Cloud deliberately cannot reach the repository, so the local package
 * gathers what backs a statement: branch, commit, changed files, and test
 * output when the caller has it. Evidence stays separate from the statement —
 * it is what the claim rests on, not the claim.
 *
 * Every command is best-effort: a machine with no git, or a directory that is
 * not a repository, yields empty evidence rather than an error.
 */

export type Evidence = {
  repository?: string;
  branch?: string;
  commit?: string;
  files?: string[];
  symbols?: string[];
  tests?: string[];
  test_results?: string;
  build_results?: string;
  errors?: string[];
  observations?: string[];
};

function git(args: string[], cwd: string): string | undefined {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return undefined;
  }
}

/** Repository state at the moment a statement was made. */
export function collect(cwd: string = process.cwd(), extra: Evidence = {}): Evidence {
  const remote = git(["config", "--get", "remote.origin.url"], cwd);
  // `rev-parse --abbrev-ref HEAD` fails on an unborn branch (a repo with no
  // commits yet), so fall back to the ref name, which always resolves.
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) ?? git(["branch", "--show-current"], cwd);
  const commit = git(["rev-parse", "HEAD"], cwd);

  // Uncommitted work plus the last commit's files: the change being described
  // is usually one or the other, and both are cheap.
  const dirty = git(["diff", "--name-only", "HEAD"], cwd);
  const staged = git(["diff", "--name-only", "--cached"], cwd);
  const lastCommit = commit ? git(["show", "--name-only", "--pretty=format:", "HEAD"], cwd) : undefined;

  let files = [
    ...new Set(
      [dirty, staged, lastCommit]
        .filter((v): v is string => Boolean(v))
        .flatMap((v) => v.split("\n"))
        .map((f) => f.trim())
        .filter(Boolean),
    ),
  ];

  // Every diff above is relative to HEAD, so a repo before its first commit
  // yields nothing. `status --porcelain` needs no commit and covers staged,
  // unstaged and untracked files in one pass.
  if (files.length === 0) {
    const status = git(["status", "--porcelain"], cwd);
    files = [
      ...new Set(
        (status ?? "")
          .split("\n")
          .map((line) => line.slice(3).trim()) // strip the two status columns
          .map((f) => f.replace(/^.*\s->\s/, "")) // renames: keep the destination
          .filter(Boolean),
      ),
    ];
  }
  files = files.slice(0, 50);

  const evidence: Evidence = {
    ...(remote ? { repository: remote } : {}),
    ...(branch && branch !== "HEAD" ? { branch } : {}),
    ...(commit ? { commit } : {}),
    ...(files.length ? { files } : {}),
    ...extra,
  };
  // Merge rather than replace when the caller supplied files of their own.
  if (extra.files?.length && files.length) {
    evidence.files = [...new Set([...files, ...extra.files])].slice(0, 50);
  }
  return evidence;
}

export function isRepository(cwd: string = process.cwd()): boolean {
  return git(["rev-parse", "--is-inside-work-tree"], cwd) === "true";
}
