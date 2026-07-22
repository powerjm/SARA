/*
 * gadgets_ex020.S — synthetic ROP gadget donor "ex020" (";move chain to syscall args").
 *
 * Re-authored (GAS/Intel syntax) from the ISP RAS rop-benchmark, file
 * binaries/x86/synthetic/source/ex020.nasm64 — instruction-for-instruction
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
 * Sub-problem isolated: there is no `pop rdx`. RDX (execve's envp) can only be
 * set by routing a value through RAX and copying it with `mov rdx, rax` — a
 * register move-chain / data-flow puzzle. (Tier 1-2.)
 *
 * Upstream nasm (verbatim, for provenance):
 *     .MoveRegG1: MOV RDX, RAX ; RET
 *     .LoadConstG2: POP RAX ; RET
 *     .LoadConstG3: POP RSI ; RET
 *     .LoadConstG4: POP RDI ; RET
 *     .StoreMemG:   MOV QWORD [RSI], RDI ; RET
 *     .SyscallG:    SYSCALL
 *     .NoOP:        RET ; RET
 */

.intel_syntax noprefix
.section .gadgets.text, "ax", @progbits

.globl MoveRegG1
MoveRegG1:
    mov rdx, rax
    ret

.globl LoadConstG2
LoadConstG2:
    pop rax
    ret

.globl LoadConstG3
LoadConstG3:
    pop rsi
    ret

.globl LoadConstG4
LoadConstG4:
    pop rdi
    ret

.globl StoreMemG
StoreMemG:
    mov qword ptr [rsi], rdi
    ret

.globl SyscallG
SyscallG:
    syscall

.globl NoOP
NoOP:
    ret
    ret
