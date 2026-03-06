import java.io.*;

public class ClassDecompiler {

    public static void main(String[] args) throws IOException, InterruptedException {
        if (args.length < 2) {
            System.out.println("Usage: java ClassDecompiler <path to .jar> <output folder>");
            return;
        }

        File jarFile = new File(args[0]);
        File outputDir = new File(args[1]);

        if (!jarFile.exists()) {
            System.err.println("❌ File not found: " + jarFile.getAbsolutePath());
            return;
        }

        if (!outputDir.exists()) {
            outputDir.mkdirs();
        }

        String procyonPath = "tools/procyon-decompiler-0.6.0.jar";
        File procyonFile = new File(procyonPath);
        if (!procyonFile.exists()) {
            System.err.println("❌ Procyon jar not found at: " + procyonFile.getAbsolutePath());
            return;
        }

        ProcessBuilder pb = new ProcessBuilder(
                "java", "-jar", procyonFile.getAbsolutePath(),
                "-jar", jarFile.getAbsolutePath(),
                "-o", outputDir.getAbsolutePath()
        );

        pb.redirectErrorStream(true);
        Process process = pb.start();

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                
            }
        }

        int exitCode = process.waitFor();
        if (exitCode == 0) {
            System.out.println("📂 Output folder: " + outputDir.getAbsolutePath());
        } else {
            System.err.println("❌ Procyon exited with code " + exitCode);
        }
    }
}
