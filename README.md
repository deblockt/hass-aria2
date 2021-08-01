# Aria2 integration on home assistant

Very first step of aria2 integration

Allow to:
   - have sensor on some aria2 stats
   - call a service to start to downlod
   - get the list of all downloads

## installation

Copy the `custom_components/aria2` directory on your `custom_components` directory.
This repository is compatible with hacs.

## configuration

Use `add integration` button and search for aria2

## service

You can call the service `aria2.start_download` with the `url` parameter to start to download the file

