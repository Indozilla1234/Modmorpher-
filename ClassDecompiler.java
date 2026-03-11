import java.io.*;
import java.util.regex.*;

public class ClassDecompiler {

    // ANSI escape codes
    private static final String RESET  = "\u001B[0m";
    private static final String GREEN  = "\u001B[32m";
    private static final String CYAN   = "\u001B[36m";
    private static final String YELLOW = "\u001B[33m";
    private static final String RED    = "\u001B[31m";
    private static final String BOLD   = "\u001B[1m";
    private static final String DIM    = "\u001B[2m";
    private static final String CLEAR_LINE = "\u001B[2K\r";

    private static final int BAR_WIDTH = 35;

    // Vineflower logs: "Decompiling class X of Y : com/example/Foo"
    private static final Pattern PROGRESS_PATTERN =
            Pattern.compile("Decompiling class (\\d+) of (\\d+)");

    // Fallback: count any "Decompiling" mentions
    private static final Pattern DECOMPILE_PATTERN =
            Pattern.compile("(?i)decompil");

    public static void main(String[] args) throws IOException, InterruptedException {
        if (args.length < 2) {
            System.out.println("Usage: java ClassDecompiler <input.jar> <outputFolder>");
            return;
        }

        File inputJar  = new File(args[0]);
        File outputDir = new File(args[1]);

        if (!inputJar.exists()) {
            System.err.println(RED + "✗ Input JAR not found: " + inputJar.getAbsolutePath() + RESET);
            return;
        }

        if (!outputDir.exists()) outputDir.mkdirs();

        File vineflowerJar = new File("tools/vineflower.jar");
        if (!vineflowerJar.exists()) {
            System.err.println(RED + "✗ Vineflower JAR not found at: " + vineflowerJar.getAbsolutePath() + RESET);
            return;
        }

        System.out.println(BOLD + CYAN + "  🌿 Vineflower Decompiler" + RESET);
        System.out.println(DIM + "  " + inputJar.getName() + "  →  " + outputDir.getPath() + RESET);
        System.out.println();

        ProcessBuilder pb = new ProcessBuilder(
                "java", "-jar", vineflowerJar.getAbsolutePath(),
                inputJar.getAbsolutePath(),
                outputDir.getAbsolutePath()
        );
        pb.redirectErrorStream(true);
        Process process = pb.start();

        int total    = 0;
        int current  = 0;
        int fallback = 0;   // used when Vineflower doesn't emit "X of Y"
        String lastClass = "";

        printProgressBar(0, 0, 1, "Starting…");

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream()))) {

            String line;
            while ((line = reader.readLine()) != null) {

                Matcher m = PROGRESS_PATTERN.matcher(line);
                if (m.find()) {
                    current   = Integer.parseInt(m.group(1));
                    total     = Integer.parseInt(m.group(2));
                    lastClass = extractClassName(line);
                    printProgressBar(current, current, total, lastClass);
                    continue;
                }

                // Fallback: Vineflower version that doesn't print "X of Y"
                if (DECOMPILE_PATTERN.matcher(line).find()) {
                    fallback++;
                    lastClass = extractClassName(line);
                    // Show spinner-style bar that fills up to 90 % without a known total
                    int fakeTotal   = Math.max(fallback + 5, total > 0 ? total : fallback + 5);
                    int fakeCurrent = Math.min(fallback, fakeTotal - 1);
                    printProgressBar(fakeCurrent, fallback, fakeTotal, lastClass);
                }
                // All other Vineflower lines (warnings, INFO, etc.) are silently swallowed.
            }
        }

        int exitCode = process.waitFor();

        // Final bar state
        System.out.print(CLEAR_LINE);
        if (exitCode == 0) {
            int finalCount = total > 0 ? total : fallback;
            printProgressBar(finalCount, finalCount, finalCount, "Done");
            System.out.println();
            System.out.println();
            System.out.println(GREEN + BOLD + "  ✔ Decompilation complete!" + RESET);
            System.out.println(DIM   + "  📁 " + outputDir.getAbsolutePath() + RESET);
        } else {
            System.out.println(RED + BOLD + "  ✗ Vineflower exited with code " + exitCode + RESET);
        }
        System.out.println();
    }

    // ── Render a single-line progress bar ──────────────────────────────────────
    private static void printProgressBar(int barFill, int display, int total, String label) {
        double pct     = (total > 0) ? (double) barFill / total : 0.0;
        int    filled  = (int) (pct * BAR_WIDTH);
        int    empty   = BAR_WIDTH - filled;

        // Truncate label so the line stays on one terminal row
        String shortLabel = label.length() > 30
                ? "…" + label.substring(label.length() - 29)
                : label;

        String bar = GREEN  + "█".repeat(filled)
                   + DIM    + "░".repeat(empty)
                   + RESET;

        String counter = total > 0
                ? String.format("%d/%d", display, total)
                : String.format("%d", display);

        String pctStr = String.format("%3.0f%%", pct * 100);

        System.out.printf(CLEAR_LINE + "  %s  " + CYAN + "%s" + RESET
                        + "  " + DIM + "%-30s" + RESET,
                bar, pctStr, shortLabel + "  " + counter);
        System.out.flush();
    }

    // ── Pull a short class name out of whatever Vineflower logs ────────────────
    private static String extractClassName(String line) {
        // "… : com/example/path/ClassName" or just the last token
        int colon = line.lastIndexOf(':');
        String candidate = (colon >= 0 ? line.substring(colon + 1) : line).trim();
        // Keep only the simple class name (after the last slash or dot)
        int slash = Math.max(candidate.lastIndexOf('/'), candidate.lastIndexOf('.'));
        return slash >= 0 ? candidate.substring(slash + 1) : candidate;
    }
}