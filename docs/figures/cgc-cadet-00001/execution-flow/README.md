# CADET_00001 normal and exploited execution-flow figures

These five raster figure variants compare the service's ordinary palindrome-finder behavior with the documented controlled-lab exploit path.

1. `01-normal-execution.png` — source-level `main()` and `check()` flowchart
2. `02-normal-vs-exploited.png` — aligned side-by-side comparison
3. `03-control-flow-redirection.png` — simplified control-flow graph and overwritten return edge
4. `04-stack-state-across-execution.png` — normal and corrupted i386 stack states plus separate `.bss`
5. `05-source-to-runtime-map.png` — correspondence among source, I/O, memory, and control flow

## Sources

- Upstream CGC source: <https://github.com/CyberGrandChallenge/samples/blob/master/examples/CADET_00001/src/service.c>
- Corpus metadata: `corpus/manifest.yaml`, entry `cgc-cadet-00001`
- Documented chain: `corpus/exploits/cgc-cadet-00001.py`

## Generation notes

The figures were generated with the built-in image-generation workflow using five distinct `scientific-educational` prompts. The prompts respectively requested: a normal source flowchart; a mirrored normal/exploit comparison; a control-flow redirection graph; an i386 memory-state comparison; and a four-layer source-to-runtime timeline.

These are generated raster illustrations. Proofread all rendered labels and verify technical details against the cited source and exploit before publication.
