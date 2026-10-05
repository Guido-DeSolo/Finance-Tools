# Backend jobs

The backend contains scheduled data-ingestion services and explicit research
actions. From `DF-FinTechTerm`, list or run them with:

```sh
./df-fintechterm services
./df-fintechterm service NAME
./df-fintechterm actions
./df-fintechterm action NAME
```

The repository [README](../../README.md) lists each service and action. Services
store market/news/insider data or deliver configured alerts; they do not trade.
