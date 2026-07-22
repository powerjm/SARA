/*
 * gadgets_ex101.S — synthetic ROP gadget donor "ex101" (rich set, stack-adjusting rets).
 *
 * Re-authored (GAS/Intel syntax) from the ISP RAS rop-benchmark, file
 * binaries/x86/synthetic/source/ex101.nasm64 — instruction-for-instruction
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
 * Sub-problem isolated: a rich toolbox, but two of the load gadgets end in
 * `ret N` (RET 8, RET 4) and one init gadget is a conditional (CMP/SBB/CMOVBE).
 * The `ret N` gadgets pop extra stack slots after returning, so a naive chain
 * desynchronizes — the scheduler must insert padding of the right width after
 * each. This is the scheduling ceiling of the synthetic set. (Tier 3.)
 *
 * Note: `ret 4` pops 4 bytes (half a slot), so a chain routed through
 * LoadConstG7 (`pop rsi ; ret 4`) misaligns the 8-byte gadget stream; the
 * reference PoC avoids it and sets RSI a different way — see the PoC for the
 * chosen route.
 *
 * Upstream nasm (verbatim, for provenance):
 *     .NoOpG1: RET
 *     .NoOpG2: RET 8
 *     .LoadConstG1: POP RAX ; RET
 *     .LoadConstG2: POP RBX ; RET
 *     .LoadConstG3: POP RCX ; RET 8
 *     .LoadConstG4: POP RDX ; RET
 *     .LoadConstG5: POP RBP ; RET
 *     .LoadConstG6: POP RDI ; RET
 *     .InitConstESI: CMP RCX, RDX ; SBB ESI, ESI ; CMP RCX, RDX ; CMOVBE EAX, ESI ; RET
 *     .LoadConstG7: POP RSI ; RET 4
 *     .LoadConstG8: POP RDX ; RET
 *     .StoreMemG1: MOV [RAX], RBX ; RET
 *     .InitConstG1: XOR RBX, RBX ; RET
 *     .InitConstG2: XOR RAX, RAX ; RET
 *     .ArithmeticG1: INC EAX ; RET
 *     .SyscallG: SYSCALL
 */

.intel_syntax noprefix
.section .gadgets.text, "ax", @progbits

.globl NoOpG1
NoOpG1:
    ret

.globl NoOpG2
NoOpG2:
    ret 8

.globl LoadConstG1
LoadConstG1:
    pop rax
    ret

.globl LoadConstG2
LoadConstG2:
    pop rbx
    ret

.globl LoadConstG3
LoadConstG3:
    pop rcx
    ret 8

.globl LoadConstG4
LoadConstG4:
    pop rdx
    ret

.globl LoadConstG5
LoadConstG5:
    pop rbp
    ret

.globl LoadConstG6
LoadConstG6:
    pop rdi
    ret

.globl InitConstESI
InitConstESI:
    cmp rcx, rdx
    sbb esi, esi
    cmp rcx, rdx
    cmovbe eax, esi
    ret

.globl LoadConstG7
LoadConstG7:
    pop rsi
    ret 4

.globl LoadConstG8
LoadConstG8:
    pop rdx
    ret

.globl StoreMemG1
StoreMemG1:
    mov [rax], rbx
    ret

.globl InitConstG1
InitConstG1:
    xor rbx, rbx
    ret

.globl InitConstG2
InitConstG2:
    xor rax, rax
    ret

.globl ArithmeticG1
ArithmeticG1:
    inc eax
    ret

.globl SyscallG
SyscallG:
    syscall
