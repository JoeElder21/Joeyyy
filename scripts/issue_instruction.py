"""Mint a signed task-level instruction for one high-impact boundary action.

`AGENTS.md` reserves six actions to Joe personally, and
`PolicyEnforcementPoint._high_impact_boundary` refuses every one of them unless
the request carries a signed grant bound to *that* action and *that* resource.
Nothing in the repository could produce such a grant: `trusted_launcher.py`
issues MOUNT-shaped grants, and the only instruction-grant constructor was a
test helper calling the private `_sign`. So an action Joe had expressly
authorized had no supported path through the boundary once `enforce()` was
wired -- the control was not merely strict, it was unsatisfiable.

This is deliberately a separate command from `trusted_launcher.py`. Launching a
mount and minting Joe's personal authority are different privileges, and the
second should not be a subcommand of the first. It is also why this module
imports the launcher's signing primitive rather than defining one: two
implementations of "what a valid grant looks like" is how the issuer and the
verifier drift apart, and the enforcement point already imports the same
`_sign`.

**What this does not do.** The grant is replayable within its expiry window.
Single-use enforcement requires consuming the nonce at the execution boundary,
and a policy evaluation deliberately has no side effects -- otherwise merely
*asking* whether an action is permitted would burn the grant. `trusted_launcher`
consumes mount-grant nonces because it *is* an execution boundary; there is no
equivalent for instructions until `enforce()` has call sites. Nonce consumption
is a recorded open decision in `docs/REPO_OPTIMIZATION_2026-07-25.md`, and the
short default expiry is the mitigation, not a fix.

Usage:
    python scripts/issue_instruction.py --action publish_report \\
        --resource APEX/Strategy-Campaigns/launch-brief --minutes 15
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.policy_enforcement import (  # noqa: E402
    HIGH_IMPACT_ACTIONS,
    PolicyEnforcementPoint,
)
from scripts.trusted_launcher import DEFAULT_KEY_PATH, _sign  # noqa: E402

# An instruction authorizes an irreversible act. A grant that outlives the
# conversation it came from is a standing authorization, which is the thing the
# per-action boundary exists to prevent, so the ceiling is deliberately low.
MAX_INSTRUCTION_MINUTES = 60
DEFAULT_INSTRUCTION_MINUTES = 15


class InstructionRefused(Exception):
    """The instruction cannot be issued as stated."""


def issue_instruction(
    action: str,
    resource: str,
    minutes: int = DEFAULT_INSTRUCTION_MINUTES,
    key_path: Path = DEFAULT_KEY_PATH,
    out_dir: Path | None = None,
    now: float | None = None,
) -> Path:
    """Write a signed instruction grant and return its path.

    The `action` recorded in the grant is the boundary CATEGORY, derived with
    the enforcement point's own classifier rather than restated here. The rule
    compares the grant against `_boundary_category(request.action)`, so an
    issuer that stored the raw verb would mint grants that never match: the
    operator would hold a signed authorization the gate rejects, and would
    reasonably conclude the gate was broken.

    **The grant is therefore scoped to the category, not to the literal verb.**
    `publishReport` and `sendEmail` are both `public_publication`, so an
    instruction issued for one authorizes the other *on the same resource*.
    That is the boundary's own granularity rather than a widening introduced
    here, and it is the correct one: verb spellings are not stable -- the same
    act arrives as `publish_report`, `publishReport`, or `publish` depending on
    the dispatcher -- so binding to a literal string would produce grants that
    fail for the act they were issued for. The resource binding is exact.
    """
    if not isinstance(action, str) or not action.strip():
        raise InstructionRefused("an instruction must name an action")
    if not isinstance(resource, str) or not resource.strip():
        raise InstructionRefused("an instruction must name a resource")
    if not isinstance(minutes, int) or isinstance(minutes, bool):
        raise InstructionRefused("minutes must be an integer")
    if not 0 < minutes <= MAX_INSTRUCTION_MINUTES:
        raise InstructionRefused(
            f"minutes must be within (0, {MAX_INSTRUCTION_MINUTES}]; an instruction "
            "that outlives its conversation is a standing authorization"
        )

    category = PolicyEnforcementPoint._boundary_category(action)
    if category not in HIGH_IMPACT_ACTIONS:
        # Refused rather than issued-and-ignored. A grant for `read` authorizes
        # nothing the gate consults, so issuing one teaches the operator that
        # minting instructions is routine -- and the whole value of this
        # boundary is that it is not.
        raise InstructionRefused(
            f"{action!r} is not a high-impact boundary action, so it needs no "
            f"instruction; the boundary categories are {sorted(HIGH_IMPACT_ACTIONS)}"
        )
    if PolicyEnforcementPoint._escapes_the_tree(resource):
        raise InstructionRefused(
            f"{resource!r} resolves outside the repository; an instruction cannot "
            "authorize a target the gate refuses to classify"
        )

    now = now if now is not None else time.time()
    payload = {
        "action": category,
        "resource": resource,
        "issued_at": int(now),
        "expires_at": int(now + minutes * 60),
        # secrets, not random: a predictable nonce is a forgeable grant the day
        # nonce consumption lands.
        "nonce": secrets.token_hex(16),
    }
    # The key must ALREADY exist. `_load_or_create_key` would mint one on
    # first use, which means any process that can write the key path could
    # create a key and then sign grants the enforcement point accepts --
    # bootstrapping Joe's authority out of nothing. `trusted_launcher.authorize`
    # already takes this position for mount grants ("no signing key exists;
    # only Joe's machine can mint grants") and the issuer must not undercut it.
    if not key_path.exists():
        raise InstructionRefused(
            f"no signing key at {key_path}; an instruction cannot be minted on a "
            "machine that holds none. Creating one here would manufacture Joe's "
            "authority rather than exercise it."
        )
    grant = {**payload, "sig": _sign(key_path.read_bytes(), payload)}

    out_dir = out_dir or (key_path.parent / "instructions")
    out_dir.mkdir(parents=True, exist_ok=True)
    # The directory too, and for an EXISTING one as well. `mkdir(exist_ok=True)`
    # leaves the mode of a directory it did not create, so a folder made once
    # under a 0022 umask stays 0755 forever while every grant written into it is
    # 0600. Listing the directory then reveals the category and nonce prefix of
    # every live authorization, which is enumeration of Joe's outstanding
    # instructions even when the contents are unreadable.
    out_dir.chmod(0o700)

    path = out_dir / f"instruction-{category}-{payload['nonce'][:8]}.json"
    # Opened 0600 at the CREATING syscall, not chmod'ed after writing.
    #
    # `write_text()` creates with 0666 & ~umask -- 0644 under the common 0022 --
    # and the following `chmod(0o600)` closed that window only after the signed
    # bearer grant was already on disk and readable by every local user. The
    # window is short but the failure is total: another user reads a signed
    # high-impact authorization and can present it until it expires. And if the
    # process dies between the write and the chmod, the grant stays 0644
    # permanently, which is the state a crash leaves behind rather than a race
    # to lose.
    #
    # `os.open` with the mode argument is the only way to get the permission
    # right at creation; `Path.write_text` has no mode parameter. O_EXCL because
    # a nonce collision, or a pre-planted symlink at this path, must fail rather
    # than silently write Joe's authority somewhere else -- the same reason
    # `evals/run_evaluations.py` creates its run directory with `exist_ok=False`.
    #
    # The umask cannot loosen this: 0600 & ~umask only ever removes bits.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(grant, indent=1, sort_keys=True))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue one signed task-level instruction.")
    parser.add_argument("--action", required=True, help="The action Joe is authorizing.")
    parser.add_argument("--resource", required=True, help="The exact target it is bound to.")
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_INSTRUCTION_MINUTES,
        help=f"Validity window, at most {MAX_INSTRUCTION_MINUTES}.",
    )
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    # A human at a terminal, by default. This does NOT prove the human is Joe
    # -- nothing available in this repository can -- but it stops an unattended
    # agent process from minting a publication or transaction grant simply
    # because it runs under the same account. The check lives here in the CLI
    # rather than in `issue_instruction()` on purpose: a `confirm=` parameter on
    # the library function would be a caller-set boolean guarding an
    # authorization, which is the exact defect this codebase removed three times
    # (`mutating`, `launch_grant_verified`, `explicit_instruction`).
    #
    # THE REAL CONTROL IS KEY CUSTODY. Anything that can READ the signing key
    # can mint a grant without going through this command at all, so where the
    # key lives, and which processes can read it, is the decision that actually
    # bounds this -- and it is Joe's, not the code's. Recorded as open in
    # docs/REPO_OPTIMIZATION_2026-07-25.md.
    if not sys.stdin.isatty():
        print(
            "refusing to issue: no terminal. An instruction authorizes an "
            "irreversible act reserved to Joe, so it is not minted from an "
            "unattended process.",
            file=sys.stderr,
        )
        return 2
    # No skip flag. The first version offered `--yes`, which meant an
    # unattended process could allocate a pseudo-terminal, satisfy isatty(),
    # pass the flag and mint a grant with nobody present -- an escape hatch
    # through the only confirmation there is. A control with an opt-out is the
    # caller-set-boolean defect in another costume.
    category = PolicyEnforcementPoint._boundary_category(args.action)
    print(f"Authorize {category!r} on {args.resource!r}? Type the category to confirm: ")
    if input().strip() != category:
        print("refusing to issue: not confirmed", file=sys.stderr)
        return 2

    try:
        path = issue_instruction(
            args.action,
            args.resource,
            minutes=args.minutes,
            key_path=args.key,
            out_dir=args.out_dir,
        )
    except InstructionRefused as refusal:
        print(f"refusing to issue: {refusal}", file=sys.stderr)
        return 2
    print(path)
    print(
        "This grant is replayable until it expires; nonce consumption is not yet "
        "implemented. Keep the window short.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
