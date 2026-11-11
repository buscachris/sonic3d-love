// Ghidra headless analysis export. Run with tools/analyze.sh.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.file.*;

public class ExportSonic extends GhidraScript {
    @Override public void run() throws Exception {
        Path out = Paths.get(getScriptArgs()[0]);
        Files.createDirectories(out.resolve("functions"));
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        PrintWriter index = new PrintWriter(Files.newBufferedWriter(out.resolve("functions.tsv")));
        PrintWriter refs = new PrintWriter(Files.newBufferedWriter(out.resolve("references.tsv")));
        index.println("address\tname\tsize\tcalling_convention\tsignature");
        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        int count = 0;
        while (functions.hasNext() && !monitor.isCancelled()) {
            Function f = functions.next();
            String addr = f.getEntryPoint().toString();
            index.println(addr + "\t" + f.getName() + "\t" + f.getBody().getNumAddresses()
                + "\t" + f.getCallingConventionName() + "\t" + f.getSignature().toString());
            DecompileResults result = decompiler.decompileFunction(f, 15, monitor);
            if (result.decompileCompleted()) {
                Files.writeString(out.resolve("functions").resolve(addr + ".c"),
                    "/* " + f.getName() + " at " + addr + " */\n" + result.getDecompiledFunction().getC());
            } else {
                Files.writeString(out.resolve("functions").resolve(addr + ".error"), result.getErrorMessage());
            }
            if (++count % 100 == 0) println("Exported " + count + " functions");
        }
        index.close();
        for (Reference r : currentProgram.getReferenceManager().getReferenceIterator(currentProgram.getMinAddress())) {
            refs.println(r.getFromAddress() + "\t" + r.getToAddress() + "\t" + r.getReferenceType());
        }
        refs.close();
        decompiler.dispose();
        println("Export complete: " + count + " functions");
    }
}
