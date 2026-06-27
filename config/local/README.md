# Local-only mail intelligence assets

Host-bound configuration and encrypted stores for Mail Intelligence. **Nothing in this tree should be committed** except the example schema and this README.

Use the example JSON schema as a shape reference when initializing your encrypted local vault (prompts, tool keys, connector references). Vault master material and HSM enrollment blobs live in gitignored directories alongside this folder — provision them offline on the host.

Unlock flow: HSM touch in the explore UI establishes an ephemeral session; the vault API then releases runtime-resolved prompts and keys into the agent graph. Obsidian write paths may require a separate vault gate when dual-control is enabled.

See the Docker operator README and public self-host guide for stack setup; security wiring stays local.
