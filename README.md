# Blue Kite: build governed AI agents in Python

The code for the course *Build Governed AI Agents in Python*. Blue Kite is a small online kite shop.
Sam is its support agent. Sam reads customer tickets and can look up orders, change an address,
issue refunds and close accounts. In section 1, Sam has no controls and fails five practice tickets.
Each later section adds one control and replays the same tickets.

All people, emails and addresses in this project are fictional.

## Get the code

```
git clone https://github.com/Nextia-Intelligence/build-governed-ai-agents.git
cd build-governed-ai-agents
```

## Set up (3 commands)

You need Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run bluekite reset
uv run pytest -q
```

Then try `uv run bluekite tickets`: the five practice tickets. From section 1 on,
`uv run bluekite run T-1001` lets Sam work on the first one.

## Replay mode and live mode

- **Replay mode** is the default. The model's answers come from recorded files in
  `src/bluekite/recordings/`. You need no API key and no network, and every run prints the same
  output as the videos.
- **Live mode** (from section 1 on, when Sam exists) uses any OpenAI-compatible endpoint:

  ```
  uv sync --extra live
  export BLUEKITE_BASE_URL=https://your-endpoint/v1
  export BLUEKITE_API_KEY=...
  export BLUEKITE_MODEL=your-model
  uv run bluekite --live run T-1001
  ```

  A live model may answer differently from the recording. The controls still apply.

## One tag per section

Check out the code as it is at the end of any section, for example `git checkout s03`.

| Tag | Section | What it adds |
|---|---|---|
| `s00` | Welcome | the project, the shop and the tickets |
| `s01` | Why an agent needs governing | Sam, ungoverned: five tickets, five failures |
| `s02` | Identity and least privilege | agent and run identity, a tool registry, scoped credentials |
| `s03` | Policy as code | one guard before every tool call, rules in Python and in Cedar |
| `s04` | Human approval | an approval queue, the run waits for a person |
| `s05` | Budgets and stopping | step, time and cost limits, a loop detector, a kill switch |
| `s06` | Untrusted input | ticket text and tool results marked as data, an injection flag |
| `s07` | Audit trail | a hash-chained audit log, personal data redacted, replay |
| `s08` | Test the controls | governance tests, attack tests, a release gate in CI, metrics |
| `s09` | From code to evidence | an evidence pack mapped to common frameworks |
| `s10` | Capstone | Kit, the restocking agent, for you to govern |

Sections 2 to 8 have an exercise in `exercises/`. The solution is on the tag `sNN-solution`,
for example `git checkout s03-solution`. The capstone solution is on `s10-solution`.

## Where things are

```
src/bluekite/
  shop.py         the fake shop: SQLite in state/shop.db
  tickets.json    the practice tickets
  tools.py        Sam's four tools
  model.py        the model: replay or live
  agent.py        the agent loop
  cli.py          the bluekite command
  recordings/     the recorded model answers, one file per ticket
  governance/     the controls, added section by section
policies/         Cedar policies (from section 3)
tests/            the tests
exercises/        one task per section
capstone/         Kit, the capstone agent (section 10)
```
