# Contributing

Open an issue with the operating system, audio server, model, device and steps needed to reproduce the problem. Include expected and actual behavior. Do not attach private meeting recordings, transcripts, local caption URLs or credentials.

For a code change:

1. Create a branch and keep the change focused on one problem.
2. Use Python 3.12 and the setup described in the README.
3. Run `python -m unittest discover -s tests -v` in that environment.
4. Run `python bin/check_publication.py` and review the staged diff before pushing.
5. Explain the change, how you checked it and any remaining limits in the pull request.

Performance changes need a reproducible comparison: the same public audio and references, model version, hardware, configuration, recognition errors, latency and memory. Report GPU fallback separately. A faster single clip does not establish better meeting performance.

Keep interface text available in Spanish and English. Treat recognized speech as text, never HTML or commands. Downloads and optional models must be explicit. New capture code must stop only the resources it creates.

Preserve the original transcript when adding corrections or annotations. Keep recordings, weights, environments and session artifacts out of Git. Describe third-party model licenses separately from this wrapper's MIT license.
