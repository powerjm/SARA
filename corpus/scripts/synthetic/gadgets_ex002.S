/*
 * gadgets_ex002.S — synthetic ROP gadget donor "ex002" ("; minimal gadget set").
 *
 * Re-authored (GAS/Intel syntax) from the ISP RAS rop-benchmark, file
 * binaries/x86/synthetic/source/ex002.nasm64 — instruction-for-instruction
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
 * Sub-problem isolated: a minimal-but-sufficient set — single-register pops and
 * one store gadget whose destination register (RDX) is *also* a syscall arg, so
 * the store and the register setup interfere and must be ordered. (Tier 1.)
 *
 * Upstream nasm (verbatim, for provenance):
 *     .LoadConstG6: POP RDI ; RET
 *     .LoadConstG7: POP RSI ; RET
 *     .LoadConstG8: POP RDX ; RET
 *     .LoadConstG9: POP RAX ; RET
 *     .StoreMemG1:  MOV QWORD [RDX], RSI ; RET
 *     .SyscallG:    SYSCALL
 *     .NoOP:        RET ; RET
 */

.intel_syntax noprefix
.section .gadgets.text, "ax", @progbits

.globl LoadConstG6
LoadConstG6:
    pop rdi
    ret

.globl LoadConstG7
LoadConstG7:
    pop rsi
    ret

.globl LoadConstG8
LoadConstG8:
    pop rdx
    ret

.globl LoadConstG9
LoadConstG9:
    pop rax
    ret

.globl StoreMemG1
StoreMemG1:
    mov qword ptr [rdx], rsi
    ret

.globl SyscallG
SyscallG:
    syscall

.globl NoOP
NoOP:
    ret
    ret
