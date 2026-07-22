/*
 * gadgets_ex005.S — synthetic ROP gadget donor "ex005" (";set reg with load all").
 *
 * Re-authored (GAS/Intel syntax) from the ISP RAS rop-benchmark, file
 * binaries/x86/synthetic/source/ex005.nasm64. Instruction-for-instruction
 * identical to the upstream nasm; only the assembler dialect differs (the lab
 * host has GNU as, not nasm). See harness.c for the full "Cite us" block:
 *   - Vishnyakov & Nurmukhametov, Programming and Computer Software 47(4), 2021,
 *     doi:10.1134/S0361768821040071
 *   - Nurmukhametov et al., "MAJORCA", Ivannikov ISPRAS Open Conf., IEEE 2021,
 *     doi:10.1109/ISPRAS53967.2021.00011
 *   - https://github.com/ispras/rop-benchmark
 *
 * Sub-problem isolated: the easiest real chain — one gadget pops every syscall
 * register at once, plus a single store to plant "/bin/sh". (SARA difficulty
 * tier 0.)
 *
 * Upstream nasm (verbatim, for provenance):
 *     .LoadConstG1: POP RDI ; POP RSI ; POP RDX ; POP RAX ; RET
 *     .LoadConstG2: POP RDI ; POP RBP ; RET
 *     .StoreMemG:   MOV QWORD [RDI], RBP ; RET
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

.globl StoreMemG
StoreMemG:
    mov qword ptr [rdi], rbp
    ret

.globl SyscallG
SyscallG:
    syscall

.globl NoOP
NoOP:
    ret
    ret
