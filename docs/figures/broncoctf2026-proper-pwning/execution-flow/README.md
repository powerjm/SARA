# Proper Pwning normal and exploited execution-flow figures

Five raster variants compare ordinary gate progression with the verified controlled-lab ret2syscall path.

1. `01-normal-execution.png` — the three checks and treasure-room return
2. `02-normal-vs-exploited.png` — gate-data overwrites versus final saved-RIP overwrite
3. `03-control-flow-redirection.png` — gate CFG and direct stack ROP path
4. `04-stack-state-across-execution.png` — all four input lines and relevant frame offsets
5. `05-source-to-runtime-map.png` — program logic, I/O, stack memory, and control timeline

## Sources

- Corpus metadata: `corpus/manifest.yaml`, entry `broncoctf2026-proper-pwning`
- Verified exploit: `corpus/exploits/broncoctf2026-proper-pwning.py`
- Challenge attribution and upstream source repository recorded in those files

Generated with five `scientific-educational` prompts using the built-in image-generation workflow. Proofread rendered labels and verify technical details against the cited sources before publication.
