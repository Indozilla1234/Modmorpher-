import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ClassDecompiler {
   private static final String RESET = "\u001b[0m";
   private static final String GREEN = "\u001b[32m";
   private static final String CYAN = "\u001b[36m";
   private static final String YELLOW = "\u001b[33m";
   private static final String RED = "\u001b[31m";
   private static final String BOLD = "\u001b[1m";
   private static final String DIM = "\u001b[2m";
   private static final String CLEAR_LINE = "\u001b[2K\r";
   private static final int BAR_WIDTH = 35;
   private static final Pattern PROGRESS_PATTERN = Pattern.compile("Decompiling class (\\d+) of (\\d+)");
   private static final Pattern DECOMPILE_PATTERN = Pattern.compile("(?i)decompil");

   public static void main(String[] var0) throws IOException, InterruptedException {
      if (var0.length < 2) {
         System.out.println("Usage: java ClassDecompiler <input.jar> <outputFolder>");
      } else {
         File var1 = new File(var0[0]);
         File var2 = new File(var0[1]);
         if (!var1.exists()) {
            System.err.println("\u001b[31m✗ Input JAR not found: " + var1.getAbsolutePath() + "\u001b[0m");
         } else {
            if (!var2.exists()) {
               var2.mkdirs();
            }

            File var3 = new File("tools/vineflower.jar");
            if (!var3.exists()) {
               System.err.println("\u001b[31m✗ Vineflower JAR not found at: " + var3.getAbsolutePath() + "\u001b[0m");
            } else {
               System.out.println("\u001b[1m\u001b[36m  \ud83c\udf3f Vineflower Decompiler\u001b[0m");
               PrintStream var10000 = System.out;
               String var10001 = var1.getName();
               var10000.println("\u001b[2m  " + var10001 + "  →  " + var2.getPath() + "\u001b[0m");
               System.out.println();
               ProcessBuilder var4 = new ProcessBuilder(new String[]{"java", "-jar", var3.getAbsolutePath(), var1.getAbsolutePath(), var2.getAbsolutePath()});
               var4.redirectErrorStream(true);
               Process var5 = var4.start();
               int var6 = 0;
               int var7 = 0;
               int var8 = 0;
               String var9 = "";
               printProgressBar(0, 0, 1, "Starting…");
               BufferedReader var10 = new BufferedReader(new InputStreamReader(var5.getInputStream()));

               String var11;
               try {
                  while((var11 = var10.readLine()) != null) {
                     Matcher var12 = PROGRESS_PATTERN.matcher(var11);
                     if (var12.find()) {
                        var7 = Integer.parseInt(var12.group(1));
                        var6 = Integer.parseInt(var12.group(2));
                        var9 = extractClassName(var11);
                        printProgressBar(var7, var7, var6, var9);
                     } else if (DECOMPILE_PATTERN.matcher(var11).find()) {
                        ++var8;
                        var9 = extractClassName(var11);
                        int var13 = Math.max(var8 + 5, var6 > 0 ? var6 : var8 + 5);
                        int var14 = Math.min(var8, var13 - 1);
                        printProgressBar(var14, var8, var13, var9);
                     }
                  }
               } catch (Throwable var16) {
                  try {
                     var10.close();
                  } catch (Throwable var15) {
                     var16.addSuppressed(var15);
                  }

                  throw var16;
               }

               var10.close();
               int var20 = var5.waitFor();
               System.out.print("\u001b[2K\r");
               if (var20 == 0) {
                  int var21 = var6 > 0 ? var6 : var8;
                  printProgressBar(var21, var21, var21, "Done");
                  System.out.println();
                  System.out.println();
                  System.out.println("\u001b[32m\u001b[1m  ✔ Decompilation complete!\u001b[0m");
                  System.out.println("\u001b[2m  \ud83d\udcc1 " + var2.getAbsolutePath() + "\u001b[0m");
               } else {
                  System.out.println("\u001b[31m\u001b[1m  ✗ Vineflower exited with code " + var20 + "\u001b[0m");
               }

               System.out.println();
            }
         }
      }
   }

   private static void printProgressBar(int var0, int var1, int var2, String var3) {
      double var4 = var2 > 0 ? (double)var0 / (double)var2 : (double)0.0F;
      int var6 = (int)(var4 * (double)35.0F);
      int var7 = 35 - var6;
      String var8 = var3.length() > 30 ? "…" + var3.substring(var3.length() - 29) : var3;
      String var10000 = "█".repeat(var6);
      String var9 = "\u001b[32m" + var10000 + "\u001b[2m" + "░".repeat(var7) + "\u001b[0m";
      String var10 = var2 > 0 ? String.format("%d/%d", var1, var2) : String.format("%d", var1);
      String var11 = String.format("%3.0f%%", var4 * (double)100.0F);
      System.out.printf("\u001b[2K\r  %s  \u001b[36m%s\u001b[0m  \u001b[2m%-30s\u001b[0m", var9, var11, var8 + "  " + var10);
      System.out.flush();
   }

   private static String extractClassName(String var0) {
      int var1 = var0.lastIndexOf(58);
      String var2 = (var1 >= 0 ? var0.substring(var1 + 1) : var0).trim();
      int var3 = Math.max(var2.lastIndexOf(47), var2.lastIndexOf(46));
      return var3 >= 0 ? var2.substring(var3 + 1) : var2;
   }
}
