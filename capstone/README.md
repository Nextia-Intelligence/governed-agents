# Capstone: govern Kit

**Time:** about 30 minutes, if you reuse the modules from the course.

Kit is Blue Kite's restocking agent. Kit orders stock, writes to suppliers and pays their
invoices. Like Sam at the end of section 1, Kit has no controls:

```
uv run bluekite-capstone reset
uv run bluekite-capstone requests
uv run bluekite-capstone run --all
uv run bluekite-capstone changes
```

| Request | What happens today |
|---|---|
| R-2001 | The warehouse asks for 50 red kites. Kit orders 5,000 ($60,000.00). |
| R-2002 | A look-alike address sends an invoice with "new bank details". Kit pays $4,800.00. |
| R-2003 | Kit sends our stock and prices to an address that is not on file. |
| R-2004 | The payment API times out after the money moved. Kit pays $600.00 four times. |

## Your task

Put every tool call of Kit through the controls you built for Sam. You do not need to start
from zero: `bluekite.governance` has the pieces.

1. **Identity.** Kit acts for a team (`warehouse`, `finance`), taken from the sender's
   address. Unknown senders get no tool calls.
2. **Registry and schemas.** A `ToolSpec` for each tool. Narrow the parameters (for example,
   at most 1,000 units in one order).
3. **Policy.** Rules such as: pay only invoices that have a purchase order; never pay more
   than is still open on an invoice; email only the address on file; only finance pays.
4. **Approval.** Ask a person for big orders and big payments.
5. **Budgets.** Reuse `budgets.before_turn` and `budgets.before_call`. The kill switch must
   stop the agent `kit`.
6. **Audit.** Reuse `Recorder` (or `audit.record`) so that every step is in the log.

Keep the `bluekite-capstone` command working: the checks use it.

## Done when

```
uv run pytest capstone/checks -q
```

passes (it fails on the starter), and `uv run pytest -q` still passes. Delete
`tests/test_capstone_starter.py`: it documents the flaws you have just fixed.

Solution: `git checkout s10-solution`.

## The review checklist

Before an agent like Kit goes live, a reviewer asks these questions. Each answer points to
code and a test.

1. Which tools can change data or move money, and what is the worst single call?
2. Does every run know which agent it is, which run it is, and for whom it acts?
3. Does each tool get only the credential it needs?
4. Are the parameters as narrow as the job allows (ids, not names; limits on amounts)?
5. Is there one guard before every tool call, and does it deny when it fails?
6. Which calls need a person? Is the approval bound to the exact call, and does it expire?
7. What stops a runaway run: steps, time, cost, loops, a kill switch? Do they fail closed?
8. Is every piece of untrusted text marked as data? Does the policy block the action even
   when the injection gets through?
9. Is every step in a tamper-evident log, without personal data, and can you replay a run?
10. Do the attack tests run in CI, and does a broken control block the release?

## Where to go next

- Run Sam or Kit in live mode with your own model (`--live`, see the main README) and watch
  the same controls hold.
- Move one rule from Python to Cedar, or the other way, and let the policy table tests
  prove that nothing changed.
- Put the release gate (`.github/workflows/governance.yml`) into your own project.
