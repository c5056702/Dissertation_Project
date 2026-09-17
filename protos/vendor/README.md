# Vendored Webots R2025a resources

This directory contains the official Cyberbotics R2025a e-puck PROTO,
e-puck distance-sensor PROTO, four appearance PROTOs, and only their referenced
texture files. They are stored locally so the simulation does not depend on
Webots' runtime HTTP asset downloader.

The appearance PROTOs are Apache-2.0 licensed. The e-puck assets retain their
original Cyberbotics headers and are licensed for use with Webots. The local
e-puck copy replaces two purely visual external helpers (copper material and
decorative ring) with equivalent native geometry; robot devices, dimensions,
wheel joints, collision geometry, and sensors are unchanged.

Upstream source: `https://github.com/cyberbotics/webots/tree/R2025a/projects`
