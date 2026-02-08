[![GitHub release](https://img.shields.io/github/release/deblockt/hass-aria2)](https://github.com/deblockt/hass-aria2/releases/latest)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

# Aria2 Integration for Home Assistant

A Home Assistant integration that connects to your Aria2 download manager, allowing you to monitor and control downloads directly from Home Assistant.

## Features

- **Real-time sensors** for monitoring download/upload speeds and download statistics
- **Download control** via Home Assistant services
- **Events** for download state changes (start, stop, pause, complete, error)
- **Lovelace card** support for visual download management

## Installation

### Prerequisites

You need a running Aria2 server with RPC enabled. Make sure you have:
- Aria2 installed and running
- RPC access enabled (usually on port 6800)
- The RPC secret token if you have configured one

### Via HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Search for "aria2 integration"
3. Click "Download"
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/aria2` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

Add your device via the Integration menu.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aria2)

## Services

### `aria2.start_download`

Start a new download by providing a URL.

**Parameters:**
- `url` (required): The URL of the file to download

**Example:**
```yaml
service: aria2.start_download
data:
  url: "https://example.com/file.zip"
```

## Sensors

The following sensors are available:

- **`download_speed`**: Current global download speed of your Aria2 server (bytes/s)
- **`upload_speed`**: Current global upload speed of your Aria2 server (bytes/s)
- **`number_of_active_download`**: Total number of active downloads
- **`number_of_waiting_download`**: Total number of downloads waiting to start or resume
- **`number_of_stopped_download`**: Total number of stopped/completed downloads

## Events

### `download_state_updated`

This event is triggered when a download changes state (start, stop, pause, complete, or error).

**Event data:**
- `gid`: The GID (unique identifier) of the download
- `status`: The current status (`active`, `paused`, `stopped`, `complete`, or `error`)
- `download.name`: The name of the downloaded file
- `download.total_length`: Total file size in bytes
- `download.completed_length`: Downloaded size in bytes
- `download.download_speed`: Current download speed in bytes/s

**Example automation:**

```yaml
automation:
  - alias: "Notify when download completes"
    trigger:
      - platform: event
        event_type: download_state_updated
        event_data:
          status: complete
    action:
      - service: notify.mobile_app
        data:
          title: "Download Complete"
          message: "{{ trigger.event.data.download.name }} has finished downloading"
```

You can access event data in templates using `{{trigger.event.data}}` followed by the property name (e.g., `{{trigger.event.data.download.name}}`).

## Lovelace Card

For a visual interface to manage your downloads, you can use the dedicated [aria2-card](https://github.com/deblockt/aria2-card).

This custom card allows you to:
- View all active, waiting, and completed downloads
- Pause, resume, and stop downloads
- Monitor download progress in real-time

![screenshot](./doc/aria2-card.png)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
