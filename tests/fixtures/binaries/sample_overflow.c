/*
 * sample_overflow.c — a tiny, intentionally-vulnerable CTF-style trainer.
 *
 * This is the worked-example target for the sara apparatus. It exists only as
 * test ground-truth: every integration test and the validator need a real ELF
 * with a real, documented exploit chain to run against.
 *
 * The vulnerability is a classic unbounded stack read in vuln(). The intended
 * exploit is a small return-oriented chain (ret2win-with-argument):
 *
 *     pop rdi ; ret      <- load the magic value into rdi
 *     MAGIC              <- the value popped into rdi
 *     ret                <- 16-byte stack realignment before the call
 *     win               <- prints the success marker iff rdi == MAGIC
 *
 * Because the program is built -no-pie (see build.sh) every address is fixed at
 * link time, so the documented chain in chain.json is stable and reproducible.
 *
 * Ethical scope: educational target only. NX is on; the payload is a
 * proof-of-concept that prints a marker string, never a real payload.
 */

#include <stdio.h>
#include <unistd.h>

#define MAGIC 0xdeadbeefUL
#define SUCCESS_MARKER "Hello World"

/*
 * The win() function. It only prints the success marker when called with the
 * magic argument, so a working exploit must control rdi (a genuine ROP step) —
 * not merely redirect the saved return address. On success it flushes and
 * _exit()s cleanly so the exploited process returns code 0 with the marker on
 * stdout.
 */
void win(unsigned long magic)
{
    if (magic == MAGIC) {
        puts(SUCCESS_MARKER);
        fflush(stdout);
        _exit(0);
    }
    puts("Nope.");
}

/*
 * A self-contained `pop rdi ; ret` gadget at a stable, documented address.
 * Modern gcc no longer emits __libc_csu_init, which historically supplied this
 * gadget, so the trainer provides its own. It is never called from C; it exists
 * purely to be reached by the ROP chain.
 */
__asm__(
    ".text\n"
    ".globl gadget_pop_rdi\n"
    ".type gadget_pop_rdi, @function\n"
    "gadget_pop_rdi:\n"
    "    pop %rdi\n"
    "    ret\n"
    ".size gadget_pop_rdi, .-gadget_pop_rdi\n"
);

/*
 * The vulnerable function: an unbounded read into a fixed-size stack buffer.
 * Reading more than sizeof(buf) bytes overruns the saved frame and return
 * address — the entry point for the documented chain.
 */
void vuln(void)
{
    char buf[64];
    read(0, buf, 512);
}

int main(void)
{
    /* Unbuffered stdout so the marker is visible even on an abnormal exit. */
    setvbuf(stdout, NULL, _IONBF, 0);
    vuln();
    return 0;
}
