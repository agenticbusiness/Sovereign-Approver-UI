"""
Part Number Extractor v5 — Adversarial Team Pipeline

Pipeline:
  Phase 0: Pre-Scan -> document_intelligence.yaml (page classify + table detect)
  Phase 1: 3 engines run IN PARALLEL (2 teams):
    Team Alpha (Text Extractors):
      1. PyMuPDF — embedded text + column filter (Captain)
      2. Font Signature — font metadata matching (Specialist)
    Team Beta (Visual Verifiers):
      3. Tesseract OCR — image-based extraction (Captain)
  Phase 2: Judge Orchestrator -> consensus across teams
  Phase 3: SHA-512 Auto-Verify -> drift detection against locked fingerprints

Usage:
  python part_number_extractor.py
  python part_number_extractor.py --file "FITTINGS - 150LB..." --pages "1,2"
  python part_number_extractor.py --engine pymupdf   (single engine only)
  python part_number_extractor.py --parallel          (force parallel mode)
  python part_number_extractor.py --skip-prescan      (skip pre-scan phase)
"""
import json
import os
import sys
import subprocess
import time
import argparse
import concurrent.futures

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINES_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(VAULT_DIR, "_1 INPUT FOLDER")
OUTPUT_FOLDER = os.path.join(VAULT_DIR, "_2 Output Data")

sys.path.insert(0, ENGINES_DIR)


def run_subprocess(cmd, label, timeout=120):
    """Run a subprocess engine and return (success, stdout, elapsed)."""
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                               encoding='utf-8', errors='replace',
                               timeout=timeout)
        elapsed = time.time() - t0
        return result.returncode == 0, result.stdout, elapsed
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s", time.time() - t0
    except Exception as e:
        return False, str(e), time.time() - t0


def run_prescan(pdf_file, pages_arg):
    """Phase 0: Pre-Scan Orchestrator."""
    print("\n" + "=" * 60)
    print("  PHASE 0: DOCUMENT INTELLIGENCE PRE-SCAN")
    print("=" * 60)

    cmd = [sys.executable, os.path.join(ENGINES_DIR, "pre_scan_orchestrator.py"),
           "--file", pdf_file]
    if pages_arg:
        cmd.extend(["--pages", pages_arg])

    success, stdout, elapsed = run_subprocess(cmd, "PreScan")
    print(stdout)
    print(f"  [TIMER] Pre-Scan completed in {elapsed:.2f}s")
    return success


# Team assignments for adversarial competition
TEAM_ALPHA = ["pymupdf", "font_signature"]  # Text Extractors
TEAM_BETA = ["tesseract"]                    # Visual Verifiers


def make_engine_cmd(engine_name, pdf_file, pages_arg):
    """Build the subprocess command for an engine."""
    engine_map = {
        "pymupdf": ("engine_pymupdf.py", sys.executable),
        "tesseract": ("engine_tesseract.py", sys.executable),
        "font_signature": ("engine_font_signature.py", sys.executable),
    }

    if engine_name not in engine_map:
        return None

    script, interpreter = engine_map[engine_name]
    script_path = os.path.join(ENGINES_DIR, script)

    if not os.path.exists(script_path):
        return None

    cmd = [interpreter, script_path, "--file", pdf_file]
    if pages_arg:
        cmd.extend(["--pages", pages_arg])

    return cmd


def run_engine_sequential(engine_name, pdf_file, pages_arg):
    """Run a single engine sequentially."""
    team = "ALPHA" if engine_name in TEAM_ALPHA else "BETA"
    label_map = {
        "pymupdf": f"[Team {team}] PyMuPDF (Embedded Text — Captain)",
        "tesseract": f"[Team {team}] Tesseract OCR (Image-Based — Captain)",
        "font_signature": f"[Team {team}] Font Signature (Font Metadata — Specialist)",
    }

    print(f"\n{'=' * 60}")
    print(f"  {label_map.get(engine_name, engine_name)}")
    print(f"{'=' * 60}")

    cmd = make_engine_cmd(engine_name, pdf_file, pages_arg)
    if not cmd:
        print(f"  [SKIP] {engine_name} script not found")
        return False

    timeout = 120 if engine_name == "liteparse" else 30
    success, stdout, elapsed = run_subprocess(cmd, engine_name, timeout)
    print(stdout)
    print(f"  [TIMER] {engine_name} completed in {elapsed:.2f}s")
    return success


def run_engine_parallel_worker(args):
    """Worker function for parallel engine execution."""
    engine_name, pdf_file, pages_arg = args
    cmd = make_engine_cmd(engine_name, pdf_file, pages_arg)
    if not cmd:
        return engine_name, False, "", 0

    timeout = 120 if engine_name == "liteparse" else 30
    success, stdout, elapsed = run_subprocess(cmd, engine_name, timeout)
    return engine_name, success, stdout, elapsed


def run_engines_parallel(engines, pdf_file, pages_arg):
    """Phase 1: Run all engines in parallel."""
    print("\n" + "=" * 60)
    print("  PHASE 1: PARALLEL ENGINE EXTRACTION")
    print("=" * 60)
    print(f"  Engines: {', '.join(engines)}")

    tasks = [(eng, pdf_file, pages_arg) for eng in engines]
    results = {}

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run_engine_parallel_worker, task): task[0]
                   for task in tasks}

        for future in concurrent.futures.as_completed(futures):
            engine_name = futures[future]
            try:
                name, success, stdout, elapsed = future.result()
                results[name] = success
                status = "PASS" if success else "FAIL"
                print(f"  [{name:15s}] [{status}] {elapsed:.2f}s")
            except Exception as e:
                results[engine_name] = False
                print(f"  [{engine_name:15s}] [FAIL] {e}")

    total_parallel = time.time() - t0
    print(f"\n  [PARALLEL] All engines completed in {total_parallel:.2f}s")
    return results


def run_judge(doc_id):
    """Phase 2: Judge Orchestrator."""
    print("\n" + "=" * 60)
    print("  PHASE 2: JUDGE ORCHESTRATOR (Team Alpha vs Team Beta)")
    print("=" * 60)

    from judge_orchestrator import run_judge as judge_run
    return judge_run(doc_id)


def run_sha512_verify(doc_id, judge_result):
    """Phase 3: SHA-512 Auto-Verify against locked fingerprints."""
    print("\n" + "=" * 60)
    print("  PHASE 3: SHA-512 FINGERPRINT VERIFICATION")
    print("=" * 60)

    from fingerprint_lock import verify_extraction, get_locked_pages

    locked_pages = get_locked_pages(doc_id)
    if not locked_pages:
        print("  [INFO] No locked fingerprints found. Awaiting UI approval.")
        print("  [INFO] Approve bounding boxes in the UI to create the lock.")
        return

    all_verified = True
    for page_data in judge_result.get("pages", []):
        page_num = page_data["page_num"]
        if page_num not in locked_pages:
            continue

        matches = page_data.get("matches", [])
        result = verify_extraction(doc_id, page_num, matches)

        if result["matches"]:
            print(f"  Page {page_num}: VERIFIED (hash matches locked approval)")
        else:
            all_verified = False
            drift = result.get("drift_report", {})
            print(f"  Page {page_num}: DRIFT DETECTED!")
            print(f"    Locked: {drift.get('old_count', '?')} items")
            print(f"    Current: {drift.get('new_count', '?')} items")
            if drift.get("added"):
                print(f"    Added:   {drift['added'][:5]}")
            if drift.get("removed"):
                print(f"    Removed: {drift['removed'][:5]}")

    if all_verified:
        print("\n  [SHA-512] ALL LOCKED PAGES VERIFIED")
    else:
        print("\n  [SHA-512] DRIFT DETECTED — Re-review required!")


def main():
    parser = argparse.ArgumentParser(
        description="Adversarial Team Pipeline — Sovereign Extraction v5")
    parser.add_argument('--file', type=str, default=None,
                        help='Specific PDF filename to process')
    parser.add_argument('--pages', type=str, default=None,
                        help='Comma-separated page numbers (1-indexed)')
    parser.add_argument('--engine', type=str, default=None,
                        choices=['tesseract', 'pymupdf',
                                 'font_signature', 'all'],
                        help='Run specific engine only (default: all)')
    parser.add_argument('--parallel', action='store_true',
                        help='Force parallel engine execution')
    parser.add_argument('--skip-prescan', action='store_true',
                        help='Skip the pre-scan phase')
    args = parser.parse_args()

    all_engines = TEAM_ALPHA + TEAM_BETA  # pymupdf, font_signature, tesseract
    engine = args.engine or "all"
    engines_to_run = all_engines if engine == "all" else [engine]
    use_parallel = args.parallel or engine == "all"

    print("=" * 60)
    print("  SOVEREIGN EXTRACTION PIPELINE v5")
    print("  Adversarial Team Architecture + SHA-512 Verify")
    print("=" * 60)
    print(f"  Engines:  {', '.join(engines_to_run)}")
    print(f"  Mode:     {'PARALLEL' if use_parallel else 'SEQUENTIAL'}")
    print(f"  File:     {args.file or 'ALL PDFs'}")
    print(f"  Pages:    {args.pages or 'ALL'}")
    print(f"  Pre-Scan: {'SKIP' if args.skip_prescan else 'ENABLED'}")
    print(f"  CWD:      {VAULT_DIR}")

    # Collect PDFs to process
    pdfs = []
    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith('.pdf'):
            continue
        if args.file and fname != args.file:
            continue
        pdfs.append(fname)

    if not pdfs:
        print("\n[ERROR] No PDFs found to process.")
        return

    t_global = time.time()

    for pdf_file in pdfs:
        doc_id = pdf_file[:-4]
        out_dir = os.path.join(OUTPUT_FOLDER, doc_id)
        os.makedirs(out_dir, exist_ok=True)

        print(f"\n{'#' * 60}")
        print(f"  DOCUMENT: {pdf_file}")
        print(f"{'#' * 60}")

        # Phase 0: Pre-Scan
        if not args.skip_prescan:
            run_prescan(pdf_file, args.pages)

        # Phase 1: Engines
        if use_parallel:
            engine_results = run_engines_parallel(engines_to_run, pdf_file,
                                                   args.pages)
        else:
            engine_results = {}
            for eng in engines_to_run:
                engine_results[eng] = run_engine_sequential(eng, pdf_file,
                                                             args.pages)

        # Report
        print(f"\n{'=' * 60}")
        print("  ENGINE STATUS REPORT")
        print(f"{'=' * 60}")
        for eng, success in engine_results.items():
            status = "PASS" if success else "FAIL"
            print(f"  {eng:20s} [{status}]")

        # Phase 2: Judge
        if any(engine_results.values()):
            result = run_judge(doc_id)
            if result:
                print(f"\n  FINAL: {result['total_matches']} part numbers, "
                      f"{result['total_rejected']} rejected "
                      f"({len(result.get('engines_used', []))} engines)")

                # Phase 3: SHA-512 Auto-Verify
                run_sha512_verify(doc_id, result)
        else:
            print("\n  [ABORT] All engines failed. No judge run.")

    total_time = time.time() - t_global
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETE — {total_time:.2f}s total")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
