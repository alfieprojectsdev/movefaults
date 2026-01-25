# Technical Specification: Public Data Portal and API

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document provides the technical specifications for the POGF Public Data Portal and its associated RESTful API. The system's purpose is to provide intuitive, open access to **processed, historical** geodetic data and products stored in the Centralized Geodetic Database for the public, researchers, and partner agencies. It complements real-time monitoring systems by offering a comprehensive view of historical trends and long-term station behavior.

### 1.2. Scope

This specification covers the frontend user interface, the backend API, the technology stack, and deployment strategy.

## 2. System Architecture

The system is designed as a decoupled (or "headless") application, comprising a modern single-page application (SPA) frontend that communicates with a backend via a RESTful API. This portal specifically focuses on **historical and processed geodetic data**, complementing real-time monitoring efforts. Real-time data streams and event detection are handled by dedicated systems such as the `vadase-rt-monitor` project.

- **Frontend (SPA):** A browser-based application built with React that handles all user interaction and presentation logic for historical data.
- **Backend (API):** A Python-based application built with FastAPI that exposes **processed and historical data** from the database via a set of RESTful endpoints.
- **Database:** The backend connects to the Centralized Geodetic Database using a dedicated, read-only user account to prevent any possibility of data modification.

![Portal Architecture](https://i.imgur.com/example4.png "Diagram showing a User's Browser with the React SPA, which communicates with the FastAPI Backend. The Backend, in turn, reads from the POGF Database.")

## 3. Frontend Features (React SPA)

### 3.1. Interactive Station Map

- **Description:** The homepage will feature a full-screen interactive map displaying the locations of all GNSS stations.
- **Technology:** Leaflet.js with OpenStreetMap as the base layer.
- **Functionality:**
  - Station markers will be color-coded by agency or status.
  - Clicking a marker will open a popup with basic station information (code, name) and a link to the full station page.
  - Map controls for zoom and layer selection.

### 3.2. Station Pages

- **Description:** Each station will have a dedicated page.
- **Functionality:**
  - Displays detailed station metadata (coordinates, elevation, equipment history, etc.).
  - Features an interactive time series plot.
  - Provides a button to download the station's complete time series data.

### 3.3. Time Series Visualization

- **Description:** An interactive plotting component used on station pages.
- **Technology:** Plotly.js.
- **Functionality:**
  - Displays North, East, and Up displacement components over time.
  - Includes error bars (sigma values).
  - Controls for panning, zooming, and toggling series visibility.
  - Option to download the plotted data as a CSV or the plot as a PNG image.

### 3.4. Data Search and Download

- **Description:** A dedicated page allowing users to find and download data.
- **Functionality:**
  - Search filters for station, date range, data type, and agency.
  - Results are displayed in a table.
  - Users can select multiple datasets for bulk download as a zip archive.

### 3.5. Real-time Monitoring Links

- **Description:** Provide direct links to the `vadase-rt-monitor` dashboards for real-time data visualization and earthquake detection, ensuring users can access both historical and live information.

## 4. Backend (RESTful API)

The API will be versioned (e.g., `/api/v1/`) and provide self-documenting endpoints.

### 4.1. API Endpoints

- **`GET /api/v1/stations`**
  - **Description:** Returns a GeoJSON FeatureCollection of all stations, suitable for populating the interactive map.
  - **Response Body:** Array of station objects with `station_code`, `name`, and `geometry`.

- **`GET /api/v1/stations/{station_code}`**
  - **Description:** Returns detailed information for a single station.
  - **Response Body:** A JSON object with all fields from the `stations` table, including metadata.

- **`GET /api/v1/timeseries/{station_code}`**
  - **Description:** Returns time series data for a given station.
  - **Query Parameters:**
    - `start_date` (ISO 8601 format)
    - `end_date` (ISO 8601 format)
    - `format` (`json` or `csv`)
  - **Response Body:** A JSON object with arrays for `time`, `north`, `east`, `up`, and sigmas, or a CSV file.

- **`GET /api/v1/velocities`**
  - **Description:** Returns the latest computed velocity field for all stations.
  - **Response Body:** GeoJSON FeatureCollection with velocity vectors as properties.

### 4.2. API Documentation

- **Technology:** OpenAPI (formerly Swagger).
- **Implementation:** FastAPI will automatically generate an OpenAPI 3.0 compliant schema. Interactive documentation will be available at the `/docs` endpoint, and a ReDoc version at `/redoc`.

## 5. Technology Stack

- **Backend:** Python 3.11+ with FastAPI.
  - **Justification:** High performance, asynchronous support, and automatic data validation and documentation.
- **Frontend:** React 18+ with Vite for building.
  - **Justification:** Rich ecosystem, component-based architecture, and excellent performance.
- **UI Toolkit:** A pre-built component library like Material-UI or Ant Design will be used to ensure a consistent and professional look.
- **Database Interaction:** SQLAlchemy 2.0 (using async drivers).
- **Mapping Library:** Leaflet.js.
- **Plotting Library:** Plotly.js.

## 6. Deployment

- **Containerization:** Both the frontend and backend applications will be containerized using Docker.
- **Web Server:** A web server like Nginx will be used as a reverse proxy. It will serve the static frontend files and proxy API requests to the FastAPI backend.
- **Hosting:** The containers will be deployed on a cloud provider (e.g., AWS, GCP) or on-premise servers.
