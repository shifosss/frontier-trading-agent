# Learned stock models and ensembles

The Strategy lab now includes a **multi-model** historical study. It uses existing frozen daily histories and keeps the active paper policy separate. The owner requested this expansion on September 19, 2026; the old technical rules are controls, not the final ceiling of the system.

## What is implemented

- 27 price/volume, volatility, market-relative and cross-sectional features with causal trailing windows.
- Four learned predictors: regularized linear regression, randomized trees, gradient-boosted trees and a shared-hidden neural network.
- Six targets: gross returns and completed-close downside magnitudes over 1/3/5 sessions after next-close entry. The neural network jointly learns these outputs. It does not implement transformer attention or calibrated probabilities.
- Equal-weight and validation-weighted forecast ensembles, plus a separately reported correlation-constrained portfolio variant.
- Ten existing technical-rule variants and three declared short-term relative-reversal/continuation rules as matched controls.
- Daily independent cash positions, settled funds, whole shares and the existing sizing constraints.

## Use

Open **Strategy lab → Historical strategy development**. Choose the multi-model study and reuse the saved capture. The application defaults to this new mode; short-hold v1 and legacy remain selectable. Page loads do not launch jobs. A running historical worker is reused through the existing ownership lock.

The study declares 720 account comparisons across US/Canada, native 2,000/10,000 balances, three holding periods and three cost assumptions. Detailed trade records are retained for 42 learned-account comparisons at 2,000 and 40 bps; all paths retain aggregate metrics, daily curves and failures. The panel shows model fitting/calibration diagnostics, benchmark comparisons and research forecast rankings. Those forecasts are not a qualified buy list.

The agent runs the initial qualification and full study; the owner does not need to press Run. Saved status and results distinguish running work from completed reports.

## Evaluation

Each 252-session test block uses an earlier 504-session fitting window and 252-session calibration window. Every training/calibration label must finish strictly before the following window. Models and preprocessing never fit test observations. The calibration window sets per-horizon ensemble weights by prediction error, with explicit equal-weight fallback if none improves on the training-mean baseline. Daily trades still hold only 1/3/5 sessions.

Sampling is bounded to 96 eligible examples per training/calibration date; every eligible stock is forecast during test periods. Missing future outcomes never determine present-day prediction eligibility. Model diagnostics preserve sampling seeds/digests, missing outcomes, convergence warnings and learned weights.

Forecast ranking uses the same proportional fee basis as the cash engine: predicted return times (1-half-cost), less two half-costs and half predicted close-path downside. A positive score is a research entry criterion, not proof of profitability. Current proportional costs exclude fixed broker fees, FX, account charges, taxes and interest. Those require a separate execution-cost qualification.

Current-listed membership, missing delisted firms, current adjusted-price vintage and incomplete corporate-action information remain limitations. Hourly individual-stock models, event/news/fundamental inputs, options strategies, live operation and paper-policy migration are unfinished. See the [predeclared design](superpowers/plans/2026-09-19-multi-model-study.md).
