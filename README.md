# Wiser by Feller Integration

[![Testing & Linting](https://github.com/Syonix/ha-wiser-by-feller/actions/workflows/test.yml/badge.svg)](https://github.com/Syonix/ha-wiser-by-feller/actions/workflows/test.yml)

Use your Wiser by Feller smart light switches, cover controls and scene buttons in Home Assistant. Note that this is an unofficial integration that is not affiliated with Feller AG. All brand and product names are courtesy of Feller AG.

> [!IMPORTANT]
> This integration implements [Wiser by Feller](https://wiser.feller.ch) and not [Wiser by Schneider Electric](https://www.se.com/de/de/product-range/65635-wiser/), which is a competing Smart Home platform (and is not compatible). It es even more confusing, as Feller (the company) is a local subsidiary of Schneider Electric, catering only to the Swiss market.

> [!WARNING]
> Be advised: This integration's stability is somewhere between Alpha and Beta and the integration is still under active development. It has been running relatively stable since April 2024, but still, there might be bugs. Proceed with caution.

## 📦 Installation
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

## ⚙️ Setup
> [!WARNING]
> Please make sure your Wiser setup has been fully configured by your electrition before adding it to Home Assistant. Otherwise naming and categorizing all the devices can be very time consuming and confusing.

Home Assistant should ✨automagically✨ discover your µGateway and suggest to set it up. If not, you can follow these steps to connect manually:

1. Go to Settings → Devices & services and click **"Add Integration"**.
2. Search for **Wiser by Feller**
3. Enter the **IP address** of your µGateway.\
   ***Important:** If you have multiple home assistant installations or other applications that connect to your µGateway, make sure to use a unique username (e.g. `homeassistant` and `ha-testbench`) for each installation. Connecting with the same username on a second installation leads to the first one being de-authorized.*
4. Fill in the **username** you would like home assistant to claim with the Gateway.
5. The buttons on your µGateway should start **flashing purple and pink**. Press one of them within 30 seconds
 

> [!TIP]
> In the moment you connect your gateway all your settings (room and device names, scenes, etc.) are copied over from the user you pick (for a normal install that's either the installer (`installer`, via Wiser eSetup app) or the end user (`admin`, via Wiser Home app).
> 
> If you add more scenes with the Wiser eSetup or Wiser Home app, you need to reconnect the user (Note: This is currently under development).

### Configuration
#### Allow missing µGateway data
By default, the setup fails, if fields like `fw_version` or `serial_nr` are missing for devices in the API response. Enable this option for debug purposes to disable the check. See [this Wiser API GitHub issue for more details](https://github.com/Feller-AG/wiser-api/issues/43).

> [!CAUTION]
> Use with caution, this can affect entity IDs and functionality! You should always check the actual API output manually before checking this checkbox.

## 🧰 Basic functionality
Wiser by Feller devices always consist of two parts: The control front and the base module. There are switching base modules (for light switches and cover controllers) and non-switching base modules (for scene buttons and secondary controls).

Learn more about Wiser devices on the [official website](https://wiser.feller.ch) and [API documentation](https://github.com/Feller-AG/wiser-tutorial).

## 🚀 Features
Here's what the integration currently supports:

### ✨ Seamless setup & autodiscovery
After you've installed the integration, Home Assistant will autodetect your µGateway and suggest installing it. Based on your network it might be possible that you have to manually enter its hostname or IP address. 

You can also give your installation a unique username and select from which user you want to copy scenes and settings from. Room assignments are automatically suggested on setup, as long as their names match between Home Assistant and Wiser.

### 💡 Devices and Entities 
Your Wiser setup will integrate into Home Assistant as devices and entities. What Wiser calls a load (e.g. a light or an awning) will be represented as a device. This means that light switches with two loads will be represented as two separate devices.

Wiser devices without any loads (e.g. "Nebenstellen" or secondary switches) are represented in Home Assistant as a single device. They only have the identify entity but are also selectable in the status LED service (see [below](#-status-led-service)).

### 🕹️ Identify buttons for devices
You can ping (identify) any device, which makes their button illumination flash for a short amount of time.

### 🌅 Trigger Wiser scenes
Wiser scenes are integrated as native Home Assistant scenes, allowing to trigger them like any other scene as well as use them in automations.

### 🔄 Websocket Updates
The integration listens to state changes via a Websocket, leading to near-instant updates in Home Assistant

### 🚨 Status LED Service
The integration also provides a status light service that allows you to control the status leds of a Wiser device. Each channel (load) of the device supports a brightness value for the logical "on" and "off" state. Secondary devices follow the main device. As there currently is no way in the Wiser ecosystem to determine wheter a scene is active, scene buttons do not have a logical "on" state. Two-channel devices (e.g. two dimmers in the same switch) allow for different configurations for each channel.

This feature can be used to indicate system status (e.g. turn a light switch to red to indicate that your washing machine has finished and wants to be emptied or detected motion in a different room).

#### Limitations
- In the current implementation of the Wiser ecosystem it is not possible to configure different colors for the "on" and "off" state.
- Note that updating the configuration can take up to multiple seconds as there are multiple slow API calls involved.

### 🧰 Housekeeping
The integration automatically prompts you to re-connect if there is any authentication error.

## ☑️ Supported devices
| Device                            |  Support  | Remarks                        |
|-----------------------------------|:---------:|--------------------------------|
| Light switches                    |     ✅     | Full support, well tested      |
| LED dimmers                       |     ✅     | Full support, well tested      |
| DALI dimmers                      |     ✅     | Full support, well tested      |
| Blind / awning controls           |     ✅     | Full support, well tested      |
| Secondary controls (Nebenstellen) |     ✅     | Support for status LED control |
| Heating controller 6K             |    🏗️    | Under development...           |
| Temperature sensors               |    🏗     | Under development...           |
| Weather station + REG module      |           | On the roadmap...              |

> [!NOTE]
> If you own a Wiser system with a heating controller or a weather station, please contact me. I am looking for real life API data examples and test users 😉

## 🛣️ Roadmap
Here's a couple of things that are on the roadmap for future releases:
- Full support for all light types
- Add support for HVAC features
- Add support for weather stations
- Template for [Micro-Python script](https://github.com/Feller-AG/wiser-tutorial/blob/main/doc/api_scripts.md) to trigger Home Assistant events. This way you could use Wiser scene buttons to trigger actions in Home Assistant.

## ⚠️ Known issues
- As of right now, the µGateway API only supports Rest and Websockets. MQTT is implemented, [but only for the proprietary app](https://github.com/Feller-AG/wiser-api/issues/23).
- Currently only light and motor devices are supported. Dali Tunable White and Dali RGB devices are untested.
- While Home Assistant supports updating the state of multiple devices at once, it does not support controlling multiple devices together. Home Assistant scenes will therefore always update one device after another, while Wiser native scenes will update all devices in parallel. For an optimal experience it is therefore recommended to maintain scenes in Wiser and trigger them with Home Assistant.
