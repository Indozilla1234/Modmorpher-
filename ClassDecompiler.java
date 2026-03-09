import java.io.*;

public class ClassDecompiler {

    public static void main(String[] args) throws IOException, InterruptedException {
        if (args.length < 2) {
            System.out.println("Usage: java ClassDecompiler <input.jar> <outputFolder>");
            return;
        }

        File inputJar = new File(args[0]);
        File outputDir = new File(args[1]);

        if (!inputJar.exists()) {
            System.err.println("❌ Input JAR not found: " + inputJar.getAbsolutePath());
            return;
        }

        if (!outputDir.exists()) {
            outputDir.mkdirs();
        }

        // This is the main Vineflower JAR (the CLI is built into it)
        File vineflowerJar = new File("tools/vineflower.jar");

        if (!vineflowerJar.exists()) {
            System.err.println("❌ Vineflower JAR not found at: " + vineflowerJar.getAbsolutePath());
            return;
        }

        // Vineflower CLI syntax:
        // java -jar vineflower.jar [args...] input.jar output/
        ProcessBuilder pb = new ProcessBuilder(
                "java", "-jar", vineflowerJar.getAbsolutePath(),
                inputJar.getAbsolutePath(),
                outputDir.getAbsolutePath()
        );

        pb.redirectErrorStream(true);
        Process process = pb.start();

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line); // Show Vineflower CLI output
            }
        }

        int exitCode = process.waitFor();
        if (exitCode == 0) {
            System.out.println("🌿 Decompilation complete!");
            System.out.println("📁 Output: " + outputDir.getAbsolutePath());
        } else {
            System.err.println("❌ Vineflower exited with code " + exitCode);
        }
    }
}
