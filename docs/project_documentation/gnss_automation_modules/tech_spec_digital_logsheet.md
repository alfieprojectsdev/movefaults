# Technical Specification: Digital Field Operations System

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document outlines the technical specifications for the Digital Field Operations System. This system is designed to replace the current paper-based log sheets used by field staff during the installation, maintenance, and data collection at GNSS stations. The goal is to improve data quality, timeliness, and operational efficiency.

### 1.2. Scope

This specification covers the system's architecture, core features for both users and administrators, its technology stack, and API design. The system will be a mobile-first Progressive Web App (PWA) to ensure offline capability.

## 2. System Architecture

The system follows a decoupled architecture, consisting of a frontend PWA that communicates with a backend API. It will have its own dedicated database, separate from the main POGF geodetic data store.

- **Frontend (PWA):** A mobile-first, single-page application built using a modern JavaScript framework. It will be "installable" on mobile devices and will use a Service Worker to provide core functionality (form filling, local storage) while offline.
- **Backend (API):** A Python web service providing a RESTful API for data synchronization, user authentication, and administrative tasks.
- **Database:** A dedicated PostgreSQL database to store user accounts, equipment inventory, and all submitted log sheet data.

![Digital Logsheet Architecture](https://i.imgur.com/example5.png "Diagram showing a mobile device with the PWA. The PWA syncs with the FastAPI Backend, which has its own dedicated PostgreSQL Database.")

## 3. Core Features

### 3.1. User Authentication

- All users (field staff) must log in with a username and password.
- The PWA will securely store an authentication token to keep the user logged in, even when offline.

### 3.2. Digital Log Sheet Form

This is the core feature of the PWA. The form will be structured but flexible.
- **Fields:**
  - Station ID (can be auto-filled by QR code)
  - Date and time (auto-filled)
  - Arrival and departure times
  - Weather conditions (dropdown: Sunny, Cloudy, Rain, etc.)
  - A checklist of routine maintenance tasks (e.g., "Cleaned solar panels," "Checked battery voltage").
  - Free-text notes section for observations.
- **Equipment Section:**
  - A section to record equipment changes.
  - Fields for Receiver S/N and Antenna S/N can be auto-filled by scanning a QR code.
- **Photo Attachments:**
  - Ability to use the device's camera to take and attach photos to the log sheet (e.g., of the new setup, or of any issues found). Photos will be compressed on the client-side before submission.

### 3.3. Offline-First Functionality

- The PWA must be fully functional without an internet connection.
- New log sheets created while offline will be stored locally on the device (e.g., in IndexedDB).
- When the device regains network connectivity, the PWA will automatically detect it and sync all locally stored records to the server in the background.

### 3.4. Equipment Inventory & QR Code Integration

- **Inventory Management:** A web interface for administrators to manage the inventory of all receivers, antennas, and other key equipment.
- **QR Code Generation:** The system will generate a unique QR code for each piece of equipment and for each permanent station monument. These can be printed as durable, weatherproof stickers.
- **QR Code Scanning:** Within the PWA, a "Scan QR Code" button will open the device camera. Scanning a code will instantly populate the relevant field in the log sheet (e.g., Station ID, Receiver S/N).

### 3.5. Log Sheet History

- Users can browse and view all previously submitted log sheets for any given station directly within the PWA. This provides valuable context during field visits.

## 4. Technology Stack

- **Backend:** Python 3.11+ with FastAPI.
  - **Justification:** Consistent with other project components. Excellent for building efficient, well-documented APIs.
- **Frontend:** React or Vue, bootstrapped with a PWA template.
  - **Justification:** Both are excellent choices for building interactive SPAs. The choice may depend on team familiarity.
- **Database:** PostgreSQL.
  - **Justification:** A robust, open-source relational database.
- **Database Interaction:** SQLAlchemy (ORM with `asyncio` support).
- **QR Code Library:** A Python library like `qrcode` for generation and a JavaScript library like `html5-qrcode` for scanning in the browser.
- **Offline Storage:** Service Workers and the IndexedDB API.

## 5. API Endpoints

- `POST /api/v1/token`: User login, returns an auth token.
- `POST /api/v1/logsheets`: Submit one or more new log sheets (to support bulk sync).
- `GET /api/v1/logsheets?station_code={code}`: Get a list of past log sheets for a station.
- `GET /api/v1/equipment?id={qr_id}`: Get equipment details from a scanned QR code ID.
- `GET /api/v1/inventory`: (Admin) Get the full equipment inventory list.
- `POST /api/v1/inventory`: (Admin) Add a new piece of equipment to the inventory.
