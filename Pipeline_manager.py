import os
import subprocess
import modmorpher  # your merged script

def run_class_decompiler(jar_file, output_dir):
    """Compile and run ClassDecompiler.java to decompile the jar"""
    java_file = os.path.join(os.path.dirname(__file__), "ClassDecompiler.java")

    if not os.path.isfile(java_file):
        print("❌ ClassDecompiler.java not found!")
        return False

    print("🔹 Compiling ClassDecompiler.java...")
    subprocess.run(["javac", java_file], check=True)

    print(f"🔹 Running ClassDecompiler on {jar_file}...")
    subprocess.run(["java", "ClassDecompiler", jar_file, output_dir], check=True)
    print("✅ Decompilation completed.")
    return True

def main():
    print("=== Pipeline Launcher ===")

    # Step 1: Locate .jar file
    jar_file = next((f for f in os.listdir(".") if f.endswith(".jar")), None)
    if not jar_file:
        print("⚠️ No .jar file found in the directory.")
        return

    # Step 2: Define decompiled output folder
    output_dir = f"decompiled_java_{os.path.splitext(jar_file)[0]}"
    os.makedirs(output_dir, exist_ok=True)

    # Step 3: Decompile the .jar
    if not run_class_decompiler(jar_file, output_dir):
        return

    # Step 4: Run the merged converter pipeline
    print("🔹 Running merged Pack Creator + Converter...")
    modmorpher.run_pipeline()

    print("✅ Full pipeline completed successfully!")

if __name__ == "__main__":
    main()
