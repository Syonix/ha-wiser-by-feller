# 🎛️ Button presses on Generation A gateways

[Button events](button-triggers.md) are emitted natively only on **Generation B**
gateways. Generation A gateways (API version 5) don't send them on their own.

With a little more manual work you get the **same functionality**: install a
small script on the µGateway that pushes a WebSocket message on each button
press, in the exact same structure a Generation B gateway sends. The integration
already understands that structure, so it fires the same
`wiser_by_feller_button_event` event — and you build automations exactly as
described in [Button Events](button-triggers.md).

## Install the gateway script

As described in the [Wiser API documentation](https://github.com/Feller-AG/wiser-api/issues/40),
a script can push an arbitrary WebSocket message. Use the following script,
which builds the **native button structure**. It is identical for every button:

```python
import websockets

async def onButtonEvent(*argv):
    button_cmd, button_type, button_id = argv
    await websockets.push_event('/api', {
        "button": {
            "id": button_id,
            "cmd": {"event": button_cmd, "type": button_type},
        }
    })
```

Install it on the gateway and assign it to the buttons you want to use. This is
an advanced, gateway-side step that the integration does not automate.

## Use it in automations

Once the script is in place, presses fire `wiser_by_feller_button_event` just
like on a Generation B gateway. Follow [Button Events](button-triggers.md) for
the event data, how to discover a button's id, and example automations.
