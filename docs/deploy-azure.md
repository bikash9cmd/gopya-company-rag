# Deploying to Azure

A small deployment for one company: one container, no database server, roles from Entra ID.

## Pieces

| Need | Azure service |
|---|---|
| Run the API and UI | Azure Container Apps (scale to zero when idle) |
| Image | Azure Container Registry |
| Sign-in and roles | Microsoft Entra ID; one security group per role, sent as the `groups` claim |
| Model key | Azure Key Vault, referenced as a Container Apps secret |
| Traces and cost dashboard | Log Analytics; the trace JSON lines go to stdout and are collected by Container Apps |
| Documents | Azure Blob Storage, one container per collection, synced into the image at build time |

## Steps

```bash
az group create -n gopya-rg -l centralindia
az acr create -g gopya-rg -n gopyaacr --sku Basic
az acr build -r gopyaacr -t gopya:1 .

az containerapp env create -g gopya-rg -n gopya-env -l centralindia
az containerapp create -g gopya-rg -n gopya --environment gopya-env \
  --image gopyaacr.azurecr.io/gopya:1 --registry-server gopyaacr.azurecr.io \
  --target-port 8000 --ingress external --min-replicas 0 --max-replicas 2 \
  --secrets llm-key=keyvaultref:https://<vault>.vault.azure.net/secrets/llm-key,identityref:system \
  --env-vars GOPYA_LLM_API_KEY=secretref:llm-key GOPYA_TRACE_FILE=/dev/stdout
```

Then turn on Container Apps authentication with Entra ID and require sign-in.

## Mapping Entra ID groups to roles

`data/users.toml` holds demo tokens. In production, replace `current_user` in `gopya/api.py` with
a function that reads the `X-MS-CLIENT-PRINCIPAL` header Container Apps adds after sign-in, takes
the user's group IDs from it, and maps them to a role:

```toml
# data/roles.toml
[roles.finance]
collections = ["general", "finance"]
entra_groups = ["<object id of the Finance group>"]
```

A user in more than one group gets the union of the collections, and PII clearance only if one of
their roles has it.

## Cost

With scale to zero and the offline answerer, the running cost is the registry (about $5 a month)
plus Log Analytics ingestion. With a model, the trace file gives the per-request token cost, and
`GOPYA_DAILY_TOKEN_BUDGET` caps each user's daily spend.

## Updating documents

Documents are baked into the image with the index, so an update is a new build. That keeps the
running container read-only and makes every answer traceable to an image tag. For frequent updates,
mount the index from Azure Files and rebuild it with a scheduled job instead.
