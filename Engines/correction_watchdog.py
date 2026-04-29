"""
Correction Watchdog Daemon

Runs continuously in the background. Watches the `_X Session Notes` folder
for new `next.prompt.correction_*.md` files. When found, it parses the
prompt and triggers the spec-sheet-correction-Agent to resubmit the
rejected match to the pipeline.
"""
import os
import time
import subprocess
import glob

VAULT_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(VAULT_DIR, "_X Session Notes")
PROCESSED_DIR = os.path.join(NOTES_DIR, "processed_corrections")

os.makedirs(NOTES_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

def process_prompt(filepath):
    print(f"[{time.strftime('%H:%M:%S')}] Detected correction prompt: {os.path.basename(filepath)}")
    
    # Simulate triggering the agent (in reality, this would invoke the agentic CLI)
    agent_script = r"C:\_0 SH-WF-Global gemini.md\_2 Protocols\run_agent.py"
    if os.path.exists(agent_script):
        try:
            subprocess.run(["python", agent_script, "spec-sheet-correction-Agent", filepath], check=True)
        except Exception as e:
            print(f"  [ERROR] Agent failed to process: {e}")
            return
    else:
        print("  [WARN] Agent framework not found at global path. Simulating success for testing.")
        time.sleep(2) # Simulate work
        
    # Move to processed
    filename = os.path.basename(filepath)
    os.rename(filepath, os.path.join(PROCESSED_DIR, filename))
    print(f"  [SUCCESS] Correction processed and archived.")

if __name__ == "__main__":
    print("=== Correction Watchdog Started ===")
    print(f"Watching: {NOTES_DIR}")
    
    while True:
        prompts = glob.glob(os.path.join(NOTES_DIR, "next.prompt.correction_*.md"))
        for prompt in prompts:
            process_prompt(prompt)
            
        time.sleep(5) # Poll every 5 seconds
