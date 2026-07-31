# Portfolio Risk Limits

**Effective date:** 2026-07-28
**Scope:** Unlevered, long-only, ten-stock model portfolio measured against total portfolio value unless stated otherwise.

| Control | Limit | Required response |
|---|---:|---|
| Target stock count | 10 | Do not add an eleventh stock; replace or hold cash. |
| Target cash | 13% | Normal operating target. |
| Minimum cash | 10% | Reject any new/add proposal that would fall below it. |
| Maximum cash | 25% | Permitted during weak opportunity sets or elevated risk; above 25% requires a documented defensive rationale. |
| Target initial position | 8.7% | Equal-weight starting point for the normalized model. |
| Maximum initial position | 10% | Reject larger initiations. |
| Maximum single position | 13% | Trim-review trigger after appreciation; never an automatic order. |
| Maximum sector exposure | 26% | Use GICS where available and calculate before/after exposure. |
| Maximum single-theme exposure | 26% | Aggregate economically correlated names even when sectors differ. |
| Maximum total speculative exposure | 8% | Includes all positions meeting the speculative definition below. |
| Maximum single speculative position | 4% | A speculative holding cannot be a full core position. |
| Portfolio drawdown review | −10% | Freeze additions; refresh all theses and stress tests. |
| Portfolio drawdown de-risk review | −15% | Present cash-raising alternatives; Joe decides. |
| Single-position loss review | −12% from verified cost | Immediate thesis review; no mechanical sale. |
| Single-position hard invalidation review | −18% from verified cost | Default to `EXIT-REVIEW` unless primary evidence affirmatively repairs the thesis. |
| Drawdown-from-high review | −20% from trailing 52-week high | Re-underwrite catalyst, valuation, and trend. |
| Options | Prohibited | No opening option recommendation. |
| Margin and leverage | Prohibited | Include embedded leverage when classifying products. |
| Short selling | Prohibited | Long-only mandate. |

## Exposure and classification rules

- Use total portfolio value for target weights and cash. Also report invested-capital weights when comparing with the repository’s mechanical risk engine.
- Calculate position, sector, theme, speculative, and cash exposures before and after every proposal. Look through funds when reliable holdings are available.
- Theme exposure follows economic drivers, not issuer labels. At minimum track `AI/cloud`, `digital-commerce/advertising`, `consumer-defensive`, `financial/payments`, `healthcare`, `energy`, and `industrial-cycle`.
- A position is speculative when material value depends on unproven commercialization, a binary regulatory/clinical/legal result, near-term external financing, highly uncertain commodity/crypto sensitivity, or a pre-profit model without demonstrated funding resilience. When classification is uncertain, use speculative.
- The initial ten-name model contains no designated speculative holding. A later speculative addition must replace—not sit on top of—a core allocation and comply with both speculative caps.
- A new/add limit breach produces `REJECT`. An existing breach produces `REVIEW`, not an automatic transaction.
- Correlation matters even when sector caps pass. If trailing 60-session pairwise correlation exceeds 0.75 for three or more full-size holdings, reduce combined theme exposure to 22% or less.
- Use closing or real-time prices from one timestamped source for a complete exposure calculation; do not mix timestamps silently.

## Portfolio-level stress tests

Before any `CANDIDATE` status, report estimated portfolio impact under: broad market −10%; growth/AI factor −20%; oil −20%; consumer demand slowdown; 100-basis-point rate increase; and issuer-specific bear cases. If estimated portfolio loss exceeds 15% in a plausible combined scenario, propose smaller positions or more cash.
