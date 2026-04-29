# Architecture Pipeline: Sovereign PDF Table Extraction
> **Version:** 1.0 | **Date:** 2026-04-28  
> **CCO-UPC Compliance:** V2 §1 (Dumb Reader), §3 (Hallucination Cross-Reference), §7 (Build Protocol)  
> **Source Analysis:** InfoQ — *"Redesigning Banking PDF Table Extraction: a Layered Approach with Java"*

---

## 1. Executive Summary

This document codifies the end-to-end architecture for extracting structured part-level variable data from manufacturer PDF catalogs (Everflow, Jones Stephens). It synthesizes our existing **Grid/Column Snipper** protocol with the industry-validated **Layered Hybrid Parsing** architecture from InfoQ's banking PDF extraction case study.

> **IMPORTANT:** The key insight from the InfoQ article is that **PDF extraction is a reliability and validation problem, not a file-format problem.** Single-strategy architectures fail in production. Our pipeline must treat every extraction as a *candidate* that passes through scoring and validation gates — never as trusted truth.

---

## 2. Current Pipeline (AS-IS)

### Current Capabilities
| Layer | Engine | Status |
|-------|--------|--------|
| **Section Detection** | Bold font signature + y-position clustering | ✅ Production |
| **Part Number Extraction** | Regex `[A-Z]{1,5}\d{2,6}[A-Z]?` | ✅ Production |
| **Column Detection** | `page.rect.width / 2` midpoint split | ✅ Production |
| **Table Data Extraction** | PyMuPDF `get_text('dict')` with spatial clipping | ⚠️ Partial — only 2/5 rows captured |
| **Variable Mapping** | Positional column inference (column index → key) | ⚠️ Fragile — unnamed columns → `extra_N` |
| **Human Validation** | TLS Approver UI (approve/reject) | ✅ Production |

### Current Gaps (Root Cause Analysis)
1. **Missing Part Rows:** The table parser only captures 2 of 5 data rows because it keys on `part_numbers` array entries that happen to match raw cell values, not the structured `ITEM GALVANIZED` column.
2. **Unnamed Columns (`extra_7`, `extra_8`):** The column-to-variable mapper has no header row awareness. It assigns positional indices instead of semantic names (NOMINAL PIPE SIZE, INNER BOX, MASTER BOX, PALLET QTY).
3. **No Scoring or Confidence:** There is zero confidence scoring. Partial extractions look identical to complete ones.
4. **Single Strategy:** Only stream parsing (text-layer) is used. No lattice or OCR fallback.

---

## 3. Target Pipeline (TO-BE) — Hybrid Layered Architecture

Synthesized from InfoQ's production-grade banking pipeline, adapted for manufacturing catalogs.

### Flow: INGEST → EXTRACT → VALIDATE → OUTPUT

1. **Document Ingestion:** Source PDF → Page Classifier → Section Snipper V6 (product pages) / REJECT (TOC/Footer)
2. **Multi-Strategy Extraction:** Section Crop → Stream Parser + Lattice Parser + LLM Vision Parser (run in parallel)
3. **Validation & Scoring:** All candidates → Header Detection Gate → Column Semantic Mapper → Row Parity Check → Confidence Scorer → Threshold Check
4. **Output & Review:** High confidence → _DATA.yaml (structured) / Low confidence → Manual Review Queue → TLS Approver UI

---

## 4. Layer Specifications

### Layer 1: Document Ingestion & Section Detection
**Engine:** Grid/Column Snipper V6 (existing, production-grade)

| Step | Method | Notes |
|------|--------|-------|
| Page Classification | Font signature + keyword filter | Rejects TOC, footer-only, informational pages |
| Header Detection | Bold text >= 11pt, sorted by y0 | Identifies section boundaries |
| Column Detection | `mid_x = width / 2` | Splits left/right column layouts |
| Crop Generation | `fitz.Rect` clip → 200 DPI PNG | Produces isolated section images |

**No changes needed.** This layer is validated and production-locked.

### Layer 2: Multi-Strategy Table Extraction

> **InfoQ Key Lesson:** "Avoid single-strategy architectures; use stream + lattice/OCR as complementary approaches."

#### Strategy A — Stream Parser (Current Default)
- **Engine:** PyMuPDF `get_text('dict')` with spatial clipping
- **Best For:** Clean text-layer PDFs with consistent spacing
- **Known Failures:** Column drift when font widths vary, missed rows when y-clustering tolerance is too tight

#### Strategy B — Lattice Parser (NEW)
- **Engine:** Grid line detection on the rendered PNG → cell matrix reconstruction
- **Best For:** Tables with visible ruled lines (red-bordered headers like Everflow uses)
- **Method:**
  1. Render section crop at 200 DPI
  2. Detect horizontal + vertical lines (edge detection)
  3. Find intersections → build cell grid
  4. OCR text within each cell → map to grid positions
- **Known Failures:** Watermarks, broken/partial gridlines, merged cells

#### Strategy C — LLM Vision Parser (Existing, Selective)
- **Engine:** Gemini Vision / GPT-4V with structured output prompting
- **Best For:** Edge cases where both stream and lattice fail
- **Guard:** Must be validated against deterministic checks (CCO-UPC §3)

### Layer 3: Validation & Scoring

> **WARNING (InfoQ's Most Important Rule):** "Never hide low confidence." An incorrect extraction is worse than no extraction.

#### Gate 1: Header Detection
- Scan the first 2 rows of extracted data for column header keywords:
  - `SIZE`, `INCHES`, `ITEM`, `GALVANIZED`, `WEIGHT`, `SPACING`, `PIPE SIZE`, `BOX`, `QTY`, `PALLET`
- **Pass:** >= 3 header keywords matched → proceed with semantic mapping
- **Fail:** < 3 keywords → flag as `LOW_CONFIDENCE`

#### Gate 2: Column Semantic Mapper
- Map detected headers to canonical variable names:

| Detected Header | Canonical Variable | Data Type |
|----------------|-------------------|-----------|
| SIZE INCHES | `size_inches` | String |
| ITEM GALVANIZED | `item_number` (Part #) | String |
| MAX SPACING | `max_spacing` | String |
| WEIGHT | `weight_lbs` | Float |
| A, B, C | `dim_a`, `dim_b`, `dim_c` | Float |
| NOMINAL PIPE SIZE | `nominal_pipe_size` | Float |
| INNER BOX | `inner_box_qty` | Integer |
| MASTER BOX | `master_box_qty` | Integer |
| PALLET QTY | `pallet_qty` | Integer |

- **This eliminates `extra_N` fields entirely.**

#### Gate 3: Row Count Parity
- Compare extracted row count against the `part_numbers[]` array length
- **Pass:** Row count matches ± 1
- **Fail:** Mismatch > 1 → flag extraction for manual review

#### Gate 4: Confidence Scoring
```yaml
scoring_model:
  header_match_strength:    weight: 0.30  # How many columns were semantically mapped
  row_count_parity:         weight: 0.25  # Extracted vs expected row count
  numeric_parse_rate:       weight: 0.20  # % of numeric columns that parsed successfully
  part_number_coverage:     weight: 0.25  # % of part_numbers[] found in extraction

  thresholds:
    TIER_1_AUTO_PASS:  >= 0.88   # High confidence — auto-populate
    TIER_2_REVIEW:     >= 0.70   # Acceptable — pass with warning flag
    TIER_3_BLOCKED:    <  0.70   # Low confidence — route to manual
```

#### Gate 5: CCO-UPC Hallucination Cross-Reference (§3)
- Every extracted part number is fuzzy-matched against the `part_numbers[]` array from the Section Snipper
- Tiered thresholds: 88% for 6+ char, 79% for 5-char
- **Block** any part number with < 79% match score

### Layer 4: Output & Human Review

#### Structured _DATA.yaml Schema (Target)
```yaml
section: "CPVC SIDE MOUNT STRAPS"
page: 413
column: "FULL"
image_file: "Page_413_Sec_CPVC_SIDE_MOUNT_STRAPS.png"
confidence_score: 0.92
strategy_used: "STREAM"

# Section-level metadata
sub_headline: 'Sizes: 3/4" - 2"'
material: "Carbon Steel"
finish: "Galvanized"
approvals: "UL"

# Red-box part number list (from Section Snipper)
part_numbers: [CPSM-G34, CPSM-G01, CPSM-G114, CPSM-G112, CPSM-G02]

# Structured table extraction (from Hybrid Parser)
parts:
  CPSM-G34:
    size_inches: '3/4"'
    max_spacing: "5'-6'"
    weight_lbs: 0.85
    dim_a: "2-1/3"
    dim_b: "1-11/16"
    dim_c: "1-3/16"
    nominal_pipe_size: 1.05
    inner_box_qty: 10
    master_box_qty: 100
    pallet_qty: 6400
  CPSM-G01:
    size_inches: '1"'
    max_spacing: "6'-0'"
    weight_lbs: 0.094
    # ... (all 5 parts fully mapped)
```

---

## 5. Implementation Roadmap

| Phase | Task | Priority | Status |
|-------|------|----------|--------|
| **P0** | UI: Zoom + all part numbers + clean variable display | Critical | ✅ Done |
| **P1** | Header Detection Gate (keyword scan in first 2 rows) | Critical | TODO |
| **P2** | Column Semantic Mapper (header → canonical variable) | Critical | TODO |
| **P3** | Row Count Parity Check | High | TODO |
| **P4** | Confidence Scoring Model | High | TODO |
| **P5** | Lattice Parser (grid line detection on PNG) | Medium | TODO |
| **P6** | LLM Vision fallback with CCO-UPC validation | Medium | TODO |
| **P7** | Hybrid Orchestrator (best-of-N strategy selection) | Medium | TODO |

---

## 6. CCO-UPC Compliance Matrix

| CCO-UPC Section | Requirement | Implementation |
|-----------------|-------------|----------------|
| §1 Dumb Reader | Frontend must not perform data transformation | ✅ UI iterates backend JSON only |
| §3 Hallucination XRef | All extractions fuzzy-matched against source | ✅ Gate 5 — tiered 79/88% thresholds |
| §4 TDD Iron Law | Every gate has pass/fail criteria | ✅ Gates 1-5 defined above |
| §7 Build Protocol | Schema-first, then implementation | ✅ Target YAML schema defined |
| §8 Search Protocol | Outputs must be machine-queryable | ✅ Structured YAML + SQLite ledger |

---

## 7. InfoQ Delta Analysis: What Improves Our Pipeline?

| InfoQ Concept | Our Current State | Improvement |
|---------------|-------------------|-------------|
| **Multi-strategy parsing** | Single (stream only) | Add lattice + LLM vision as complementary candidates |
| **Validation scoring** | None — binary pass/fail | Add weighted confidence model (4 signals) |
| **Never hide low confidence** | Silent partial extractions | Route low-score items to manual review queue |
| **Header-driven column mapping** | Positional index (`extra_N`) | Semantic keyword matching → canonical variables |
| **Hybrid orchestrator** | N/A | Best-of-N runtime strategy selection |
| **Explicit fallback paths** | N/A | Low-confidence → manual queue, not silent drop |
| **ML-assisted segmentation** | N/A (future) | Narrow use behind deterministic gates only |

> **CAUTION:** Per InfoQ and CCO-UPC §3: **ML should never be used as an unverified truth extractor.** Its role is to reduce the search space (e.g., detect table regions), not to bypass deterministic validation gates.

---

## 8. References

- InfoQ: Redesigning Banking PDF Table Extraction (https://www.infoq.com/articles/redesign-pdf-table-extraction/)
- CCO-UPC V2 Protocol
- Section Crop Inference YAML
- Gates YAML
