# spdxshow

You can use this script to see a summary of the content of an
SPDX 2.3 document.

## Packages

Example:

```
$ spdxshow packages mydoc.spdx.json
oci.index: ubi9-micro sha256:1c848...
oci.ppc64le: ubi9-micro sha256:1c848...
oci.s390x: ubi9-micro sha256:1c848...
oci.arm64: ubi9-micro sha256:1c848...
oci.amd64: ubi9-micro sha256:1c848...
```

## Relationships

The output is in the format used by [graph-easy](http://bloodgate.com/perl/graph/manual/).
Example:

```
$ spdxshow relationships mydoc.spdx.json | graph-easy --as=boxart
┌─────────────────────────────────────────┐
│  oci.amd64: ubi9-micro sha256:1c848...  │
│  oci.arm64: ubi9-micro sha256:1c848...  │
│ oci.ppc64le: ubi9-micro sha256:1c848... │
│  oci.s390x: ubi9-micro sha256:1c848...  │
└─────────────────────────────────────────┘
  │
  │ VARIANT_OF
  ∨
┌─────────────────────────────────────────┐
│  oci.index: ubi9-micro sha256:1c848...  │
└─────────────────────────────────────────┘
```
