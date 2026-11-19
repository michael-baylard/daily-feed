# daily-feed

A watchlist that runs once a day at 3pm America/Chicago. It posts Discord markdown for the games, shows, movies, publishers, and Twitch streamers you locked in. It does not ping anyone.

A new row in `inbox/` is picked up on the next run.

## What stays cheap

The harness checks the list every day. It calls a model only when a movie or publisher page has changed. Steam news, a TVMaze episode, and a locked Twitch title are read from the payload. Those posts skip the model.

Names share one id. `Spider-Man: No Way Home` becomes `spider_man_no_way_home`. The letters-only search key is `spidermannowayhome`. The prompt includes both, so a later search hits the same string the file uses.

## Locked list

Only rows on the watchlist can post. A Twitch update must match that person's login. DC Comics and Marvel are publishers with their own page URLs. A fetched slug that is not on the list is dropped.

Copy `config/watchlist.example.yaml` to start. Kinds: `game`, `show`, `movie`, `publisher`, `person`.

## Add a title

Friends copy `inbox/FORM.txt`. One block per title. A line that is exactly `---` starts the next block.

```
type: movie
name: The Batman
url: https://example.com/the-batman
```

`streamer` is a person. `twitch:` sets the login. A leading `@` is removed.

## Run

```powershell
uv sync --extra dev
uv run daily-feed due --now 2026-11-19T21:00:00+00:00
uv run pytest
```

`due` prints `yes` at or after 3pm America/Chicago when today's run has not happened yet.

```powershell
uv run daily-feed run --watchlist config/watchlist.example.yaml --state state.json --inbox inbox --dry-run --demo
```

`--dry-run` prints the messages and does not post. Live page fetch and the Discord webhook POST are the next wiring step. The run, the order, and the safety checks are already tested.

Posts go out oldest first. Each message is a header, a few lines, a masked link, and a small source line. `@everyone`, `@here`, and user or role mentions are stripped before send.

130 tests cover slugs, the form, dedupe, order, pings, the 3pm gate, and the lock to listed streamers and publishers.
