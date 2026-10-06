# NadiNet v3.0

Sentinel-1 radar watches the Jamuna's banks through monsoon cloud, after every
pass, and ranks 200 m bank segments by their risk of losing at least the
threshold distance of land in the next 28 days — tested against what actually
happened in held-out years.

*Work in progress. Full README follows once results are measured.*

## Success criteria (fixed before the test years are scored)

See [docs/VALIDATION.md](docs/VALIDATION.md) for the full protocol.

| Level | Criterion |
|---|---|
| Minimum | Median bank-position error of 20 m or less against Sentinel-2; detection runs across the full 2015–2025 archive |
| Good | Model beats persistence on test precision@20 (2023–2025), with a bootstrap 95% interval that excludes zero |
| Strong | Model beats persistence on both the temporal and spatial hold-outs, and has a lower Brier score |

If the model does not beat persistence, that is reported plainly.
