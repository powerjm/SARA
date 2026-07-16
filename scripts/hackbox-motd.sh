# Printed on interactive login inside the sara-hackbox container.
# Sourced from /etc/profile.d, so keep it POSIX and side-effect-free.
case "$-" in
    *i*) ;;      # interactive — print the banner
    *) return ;; # non-interactive (scripts) — stay quiet
esac

cat <<'BANNER'
┌───────────────────────────────────────────────────────────────────────────┐
│  sara hackbox — ROP exploit-dev workbench (NOT the validator sandbox)       │
│                                                                             │
│  Targets: intentionally-vulnerable CGC binaries in corpus/binaries/ (i386,  │
│  static, NX, no PIE/canary). Author PoCs here as corpus/exploits/<id>.py;    │
│  they land in the mounted repo. Verify on the HOST (needs .venv + Docker,    │
│  which spawn the validator sandbox — not available inside this container):   │
│      sara verify --binary <id>                                              │
│                                                                             │
│  Core:   gdb+GEF · radare2 · pwntools · ROPgadget · ropper · keystone       │
│          32-bit gcc-multilib · patchelf · strace/ltrace                     │
│  Extras: angr (best-effort) · one_gadget (glibc/dynamic only — errors on    │
│          these static targets)                                              │
│                                                                             │
│  Recipes (corpus is static i386, NX, execve via int 0x80 — no libc gadget): │
│    rabin2 -I  corpus/binaries/cgc-cromu-00004            # checksec/arch    │
│    ROPgadget --binary corpus/binaries/cgc-cromu-00004 | grep 'pop eax'      │
│    ropper -f corpus/binaries/cgc-cromu-00004 --search 'pop eax'             │
│    gdb -q corpus/binaries/cgc-cromu-00004               # GEF auto-loads    │
│    setarch -R ./corpus/binaries/cgc-cromu-00004         # run, ASLR off     │
│                                                                             │
│  PoC skeleton (pwntools; default context is already i386/linux):           │
│    from pwn import *                                                        │
│    elf = ELF('corpus/binaries/cgc-cromu-00004')                            │
│    rop = ROP(elf)                                                           │
│    # marker must be PRODUCED by the shell, never in payload bytes (ADR 0009)│
│    # spawn /bin/sh, then feed:  X=SANS; echo HELLO $X                       │
└───────────────────────────────────────────────────────────────────────────┘
BANNER
