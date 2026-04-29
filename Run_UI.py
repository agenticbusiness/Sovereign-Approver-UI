import os
import subprocess
import sys
import webbrowser
import time
import yaml

def run_ui():
    print("==========================================================")
    print("   SOVEREIGN UI VAULT: SPEC SHEET APPROVAL (SVBL)")
    print("==========================================================\n")
    
    vault_dir = os.path.dirname(os.path.abspath(__file__))
    engines_dir = os.path.join(vault_dir, "Engines")
    matrices_dir = os.path.join(vault_dir, "Matrices")
    server_script = os.path.join(engines_dir, "ui_server.py")
    
    print("[JUDGE] Executing Round 2 Symmetry Checks...")
    
    required_files = ["ui_config.yaml", "constraints.yaml", "schema_validation.json"]
    for f in required_files:
        if not os.path.exists(os.path.join(matrices_dir, f)):
            print(f"[FATAL] Missing SVBL Matrix Component: {f}")
            sys.exit(1)
    print("  [OK] Matrix completeness verified.")
            
    constraints_path = os.path.join(matrices_dir, "constraints.yaml")
    with open(constraints_path, 'r', encoding='utf-8') as f:
        constraints = yaml.safe_load(f)
    
    port = constraints.get('network_bounds', {}).get('allowed_ports', [8100])[0]
    print(f"  [OK] Port Symmetry Locked: {port}")
    
    print("[JUDGE] All SVBL checks passed. Booting Flask Backend...\n")
    
    server_proc = subprocess.Popen([sys.executable, server_script])
    time.sleep(2.0)
    
    if server_proc.poll() is None:
        print(f"\n[SYSTEM] Server successfully booted on Port {port}.")
        url = f"http://127.0.0.1:{port}"
        print(f"[SYSTEM] Auto-launching browser: {url}")
        webbrowser.open(url)
        
        try:
            server_proc.wait()
        except KeyboardInterrupt:
            print("\n[SYSTEM] Received keyboard interrupt. Shutting down server...")
            server_proc.terminate()
            server_proc.wait()
            sys.exit(0)
    else:
        print("\n[FATAL] Server failed to boot.")
        sys.exit(1)

if __name__ == "__main__":
    run_ui()
