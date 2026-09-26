# Kestrel Market: Account Health

Account Health is Kestrel Market's single score summarizing how reliably a seller is
fulfilling orders and following platform rules. It determines what selling privileges a
seller keeps, and whether they're at risk of suspension.

## What goes into the score

Account Health is a 0-100 score recalculated nightly from a trailing 90-day window, weighted
across four inputs:

- **Order defect rate** (40% of score): the share of orders resulting in a valid buyer
  complaint, an unresolved refund request, or a payment dispute. Must stay under **1%** to
  avoid a penalty.
- **On-time delivery** (25% of score): pulled directly from the metrics defined in the
  Shipping and Delivery SLAs policy. Must stay at or above 90%.
- **Policy violations** (25% of score): strikes from the Listing Rules policy and any
  confirmed Trust and Safety violation. Each active strike subtracts 10 points.
- **Response time** (10% of score): average time to respond to buyer messages and refund
  requests. Must stay under 24 hours on average.

## Score bands and what they mean

| Score    | Standing          | What it means                                                 |
| -------- | ----------------- | ------------------------------------------------------------- |
| 90-100   | Good standing     | Full selling privileges, eligible for featured placement.     |
| 70-89    | Fair standing     | Full selling privileges, not eligible for featured placement. |
| 50-69    | At risk           | Warning issued; seller must submit an improvement plan.       |
| Below 50 | Suspension review | Selling paused pending manual review by Kestrel Market.       |

## Falling into "At risk"

When a score drops into the 50-69 band, the seller receives a notice explaining which
inputs are driving the drop, and has **14 days** to submit a written improvement plan through
the Seller Portal. Selling privileges continue during this period. If the score does not
improve within 60 days of the plan being accepted, the account moves to suspension review.

## Suspension review and appeals

A score below 50 pauses new listings and checkout on existing ones while Kestrel Market
reviews the account. The seller keeps access to fulfill orders already placed and to respond
to open refund requests during this period. A decision is issued within **5 business days**:
reinstatement, continued restriction with specific conditions, or permanent suspension for
repeated or severe violations (such as a confirmed counterfeit strike).

Sellers can appeal a suspension once, within 30 days of the decision, by submitting evidence
through the Seller Portal. Appeals are reviewed by a different Trust and Safety reviewer than
the one who made the original decision. There is no fee to appeal.

## Excluded from the score

Order defects and delivery delays caused by documented events outside the seller's control
(carrier-wide service disruptions, natural disasters affecting a shipping region, a Kestrel
Market platform outage) are excluded from the calculation once verified by support. Sellers
should flag these situations proactively through the Seller Portal rather than waiting for
Account Health to reflect them, since automatic exclusion is not guaranteed for every
disruption.
