import os
import subprocess
import zipfile
import shutil
import modmorpher

def run_class_decompiler(jar_file, output_dir):
    """
    Runs ClassDecompiler.jar from the /tools folder.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    lib_jar = os.path.join(script_dir, "tools", "ClassDecompiler.jar")
    
    if not os.path.exists(lib_jar):
        print(f"Error: ClassDecompiler.jar not found at {lib_jar}")
        return False

    try:
        # Extract the internal decompiler engine to /tools
        with zipfile.ZipFile(lib_jar, 'r') as z:
            internal_path = next(
                (name for name in z.namelist() if "vineflower.jar" in name.lower()), 
                None
            )
            if internal_path:
                z.extract(internal_path, script_dir)

        # Execute the decompiler
        # Java will output the source code into 'output_dir'
        subprocess.run(
            ["java", "-jar", os.path.abspath(lib_jar), 
             os.path.abspath(jar_file), os.path.abspath(output_dir)],
            cwd=script_dir,
            check=True
        )
        return True

    except Exception as e:
        print(f"Decompilation failure: {e}")
        return False

def main():
    # 1. Identify the target jar
    target_jar = next(
        (f for f in os.listdir(".") if f.endswith(".jar")), 
        None
    )

    if not target_jar:
        print("No target jar file found.")
        return

    # 2. The folder ModMorpher actually needs
    # This stays after the script runs
    modmorpher_input_folder = f"src_{os.path.splitext(target_jar)[0]}"
    
    # 3. Run the decompiler
    success = run_class_decompiler(target_jar, modmorpher_input_folder)
    
    if success:
        # 4. Clean up only the "ClassDecompiler" footprint
        # We leave 'modmorpher_input_folder' exactly where it is.
        print(f"Decompilation successful. Preparing environment for ModMorpher...")
        
        # Remove the extracted engine so ModMorpher doesn't see extra JARs in /tools
        extracted_engine = os.path.join("tools", "vineflower.jar")
        if os.path.exists(extracted_engine):
            os.remove(extracted_engine)

        # 5. Run the ModMorpher pipeline
        # It will now find the folder created in Step 2
        print("Running modmorpher pipeline...")
        modmorpher.run_pipeline()
        
        print("Pipeline finished.")
    else:
        print("Pipeline aborted due to decompiler errors.")

if __name__ == "__main__":
    main()