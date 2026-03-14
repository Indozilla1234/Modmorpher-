import os
import subprocess
import zipfile
import shutil
import modmorpher

def run_class_decompiler(jar_file, output_dir):
    
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    lib_jar = os.path.join(script_dir, "tools", "ClassDecompiler.jar")
    
    if not os.path.exists(lib_jar):
        print(f"Error: ClassDecompiler.jar not found at {lib_jar}")
        return None

    try:
        
        with zipfile.ZipFile(lib_jar, 'r') as z:
            internal_path = next(
                (name for name in z.namelist() if "vineflower.jar" in name.lower()), 
                None
            )
            if internal_path:
                z.extract(internal_path, script_dir)
                extracted_engine = os.path.join(script_dir, internal_path)
            else:
                print("Vineflower jar not found in ClassDecompiler.jar")
                return None
        
        subprocess.run(
            ["java", "-jar", os.path.abspath(lib_jar), 
             os.path.abspath(jar_file), os.path.abspath(output_dir)],
            cwd=script_dir,
            check=True
        )
        return extracted_engine

    except Exception as e:
        print(f"Decompilation failure: {e}")
        return None

def main():
    
    target_jar = next(
        (f for f in os.listdir(".") if f.endswith(".jar")), 
        None
    )

    if not target_jar:
        print("No target jar file found.")
        return

    
    modmorpher_input_folder = f"src_{os.path.splitext(target_jar)[0]}"
    
    
    extracted_engine = run_class_decompiler(target_jar, modmorpher_input_folder)
    
    if extracted_engine:
        
        print(f"Decompilation successful. Preparing environment for ModMorpher...")
        
        
        if os.path.exists(extracted_engine):
            os.remove(extracted_engine)

        
        print("Running modmorpher pipeline...")
        modmorpher.run_pipeline()
        
        print("Pipeline finished.")
    else:
        print("Pipeline aborted due to decompiler errors.")

if __name__ == "__main__":
    main()