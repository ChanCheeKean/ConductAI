---
name: "balance-transfer-disclosure"
description: "Reconcile what was said, offered, and billed for a balance transfer, and distinguish precedents"
routes: ["balance_transfer_disclosure"]
version: "1.0"
---
# Reconcile balance-transfer disclosure across transcript, offer, and statement

1. Read the exact fee language spoken against the offer instance actually submitted, not an earlier offer panel the customer was ineligible for.
2. Resolve the disclosure policy by interaction date; a fee quoted as a percentage only is incomplete once the policy requires a dollar amount too.
3. Compute the fee difference between the quoted rate and the submitted rate with the registered arithmetic helper; never do fee arithmetic in prose.
4. Retrieve candidate precedents and verify each one's governing policy version and offer terms before relying on it — a precedent decided under an earlier rule, or on a materially different offer, does not transfer.

Stop once the spoken rate, submitted rate, governing disclosure clause, and remediation arithmetic are all verified against source records.
