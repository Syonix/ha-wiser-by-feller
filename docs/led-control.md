# 💡 LED Control

Wiser by Feller devices have customizable status LEDs that can indicate load states or system status. There are two ways to control these LEDs, which are fundamentally different in how they work and what they are meant to be used for:

|                          | ⚙️ Device Configuration                                                                        | 🕐 Temporary Override                                              |
|--------------------------|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| **What it changes**      | The LED configuration stored on the device                                                     | A temporary override on top of the configuration                   |
| **Targeted by**          | Wiser device and button position                                                               | Button ID                                                          |
| **Reacts to load state** | ✅ Yes                                                                                          | ❌ No                                                               |
| **Persists**             | Until reconfigured (can be overridden)                                                         | Until reboot or cleared                                            |
| **Performance**          | 🐌 Slow                                                                                        | 🚀 Fast                                                            |
| **Purpose**              | To represent load state (e.g. show if the light is on) or use as orientation light in the dark | Use in HA automations (e.g. notifications, show air quality, etc.) |

## ⚙️ Device Configuration
The first method modifies the LED configuration directly on the device, via the **configure status light** service (`wiser_by_feller.status_light`). This is the same configuration available in the Wiser apps (Frontset-Eigenschaften). You set a color and brightness levels for when the load is on and when it is off, and the device automatically switches the LEDs based on the actual load state.

By default, the same color is used for both states and only the brightness differs. You can optionally set a separate **color when off** (`color_off`) to use a different color while the load is off; when it is left unset, the on-state color is used for both states.

Secondary controls without loads mirror the LED state of their primary device. Scene buttons do not have an inherent on or off state, since scenes are triggered rather than toggled.

> [!TIP]
> You can assign a system flag to a scene button to give it an on or off state for the LED. This is an advanced feature that requires knowledge of the Wiser ecosystem and API. A more convenient integration of this is planned for a future release (see [#20](https://github.com/Syonix/ha-wiser-by-feller/issues/20)).

## 🕐 Temporary Override

> [!NOTE]
> Requires µGateway firmware **≥ 6.0.41**.

The second method directly overrides LED states without modifying device configuration. Instead of targeting a Wiser device, it targets a **button ID**, which lets you address specific buttons anywhere in the system, independent of device associations[^1].

### 🔍 Discovering Button IDs
Before you can override an LED, you need to find the button ID:

1. Call the **discover button IDs** service. All buttons in the system start flashing.
2. Press the button you want to configure.
3. If the button is already configured (a *managed* button), the service returns the button ID along with additional information about it.

> [!NOTE]
> Button IDs are only unique per µGateway. If you have more than one µGateway configured, you must select which one a service call targets via the **µGateway** field (`config_entry_id`). With a single µGateway the field is optional and that gateway is used automatically.

> [!NOTE]
> If you press a button that is not yet configured (an *unmanaged* button), the service raises an error naming the button's device reference and channel. You can either register it in the same flow by calling the service with **Register unmanaged button** (`register_unmanaged: true`), or register it manually afterwards with the **register button** service. See [Registering Buttons](#%EF%B8%8F-registering-buttons) below.

### 🎨 Overriding LEDs
Once you have a button ID, use the **override LED** service to set the LED state. You specify the button ID, the color as RGB values, and a blink pattern.

> [!IMPORTANT]
> The override remains active until the device reboots, or you explicitly clear it.

### ↩️ Clearing Overrides
The **clear LED** service reverts an overridden LED back to its configured state. For example, if you previously configured a button to red with 50% brightness via device configuration, then used the override service to set it to blue at full brightness, calling clear returns it to the original red at 50% brightness.

### 🛠️ Registering Buttons

> [!NOTE]
> Requires µGateway firmware **≥ 6.0.42**.

Only *registered* (managed) buttons have a button ID and emit [button events](button-triggers.md). Buttons that have never been registered are "sleeping": they work physically, but the gateway does not expose them.

> [!WARNING]
> Button management is a **beta feature** of the µGateway firmware. Only register buttons you actually need — too many registered buttons can slow the gateway down.

The easiest way to register a button is directly from the **find button** service:

```yaml
action: wiser_by_feller.find_button
data:
  register_unmanaged: true
response_variable: found
```

Press the physical button when the LEDs start blinking. If it was unmanaged, it is registered automatically and `found.button_id` contains its new button ID.

Alternatively, register it explicitly if you already know the device reference and channel (e.g. from a previous `find_button` error message):

```yaml
action: wiser_by_feller.register_button
data:
  device: 0000a98f
  channel: 1
```

To remove a registration again, use `wiser_by_feller.unregister_button` with the button ID.

<details>
<summary>Configuring buttons in the Wiser gateway web UI instead</summary>

1. Navigate to `http://<gateway-ip>/buttons.html` (login is required)
2. Press the `Find me 📍` button (top right)
3. Tap the button you like to set up. The line in the list will be highlighted.
4. Click the button at the right end of the line (⚙️ or ✨).
5. If it's already managed, you will see the ID there. The button is ready for use.
6. If it's not managed yet, press the `🔳 Create` button.
7. Press the `ℹ️ Show Button Info` or refer to the [Feller Wiser Tutorial](https://github.com/Feller-AG/wiser-tutorial) for more information.

</details>

## 📋 Service Reference

### `wiser_by_feller.status_light`
Configures the device's status LED for a channel (see [⚙️ Device Configuration](#️-device-configuration)). The setting is persisted on the device, and the device switches the LED automatically based on the load state.

**Parameters:**

| Parameter       | Required | Type        | Description                                                                                                              |
|-----------------|----------|-------------|--------------------------------------------------------------------------------------------------------------------------|
| `device`        | ✅        | `string`    | The target device (load, or scene / secondary control unit).                                                             |
| `channel`       | ✅        | `"0"`–`"3"` | The button on the device to control.                                                                                     |
| `color`         | ✅        | `[r, g, b]` | LED color as RGB values (0–255 each). Used while the load is on, and also while off unless `color_off` is set.            |
| `color_off`     |          | `[r, g, b]` | LED color while the load is off. When unset, `color` is used for both states.                                            |
| `brightness_on` | ✅        | `int`       | LED brightness while the load is on (0–100).                                                                             |
| `brightness_off`|          | `int`       | LED brightness while the load is off (0–100). When unset, `brightness_on` is used.                                       |

**Example automation:**
```yaml
action: wiser_by_feller.status_light
data:
  device: 000004d7
  channel: "0"
  color: [26, 188, 242]
  color_off: [0, 0, 0]
  brightness_on: 100
  brightness_off: 15
```

### `wiser_by_feller.find_button`
Activates find-me mode: all button LEDs start blinking. Press any physical button to identify it. The service blocks until a button is pressed or the 2-minute timeout expires.

**Parameters:**

| Parameter            | Required | Type     | Description                                                                                                            |
|----------------------|----------|----------|--------------------------------------------------------------------------------------------------------------------------|
| `config_entry_id`    |          | `string` | µGateway to activate find-me mode on. Optional with a single µGateway; required when multiple are configured.          |
| `register_unmanaged` |          | `bool`   | If the pressed button is not yet registered, register it automatically and return its new button ID. Requires firmware ≥ 6.0.42. Defaults to `false`. |

**Response fields:**

| Field         | Type          | Description                                          |
|---------------|---------------|------------------------------------------------------|
| `button_id`   | `int \| null` | Wiser button ID of the pressed button                |
| `device`      | `str \| null` | Internal device ID of the pressed button             |
| `channel`     | `int \| null` | Input channel on the device                          |
| `room_name`   | `str \| null` | Room name resolved from the device's load assignment |
| `device_name` | `str \| null` | Human-readable device name                           |
| `scene_name`  | `str \| null` | Name of the linked scene, if the button triggers one |

> [!NOTE]
> Pressing an unmanaged button raises an error instead of returning a response, unless `register_unmanaged` is enabled. The error message names the button's device reference and channel, which can be passed to `register_button`.
> `button_id` is only `null` in the rare case where the gateway reports a press it cannot resolve at all.

**Example automation:**
```yaml
action: wiser_by_feller.find_button
response_variable: found
```

**Find and register in one call:**
```yaml
action: wiser_by_feller.find_button
data:
  register_unmanaged: true
response_variable: found
```

### `wiser_by_feller.register_button`
Registers an available (sleeping) physical button on the µGateway so it gets a button ID and starts emitting [button events](button-triggers.md). Requires µGateway firmware ≥ 6.0.42.

> [!WARNING]
> Button management is a **beta feature** of the µGateway firmware. Only register buttons you actually need — too many registered buttons can slow the gateway down.

**Parameters:**

| Parameter         | Required | Type     | Description                                                                                             |
|-------------------|----------|----------|-----------------------------------------------------------------------------------------------------------|
| `config_entry_id` |          | `string` | µGateway to register the button on. Optional with a single µGateway; required when multiple are configured. |
| `device`          | ✅        | `string` | Gateway device reference (e.g. `0000a98f`), as reported by `find_button`.                               |
| `channel`         | ✅        | `int`    | Input channel of the button on the device.                                                              |

**Response fields:**

| Field         | Type          | Description                                          |
|---------------|---------------|------------------------------------------------------|
| `button_id`   | `int`         | Wiser button ID of the newly registered button       |
| `device`      | `str`         | Internal device ID                                   |
| `channel`     | `int`         | Input channel on the device                          |
| `room_name`   | `str \| null` | Room name resolved from the device's load assignment |
| `device_name` | `str \| null` | Human-readable device name                           |
| `scene_name`  | `str \| null` | Name of the linked scene, if the button triggers one |

**Example automation:**
```yaml
action: wiser_by_feller.register_button
data:
  device: 0000a98f
  channel: 1
response_variable: registered
```

### `wiser_by_feller.unregister_button`
Removes a registered button from the µGateway. It stops emitting button events and its LEDs are turned off. Requires µGateway firmware ≥ 6.0.42.

**Parameters:**

| Parameter         | Required | Type     | Description                                                                                              |
|-------------------|----------|----------|--------------------------------------------------------------------------------------------------------|
| `config_entry_id` |          | `string` | µGateway the button belongs to. Optional with a single µGateway; required when multiple are configured. |
| `button_id`       | ✅        | `int`    | Button ID (from `find_button`)                                                                           |

**Example automation:**
```yaml
action: wiser_by_feller.unregister_button
data:
  button_id: 43
```

### `wiser_by_feller.set_button_led_override`
Temporarily overrides the LED state of a specific button LED. The override persists until the device reboots or it is explicitly cleared.

**Parameters:**

| Parameter         | Required | Type           | Description                                                                                                                                                                         |
|-------------------|----------|----------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `config_entry_id` |          | `string`       | µGateway the button belongs to. Optional with a single µGateway; required when multiple are configured.                                                                             |
| `button_id`       | ✅        | `int`          | Button ID (from `find_button`)                                                                                                                                                      |
| `led_index`       | ✅        | `"0"` or `"1"` | For Up/Down-Buttons (dimmers or motor controls), both buttons have the same button ID, so to select the down button you need to select `"1"` here. For all other cases, it's `"0"`. |
| `rgb_color`       | ✅        | `[r, g, b]`    | LED color as RGB values (0–255 each)                                                                                                                                                |
| `effect`          |          | `string`       | Blink pattern (see table below). Defaults to `permanent`                                                                                                                            |

**Example automation:**
```yaml
action: wiser_by_feller.set_button_led_override
data:
  button_id: 43
  led_index: "0"
  rgb_color: [255, 0, 0]
  effect: slow
```

### `wiser_by_feller.clear_button_led_override`
Reverts an overridden LED back to its device-configured state (see [⚙️ Device Configuration](#️-device-configuration)).

**Parameters:**

| Parameter         | Required | Type           | Description                                                                                             |
|-------------------|----------|----------------|---------------------------------------------------------------------------------------------------------|
| `config_entry_id` |          | `string`       | µGateway the button belongs to. Optional with a single µGateway; required when multiple are configured. |
| `button_id`       | ✅        | `int`          | Button ID (from `find_button`)                                                                          |
| `led_index`       | ✅        | `"0"` or `"1"` | Same as in `set_button_led_override`                                                                    |

**Example automation:**
```yaml
action: wiser_by_feller.clear_button_led_override
data:
  button_id: 43
  led_index: "0"
```

### Blink Patterns

| Value       | Description                |
|-------------|----------------------------|
| `permanent` | Steady, always on          |
| `slow`      | Slow blink                 |
| `fast`      | Fast blink                 |
| `ramp`      | Fade in and out repeatedly |
| `ramp_up`   | Fade in once               |
| `ramp_down` | Fade out once              |

[^1]: Button IDs are assigned by the Wiser µGateway and are stable across reboots.
