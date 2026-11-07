# Mistral plan and spend for Omarchy

An [Omarchy](https://omarchy.org) shell plugin that adds your Mistral plan, Vibe
budget and API budget to the Agents panel, next to Claude Code, OpenRouter and
the rest. Omarchy's built-in Mistral Vibe section only shows local stats.

```
Mistral Vibe                       Team · PAYG
Vibe     ▓▓▓▓▓░░░░░░░░░              23d 15h
API      ░░░░░░░░░░░░░░              23d 15h
Balance  ▓▓▓▓▓▓▓▓░░░░░░              €180.00
€120.00 spent of €300.00 funded
```

These are example numbers.

## Install

You need Omarchy with the Agents panel, and a Mistral API key in `~/.vibe/.env`
or the `MISTRAL_API_KEY` environment variable. Keys Vibe keeps in the system
keyring aren't read.

```bash
omarchy plugin add https://github.com/jeesondk/omarchy-mistral-plan.git --enable
```

If nothing appears, run `omarchy restart shell`. To turn it off:

```bash
omarchy plugin disable jesper.mistral-plan
```

The panel's next refresh removes everything the plugin added.

## What it reads

- **Network:** every 15 minutes, or 5 minutes after a failed check, it sends your
  API key to `api.mistral.ai`, and nowhere else, to call `GET /v1/billing/budget`
  and `GET /v1/billing/subscription`. These are the calls Vibe uses for its footer.
- **Files:** it writes the result to
  `~/.local/state/omarchy/mistral-plan/budget.json` and adds it to the panel's
  `vibe.json` record. It reads `~/.vibe/.env` and never writes to `~/.vibe`.

## What it can't show

- **Pay-as-you-go spend or credit balance.** The API only says whether PAYG is on,
  so `PAYG` in the header doesn't mean anything has been charged. Check the
  [Admin Panel](https://admin.mistral.ai/organization/usage) for those.
- **Spend past the included budget.** Mistral documents usage as 0-100%, so the
  balance line is expected to stop at the full budget while PAYG keeps charging.
- **Your overage spending cap.** The API doesn't report it.

"Spent" is the reported percentage times the budget, which is your use of the
included allowance, not an invoice.

## Limitations

- Only tested on one Team plan. Other plans may answer differently.
- Mistral's billing API is tagged beta and could change.
- `/v1/billing/budget` needs the `see_org_inference_usage` permission. Without it,
  or if the key is refused, the plugin removes its figures.
- It re-applies its figures each time Omarchy's collector rewrites the record, so
  they're missing for a few milliseconds on each panel refresh.
- After editing `Service.qml`, run `omarchy restart shell` to load the new code.

## Tests

```bash
python3 -I -B test/test_refresh_budget.py
```

Not affiliated with Mistral AI or Omarchy.
