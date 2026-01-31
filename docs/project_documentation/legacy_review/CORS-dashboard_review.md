# Legacy Project Review: CORS-Dashboard

**Date:** 2026-01-26

**Project Location:** `/home/finch/repos/movefaults/packages/CORS-dashboard/`
**Status:** Discontinued
**Original Developer:** Oriel Absin

## 1. Overview and Purpose

The `CORS-dashboard` was an older implementation of a web application designed to serve as a dashboard for Continuous Operating Reference Stations (CORS). It aimed to provide a user interface for presenting geodetic data, likely including visualization and interactive elements. The project was discontinued after its initiator left the project.

## 2. Technology Stack (from `package.json`)

The `CORS-dashboard` was built primarily with a **JavaScript (Node.js/React)** ecosystem:

-   **Backend Framework:** **Express.js** (`app.js` confirms a basic static file server).
-   **Frontend Framework:** **React 15.x** (heavily used libraries like `react`, `react-dom`, `react-redux`, `react-router`).
-   **UI Library:** **Material-UI 0.x** (older version) for component styling.
-   **Mapping Libraries:** **Leaflet.js**, `react-leaflet`, `mapbox-gl`, `leaflet.markercluster` - indicating strong mapping capabilities.
-   **Data Visualization:** **D3.js** (`d3`, `d3act`), **Plotly** (inferred from `react-json-tree` and general data viz needs).
-   **GraphQL:** Utilized `graphql`, `apollo-client`, `react-apollo`, suggesting a modern API communication layer.
-   **Build Tooling:** **Webpack** for bundling, `nodemon` for development, `yarn` for package management.
-   **Utilities:** `moment` (date/time), `lodash` (utilities), `axios` (HTTP client).

## 3. Detailed Project Structure & Client Overview (from `To Document.docx`)

### Project Structure
The client-side of the application is a React-based web dashboard. Its structure followed typical Node.js conventions:
-   **`node_modules`**: Contains all project dependencies.
-   **`public`**: Contains the uncompiled source code, packaged by Webpack.
-   **`actions`**: Redux actions for managing application UI and data states.
-   **`comp`**: React components, organized by classes, managing viewable parts.
-   **`css`**: Cascading stylesheets for component styling.
-   **`gqlFiles`**: Holds GraphQL query objects.
-   **`reducers`**: Redux reducers handling state changes.
-   **`views`**: Contains EJS (Embedded JavaScript) template for main HTML markup.

### Available Scripts (from `package.json` & `To Document.docx`)
| Command | Function |
| --- | --- |
| `npm run dev` | Run in development mode |
| `npm run prod` | Run in production mode |
| `npm run clean` | Clean distribution folder contents |
| `npm run start` | Alternate prod mode without webpack (using `nodemon app.js`) |
| `npm run buildrun` | Build and run the application |

## 4. Server Setup (from `Procfile` and `app.js`)

-   **Backend Framework:** **Express.js**.
-   **`Procfile`:** `web node app` indicating `app.js` as the entry point.
-   **`app.js` configuration:**
    -   Serves static files from the `dist` directory.
    -   Routes all requests to `index.html`.
    -   Listens on `PORT = 8000`.

## 5. Views and Templating (from `To Document.docx`)

-   The main entry point was defined in `index.ejs`.
-   **Mount Point:** The React application rendered within `<div id='app' />`.
-   **External Dependencies:** The view included external resources like Google Fonts, Mapbox GL JS, and Leaflet CSS.

## 6. React Component Architecture (from `To Document.docx`)

The UI was built using React, with components managing their own state and passing data via props.

### The Logsheet Component (Detailed Insight!)
A key complex component was `LogSheetForm`, composed of several child fields for data entry, including:
-   `DateFields` (with DatePicker).
-   `ObserversFields` (with StaffForm).
-   `MeasurementFields` and `StatusFields`.
-   `LogSheetButtons` (handling Edit, Send, Check, and Error states).

The `LogSheetViewer` managed the display of these logs using components like `SwipeableViews`, `Filter`, and `Details` with tabbed data tables.

## 7. Relevance to Current Monorepo Deliverables

This detailed forensic analysis significantly enhances its relevance to our **Public Data Portal and API (Deliverable 1.4)** and provides critical insights for the **Digital Field Operations System (Deliverable 2.3)**:

-   **Direct UI/UX Inspiration:** The detailed component breakdown, especially for the `LogSheetForm` and `LogSheetViewer`, provides concrete design patterns for our `Digital Field Operations System`. This includes ideas for field data entry forms, handling different states (Edit, Send, Check), and viewing historical logs.
-   **Feature Prioritization:** Features implemented in `CORS-dashboard` (e.g., specific map interactions, GraphQL data fetching, the logsheet details) can directly inform the feature roadmap of both the Public Data Portal and the Digital Logsheet.
-   **Mapping Strategy:** The extensive use of mapping libraries (`Leaflet`, `Mapbox GL`) confirms the importance of robust geospatial visualization and interaction, which our new portal must support.
-   **State Management Patterns:** The use of Redux actions and reducers indicates a structured approach to client-side state management, a concept our new React frontend will also need to address.
-   **GraphQL as an Alternative:** While our current portal plan is FastAPI (REST), the `CORS-dashboard`'s successful use of GraphQL highlights it as a powerful alternative or future enhancement for our API if more complex query capabilities are needed.

## 8. Actionable Insights for the Future

-   **Deep Dive into Logsheet Component:** The `LogSheetForm` and `LogSheetViewer` are direct predecessors/inspirations for components in our `Digital Field Operations System`. A thorough review of their code would be beneficial during the implementation of Deliverable 2.3.
-   **User Interface Flow:** Understanding the typical user interactions and flows within this dashboard can guide the design of our new portal to ensure a familiar and efficient user experience for existing stakeholders.
-   **Data Schemas:** The GraphQL queries in `gqlFiles` would contain implicit definitions of the data schemas for CORS data that the dashboard consumed. These can serve as valuable references for designing our `Centralized Geodetic Database` (Deliverable 1.1) and `Public Data Portal API` (Deliverable 1.4).

---
This concludes the enhanced forensic analysis of the `CORS-dashboard` project.