# Head Gesture and Voice Controlled Smart Vehicle for Autonomous Point-to-Point Navigation

## MSc Artificial Intelligence Dissertation Project

**Student:** Manikanta Inapakurthi  
**Student ID:** 35056702  
**University:** Sheffield Hallam University  

## Project Overview

This project implements a multimodal human–robot interaction system for controlling an e-puck robot in the Webots simulation environment.

The system combines:

- Offline voice recognition using Vosk
- Head gesture recognition using MediaPipe and OpenCV
- Multimodal command validation and confirmation
- State-based robot control
- Point-to-point autonomous navigation
- Route selection and replanning
- GPS and compass-based navigation
- Proximity-triggered fail-safe stopping
- Live system status and event logging

Voice commands are used to activate the system and select destinations, while head gestures are used for route selection, confirmation and emergency stopping.

## Technologies

- Python
- Webots R2025a
- MediaPipe
- OpenCV
- Vosk Offline Speech Recognition
- NumPy

## Project Structure

- `controllers/` – Main e-puck controller and multimodal control modules
- `worlds/` – Webots simulation world
- `models/` – Offline Vosk speech-recognition model
- `protos/` – Webots robot and environment assets
- `tests/` – Automated unit and integration tests
- `tools/` – Setup, execution and validation utilities
- `validation_runs/` – Recorded validation results
- `evidence/` – Experimental and system evidence
- `demo/` – Project demonstration material

## Main Webots World

`worlds/epuck_waypoint_navigation.wbt`

## Main Controller

`controllers/epuck_waypoint_controller/epuck_waypoint_controller.py`

## Installation

Install Python 3.12 and Webots R2025a.

Create the project environment using:

    py -3.12 tools/setup_client.py

List available microphones:

    .\.venv\Scripts\python.exe tools/run_live.py --list-microphones

Run the live multimodal system:

    .\.venv\Scripts\python.exe tools/run_live.py

## Basic Interaction

1. Start the system and allow camera calibration.
2. Say `start` to activate the controls.
3. Say `go to A`, `go to B`, `go to C`, or `go to S`.
4. Tilt left for the shortest route or right for an alternative route.
5. Nod to confirm the selected route.
6. Say `stop` or perform a head shake for an immediate safety stop.

The robot autonomously follows the confirmed route using its simulated GPS and compass.

## Testing

Run the local automated test suite with:

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Validation outputs and experimental evidence are available in the `validation_runs/` and `evidence/` directories.

## Demonstration

Project demonstration material is available in the `demo/` directory.

## Safety

The system implements proximity-triggered fail-safe stopping. Voice `stop` and the head-shake gesture are treated as high-priority stop commands.

## Academic Purpose

This repository contains the software artefact developed for the MSc Artificial Intelligence dissertation at Sheffield Hallam University.
