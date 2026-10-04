# Foundation verification

Verified on Linux, 2026-10-05. All committed fixtures and terminal captures use synthetic projects only.

## Corrected audit findings

- TODO samples and commit subjects no longer bypass secret redaction. The assembled prompt is filtered too.
- Ignore rules apply to tracked and untracked files. Nested `.gitignore` rules also apply outside Git repositories. Commits affecting only ignored paths are omitted from semantic context and drift subjects.
- Symlinks, including linked ignore files and project roots, are rejected. File reads and directory scans use no-follow descriptors for every path component, with regression coverage for a symlink replacement during access.
- Excluded roots are checked before directory inspection. Discovery is bounded to four directory levels by default, stops at project roots, and prunes dependencies/caches. Existing registry entries for newly excluded roots are hidden from operations.
- Terminal output masks absolute local paths, replaces registered directory names with aliases, and uses symbolic swap/core locations.
- Restoration selects the newest valid saved copy. Rescanning no longer leaves restoration using an older swap image.
- Decisions without usable source paths are marked inferred.
- LOAD clips completed and current sessions to the displayed 24-hour window.
- Core dumps use atomic replacement. Documentation now distinguishes this from append-only event logging and correctly describes fingerprint-based image reuse.
- Ollama requests require loopback endpoints, ignore environment proxies, and reject cloud model names. The server must itself use local model weights.

## Tests and installation

The original 51-test suite was expanded to **91 passing tests** with privacy and foundation regressions. The complete suite passed again after private read-only integration checks. Tests use only synthetic repositories, mocked inference, and temporary state; they require no network or Gemma.

A clean Python 3.12 environment installed the package and dependencies from the local package cache, and the installed `thrash --help` succeeded.

## Network-isolated demo

Both THRASH and a temporary Ollama server ran in a Linux network namespace created with Bubblewrap. The only network interface inside it was `lo`; no external network interface was available. Installed Gemma weights were mounted read-only. The server's application directory and demo state were temporary; the existing host server and physical Wi-Fi were unchanged.

Model: `gemma3:4b`.

| Check | Result |
| --- | --- |
| Register five synthetic projects | Passed |
| Normal switch / save / restore | Passed |
| 71-hour-old image and drift | Passed; age deliberately simulated by demo tooling |
| THRASHING | Displayed |
| ZOMBIE | Displayed |
| Kill / core dump / resurrect | Passed |
| Demo script exit status | 0 |
| Local model unavailable errors | 0 |
| Rejected model outputs | 0 |

Evidence: [actual synthetic transcript](examples/offline-demo-run.txt), [page-fault terminal capture](examples/page-fault.svg), [thrashing terminal capture](examples/thrashing.svg).

The SVGs render captured text with Rich; they are not invented output. Reproduce the rendering with `python demo/capture.py`.

## Limits retained honestly

- The laptop's Wi-Fi was not physically disabled. The demonstration above instead removes external networking for the tested processes.
- Model validation and evidence-path checks cannot guarantee semantic correctness. An empty next-action field falls back to the saved program counter in the current UI.
- The original kernel commit was broad. History has not been rewritten to imply granular implementation commits.
- Arbitrary private names and unusual secret formats cannot all be recognized by pattern matching. Public artifacts must continue to use synthetic repositories only.
- Starvation and the expanded canonical resume-report experience remain prompt2 work.
