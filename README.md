# Meshtastic Site Planner

## About

To use this tool, go to the hosted version here: TODO

This is a web utility for predicting the range of a meshtastic radio. 
It uses the SPLAT! software by John A. Magliacane, KD2BD (https://www.qsl.net/kd2bd/splat.html) and ITM / Longely-Rice model to create maps of predicted RSSI (received signal strength indication).
These maps are useful for planning repeater deployments to cover specific areas, and for estimating the coverage provided by an existing mesh network. 
The default model parameters have been carefully chosen based on experimental data and practical experience to produce results which are accurate for Meshtastic devices. 
Each of the parameters is also adjustable, so this tool may be applied to amateur radio projects using different bands and higher transmit powers.

Terrain elevation tiles are streamed from AWS open data (https://registry.opendata.aws/terrain-tiles/) which are based on the NASA 
SRTM (shuttle radar topography) dataset (https://www.earthdata.nasa.gov/data/instruments/srtm).

## Model and Assumptions

This tool runs a physics simulation which depends on several important assumptions. The most important ones are:

1) The SRTM terrain model is accurate to 90 meters.
2) There are no obstructions besides terrain which attenuate the radio signal. This includes trees, artificial structures such as buildings, or transient effects like precipitation.
3) Antennas are isotropic in the horizontal plane (we do not account for directional antennas). 

A detailed description of the model parameters and their recommended values is available at TODO.

## Building

Requirements:

* docker and docker-compose
* git
* pnpm

```
git clone --recurse-submodules https://github.com/mrpatrick1991/splat-api/ && cd meshtastic-site-planner

pnpm i && pnpm run build

docker-compose up --build
```

For development, run `pnpm run dev`.

## Usage
