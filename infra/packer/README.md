# packer/

Builds the cloud VM image (AMI) used by `../terraform/` to provision the
experiment VM.

## Files

- `sara-lab.pkr.hcl` — the image template (an `amazon-ebs` source on Ubuntu
  26.04 + three shell provisioners + a manifest post-processor).
- `variables.pkr.hcl` — build-time variables (`region`, `build_instance_type`,
  `root_volume_gb`, `repo_url`, `repo_ref`).
- `provision/install-base.sh` — toolchain, Python 3.14, Docker, JDK 21, extras.
- `provision/install-tools.sh` — clones the apparatus at `repo_ref`, bootstraps
  it, installs ROPgadget/Ropper, builds `sara-sandbox:latest`, runs `make test`,
  and installs Ghidra when `GHIDRA_URL` is supplied.
- `provision/setup-experimenter.sh` — creates the non-root `experimenter` user,
  hands it the apparatus, pins `VALIDATOR_IMAGE`, and records provenance in
  `/etc/sara-version`.

## Build

```bash
packer init .
packer validate .
packer build \
  -var repo_ref=<run-for-record-tag> \
  -var repo_url=<your fork or mirror, if not the default> \
  sara-lab.pkr.hcl
```

The build writes `packer-manifest.json` (the new AMI id + region). Pin the
run-for-record to a tag and pass it as `repo_ref` so the image's
`/etc/sara-version` matches the thesis citation.

## Notes

- **CPU baseline.** The image targets the API backends on CPU. Local models in
  the cloud are an explicit GPU extension (NVIDIA drivers + LM Studio), not baked
  in here — see `../README.md`.
- **Ghidra is optional.** It is large and its release asset carries a build-date
  suffix; set `GHIDRA_URL` (and `GHIDRA_VERSION`) to the pinned 11.4.3 asset to
  include it. When absent, the Ghidra tool's tests skip (they never fail).
- **Untested from this checkout.** No AWS account is wired up here; run `packer
  validate .` with credentials before building for real.
