# NRFIN_00056 normal and exploited execution-flow figures

Five raster variants compare ordinary EternalPass password generation with the verified controlled-lab indirect-call exploit.

1. `01-normal-execution.png` — prompt, PRNG, password-generation loop
2. `02-normal-vs-exploited.png` — legitimate versus captured custom-PRNG call
3. `03-control-flow-redirection.png` — indirect-call redirection and staged ROP flow
4. `04-stack-state-across-execution.png` — call registers, relative stack pivot, buffered input, and `.bss`
5. `05-source-to-runtime-map.png` — password logic, I/O, memory, and control timeline

## Sources

- Corpus metadata: `corpus/manifest.yaml`, entry `cgc-nrfin-00056`
- Verified exploit: `corpus/exploits/cgc-nrfin-00056.py`
- Upstream challenge source linked by the manifest's `documented_exploit_url`

Generated with five `scientific-educational` prompts using the built-in image-generation workflow. Proofread rendered labels and verify technical details against the cited sources before publication.
