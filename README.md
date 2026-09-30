# Cookpal for Home Assistant

Your [Cookpal](https://cookpal.io) shopping lists as Home Assistant to-do lists. Add, tick off and remove items from dashboards, automations and voice assistants, and see changes from the Cookpal app within half a minute.

Handy as a bridge: anything that can add to a Home Assistant to-do list can now fill your Cookpal list, for example a Google Keep sync for "Hey Google, add milk to my shopping list".

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=steve192&repository=cookpal-home-assistant&category=integration)

1. Click the button above, or in HACS add `https://github.com/steve192/cookpal-home-assistant` as a custom repository of type *Integration*.
2. Download **Cookpal** and restart Home Assistant.

Requires Home Assistant 2026.3 or newer.

## Setup

1. In the Cookpal app, open **Settings > API keys** and create a key. Tick **Read shopping lists**, and **Add, tick off and remove items** if Home Assistant should change the list. Copy the key; it is shown only once.
2. Add the integration:

   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=cookpal)

3. Keep the server address unless you run your own Cookpal server, paste the key, and pick the lists to show.

To show other lists later, open the integration and choose **Configure**. If you revoke the key in the app, Home Assistant asks for a new one.

## How items map

| Cookpal | Home Assistant |
|---|---|
| Item name | Summary |
| Amount, e.g. "500 g" | Description |
| On the list | Needs action |
| Recently bought | Completed |

- Text added in Home Assistant is split like in the app: "2 kg Kartoffeln" becomes *Kartoffeln* with the amount *2 kg*. A description set in Home Assistant wins over the split amount.
- Adding a name that is already on the list asks for more of it, as in the app.
- *Remove completed items* deletes the recently bought items in Cookpal as well.
- Items cannot be reordered; Cookpal sorts them by aisle.

## Privacy

The key only reaches what you ticked when creating it. It cannot read your recipes, change your account, or create other keys. Revoke it in the app at any time.

## License

MIT
