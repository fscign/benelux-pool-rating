# Benelux Pool Rating (data collection: Netherlands, Belgium, Luxembourg)

Non-commercial, for the pool community. This repository collects CueScore pool results from the Netherlands, Belgium and
Luxembourg every day (started 7 Nov 2026). Everything is stored raw; a later build decides what counts.

- `collect_cuescore.py` (CS_COUNTRY, CS_FILE) -> `data/{nl,be,lu}_cuescore_raw.json.gz`: every pool tournament since 2016.
- `collect_team.py` (CS_COUNTRY, CS_TEAM_FILE) -> `data/{nl,be,lu}_team_raw.json`: single games inside CueScore team events.
- `data/status/*.txt`: last run per country and script (time, OK/FAILED, last log line).
- Runs every day at 00:07 UTC. The first run reads everything since 2016; if the time limit cuts it off, the next run continues.
- The German rating (fscign/german-pool-rating) copies these files every day and counts the matches of German players.
