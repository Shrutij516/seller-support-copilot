# data

Synthetic sample data for local development. No real seller or customer data belongs here.

- `policies/`: original policy docs for the fictional marketplace "Kestrel Market" (returns,
  shipping, listing rules, account health, fees, disputes). Written for this project, not
  copied from any real marketplace; used later as the Bedrock Knowledge Base source and for
  eval fact-checking.
- Seller/listing/order rows aren't files here: `make seed` generates them directly into
  Postgres (see [services/api](../services/api/README.md)).
