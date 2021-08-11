# Aria2 integration on home assistant

Aria2 integration for home assistant

Allow to:
   - have sensor on some aria2 stats
   - call a service to start to downlod
   - get the list of all downloads (to stop, pause and resume)

## installation

Copy the `custom_components/aria2` directory on your `custom_components` directory.
This repository is compatible with hacs.

## configuration

Use `add integration` button and search for aria2

## service

You can call the service `aria2.start_download` with the `url` parameter to start to download the file

## sensor

The following sensor are available:
   - download_speed: the current global download speed or your aria2 server
   - upload_speed: the current global upload speed or your aria2 server
   - number_of_active_download: the total number of active download
   - number_of_waiting_download: the total number of download waiting to start or resume
   - number_of_stopped_download: the total number of downloaded file

## lovelace card

To be able to display the download list you can use the [aria2-card](https://github.com/deblockt/aria2-card)

![screenshot](./doc/aria2-card.png)