# Run the paper operator

Activated September 18, 2026 at approximately 14:51 Toronto time on the existing **US$100,000 Alpaca paper account**, following the owner's instruction to use its current balance. Initialization, real paper-account reconciliation and the hidden five-minute worker were verified. The first observations contain no holdings or orders; no daily decision has been saved yet. Check the Trading desk and runner logs for current state. No live endpoint exists in this integration.

This is a larger-account operating and strategy trial. Signal rules are unchanged, but whole-share affordability and position sizes differ from a US$500 account. These results must not be presented as small-budget execution validation. The setup below is for a fresh account; **do not reinitialize the active journal**.

1. Create/use a dedicated **Alpaca paper** account with no holdings or orders and the simulated USD cash you intend to test. Current Alpaca documentation says a different starting balance requires creating a new paper account from the dashboard account selector, then generating that account's new keys; no account needs to be deleted. [Official instructions](https://docs.alpaca.markets/us/docs/paper-trading). The normal USD100,000 default does not represent the small active sleeve. Do not fund a live account for this setup.
2. Configure `FRONTIER_ALPACA_PAPER_KEY` and `FRONTIER_ALPACA_PAPER_SECRET` in your local environment using paper credentials. The process reads them from its environment; on Windows it also reads these exact two User variables when both are absent from an older process environment. Neither the dashboard nor repository stores keys. Do not paste secrets into chat.
3. From the project directory, initialize with the paper account's exact ID and simulated cash. For example, when that empty paper account contains US$100,000:

```powershell
.venv/Scripts/python.exe -m frontier.cli paper-init --account-id YOUR_PAPER_ACCOUNT_ID --cash-usd 100000
.venv/Scripts/python.exe -m frontier.cli paper-cycle
```

Initialization reads the paper account and refuses mismatched cash, existing positions/orders, a non-USD account or a different account ID. It does not deposit or convert funds. The starting balance is a required input; CAD700 monthly contributions are not silently treated as available cash.

4. Start unattended cycles, then open the Trading desk at http://127.0.0.1:8765/:

```powershell
./scripts/start-paper.ps1
```

The runner is hidden on Windows, uses the same initialized account, and logs to `artifacts/paper-operator/`. Alternatively run `paper-watch` in a terminal. It checks every five minutes, only submits during regular market hours, and creates daily plans outside the session. The machine must remain awake and connected. The local runner was started for the authorized trial. It is not installed as an OS login task or cloud service; after a reboot, run `scripts/start-paper.ps1` again. Closing the dashboard does not stop the worker.

Useful controls:

```powershell
.venv/Scripts/python.exe -m frontier.cli paper-status
.venv/Scripts/python.exe -m frontier.cli paper-pause
.venv/Scripts/python.exe -m frontier.cli paper-pause --resume
```

Pause stops new entries; the next running cycle requests cancellation of open buys and continues daily exits. It is not a broker-wide immediate cancellation button. A 30% sampled CAD drawdown halt stays latched despite resume or funding additions.

After an intentional funding change **already made in the paper simulator**, record exactly that observed change with a unique ID:

```powershell
.venv/Scripts/python.exe -m frontier.cli paper-flow --event-id september-test-addition --amount-usd 500
```

The command validates cash against known fills plus the declared flow. It does not transfer money. Duplicate event IDs, unexplained holdings, unsupported corporate/manual changes or uncertain orders require reconciliation. Do not delete the journal to clear an error or automatically resend an uncertain order. Journal location: `data/operator.sqlite`.

The paper API does not reproduce dividends, all fees or real market impact. Whole-share cash constraints are imposed by Frontier; paper buying power is ignored. No completed trial, profitable edge, real account permission, Canadian execution or options capability is claimed. See [delivery plan](automated-trading-plan.md) for the remaining live-deployment work and reasons.


The existing Codex follow-up now checks this project on weekdays at 09:35 and 17:35
Toronto time. It inspects local setup first and only calls the paper cycle after the
owner has initialized the dedicated paper mandate; otherwise it continues local
qualification/research. This follow-up is not a substitute for an awake host or an
observed paper connection. Notifications remain limited to meaningful changes or
issues. The five-minute local runner was started for this trial. When it is running and observations are fresh, the follow-up inspects its saved results instead of starting a duplicate cycle.


Activation evidence is saved locally in `artifacts/paper-operator/activation.json` and `running-check.json`; the pre-activation SQLite backup passed its integrity check. For this Friday activation, the first eligible decision uses the September 18 completed close after 16:01 Toronto time, once all required data are available. Any qualifying weekly entries become eligible on Monday, September 21 at 09:30 Toronto time, and are checked on the next worker poll. This schedule is not a promise that a signal or fill will occur.


September 18 launcher qualification found that the old Windows launch retained the command parent until its child finished. Both launchers now use independent standard streams and restricted inherited handles. A disposable child survived parent exit, repeated starts reused the existing worker, and the actual paper worker recorded a later scheduled cycle. Logs append; earlier logs were backed up. Broad strategy research is separately scheduled and visible in [Strategy lab](broad-research.md).


## September 28 operating observation

The initialized worker was found stopped after its September 26 observation and was resumed using the existing launcher. At 14:37 Toronto it submitted the three saved September 25 paper intents using their original durable IDs. The broker subsequently confirmed MSFT 15 at USD511.03, META 6 at USD721.74 and XOM 42 at an average USD162.142619. These are simulated fills in the existing USD100,000 account, not a deployment of the learned USD2,000 candidate.

An XOM partial fill was observed while sequential broker snapshots were changing, causing a holdings mismatch and a visible recovery status. A read-only check reconciled all three filled orders to broker holdings and USD81,194.12 cash (USD0.000002 difference from the broker's rounded average fill prices). The next scheduled five-minute cycle at 14:42 reconciled successfully and returned `ready`, with the same three IDs and no resubmission. The frozen operator code identity remained `9fd509d8ce514b9fe3e3136684c7475637a12304670cc517b285e48aebbc26a2`.

Evidence: `.qualification/stateful-daily-agent/paper-reconciliation-20260928.json` and `paper-recovered-20260928.json`, plus the original journal acknowledgements and runner logs. This qualifies one observed partial-to-full/reconciliation recovery path, not every disconnect, rejection or corporate-action case. The host must still be awake; automatic OS startup and an always-available deployment are not established by this observation.
