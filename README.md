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
One workflow per source and per CueScore country (each can be run on its own with "Run workflow"); times UTC.
| Workflow | Source | Files |
|---|---|---|
| cuescore-de / pl / cz / nl / be / lu / at / ch / it / fr (00:07 to 01:55, every 12 min) | CueScore tournaments + team events of that country | `<cc>_cuescore_raw.json.gz`, `<cc>_team_raw.json` |
| cuescore-nordic (02:07; added 12 Nov 2026; one workflow, one parallel job per country; first run reads everything since 2016) | CueScore Finland, Sweden, Denmark, Norway | `fi_` / `se_` / `dk_` / `no_cuescore_raw.json.gz`, `<cc>_team_raw.json` |
| cuescore-uk / south / east / rest (02:19, 02:31, 02:43, 02:55; added 13 Nov 2026; countries in `cs_regions.py`; only 8/9/10-ball and straight pool) | CueScore UK & Ireland, Southern Europe, Balkans & East, Rest of World (every non-European country) | `uk_` / `south_` / `east_` / `rest_cuescore_raw.json.gz`, `<region>_team_raw.json` |
| bilijar (03:07; added 13 Nov 2026) | bilijar.club: Serbia and some clubs in HR, BA, ME, MK, since 2016 | `bilijar_raw.json.gz` |
| tbf (on push of `data/tbf_raw.json.gz`; added 13 Nov 2026) | Turkish federation pool portal, read monthly in the browser on Aleksandrs's PC (the portal refuses GitHub) | `tbf_raw.json.gz` |
| swisspool (03:31; added 13 Nov 2026) | Swisspool (Swiss federation), same collector as tournamentapp.de, since 2021 | `swisspool_raw.json` |
| oepbv (03:43; added 13 Nov 2026) | ÖPBV (Austrian federation), every tournament since 2019 | `oepbv_raw.json.gz` |
| tournamentapp.yml (00:13) | tournamentapp.de | `ta_raw.json` |
| nuliga.yml (00:25) | nuLiga Bavaria | `bbv_nuliga_data.json.gz` |
| veveto.yml (00:37) | VeVeTo Hessen | `hessen_veveto.json.gz` |
| scoretrek.yml (00:49) | Score Trek Battle | `scoretrek_raw.json.gz` |
| tournamentservice.yml (01:01) | Tournament Service (all countries) | `ts_raw.json.gz` |
| pzbil.yml (01:13) | pzbil.pl (Polish federation) | `pzbil_raw.json.gz` |
| epbf.yml (01:25) | EPBF | `epbf_data.json.gz` |
| wnt.yml (01:37) | Matchroom / WNT (needs secrets WNT_EMAIL, WNT_PASSWORD) | `wnt_data.json.gz` |
| pbs.yml (Mondays 01:49, and right after `pbs_ids.json` changes) | Predator Pro Billiard Series (ids in `pbs_ids.json`, added by a monthly check in the browser; fixes in `pbs_fixes.json`) | `pbs_data.json.gz` |

If one source fails, the others are not affected.
Collectors were moved here on 9 Nov 2026 from german-pool-rating, polish-pool-rating, benelux-pool-rating (this repo,
renamed) and latvian-pool-rating (EPBF, Matchroom, PBS).
