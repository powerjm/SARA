# EAGLE_00005 normal and exploited execution-flow figures

Five raster variants compare ordinary Hangman execution with the verified controlled-lab exploit path.

1. `01-normal-execution.png` — password, seeded word selection, guessing, and high-score flow
2. `02-normal-vs-exploited.png` — aligned behavior through the vulnerable high-score-name read
3. `03-control-flow-redirection.png` — game CFG and overwritten `getHighScore` return
4. `04-stack-state-across-execution.png` — game gate, 4096-byte input boundary, stack, and `.bss`
5. `05-source-to-runtime-map.png` — game logic, I/O, memory, and control timeline

## Sources

- Corpus metadata: `corpus/manifest.yaml`, entry `cgc-eagle-00005`
- Verified exploit: `corpus/exploits/cgc-eagle-00005.py`
- Upstream challenge source linked by the manifest's `documented_exploit_url`

Generated with five `scientific-educational` prompts using the built-in image-generation workflow. Proofread rendered labels and verify technical details against the cited sources before publication.
