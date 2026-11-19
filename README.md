# daily-feed

A watchlist that posts Discord markdown for a locked list. It does not ping anyone.

Streamers post every hour, and only while that login is live. Everything else posts at 3pm America/Chicago, and only when the source changed.

The real cards from November 19, 2026 are in [examples/discord-posts.md](examples/discord-posts.md). Ranks are in [examples/topics.md](examples/topics.md).

## Locked list

Only rows on the watchlist can post. Copy `config/watchlist.example.yaml` to start.

| Kind | Rows |
|---|---|
| game | Grand Theft Auto Online, Grand Theft Auto VI, ROB RUN |
| publisher | Rockstar Games, Take-Two Interactive, Marvel, DC Comics, Conduct |
| league | NFL |
| person | Tfue, BurntPeanut |

Steam, the Rockstar newswire, ESPN's NFL feed, and the Conduct feed are fetched. GTA VI, Take-Two, Marvel, and DC are still page rows, so a run sends nothing for them. Twitch needs `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`.

The channel URL stays in `.env` as `DISCORD_WEBHOOK_URL`. One webhook, one channel.

## Add a title

Friends copy `inbox/FORM.txt`. One block per title. A line that is exactly `---` starts the next block.

```
type: game
name: ROB RUN
steam_app_id: 4262460
url: https://store.steampowered.com/app/4262460/ROB_RUN/
```

`streamer` is a person. `twitch:` sets the login. A leading `@` is removed.

## Run

```powershell
uv sync --extra dev
uv run pytest
uv run daily-feed due --now 2026-11-19T21:00:00+00:00
```

`due` prints `yes` at or after 3pm America/Chicago when today's run has not happened yet.

Real cards, no Discord post:

```powershell
uv run daily-feed run --watchlist config/watchlist.example.yaml --state state.json --inbox inbox --no-post
```

Offline shape check. Fixed demo payloads, no network, no post:

```powershell
uv run daily-feed run --watchlist config/watchlist.example.yaml --state state.json --inbox inbox --dry-run --demo
```

`--dry-run` alone prints `not due` or nothing, because it does not fetch. A run without `--no-post` or `--dry-run` posts to Discord. The picture from the source is attached when there is one.

Posts go out oldest first. Each message starts with an emoji, then the name and a `#source` tag on that same line, then the title as the link. A title that only repeats the name is dropped, and that name is the link. `@everyone`, `@here`, and user or role mentions are stripped before send.
