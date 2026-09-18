# Run the paper operator

The code is implemented and tested with a broker double. No paper account is connected in the delivered workspace. No live endpoint exists in this integration.

1. Create/use a dedicated **Alpaca paper** account with no holdings or orders and set its simulated USD cash to the amount you intend to test. The normal USD100,000 default does not represent the small active sleeve. Do not fund a live account for this setup.
2. Configure `FRONTIER_ALPACA_PAPER_KEY` and `FRONTIER_ALPACA_PAPER_SECRET` in your local environment using paper credentials. The process inherits them; neither the dashboard nor repository stores keys. Do not paste secrets into chat.
3. From the project directory, initialize with the paper account's exact ID and simulated cash. Example only:

```powershell
.venv/Scripts/python.exe -m frontier.cli paper-init --account-id YOUR_PAPER_ACCOUNT_ID --cash-usd 500
.venv/Scripts/python.exe -m frontier.cli paper-cycle
```

Initialization reads the paper account and refuses mismatched cash, existing positions/orders, a non-USD account or a different account ID. It does not deposit or convert funds. The starting balance is a required input; CAD700 monthly contributions are not silently treated as available cash.

4. Start unattended cycles, then open the Trading desk at http://127.0.0.1:8765/:

```powershell
./scripts/start-paper.ps1
```

The runner is hidden on Windows, uses the same initialized account, and logs to `artifacts/paper-operator/`. Alternatively run `paper-watch` in a terminal. It checks every five minutes, only submits during regular market hours, and creates daily plans outside the session. The machine must remain awake and connected. No OS login task, cloud service, broker connection or runner was automatically activated during development.

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
issues. The five-minute local runner is optional and is not currently running.
