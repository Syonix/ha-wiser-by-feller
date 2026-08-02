# 🧩 Use Cases

Recipes that combine several features of this integration into something useful. Each one links to the reference documentation of the actions it uses, so you can look up the details of every parameter.

> [!TIP]
> All examples use `button_id: 53` and made-up entity IDs. Replace them with your own. The [find button](led-control.md#-discovering-button-ids) action tells you the button ID, and the entity picker in the automation editor fills in the entities.

## 🎚️ Control a non-Wiser light with a Wiser button

**Goal:** a Wiser scene button toggles a light that Wiser knows nothing about (a Hue lamp, a smart plug, a light group), and the button's LED shows whether that light is currently on.

The toggle itself and the LED feedback are two independent pieces. Start with the toggle, then pick one of the two LED options below.

### 1. The toggle

A registered button fires the [`wiser_by_feller_button_event`](button-triggers.md) event, so toggling is a plain event automation without a scene or system flag:

```yaml
- alias: "Wiser button toggles Hue lamp"
  triggers:
    - trigger: event
      event_type: wiser_by_feller_button_event
      event_data:
        button_id: 53
        event: click
  actions:
    - action: light.toggle
      target:
        entity_id: light.hue_lamp
```

See the [LED-Control documentation](led-control.md) for more information on button setup.

### 2a. LED feedback via override (works with any button)

Mirror the light's state onto the button LED with a [temporary override](led-control.md#-temporary-override). Nothing is configured on the gateway, and the button needs no scene:

```yaml
- alias: "Wiser button LED mirrors Hue lamp"
  triggers:
    - trigger: state
      entity_id: light.hue_lamp
      to: ["on", "off"]
    - trigger: homeassistant
      event: start
  actions:
    - if: "{{ is_state('light.hue_lamp', 'on') }}"
      then:
        - action: wiser_by_feller.set_button_led_override
          data:
            button_id: 53
            led_index: "0"
            rgb_color: [26, 188, 242]
      else:
        - action: wiser_by_feller.clear_button_led_override
          data:
            button_id: 53
            led_index: "0"
```

Clearing the override returns the LED to its configured off state, so the two branches give proper on/off feedback.

> [!IMPORTANT]
> Overrides live in the device's memory and are lost when it reboots. The `homeassistant: start` trigger re-applies the correct state after a Home Assistant restart, but not after a device reboot. Repeat the automation on a time pattern if that matters to you.

### 2b. LED feedback via system flag (persistent, needs a scene)

If the button already triggers a **Wiser scene**, you can bind a [system flag](system-flags.md) to it instead. The LED then follows the flag using the device's own frontset configuration, and the setup survives reboots because it lives on the gateway.

Bind the flag once:

```yaml
action: wiser_by_feller.assign_scene_flag
data:
  scene_entity_id: scene.ugateway_hue_toggle
  flag_entity_id: switch.ugateway_hue_lamp_state
  value: true
```

Then let Home Assistant keep the flag in sync with the real light:

```yaml
- alias: "Hue lamp state to Wiser flag"
  triggers:
    - trigger: state
      entity_id: light.hue_lamp
      to: ["on", "off"]
  actions:
    - if: "{{ is_state('light.hue_lamp', 'on') }}"
      then:
        - action: switch.turn_on
          target:
            entity_id: switch.ugateway_hue_lamp_state
      else:
        - action: switch.turn_off
          target:
            entity_id: switch.ugateway_hue_lamp_state
```

Two things to be aware of with this route, both explained under [Scene Button LEDs](system-flags.md#-scene-button-leds):

- **The button needs a scene**, because the binding lives in the scene's job. A button without one cannot use this.
- **Pressing the button also runs the scene**, which sets the flag to the assigned value. With a toggle the LED therefore shows that value until your automation corrects it.

### Which one?

| | 🕐 Override (2a) | 🚩 System flag (2b) |
|---|---|---|
| **Button needs a scene** | ❌ No | ✅ Yes |
| **Survives device reboot** | ❌ No | ✅ Yes |
| **Uses frontset colors/brightness** | ❌ No, set explicitly per automation | ✅ Yes |
| **Press side effects** | None | Runs the scene's job and sets the flag |

For a scene-less button, or when you want full control over the color, use the override. For a button that already has a Wiser scene and should keep working without Home Assistant running, use the flag.

## 🚦 Wall LEDs as an information surface

**Goal:** display a Home Assistant state on a button LED.

A [temporary override](led-control.md#-temporary-override) can set any button LED to any color, so a scene button doubles as a status light. For example, an air quality traffic light driven by a Wiser CO2 sensor:

```yaml
- alias: "CO2 traffic light"
  triggers:
    - trigger: state
      entity_id: sensor.living_room_co2
  actions:
    - choose:
        - conditions: "{{ states('sensor.living_room_co2') | int(0) > 1400 }}"
          sequence:
            - action: wiser_by_feller.set_button_led_override
              data:
                button_id: 53
                led_index: "0"
                rgb_color: [255, 0, 0]
                effect: slow
        - conditions: "{{ states('sensor.living_room_co2') | int(0) > 1000 }}"
          sequence:
            - action: wiser_by_feller.set_button_led_override
              data:
                button_id: 53
                led_index: "0"
                rgb_color: [255, 170, 0]
      default:
        - action: wiser_by_feller.clear_button_led_override
          data:
            button_id: 53
            led_index: "0"
```

The same pattern works for any state you want to see at a glance: the washing machine has finished, the EV is charged, or a window is still open.

For notifications rather than states, use one of the [blink patterns](led-control.md#blink-patterns). Since a press fires an event, you can also use the button to acknowledge the notification:

```yaml
- alias: "Laundry done — flash the button"
  triggers:
    - trigger: state
      entity_id: binary_sensor.washing_machine_running
      to: "off"
  actions:
    - action: wiser_by_feller.set_button_led_override
      data:
        button_id: 53
        led_index: "0"
        rgb_color: [0, 255, 128]
        effect: fast

- alias: "Acknowledge laundry notification"
  triggers:
    - trigger: event
      event_type: wiser_by_feller_button_event
      event_data:
        button_id: 53
  actions:
    - action: wiser_by_feller.clear_button_led_override
      data:
        button_id: 53
        led_index: "0"
```

> [!TIP]
> Pick a button that isn't already showing a load state. Scene buttons and secondary controls ("Nebenstellen") work well, since they have no on/off state of their own.

## 🌙 Night orientation lighting

**Goal:** the status LEDs show a dim, warm light at night, and return to their normal configuration in the morning.

Unlike the override, the [device configuration](led-control.md#%EF%B8%8F-device-configuration) is stored on the device itself. Two scheduled action calls are enough, and the LEDs keep their configuration even if Home Assistant is offline:

```yaml
- alias: "Night orientation light on"
  triggers:
    - trigger: time
      at: "22:00:00"
  actions:
    - action: wiser_by_feller.status_light
      data:
        device: 4a7d9f2b1c8e40a3b5d6e7f8091a2b3c
        channel: "0"
        color: [26, 188, 242]
        color_off: [255, 147, 41]
        brightness_on: 100
        brightness_off: 20

- alias: "Night orientation light off"
  triggers:
    - trigger: time
      at: "07:00:00"
  actions:
    - action: wiser_by_feller.status_light
      data:
        device: 4a7d9f2b1c8e40a3b5d6e7f8091a2b3c
        channel: "0"
        color: [26, 188, 242]
        brightness_on: 100
        brightness_off: 0
```

At night the LED shows warm orange at 20 % while the light is off. In the morning the off state goes dark again and only the on state stays visible. Note that `color_off` is omitted in the second call: without it, the on color is used for both states.

> [!NOTE]
> A separate off color has [firmware requirements](led-control.md#%EF%B8%8F-device-configuration). Without it you can still schedule `brightness_off` alone, which is the more subtle version of the same idea.

> [!TIP]
> The `device` field is a Home Assistant device, so build these automations in the UI editor and let the device picker fill in the ID. Repeat the action per `channel` if the device has several buttons.

## 👆 Gestures on existing buttons

**Goal:** use a single button for more than one action.

Button events distinguish a short `click` from a long `press` and the following `release`, so one button can trigger different things. For example, a long press turns everything off when leaving the house:

```yaml
- alias: "Long press — all off"
  triggers:
    - trigger: event
      event_type: wiser_by_feller_button_event
      event_data:
        button_id: 53
        event: press
  actions:
    - action: light.turn_off
      target:
        entity_id: all
    - action: wiser_by_feller.set_button_led_override
      data:
        button_id: 53
        led_index: "0"
        rgb_color: [255, 60, 0]
        effect: ramp_down
```

A double tap is a short press repeated within a second or two. Home Assistant has no built-in double-tap trigger for custom events, so count them yourself:

```yaml
- alias: "Double tap — movie mode"
  mode: single
  triggers:
    - trigger: event
      event_type: wiser_by_feller_button_event
      event_data:
        button_id: 53
        event: click
  actions:
    - wait_for_trigger:
        - trigger: event
          event_type: wiser_by_feller_button_event
          event_data:
            button_id: 53
            event: click
      timeout: "00:00:01"
      continue_on_timeout: false
    - action: scene.turn_on
      target:
        entity_id: scene.movie_night
```

> [!IMPORTANT]
> The single-click automation for the same button still fires on the first tap of a double tap. Either give the two gestures actions that work together (dim, then dim further), or move the single click to a long press so the gestures can't overlap.

Rockers report which half was pressed in the `type` field (`up` / `down`), so a held rocker can dim a non-Wiser light while a short press keeps its normal function. See [Button Events](button-triggers.md) for that example.

## 🌬️ Weather-aware shading

**Goal:** shade the room and retract the awning based on conditions the Wiser system doesn't know about.

If you have a Wiser weather station, wind speed, rain and hail are available as entities, and covers can be controlled including slat tilt on venetian blinds. Home Assistant also knows about presence, open windows and anything else you have connected, so you can add conditions the WEST groups cannot express.

Retract the awning on wind, but only when nobody is on the terrace:

```yaml
- alias: "Retract awning on wind"
  triggers:
    - trigger: numeric_state
      entity_id: sensor.weather_station_wind_speed
      above: 35
      for: "00:00:10"
  conditions:
    - condition: state
      entity_id: binary_sensor.terrace_presence
      state: "off"
  actions:
    - action: cover.close_cover
      target:
        entity_id: cover.awning_terrace
```

Tilt the slats instead of closing the blind when it gets bright and the room is in use, so you keep the view and the daylight:

```yaml
- alias: "Sun shading with slat tilt"
  triggers:
    - trigger: numeric_state
      entity_id: sensor.weather_station_brightness
      above: 40000
      for: "00:05:00"
  conditions:
    - condition: state
      entity_id: binary_sensor.living_room_presence
      state: "on"
    - condition: state
      entity_id: binary_sensor.living_room_window
      state: "off"
  actions:
    - action: cover.set_cover_tilt_position
      target:
        entity_id: cover.living_room_blind
      data:
        tilt_position: 30
```

> [!WARNING]
> Wind and hail protection is a safety function. Keep it configured in the Wiser system (WEST groups) as well, since a Home Assistant automation only works while Home Assistant is running.

> [!TIP]
> The open-window check is worth adding to every shading rule that closes something. A blind lowered onto a tilted window can damage both.

## 🚗 Garage door with real feedback

**Goal:** see whether the garage door is open on the button that operates it.

Impulse loads (outputs configured for impulse switching, typically wired to a door or gate opener) appear as **button entities** in Home Assistant. They have no state of their own, since a pulse only triggers the opener. Pair one with a contact sensor to show the actual door state on the wall button's LED:

```yaml
- alias: "Garage door state on the wall button"
  triggers:
    - trigger: state
      entity_id: binary_sensor.garage_door
      to: ["on", "off"]
    - trigger: homeassistant
      event: start
  actions:
    - if: "{{ is_state('binary_sensor.garage_door', 'on') }}"
      then:
        - action: wiser_by_feller.set_button_led_override
          data:
            button_id: 42
            led_index: "0"
            rgb_color: [255, 60, 0]
      else:
        - action: wiser_by_feller.clear_button_led_override
          data:
            button_id: 42
            led_index: "0"
```

Add a reminder in case it stays open:

```yaml
- alias: "Garage still open at night"
  triggers:
    - trigger: state
      entity_id: binary_sensor.garage_door
      to: "on"
      for: "00:20:00"
  conditions:
    - condition: sun
      after: sunset
  actions:
    - action: notify.mobile_app_phone
      data:
        message: "The garage door has been open for 20 minutes."
    - action: wiser_by_feller.set_button_led_override
      data:
        button_id: 42
        led_index: "0"
        rgb_color: [255, 0, 0]
        effect: fast
```

> [!TIP]
> The impulse button entity can also be pressed from Home Assistant, so the door works from a dashboard, a voice assistant or an automation. The physical button keeps working as before.

## 🏖️ Holiday mode

A system flag can act as a mode that both Wiser and Home Assistant respect, and Wiser jobs can be *blocked* while it is set. See [System Flags](system-flags.md#-shared-state-between-wiser-and-home-assistant) for creating the flag, assigning it to scenes so the button LEDs show whether the mode is active, and the warning about the app-managed `vacation` flag.
