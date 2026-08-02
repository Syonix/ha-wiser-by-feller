# 🚩 System Flags

System flags are user-defined booleans stored on the µGateway. They can be used in Wiser jobs and conditions — the classic example is a **holiday mode** that automations and schedules can react to. Each flag has:

| Property | Description                                                                                          |
|----------|------------------------------------------------------------------------------------------------------|
| `symbol` | Technical identifier used in Wiser jobs and conditions. Only `A–Z`, `a–z`, `0–9` and `_` are allowed. |
| `value`  | The current boolean state.                                                                           |
| `name`   | Optional human-readable name, shown in Home Assistant and the Wiser apps.                            |

Every system flag appears as a **switch entity** in Home Assistant (attached to the µGateway device, category *config*). Toggling the switch flips the flag on the gateway. The entity exposes `flag_id` and `symbol` as state attributes. Flags changed outside Home Assistant (e.g. by a wall scene button) update instantly via websocket.

Since neither the Wiser apps nor the gateway web UI offer flag management, the integration provides actions to create, rename and delete flags. Entities appear and disappear automatically — no reload needed.

> [!WARNING]
> Do not delete or change the symbol of the flags **`vacation`** or **`present`** (legacy): they are created by the Wiser Home app for its vacation mode, and the app's presence simulation references them by symbol via a system condition ([details](https://github.com/Feller-AG/wiser-api/issues/36)). If you deleted the `vacation` flag by accident, recreate one with the same symbol to restore the app's vacation mode.

## 📋 Action Reference

### `wiser_by_feller.create_system_flag`
Creates a new system flag on the µGateway. The switch entity appears automatically, and the created flag (including its `id`) is returned as the response.

**Parameters:**

| Parameter         | Required | Type     | Description                                                                                              |
|-------------------|----------|----------|----------------------------------------------------------------------------------------------------------|
| `config_entry_id` |          | `string` | µGateway to create the flag on. Optional with a single µGateway; required when multiple are configured.  |
| `symbol`          | ✅        | `string` | Technical identifier (`A–Z`, `a–z`, `0–9`, `_`).                                                         |
| `value`           |          | `bool`   | Initial state. Defaults to `false`.                                                                      |
| `name`            |          | `string` | Optional human-readable name.                                                                            |

**Example:**
```yaml
action: wiser_by_feller.create_system_flag
data:
  symbol: holiday_mode
  name: Holiday Mode
response_variable: created
```

### `wiser_by_feller.update_system_flag`
Renames a flag or changes its symbol. Provide at least one of the two. To change the flag's *state*, just toggle its switch entity instead.

> [!WARNING]
> Wiser jobs and conditions reference a flag by its symbol. Changing the symbol breaks those references — including the app's vacation mode if you change the `vacation` flag.

**Parameters:**

| Parameter   | Required | Type     | Description                                        |
|-------------|----------|----------|----------------------------------------------------|
| `entity_id` | ✅        | `string` | The switch entity of the system flag.              |
| `symbol`    |          | `string` | New technical identifier.                          |
| `name`      |          | `string` | New human-readable name.                           |

**Example:**
```yaml
action: wiser_by_feller.update_system_flag
data:
  entity_id: switch.ugateway_holiday_mode
  name: Vacation Mode
```

> [!NOTE]
> The entity's displayed name follows the flag name from the gateway, unless you renamed the entity in Home Assistant (an entity registry override always wins). The entity ID never changes automatically.

### `wiser_by_feller.delete_system_flag`
Deletes a system flag from the µGateway and removes its switch entity.

> [!WARNING]
> Wiser jobs and conditions that reference the flag stop working. The gateway does not prevent deleting a flag that is still in use — not even the app-created `vacation` flag (see above).

**Parameters:**

| Parameter   | Required | Type     | Description                           |
|-------------|----------|----------|---------------------------------------|
| `entity_id` | ✅        | `string` | The switch entity of the system flag. |

## 💡 Scene Button LEDs

Scene buttons have no inherent on or off state, so their frontset LED normally shows the "off" configuration. By assigning a system flag to a scene you give its buttons a state ([mechanism described by Feller](https://github.com/Feller-AG/wiser-api/issues/28)):

- The buttons' frontset LEDs show the **"on" configuration** (see [LED Control → Device Configuration](led-control.md#%EF%B8%8F-device-configuration)) while the flag matches the assigned value, and the "off" configuration otherwise.
- **Triggering the scene sets the flag** to the assigned value — by wall button and by Home Assistant scene entity alike.

The assignment is stored on the gateway (in the scene's job), so it survives restarts and works without Home Assistant running.

For a toggle-style setup like holiday mode, create two scenes: one that assigns the flag with value `true` ("activate holiday mode", LED lit while active) and one with value `false` ("deactivate").

### `wiser_by_feller.assign_scene_flag`
Assigns a system flag value to a Wiser scene. Both entities must belong to the same µGateway. Re-assigning an already assigned flag replaces its value.

**Parameters:**

| Parameter         | Required | Type     | Description                                                             |
|-------------------|----------|----------|-------------------------------------------------------------------------|
| `scene_entity_id` | ✅        | `string` | The Wiser scene entity.                                                 |
| `flag_entity_id`  | ✅        | `string` | The switch entity of the system flag.                                   |
| `value`           |          | `bool`   | Value the scene sets and the LEDs light up for. Defaults to `true`.     |

**Example:**
```yaml
action: wiser_by_feller.assign_scene_flag
data:
  scene_entity_id: scene.ugateway_holiday_start
  flag_entity_id: switch.ugateway_holiday_mode
  value: true
```

### `wiser_by_feller.unassign_scene_flag`
Removes a system flag assignment from a Wiser scene. The buttons' LEDs no longer follow the flag, and triggering the scene no longer sets it.

**Parameters:**

| Parameter         | Required | Type     | Description                           |
|-------------------|----------|----------|---------------------------------------|
| `scene_entity_id` | ✅        | `string` | The Wiser scene entity.               |
| `flag_entity_id`  | ✅        | `string` | The switch entity of the system flag. |
