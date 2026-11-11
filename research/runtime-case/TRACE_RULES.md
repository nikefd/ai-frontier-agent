# Runtime research case

This directory is an isolated reproduction of a real UI bug: a deep link first
shows the landing page while session initialization is pending.

Work only in this directory. Do not read home directories, credentials, private
sessions or other repositories. Do not use sub-agents, network tools, install
packages, commit or push. Read this file and both source files. Run the tests
before editing so the original failures are visible. Fix only boot.mjs; do not
change tests. Public content must render before auth; private content must wait.
Run tests after editing and show the diff. Summarize the evidence, not just that
the task is complete. There is no need to inspect environment variables.
