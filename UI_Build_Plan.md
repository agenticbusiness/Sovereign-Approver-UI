# CCO-UPC MAP-REDUCE PLAN: Dashboard UI Build (Single View Approver)

## PHASE 1: The Protocol Mechanics Mapper
**Objective:** Convert the 4-tab Spec UI into a Single View Approver optimized for cutout/parse validation.

**Core Mechanics (The "What"):**
1. **Layout Re-architecture:**
   - **Left Panel (Data View):** Display the parsed information structured hierarchically by **Part Number**. Below each Part Number, list its extracted variables (e.g., Size, Material, Connection Type, Finish).
   - **Right Panel (Viewport):** Display the section cutouts/masked crops (e.g., the PNGs generated during the small batch rounds).
2. **Action Mechanics:**
   - Provide "Approve", "Reject", and "Correct" capabilities directly on the Part Number blocks.
3. **Data Source Integration:**
   - The backend (`ui_server.py`) must map the part numbers from the `_DATA.txt` files to their expanded variable inference data (from the LLM or master arrays).
   - The UI will consume a unified JSON schema per page/cutout.

## PHASE 2: Engineering Standards Mapper (SDD/TDD)
**Engineering Standards (The "How"):**
1. **Schema-Driven Design (SDD):**
   - We must define a strict JSON payload schema for the `/api/document/<id>/data` endpoint that includes both the part number and a `variables` object (containing keys like `diameter`, `material`, `connection`).
2. **Dumb Reader Severance:**
   - The frontend (`index.html`) must be a "dumb reader." It will not perform variable parsing or data manipulation. It will strictly iterate over the JSON provided by the backend and render the HTML nodes.
3. **TDD Iron Law (Validation States):**
   - **Pass:** UI renders Left Panel with part numbers and variables. Clicking "Approve" highlights the box green and sends a webhook to the backend.
   - **Fail:** JSON payload is missing variable data, or image fails to load.

## PHASE 3: Synthesis & Governance (Execution Roadmap)
**Synthesis against the Hallucination Cross-Reference Protocol:**
To enforce the CCO-UPC Hallucination Protocol, the UI must force visual parity. By placing the extracted variables directly on the left and the source pixel-crop on the right, the human-in-the-loop can instantly verify if a variable (like "3/4 inch") was hallucinated or genuinely exists in the image.

**Execution Steps (Pending Approval):**
1. **Directory Setup:** Migrate the base UI components (`Frontend`, `Engines`, `Matrices`) into `c:\_3.2 Parts Cross Master Updater\_30 Dashboard UI Build Files`.
2. **Schema Definition:** Update the Python backend (`ui_server.py`) to parse the cutouts and their corresponding inference data into the structured SDD JSON format.
3. **UI Refactoring:** Strip the 4-tab system from `index.html`. Expand the Left Sidebar to support collapsible/expanded variable lists under each part number.
4. **Endpoint Rewiring:** Ensure the `Approve/Reject` buttons push the exact variable states to a local SQLite database or Master JSON.

---
**Status:** Planning Complete. Awaiting authorization to begin Step 1 of the Execution Roadmap.
