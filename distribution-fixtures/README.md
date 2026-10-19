# Generic distribution acceptance

`distribution-acceptance.yml` pins the exact Releaseway automation commit.
Its default run publishes only a new `distribution-<run>-<attempt>` prerelease,
keeps the product's stable latest Release unchanged, and exercises public reads,
read-only cross-repository access, tamper rejection, repeat preparation and
native fixture scripts on Linux, macOS and Windows.

Opting into `pages: true` additionally requires the preconfigured, isolated
`releaseway/release-fixture` Pages site in Actions mode with no custom domain.
The workflow never creates a site or changes an existing product site. It tests
latest-stable assets, exact fixture Release mappings, and generated same-run
artifact files in sequence; the artifact fixture is the final live site.

The complete evidence checker requires all three native receipts and all three
Pages source modes for the same automation/source/run/attempt. `--public-only`
validates only the source component and must not be reported as complete Pages
acceptance. Reports use immutable artifact IDs and environment deployment IDs
matched to the relevant run/job. Artifacts expire; missing evidence requires a
fresh complete run. No stable automation version or product adoption is published.
