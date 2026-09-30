# Rank Providers

Show connected players' external ratings in the **ELO** column of an instance's [Live Status](live-status.md) table. Each instance has its own settings. This display does not change sorting or configure in-game balancing plugins.

## Configure A Provider

1. Open the instance action menu and choose **Edit Configuration**.
2. Select **Rank Provider**.
3. Choose a provider, enter its base URL and credential if required, and leave **Enabled** checked.
4. For qlstats, choose **Rating system**. For Thunderdome, open **Advanced** and enter the service pool in **Game type override**.
5. Click **Save** in the Rank Provider tab.

## Providers And Fields

| Provider | Base URL | Credential | Game type |
|----------|----------|------------|-----------|
| qlstats | Host root, such as `https://qlstats.net`; omit `/elo` and `/elo_b` | None | Automatically follows supported server modes |
| Slipgate | API root, such as `https://slipgate.gg/api/v1` | **Upload token**, sent as a Bearer token | Automatically maps the server mode to Slipgate's game type |
| Thunderdome elo-service | Service root, such as `http://host:5002` | **API key**, sent as `X-API-Key` | Required: set the service pool, such as `ffa_auto`, in the override |

**Base URL** is the address the QLSM application uses to reach the service. Include `http://` or `https://`; QLSM appends the request path.

For qlstats, **Rating system** selects `elo` or `elo_b`. Match your balancing plugin's system if you want the displayed ratings to agree. QLSM supplies this URL path automatically, so keep the base URL at the host root.

Leave **Advanced → Game type override** blank for qlstats and Slipgate. QLSM follows the live server game type automatically when it changes. Use the override only for providers with their own pool names, such as Thunderdome's `ffa_auto`; Thunderdome cannot derive a pool from the server game type. The override is sent as entered.

Clear **Enabled** and save to stop displaying ratings while retaining settings. Choose **None** and save to remove the configuration. Saved credentials remain visible in the settings form.

## Read The ELO Column

- With no configured provider, or with the provider disabled, the column is hidden.
- While the first ratings request loads, the column can also remain hidden briefly.
- With an enabled provider, a dash (`—`) means no rating is available for that player. The player may be unranked, the mode unsupported, the provider unreachable, or a credential or pool setting incorrect.
- Ratings can be numbers or labels such as `1650 (Gold)`. QLSM shows the provider's display text without changing team and score sorting.

If you enable a provider after opening Live Status without one, reload the page to start ratings polling for that instance.

Ratings refresh every 30 seconds while Live Status is open. Requests share a cache with a 60-second lifetime for successful results. Provider failures do not interrupt the player and match display.

## Related Pages

- [Live Status](live-status.md)
- [Instance Actions Menu](instance-actions-menu.md)
- [Edit Configs, Plugins, Factories, And Hooks](edit-configs.md)
