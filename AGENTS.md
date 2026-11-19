# AGENTS.md — daily-feed

Open this folder as the workspace: `C:\Users\bayla\GitHub\daily-feed`.

One harness. It posts Discord markdown for a locked watchlist. It never pings anyone.

## Clock

| Kind | When it posts |
|---|---|
| `person` with a Twitch login | Every hour, and only while that login is live |
| `movie` with `trailer` or `releases` | 3pm America/Chicago, from 7 days before that date through the day it lands |
| game, show, movie, publisher, tool, athlete, league, match, person with no Twitch | 3pm America/Chicago, and only when the source changed |

AI news posts only when it is about a row already on the list. An AI mod for that game, or that show, movie, publisher, or league using AI, qualifies. A general model or tool launch does not.

The LangGraph gate is `src/daily_feed/gate.py`. Streamer route: live and hour due. Daily route: day due and the page or feed changed. A ping in the text is a skip. The webhook body sets `allowed_mentions.parse` to an empty list.

## Subagents

The parent writes the reply. A subagent gets a short brief and the paths it needs, then returns a compact summary. Do not paste a raw path dump into the chat. The always-on rule is `.cursor/rules/subagents.mdc`.

| When | Who |
|---|---|
| Wide locate, 3+ files | `caveman-explore` on a fast model |
| Diff or multi-file review | `caveman-review` on a fast model |
| Tests, lint, a live pull | `highspeed` on a fast model |
| Docs a person will read | `md-plain-language` on a fast model |
| Claimed done, before push | `adversarial-verifier` |
| One file, one fact | Stay in the parent |

Under about 40% of the context window, the parent edits. Past that, pass a brief and paths, not a transcript.

## Do not

- Put `DISCORD_WEBHOOK_URL` in a committed file. It lives in `.env`.
- Send `@everyone`, `@here`, `<@`, or `<@&`.
- Announce that a streamer went offline.
- Run `graphify install`. The extract script is `.\scripts\graphify-extract.ps1`.

## Check

```powershell
uv sync --extra dev
uv run pytest
```

Steam announcements, the Rockstar newswire graph, and NFL headlines are fetched. The Conduct row reads ESPN for the last 7 days and posts only when the story reports a suspension, firing, ban, or apology tied to a racist, anti-LGBTQ, or antisemitic remark. A quoted slur is blanked in the middle before the summary is written, and it skips stories about teenagers. nfl.com itself is a shell, so the NFL row uses ESPN's public NFL news feed. Twitch needs `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`. News that has no short description asks Gemini 3.8 Flash what happened. `gemini-2.5-flash` is closed to this key. The key is the `GEMINI_API_KEY` Actions secret, passed by `.github/workflows/feed.yml`. There is no local summary. The workflow posts, then commits `state.json` so the next run does not repeat a card. A source picture is attached when Steam, Rockstar, ESPN, or Twitch has one. `fetch_url` is still `NotImplementedError`. Keep tests free of network calls.

## Form

Friends copy `inbox/FORM.txt`. Names must match the official spelling. Twitch logins match the channel URL.
