# aimanac

Operator CLI for an AiMANAC backend deployment. Stdlib-only Python — zero runtime dependencies, trivial to install.

## Install

```
pip install aimanac
```

## Commands

```
aimanac status                                # claimed? + health + first-owner claim mode
aimanac show-code                             # print the owner setup code (lockout recovery)
aimanac rotate-code --confirm                 # regenerate the owner setup code, then print it
aimanac init "<Display Name>" [--setup-code CODE]   # claim the first owner
aimanac update --confirm                      # volume-safe image update
```

## Config

- `--url` / `AIMANAC_URL` — backend base URL (default `http://127.0.0.1:8080`)
- `--container` / `AIMANAC_CONTAINER` — docker container (default `aimanac-magus-rs`)
- `--json` — machine-readable output

## Why `update` is safe

`update` only ever runs `docker compose pull` + `docker compose up -d`, which recreate containers on the new image while **preserving named volumes**. It never runs `down` — let alone `down -v`. The 2026-06-23 lockout class (a `down -v` that wiped `/app/data/.env.generated`, silently re-minting the JWT keys and the owner setup code) cannot recur through this tool. `show-code` / `rotate-code` are the recovery + rotation for when it already has.
