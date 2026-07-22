/*
 * gadgets_ex010.S — synthetic ROP gadget donor "ex010" (";set mem with arith const").
 *
 * Re-authored (GAS/Intel syntax) from the ISP RAS rop-benchmark, file
 * binaries/x86/synthetic/source/ex010.nasm64 — instruction-for-instruction
 * identical to the upstream nasm; only the assembler dialect differs (the lab
 * host has GNU as, not nasm). See harness.c for how/why this was re-authored.
 *
 * ====== Cite the original works (verbatim from rop-benchmark "Cite us") ======
 *   @article{vishnyakov21,
 *     title = {Survey of Methods for Automated Code-Reuse Exploit Generation},
 *     author = {Vishnyakov, A.~V. and Nurmukhametov, A.~R.},
 *     journal = {Programming and Computer Software},
 *     volume = {47}, number = {4}, pages = {271--297}, year = {2021},
 *     doi = {10.1134/S0361768821040071},
 *   }
 *   @inproceedings{nurmukhametov21,
 *     title = {{MAJORCA}: Multi-Architecture JOP and ROP Chain Assembler},
 *     author = {Nurmukhametov, Alexey and Vishnyakov, Alexey and Logunova, Vlada
 *               and Kurmangaleev, Shamil},
 *     booktitle = {2021 Ivannikov ISPRAS Open Conference (ISPRAS)},
 *     pages = {37--46}, year = {2021}, publisher = {IEEE},
 *     doi = {10.1109/ISPRAS53967.2021.00011},
 *   }
 *   Source: https://github.com/ispras/rop-benchmark
 * =============================================================================
 *
 * Sub-problem isolated: no gadget stores an arbitrary value to memory. The
 * "/bin/sh" string must be *synthesized in memory a byte at a time* — zero the
 * target byte (InitMemG) then add a chosen constant into it (ArithMemG adds DH,
 * the high byte of RDX loaded via LoadConstG1). This is MAJORCA's arithmetic
 * value-synthesis (their Algorithm 2) in miniature. (Tier 2-3.)
 *
 * Upstream nasm (verbatim, for provenance):
 *     .LoadConstG1: POP RDI ; POP RSI ; POP RDX ; POP RAX ; RET
 *     .LoadConstG2: POP RDI ; POP RBP ; RET
 *     .InitMemG:    MOV BYTE [RDI], 0h ; RET
 *     .ArithMemG:   ADD BYTE [RBP], DH ; RET
 *     .SyscallG:    SYSCALL
 *     .NoOP:        RET ; RET
 */

.intel_syntax noprefix
.section .gadgets.text, "ax", @progbits

.globl LoadConstG1
LoadConstG1:
    pop rdi
    pop rsi
    pop rdx
    pop rax
    ret

.globl LoadConstG2
LoadConstG2:
    pop rdi
    pop rbp
    ret

.globl InitMemG
InitMemG:
    mov byte ptr [rdi], 0
    ret

.globl ArithMemG
ArithMemG:
    add byte ptr [rbp], dh
    ret

.globl SyscallG
SyscallG:
    syscall

.globl NoOP
NoOP:
    ret
    ret
