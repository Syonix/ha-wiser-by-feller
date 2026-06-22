# 🎛️ Button Events

Physical button presses on Wiser by Feller devices are delivered to Home
Assistant as a **Home Assistant event**, `wiser_by_feller_button_event`. You can
react to it with a plain **event trigger** in your automations — for example,
double-tapping a scene button to arm an alarm, or holding a rocker to dim a
non-Wiser light.

> [!NOTE]
> Button events are emitted natively on **Generation B** gateways, starting with
> µGateway firmware **≥ 6.0.41**. On older devices you can produce the same
> events with a small gateway script — see
> [Button presses on Generation A gateways](button-triggers-v5.md).

## The event

Every press fires `wiser_by_feller_button_event` with this data:

| Field | Description                                                                                                   |
|---|---------------------------------------------------------------------------------------------------------------|
| `button_id` | Numeric button id (unique per µGateway)                                                                       |
| `event` | `click` (short press), `press` (long press / held), `release`                                                 |
| `type` | Button function, e.g. `up`, `down`, `scene`, `toggle`                                                         |
| `config_entry_id` | The µGateway the press came from (only relevant if you have mutliple gateways with overlapping IDs connected) |

For example, a short press of the down half of a dimmer switch fires:

```yaml
event_type: wiser_by_feller_button_event
data:
  config_entry_id: HCEYM5XWKREX274PYPHYHYP6N2
  button_id: 53
  event: click
  type: down
```

## Finding a button's id

You need the `button_id` to write an automation. Two ways to get it:

- **Settings → Developer Tools → Events:** listen to `wiser_by_feller_button_event` and
  press the physical button. The fired event shows the exact `button_id`,
  `event` and `type` — ready to copy into your automation (only for managed buttons, see [LED Control documentation](docs/led-control.md#%EF%B8%8F-configuring-buttons-in-the-wiser-gateway) for details).
- **Find Button action:** call the `wiser_by_feller.find_button` action
  (Developer Tools → Actions). All button LEDs start flashing; press the one you
  want and the action returns its `button_id` (plus device, channel and label
  info) so you can confirm exactly which physical button it is.

> [!NOTE]
> Button ids are only unique per µGateway. If you run more than one gateway, and the same button ID is in use in both 
> systems, add `config_entry_id` to the `event_data` to disambiguate.

## Example automations

React to any press of a button (any interaction):

```yaml
automation:
  - alias: "Scene button toggles lamp"
    triggers:
      - trigger: event
        event_type: wiser_by_feller_button_event
        event_data:
          button_id: 53
          event: click
    actions:
      - action: light.toggle
        target:
          entity_id: light.lamp
```

For an up/down rocker (one button id that reports the half via `type`), this
dims while the **down** half is held:

```yaml
automation:
  - alias: "Dim hallway light while holding down"
    triggers:
      - trigger: event
        event_type: wiser_by_feller_button_event
        event_data:
          button_id: 53
          event: press
          type: down
    actions:
      - action: light.turn_on
        target:
          entity_id: light.hallway
        data:
          brightness_step_pct: -10
```

> [!TIP]
> Only the `event_data` fields you list have to match. Match `button_id` alone to
> react to *any* press of a button, then add `event` (and `type` for direction)
> to narrow it down.
