# Client files

One JSON per client, copied from `_template.json`. The file name is the slug.
Files starting with `_` are ignored by the loader.

Fill it from the answers to `../INTAKE.md`. The prose fields go into the classifier
verbatim as the client's conversion contract, so write them the way the owner said them.

Secrets are never in the file: `*_env` fields name the Railway variable that holds
the token. Every client can share the Lumen system token; nothing client-specific
needs to be stored.

`dry_run: true` until the first week of decisions has been reviewed with the client.
