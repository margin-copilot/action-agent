# Margin Copilot: action-agent

Drafts **pending** price-change proposals. It can't approve, reject or list them: a person does that on the approval screen, through proposals-api (D-003).

Part of **Margin Copilot**, a secure multi-agent pricing assistant on Azure, built as a personal learning project.

**Start here:** [margin-copilot/docs](https://github.com/margin-copilot/docs) explains how the whole system works, the security model and the decisions behind it.

## What it does

An A2A server (skill `drafts`), behind the shared token check. The orchestrator is the only allowed caller. Per request:

1. **gpt-5-mini extracts** the request with structured output: is it a draft, which product, which region, and the new price or the percent. Reasoning effort is low and there are no tools. The request is data, not instructions.
2. **proposals-api creates the draft.** Code sends `POST /drafts` with an on-behalf-of token for the user. proposals-api reads the tier and current price itself and decides who may approve. Its reply is validated against the shared `Proposal` contract and must be `pending`.
3. **Code writes the reply** from fixed sentences built from the stored proposal (D-038), so it can't misstate the price, the percent, the status or the approver:

   > Drafted proposal 1a2b3c4d, pending approval: UHT milk 1 L in the North, 7.00 → 7.25 MAD (+3.57%). The North pricing manager can approve it on the approval screen (PP-04 §3.2).

**Refusals, set by code:**
- another region, or a sign-in with no pricing role: `no_access`;
- an unknown product or no recorded price: `no_data`.

**Other replies, with no refusal label:**
- several matching products: it asks which one;
- a draft over a hard cap: it quotes the rule and cites it.

**Failures** reach the caller only as `action-agent failed`: proposals-api errors, a 403 from its token check (a misconfiguration, not the user's permission), and a model call over its 30 s limit.

## Contract

One data part per reply, in the shared `AgentReply` (`answer`, `refusal`, `citations`).

## Settings

Names in [.env.example](.env.example); no defaults in azure mode.

## Run and test

```bash
uv sync
uv run pytest -q
ADAPTERS=fake uv run uvicorn --factory action_agent.main:create_app
```

## Deploy

A push to `main` runs the tests, publishes `ghcr.io/margin-copilot/action-agent:sha-<commit>`, then deploys the image to the container app through GitHub OIDC (no stored Azure secret). The deploy waits up to 5 minutes for the new revision to serve all traffic, or fails while the old revision keeps serving. The app has internal ingress only, so there is no smoke call from the runner; the orchestrator's live checks cover it. Deploys run one at a time, in push order; other branches and pull requests get no Azure token. Repository secrets: `AZURE_CLIENT_ID` (this repo's deploy identity), `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `CONTAINER_APP_NAME`. The infra repo creates the app and the identity; how it all fits: [docs](https://github.com/margin-copilot/docs).

## License

MIT. See [LICENSE](LICENSE).
