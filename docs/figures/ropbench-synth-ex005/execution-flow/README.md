# ROPBench synthetic ex005 execution-flow figures

Five raster variants compare the shared synthetic harness's short-input path with ex005's verified load-all-register ROP chain.

1. `01-normal-execution.png` — freestanding harness and clean exit
2. `02-normal-vs-exploited.png` — short read versus full 2048-byte ROP record
3. `03-control-flow-redirection.png` — harness CFG, RIP capture, and gadget flow
4. `04-stack-state-across-execution.png` — stack, one 8-byte store, and syscall registers
5. `05-source-to-runtime-map.png` — harness, I/O, memory, and control timeline

## Sources

- Corpus metadata: `corpus/manifest.yaml`, entry `ropbench-synth-ex005`
- Verified exploit: `corpus/exploits/ropbench-synth-ex005.py`
- Harness and gadget donor: `corpus/scripts/synthetic/harness.c` and `gadgets_ex005.S`

Generated with five `scientific-educational` prompts using the built-in image-generation workflow. Proofread labels and verify details against the cited sources before publication.
