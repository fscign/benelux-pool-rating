# Pool data (raw results for the pool ratings)

Non-commercial, for the pool community. This repository collects raw pool results from every source used by the
national ratings (German, Polish, later others). It only collects; the ratings are built in their own repositories,
which download these files. The Latvian rating keeps its own Baltic collection.

## Where the data is
- **Release "data"**: one file per source, replaced by every collection run (no growing git history).
  Download: `https://github.com/fscign/pool-data/releases/download/data/<file>`
- `data/` in the repo: starting copies from 9 Nov 2026, used only if a release file is missing.
- `status_<source>_<script>.txt` in the release: last run per source (time, OK/FAILED, last log line).

## Sources and files
| Workflow | Source | Files |
|---|---|---|
| cuescore.yml (00:07 UTC) | CueScore, per country: de, pl, cz, nl, be, lu, at, ch, it, fr | `<cc>_cuescore_raw.json.gz`, `<cc>_team_raw.json` |
| sources.yml (01:07 UTC) | tournamentapp.de | `ta_raw.json` |
| | nuLiga Bavaria | `bbv_nuliga_data.json.gz` |
| | VeVeTo Hessen | `hessen_veveto.json.gz` |
| | Score Trek Battle | `scoretrek_raw.json.gz` |
| | Tournament Service (all countries) | `ts_raw.json.gz` |
| | pzbil.pl (Polish federation) | `pzbil_raw.json.gz` |
| | EPBF | `epbf_data.json.gz` |
| | Matchroom / WNT (needs secrets WNT_EMAIL, WNT_PASSWORD) | `wnt_data.json.gz` |
| pbs.yml (manual) | Predator Pro Billiard Series (ids in `pbs_ids.json`, fixes in `pbs_fixes.json`) | `pbs_data.json.gz` |

Each country and each source is a separate job: if one fails, the others are still saved.
Collectors were moved here on 9 Nov 2026 from german-pool-rating, polish-pool-rating, benelux-pool-rating (this repo,
renamed) and latvian-pool-rating (EPBF, Matchroom, PBS).
