import os
import sys
import subprocess
import shutil

# --- THE BUNDLE HELPER ---
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CONFIGURATION ---
# We point to the .class file, not the .java file, for the final build
JAVA_ENGINE = get_resource_path("ClassDecompiler.class")

def run_decompiler(jar_path, output_dir):
    """ Executes the Java decompiler engine """
    if not os.path.exists(JAVA_ENGINE):
        print(f"❌ Error: Engine component missing at {JAVA_ENGINE}")
        return False

    print(f"🚀 [1/3] Decompiling: {jar_path}")
    
    # We use -cp to point to the directory containing the class file
    engine_dir = os.path.dirname(JAVA_ENGINE)
    
    try:
        subprocess.run([
            "java", "-cp", engine_dir, "ClassDecompiler", jar_path, output_dir
        ], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Java Engine failed: {e}")
        return False
    except FileNotFoundError:
        print("❌ Error: 'java' command not found. Please install OpenJDK.")
        return False

def main():
    print("========================================")
    print("   MODMORPHER PIPELINE - INDOZILLA1234  ")
    print("========================================\n")

    # 1. Identify the Mod
    target_jar = next((f for f in os.listdir(".") if f.endswith(".jar")), None)
    
    if not target_jar:
        print("📂 Place the Java .jar mod in this folder and restart.")
        return

    # 2. Setup Workspace
    workspace = f"temp_morph_{os.path.splitext(target_jar)[0]}"
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace)

    # 3. Step 1: Decompile
    if run_decompiler(target_jar, workspace):
        
        # 4. Step 2: Morphing (Imported logic)
        print(f"🧬 [2/3] Morphing {target_jar} to Bedrock...")
        try:
            import modmorpher
            # Assuming modmorpher has a main entry function
            modmorpher.run_conversion(workspace, target_jar)
            print("✅ [3/3] Bedrock Add-on created successfully!")
        except ImportError:
            print("❌ Error: modmorpher.py logic not found in pipeline.")
        except Exception as e:
            print(f"❌ Morphing failed: {e}")

    # 5. Cleanup
    print(f"🧹 Cleaning up workspace...")
    shutil.rmtree(workspace)
    print("✨ Done.")

if __name__ == "__main__":
    # Optional: Add your ToS check here before main()
    main()