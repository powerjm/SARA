# CROMU_00004 normal and exploited execution-flow figures

Five raster variants compare ordinary PCM/Morse decoding with the verified controlled-lab exploit path.

1. `01-normal-execution.png` — normal header validation, PCM parsing, timing buckets, and Morse decoding
2. `02-normal-vs-exploited.png` — aligned normal/exploit comparison at the integer-division boundary
3. `03-control-flow-redirection.png` — normal CFG plus overwritten return into the two-stage ROP path
4. `04-stack-state-across-execution.png` — 1 MiB PCM stack object, saved EBP/EIP overwrite, and separate `.bss`
5. `05-source-to-runtime-map.png` — source, I/O, memory, and control correspondence

## Sources

- Corpus metadata: `corpus/manifest.yaml`, entry `cgc-cromu-00004`
- Verified exploit: `corpus/exploits/cgc-cromu-00004.py`
- Upstream challenge source linked by the manifest's `documented_exploit_url`

Generated with five `scientific-educational` prompts using the built-in image-generation workflow. Proofread rendered labels and verify technical details against the cited sources before publication.
