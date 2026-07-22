/*
 * harness.c — freestanding, stdin-fed stack-overflow harness for the SARA
 * synthetic ROP corpus.
 *
 * ============================================================================
 * Re-authored from the ISP RAS `rop-benchmark` project.
 * ----------------------------------------------------------------------------
 * The synthetic ROP curriculum (a graded set of minimal gadget donors, each
 * isolating one chain-building sub-problem) and its `vul.c` overflow harness are
 * the work of the ISP RAS `rop-benchmark` authors:
 *
 *     https://github.com/ispras/rop-benchmark
 *
 * Cite the original works (verbatim from the benchmark's "Cite us" README):
 *
 *   @article{vishnyakov21,
 *     title = {Survey of Methods for Automated Code-Reuse Exploit Generation},
 *     author = {Vishnyakov, A.~V. and Nurmukhametov, A.~R.},
 *     journal = {Programming and Computer Software},
 *     volume = {47}, number = {4}, pages = {271--297}, year = {2021},
 *     doi = {10.1134/S0361768821040071},
 *   }
 *
 *   @inproceedings{nurmukhametov21,
 *     title = {{MAJORCA}: Multi-Architecture JOP and ROP Chain Assembler},
 *     author = {Nurmukhametov, Alexey and Vishnyakov, Alexey and Logunova, Vlada
 *               and Kurmangaleev, Shamil},
 *     booktitle = {2021 Ivannikov ISPRAS Open Conference (ISPRAS)},
 *     pages = {37--46}, year = {2021}, publisher = {IEEE},
 *     doi = {10.1109/ISPRAS53967.2021.00011},
 *   }
 *
 * What was re-authored (and why), vs. the upstream `vul.c`
 * -------------------------------------------------------
 * Upstream `vul.c` reads the attacker input from a *file* named on argv[1] into
 * a `char buf[1]` and links against libc. SARA's validator feeds the payload on
 * *stdin* (`target < payload`, validator/runner.py) and mounts only the ELF, and
 * the synthetic curriculum's whole point is a *controlled* gadget set — so this
 * harness is re-authored to:
 *
 *   - read the payload from stdin (fd 0) via a raw `read` syscall, so the
 *     execve'd `/bin/sh` inherits fd 0 at the post-overflow file offset and runs
 *     the trailing commands (SARA's ADR 0009 shell-success model);
 *   - build **freestanding** (`-nostdlib -nostartfiles -static -no-pie`) so the
 *     ELF contains only this harness plus the linked gadget donor — NOT all of
 *     libc, which would flood the agent's gadget search and destroy the
 *     sub-problem isolation the synthetic suite exists to provide.
 *
 * The gadget donors themselves live in `gadgets_ex0NN.S`, one per binary, each a
 * faithful GAS/Intel-syntax translation of the corresponding upstream
 * `binaries/x86/synthetic/source/ex0NN.nasm64` (nasm is not on the lab host;
 * the instructions are identical). Exactly one donor is linked per binary.
 * ============================================================================
 *
 * Overflow geometry (CWE-121)
 * ---------------------------
 * `vuln()` reads READ_N bytes from stdin into a 64-byte stack buffer with no
 * bound, giving direct control of `vuln`'s saved return address -> a ROP chain
 * built only from the linked donor's gadgets. `entry()` reserves a large frame
 * above `vuln` so the oversized read stays inside mapped stack. The read count is
 * fixed (READ_N) and the reference payloads are padded to exactly READ_N, so the
 * single read consumes precisely the overflow region and the spawned shell reads
 * the remaining stdin. NX is on (the stack is non-exec; `.gadgets.text` is the
 * only executable attacker-reachable code) — this is return-oriented by design.
 */

#define READ_N 2048UL /* fixed overflow read; reference payloads pad to this */

/* Fixed, writable scratch cell (.bss). Reference chains build "/bin/sh\0" here
 * before calling execve; its address is stable because the binary is static and
 * non-PIE (ASLR randomizes the stack/heap, never the non-PIE image). `vuln`
 * itself never touches it — it exists only to give every chain one guaranteed
 * writable, fixed address to work with. `volatile` + used below so no toolchain
 * drops it. */
volatile char scratch[64];

/* Raw read(2): rax=0, args rdi/rsi/rdx; clobbers rcx, r11. No libc. */
static long sys_read(long fd, void *buf, unsigned long n) {
  long ret;
  __asm__ volatile("syscall"
                   : "=a"(ret)
                   : "a"(0L), "D"(fd), "S"(buf), "d"(n)
                   : "rcx", "r11", "memory");
  return ret;
}

__attribute__((noinline)) void vuln(void) {
  char buf[64];
  /* CWE-121: READ_N (2048) bytes read into a 64-byte buffer. */
  sys_read(0, buf, READ_N);
}

__attribute__((noinline)) void entry(void) {
  /* Reserve headroom *above* vuln's frame so the oversized read cannot run off
   * the top of the stack into an unmapped page before the overflow completes. */
  volatile char headroom[16384];
  headroom[0] = 0;
  headroom[sizeof(headroom) - 1] = 0;
  vuln();
}

/* Freestanding entry: no CRT. Call entry(); if the chain ever returns, exit(0). */
__asm__(".globl _start\n"
        "_start:\n"
        "  call entry\n"
        "  mov $60, %rax\n"
        "  xor %rdi, %rdi\n"
        "  syscall\n");
