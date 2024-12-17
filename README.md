# Meshtastic Site Planner

## About

To use this tool, go to the hosted version here: TODO

This is a web utility for predicting the range of a meshtastic radio. 
It uses the SPLAT! software (https://www.qsl.net/kd2bd/splat.html) and ITM / Longely-Rice model to create maps of predicted RSSI (received signal strength indication).
These maps are useful for planning repeater deployments to cover specific areas, and for estimating the coverage provided by an existing mesh network. 
The default model parameters have been carefully chosen based on experimental data and practical experience to produce results which are accurate for Meshtastic devices. 
Each of the parameters is also adjustable, so this tool may be applied to amateur radio projects using different bands and higher transmit powers.

Terrain elevation tiles are streamed from AWS open data (https://registry.opendata.aws/terrain-tiles/) which are based on the NASA 
SRTM (shuttle radar topography) dataset (https://www.earthdata.nasa.gov/data/instruments/srtm).

## Physics Model and Assumptions

This tool runs a simulation which relies on several important assumptions. The most important ones are:

1) The accuracy of the SRTM terrain model is good to 90 meters (or 30, in optional high resolution mode.)
2) There are no obstructions to attenute the radio signal. This includes trees, artificial structures such as buildings, or transient effects like precipitation.
3) Antennas are isotropic in the horizontal plane (we do not account for directional antennas). 

A detailed description of the model parameters and their recommended values is available at TODO.

## Building

Requirements:

* docker and docker-compose
* git
* npm

```
git clone --recurse-submodules https://github.com/mrpatrick1991/splat-api/ && cd splat-api

docker-compose -f docker-compose.yml up

npm run dev
```

## Usage
