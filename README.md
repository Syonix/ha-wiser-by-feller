# Wiser by Feller Integration

Use your Wiser by Feller smart light switches, cover controls and scene buttons in Home Assistant.

**Beware:** This integration implements [Wiser by Feller](https://wiser.feller.ch) and not [Wiser by Schneider Electric](https://www.se.com/de/de/product-range/65635-wiser/), which is a competing Smart Home platform (and is not compatible). It es even more confusing, as Feller (the company) is a local subsidiary of Schneider Electric, catering only to the Swiss market.

> [!WARNING]
> Be advised: This integration is somewhere between Alpha and Beta. It has been running relatively stable for probably a year, but still, there might be bugs. Proceed with caution.

## Installation
### Using [HACS](https://www.hacs.xyz/)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mpbzh&repository=https%3A%2F%2Fgithub.com%2FSyonix%2Fha-wiser-by-feller)

Click the button above or perform the following steps:
1. Navigate to HACS on your Home Assistant
2. Click on the 3 dots in the top right corner.
3. Select "Custom repositories"
4. Enter the URL of this repository (https://github.com/Syonix/ha-wiser-by-feller) 
5. Select the type "Integration".
6. Click the "ADD" button.

### Manual installation
Copy the directory `custom_components/wiser_by_feller` into your `custom_components` directory. 
If it does not exist yet, you can create it in the home assistant installation directory.

## Setup
**Note:** Please make sure your Wiser setup has been fully configured by your electrition before adding it to Home Assistant. Otherwise naming and categorizing all the devices can be very time consuming and confusing.

1. Go to Settings → Devices & services and click "Add Integration".
2. Search for Wiser by Feller
3. Enter the IP address of your µGateway
4. The buttons on your µGateway should start flashing purple and pink. Press one of them within 30 seconds

### Configuration
#### Allow missing µGateway data
By default, the setup fails, if fields like fw_version or serial_nr are missing for devices in the API response. Enable this option for debug purposes to disable the check. See [this Wiser API GitHub issue for more details](https://github.com/Feller-AG/wiser-api/issues/43).

**Warning:** Use with caution, this can affect entity IDs and functionality!

## Core principles of the integration
* TODO

## Functionality
### Devices
Wiser by Feller devices always consist of two parts: The control front and the base module. There are switching base modules (for light switches and cover controllers) and non-switching base modules (for scene buttons and secondary controls).

### Status LEDs
The integration also provides a status light service that allows you to control the status leds of a Wiser device. Each channel (load) of the device supports a brightness value for the logical "on" and "off" state. Secondary devices follow the main device. As there currently is no way in the Wiser ecosystem to determine wheter a scene is active, scene buttons do not have a logical "on" state. Two-channel devices (e.g. two dimmers in the same switch) allow for different configurations for each channel.

**Limitations**
- In the current implementation of the Wiser ecosystem it is not possible to configure different colors for the "on" and "off" state.
- Note that updating the configuration can take up to multiple seconds as there are multiple slow API calls involved.

## Known issues
- As of right now, the µGateway API only supports Rest and Websockets. MQTT is implemented, [but only for the proprietary app](https://github.com/Feller-AG/wiser-api/issues/23).
- Currently only light and motor devices are supported. Dali Tunable White and Dali RGB devices are untested.