# Mail Intelligence prompts (operator-local)

Prompt bodies for the Mail Intelligence Router are not stored in this public repository. Operators maintain them under `agent/prompts/local/mail_intel/`, a sealed vault, or runtime inject at deploy. The router build defaults to skeleton stubs for CI and public clones; use `--inject-from-vault` or `--full-prompts` only on trusted machines with local prompt files present.
